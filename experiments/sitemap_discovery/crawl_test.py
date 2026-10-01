"""Bounded crawl test of the v3.1 selection on 5 sites with a known (database) deadline. 1 page per request, 2 s apart, nothing else.

For each site: take the v3.1 plan (rules_v31.plan over the stored sitemap + menu inventory), render EVERY selected page once with the
repo's renderer, and record: characters returned, soft-404 / shell, whether it states any date near call vocabulary, whether it states
OUR known deadline (verify.find_date), and whether it offers a submission/portal link. Then per site: was the known deadline found on
any selected page, at what position in the priority order, and how many pages were wasted (thin, soft 404, or nothing relevant).
Writes crawl_test.json. Read-only apart from that; no AI, no database writes.
"""
import os, asyncio, importlib.util, json, re, sqlite3, sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
import rules_v31 as r31
from src.cfp_monitor import fetch as _f                      # noqa: E402
from src.cfp_monitor.config import Settings                  # noqa: E402
from src.cfp_monitor.verify import find_date                 # noqa: E402
spec = importlib.util.spec_from_file_location("cu", ROOT / "scripts" / "check_urls_against_site.py")
cu = importlib.util.module_from_spec(spec); spec.loader.exec_module(cu)      # looks_soft_404 (existing)

DB = os.path.join(os.environ.get("LOCALAPPDATA", ""), "CFP-Monitor", "cfp_monitor.db")   # the live database, read-only here
SITES = {"ccus-expo.com": date(2026, 9, 9), "h2meet.com": date(2026, 9, 30), "actexpo.com": date(2026, 9, 10),
         "sans.org": date(2026, 5, 26), "blackhat.com": date(2026, 3, 23), "troopers.de": date(2026, 3, 31)}   # customer markets only
if "--sites" in sys.argv:      # rerun a subset: python crawl_test.py --sites h2meet.com,troopers.de
    _want = set(sys.argv[sys.argv.index("--sites") + 1].split(","))
    SITES = {k: v for k, v in SITES.items() if k in _want}
OUTNAME = ("crawl_test_swap.json" if "--swap" in sys.argv else "crawl_test_subset.json") if "--sites" in sys.argv else "crawl_test.json"
MAX_PAGES = 15
MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
ANYDATE = re.compile(rf"\b{MON}\s+\d{{1,2}}\b|\b\d{{1,2}}(?:st|nd|rd|th)?\s+{MON}|\b20\d\d-\d\d-\d\d\b", re.I)
CALLVOC = re.compile(r"deadline|submission|submit|call for|abstract|proposal|cfp|due|closes?|speaker", re.I)


class _Q:
    def log(self, *a, **k):
        pass


PAGE_STORE = HERE / "crawl_pages.json"     # url -> {"text","anchors"}: saved so later steps never need to re-render
_store = json.loads(PAGE_STORE.read_text(encoding="utf-8")) if PAGE_STORE.exists() else {}


def date_near_call(text):
    for m in CALLVOC.finditer(text):
        if ANYDATE.search(text[max(0, m.start() - 200): m.end() + 200]):
            return True
    return False


async def main():
    settings = Settings()
    db = sqlite3.connect(HERE / "site_inventory.db", timeout=60)
    out = []
    for host, known in SITES.items():
        maps = [u for (u,) in db.execute("select url from site_pages where host=? and source='map'", (host,))]
        menu = {u: l for u, l in db.execute("select url, label from site_pages where host=? and source='menu'", (host,))}
        labels = {u: l for u, l in menu.items() if l}
        plan = r31.plan(list(dict.fromkeys(maps + list(menu))), labels)[:MAX_PAGES]
        if "--swap" in sys.argv:      # e.g. --swap ko=en : test the English twin of a selected page (language-rule validation)
            a, b = sys.argv[sys.argv.index("--swap") + 1].split("=")
            plan = [(u.replace(f"/{a}/", f"/{b}/"), t) for u, t in plan]
        origin = db.execute("select origin from site_profile where host=?", (host,)).fetchone()[0]
        print(f"\n{host}: {len(maps)} sitemap urls, {len(menu)} menu links -> {len(plan)} pages selected", flush=True)
        pages, first_hit = [], None
        for rank, (u, tier) in enumerate(plan, 1):
            if _f._force_fallback_domain(u) and not _f.cdp_reachable(getattr(settings, "cdp_url", None)):
                pages.append({"rank": rank, "url": u, "tier": tier, "skipped": "anti-bot"}); continue
            try:
                html, anchors, status, body, _c = await _f._render_with_consent(u, settings, _Q(), prefer_cdp=True)
            except Exception as e:                                         # noqa: BLE001
                pages.append({"rank": rank, "url": u, "tier": tier, "error": type(e).__name__}); print(f"  {rank:>2} ERROR {u[:80]}", flush=True); continue
            body = body or ""
            _store[u] = {"text": body, "anchors": [[(a.get("href") or ""), (a.get("text") or "")[:80]] for a in (anchors or [])][:400],
                         "rank": rank, "tier": tier, "site": host}
            PAGE_STORE.write_text(json.dumps(_store), encoding="utf-8")
            shell = cu.looks_soft_404(body)
            known_found = bool(body) and find_date(body, known)
            date_call = date_near_call(body)
            submit_link = any(re.search(r"submit|submission|portal|cfp|call-for|application|form", (a.get("href") or "") + " " + (a.get("text") or ""), re.I)
                              for a in (anchors or []))
            useful = known_found or date_call
            if known_found and first_hit is None:
                first_hit = rank
            pages.append({"rank": rank, "url": u, "tier": tier[:2], "chars": len(body), "shell": shell, "known_deadline": known_found,
                          "date_near_call_words": date_call, "submit_link": submit_link, "useful": useful})
            print(f"  {rank:>2} {tier[:2]} chars={len(body):>6} known={'Y' if known_found else '-'} date+call={'Y' if date_call else '-'} "
                  f"submit-link={'Y' if submit_link else '-'} {('SHELL ' + shell[:25]) if shell else ''} {urlparse(u).path[:60]}", flush=True)
            await asyncio.sleep(2)
        done = [p for p in pages if "chars" in p]
        rec = {"site": host, "known_deadline": known.isoformat(), "pages_selected": len(plan), "pages_read": len(done),
               "known_deadline_found": first_hit is not None, "found_at_rank": first_hit,
               "pages_with_date_near_call_words": sum(p["date_near_call_words"] for p in done),
               "wasted_pages": sum((not p["useful"]) for p in done), "shell_pages": sum(bool(p["shell"]) for p in done), "pages": pages}
        out.append(rec)
        print(f"  => known deadline {known}: {'FOUND at page ' + str(first_hit) if first_hit else 'not found on any selected page'}; "
              f"useful {len(done) - rec['wasted_pages']}/{len(done)}; shells {rec['shell_pages']}", flush=True)
        (HERE / OUTNAME).write_text(json.dumps(out, indent=1), encoding="utf-8")
    tp = sum(r["pages_read"] for r in out)
    print(f"\nTOTAL pages read {tp}; known deadline found on {sum(r['known_deadline_found'] for r in out)} of {len(out)} sites; "
          f"useful pages {tp - sum(r['wasted_pages'] for r in out)}/{tp}", flush=True)
    try:
        await _f.close_fallback_browser()
    except Exception:                                                      # noqa: BLE001
        pass
    print("DONE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
