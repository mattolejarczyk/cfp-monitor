"""Fair recall test: customer-market events whose database deadline is STILL AHEAD (>= 2026-10-01). Bounded, 2 s between page loads, no AI.

For each event: take the frozen v3.1 plan for its site (rules_v31.plan over the stored sitemap + menu inventory), render every selected page (max 15)
with the repo renderer, and test each page with the corrected date reader (dates_v2): does it state the known deadline (and with what confidence)?
CONTROL: also render the call page the database already holds for the event (submission URL), and say whether the plan selected it. A miss means
different things depending on that control:
  control states the date, plan did not select it     -> a selection failure (ours)
  control states the date, plan selected it           -> a hit
  control does not state the date                     -> the ground truth itself is doubtful or the page does not publish it
Writes recall_test.json; page text is added to crawl_pages.json.
"""
import asyncio, json, re, sqlite3, sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
import rules_v31 as r31
import dates_v2 as d2
from src.cfp_monitor import fetch as _f                      # noqa: E402
from src.cfp_monitor.config import Settings                  # noqa: E402

EVENTS = [
    {"event": "SecureWorld Government & Critical Infrastructure 2026", "hosts": ["secureworld.io"], "known": date(2026, 10, 28),
     "control": None, "truth_note": "evidence is the events LISTING page; the date may be the event date, not a deadline"},
    {"event": "International Conference on Climate Change", "hosts": ["on-climate.com"], "known": date(2026, 12, 19),
     "control": "https://on-climate.com/2027-conference/call-for-papers", "truth_note": ""},
    {"event": "Global Energy Show Canada 2027", "hosts": ["globalenergyshow.com"], "known": date(2026, 12, 4),
     "control": "https://www.globalenergyshow.com/speak/abstract-submission/", "truth_note": "database state not_found (unverified)"},
]
MAX_PAGES = 15
STORE = HERE / "crawl_pages.json"
store = json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else {}


class _Q:
    def log(self, *a, **k):
        pass


async def render(url, settings):
    try:
        html, anchors, st, body, _c = await _f._render_with_consent(url, settings, _Q(), prefer_cdp=True)
        return (body or ""), [[(a.get("href") or ""), (a.get("text") or "")[:80]] for a in (anchors or [])][:400], st
    except Exception as e:                                           # noqa: BLE001
        return "", [], type(e).__name__


def canon(u):
    return re.sub(r"^https?://(www\.)?", "", u.lower()).split("#")[0].split("?")[0].rstrip("/")


async def main():
    settings = Settings()
    db = sqlite3.connect(HERE / "site_inventory.db", timeout=60)
    out = []
    for ev in EVENTS:
        known = ev["known"]
        print(f"\n=== {ev['event']}  (known deadline {known}) {('- ' + ev['truth_note']) if ev['truth_note'] else ''}", flush=True)
        plan = []
        for host in ev["hosts"]:
            maps = [u for (u,) in db.execute("select url from site_pages where host=? and source='map'", (host,))]
            menu = {u: l for u, l in db.execute("select url,label from site_pages where host=? and source='menu'", (host,))}
            p = r31.plan(list(dict.fromkeys(maps + list(menu))), {u: l for u, l in menu.items() if l})[:MAX_PAGES]
            print(f"  site {host}: {len(maps)} sitemap urls, {len(menu)} menu links -> {len(p)} pages selected", flush=True)
            plan += [(host, u, t) for u, t in p]
        rec = {"event": ev["event"], "known": known.isoformat(), "pages": [], "control": None}
        hit = None
        for rank, (host, u, tier) in enumerate(plan, 1):
            body, anchors, st = await render(u, settings)
            store[u] = {"text": body, "anchors": anchors, "rank": rank, "tier": tier, "site": host}
            r = d2.find_target(body, known) if body else None
            near = d2.any_date_near_call(body) if body else False
            if r and hit is None:
                hit = (rank, r[0], u)
            rec["pages"].append({"rank": rank, "url": u, "tier": tier[:2], "chars": len(body), "known": r[0] if r else "", "near_call": near})
            print(f"   {rank:>2} {tier[:2]} chars={len(body):>6} known={(r[0] if r else '-'):<13} near-call={'Y' if near else '-'}  {urlparse(u).path[:62]}", flush=True)
            STORE.write_text(json.dumps(store), encoding="utf-8")
            await asyncio.sleep(2)
        rec["hit"] = {"rank": hit[0], "confidence": hit[1], "url": hit[2]} if hit else None
        if ev["control"]:
            body, anchors, st = await render(ev["control"], settings)
            store[ev["control"]] = {"text": body, "anchors": anchors, "rank": 0, "tier": "control", "site": ev["hosts"][0]}
            r = d2.find_target(body, known) if body else None
            selected = canon(ev["control"]) in {canon(u) for _h, u, _t in plan}
            rec["control"] = {"url": ev["control"], "chars": len(body), "states_known_deadline": r[0] if r else "", "selected_by_plan": selected,
                              "date_near_call": d2.any_date_near_call(body) if body else False}
            print(f"  CONTROL {ev['control']}\n     chars={len(body)} states known deadline: {r[0] if r else 'no'} | selected by the plan: {selected}", flush=True)
            if body and not r:
                m = re.search(r"deadline|submission|abstract|call for|due|closes?", body, re.I)
                if m:
                    print("     page text near call wording:", re.sub(r"\s+", " ", body[max(0, m.start() - 80): m.end() + 200]), flush=True)
        verdict = ("HIT (rank %d, %s)" % (hit[0], hit[1])) if hit else "MISS"
        print(f"  => {verdict}", flush=True)
        out.append(rec)
        (HERE / "recall_test.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    STORE.write_text(json.dumps(store), encoding="utf-8")
    try:
        await _f.close_fallback_browser()
    except Exception:                                                  # noqa: BLE001
        pass
    print("\nDONE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
