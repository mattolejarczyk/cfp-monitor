"""Stage 2b: re-render each readable homepage ONCE more, this time keeping the TEXT of every link (the label a visitor reads),
and store it on the existing menu rows in site_inventory.db (column `label`). One page per site; no deeper crawling; no AI.
Same renderer and protections as collect_menus.py (hard anti-bot hosts skipped). Resumable via site_menu_labels.
    python collect_menu_labels.py [--only host]
"""
import asyncio, importlib.util, re, sqlite3, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("cmn", HERE / "collect_menus.py")
cmn = importlib.util.module_from_spec(spec); spec.loader.exec_module(cmn)        # Zones, _Quiet, DBF (reused, unchanged)
from src.cfp_monitor import fetch as _f                # noqa: E402
from src.cfp_monitor import sitewalk                   # noqa: E402
from src.cfp_monitor.config import Settings            # noqa: E402


def doc_base(raw_hrefs, anchors):
    """The address relative links must be resolved against. The renderer's anchors carry the browser's ABSOLUTE addresses (a.href), the HTML
    carries the raw attribute; a relative raw href R whose absolute form ends in R reveals the real base (redirects, <base>, sub-folders).
    Fixes a defect found 2026-10-01: relative links were resolved against the bare site address, so h2meet.com (which redirects to
    /html/ko/main.php) got addresses like /speaker.php that do not exist."""
    from collections import Counter
    absu = [a.get("href") or "" for a in anchors or []]
    c = Counter()
    for r in raw_hrefs:
        if re.match(r"^(https?:)?//|/|#|mailto:|tel:|javascript:", r) or not r:
            continue
        rr = re.sub(r"^(\./)+", "", r)
        for a in absu:
            if a.endswith(rr) and len(a) > len(rr):
                c[a[: len(a) - len(rr)]] += 1
                break
    return c.most_common(1)[0][0] if c else None


def clean(t):
    return re.sub(r"\s+", " ", t or "").strip()[:100]


async def main():
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else ""
    settings = Settings()
    db = sqlite3.connect(cmn.DBF, timeout=120)
    if "label" not in [r[1] for r in db.execute("pragma table_info(site_pages)")]:
        db.execute("alter table site_pages add column label text")
    db.execute("create table if not exists site_menu_labels(host text primary key, labelled int, note text, done_at text)")
    hosts = [(h, o) for h, o in db.execute(
        "select p.host, p.origin from site_profile p join site_menu_status m on m.host=p.host "
        "where m.homepage_chars > 200 order by p.host") if not only or h == only]
    print(f"{len(hosts)} homepages to re-render for link text", flush=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for n, (host, origin) in enumerate(hosts, 1):
        if db.execute("select 1 from site_menu_labels where host=?", (host,)).fetchone() and not only:
            continue
        note, html, anchors = "", "", []
        if _f._force_fallback_domain(origin) and not _f.cdp_reachable(getattr(settings, "cdp_url", None)):
            note = "skipped: hard anti-bot site"
        else:
            try:
                html, anchors, *_ = await _f._render_with_consent(origin, settings, cmn._Quiet(), prefer_cdp=True)
            except Exception as e:                                          # noqa: BLE001
                note = f"render failed: {type(e).__name__}"
        z = cmn.Zones()
        if html:
            z.feed(html)
        best, added = {}, 0
        base = doc_base([(h or "").strip() for h, _t, _z in z.links], anchors) or (origin + "/")
        db.execute("create table if not exists site_final(host text primary key, final_base text, different_domain int)")
        db.execute("insert or replace into site_final values(?,?,?)",
                   (host, base, int(not sitewalk.same_site(base, origin))))
        for href, text, zone in z.links:
            href = (href or "").strip()
            if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            url = urljoin(base, href).split("#")[0]
            if not sitewalk.same_site(url, base):
                continue
            lab = clean(text)
            if url not in best or (lab and not best[url][0]):
                best[url] = (lab, zone)
        if html:      # replace this site's menu rows wholesale (the old rows may carry wrongly resolved addresses)
            db.execute("delete from site_pages where host=? and source='menu'", (host,))
        for url, (lab, zone) in best.items():
            db.execute("insert or ignore into site_pages(host,url,source,in_menu,menu_zone,label,first_seen) values(?,?,?,?,?,?,?)",
                       (host, url, "menu", int(zone in ("menu", "header")), zone, lab, now)); added += 1
        db.execute("insert or replace into site_menu_labels values(?,?,?,?)", (host, len(best), note, now))
        db.commit()
        withlab = sum(1 for v in best.values() if v[0])
        print(f"[{n}/{len(hosts)}] {host[:34]:<34} links={len(best):>4} with_text={withlab:>4} new={added:>3} {note}", flush=True)
        if only:
            for url, (lab, zone) in list(best.items())[:15]:
                print(f"     {zone:<7} {lab[:40]:<40} {url[:70]}")
        await asyncio.sleep(2)
    try:
        await _f.close_fallback_browser()
    except Exception:                                                        # noqa: BLE001
        pass
    print("DONE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
