"""Stage 1: fetch each customer-market site's sitemap(s) and STORE every URL (with lastmod) in a local inventory database.

Inventory DB: experiments/sitemap_discovery/site_inventory.db (its own file - the live database is never touched).
Network: robots.txt + sitemap XML only, plain HTTP, 1.5 s between requests. No page crawling, no browser, no AI.
Resumable: a site already stored with stage1_done=1 is skipped.
"""
import asyncio, importlib.util, re, sqlite3, sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("cm", HERE / "customer_markets_sitemaps.py")
cm = importlib.util.module_from_spec(spec); spec.loader.exec_module(cm)   # load_sites, cu (existing helpers)
from src.cfp_monitor import sitewalk                                        # noqa: E402

DBF = HERE / "site_inventory.db"
MAX_URLS, MAX_MAPS = 20000, 25

SCHEMA = """
create table if not exists site_profile(
  host text primary key, origin text, markets text, events text, event_paths text,
  sitemap_found int, sitemap_how text, robots_txt int, has_lastmod int, hit_cap int, sitemap_files int,
  stage1_done int default 0, fetched_at text);
create table if not exists site_pages(
  host text, url text, source text, lastmod text, in_map int default 0, in_menu int default 0, menu_zone text,
  first_seen text, primary key(host, url, source));
"""


def parse_with_lastmod(xml_text):
    """[(loc, lastmod)], is_index. Namespace-tolerant; existing sitewalk.parse_sitemap returns locs only."""
    if not (xml_text or "").strip().startswith("<"):
        return [], False
    try:
        root = ET.fromstring(xml_text.encode("utf-8", "ignore"))
    except ET.ParseError:
        return [], False
    out = []
    for el in root:
        loc = lm = ""
        for ch in el:
            tag = ch.tag.rsplit("}", 1)[-1]
            if tag == "loc":
                loc = (ch.text or "").strip()
            elif tag == "lastmod":
                lm = (ch.text or "").strip()
        if loc:
            out.append((loc, lm))
    return out, root.tag.endswith("sitemapindex")


async def collect(origin):
    cu = cm.cu
    robots = await cu._get_raw(origin + "/robots.txt")
    seeds = sitewalk.sitemaps_from_robots(robots, origin)
    how = f"robots.txt named {len(seeds)} sitemap(s)" if seeds else "conventional path"
    if not seeds:
        seeds = sitewalk.sitemap_candidates(origin)
    pages, queue, seen, capped = [], list(seeds), set(), False
    while queue and len(seen) < MAX_MAPS:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        raw = await cu._get_raw(sm)
        await asyncio.sleep(1.5)
        items, is_index = parse_with_lastmod(raw)
        if is_index:
            queue.extend(u for u, _ in items[:MAX_MAPS])
        else:
            pages.extend(items)
        if len(pages) >= MAX_URLS:
            capped = True
            break
    return pages[:MAX_URLS], (how if pages else "none found"), capped, len(seen), bool(robots)


async def main():
    db = sqlite3.connect(DBF, timeout=120)      # wait rather than crash if another pass holds the file
    db.executescript(SCHEMA)
    sites = cm.load_sites()
    print(f"{len(sites)} sites", flush=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for n, (host, s) in enumerate(sorted(sites.items()), 1):
        if db.execute("select stage1_done from site_profile where host=?", (host,)).fetchone() == (1,):
            continue
        try:
            pages, how, capped, nmaps, has_robots = await collect(s["origin"])
        except Exception as e:                                               # noqa: BLE001
            pages, how, capped, nmaps, has_robots = [], f"error {type(e).__name__}", False, 0, False
        db.execute("delete from site_pages where host=? and source='map'", (host,))
        seenu = set()
        for u, lmod in pages:
            k = u.split("#")[0]
            if k in seenu:
                continue
            seenu.add(k)
            db.execute("insert or ignore into site_pages(host,url,source,lastmod,in_map,first_seen) values(?,?,?,?,1,?)",
                       (host, k, "map", lmod, now))
        db.execute("insert or replace into site_profile values(?,?,?,?,?,?,?,?,?,?,?,1,?)",
                   (host, s["origin"], ",".join(sorted(s["markets"])), "|".join(sorted(s["events"]))[:2000],
                    ",".join(sorted(s["prefixes"])), int(bool(pages)), how, int(has_robots),
                    int(any(lm for _, lm in pages)), int(capped), nmaps, now))
        db.commit()
        print(f"[{n}/{len(sites)}] {host[:36]:<36} urls={len(seenu):>6} {how[:28]}", flush=True)
    t = db.execute("select count(*), sum(sitemap_found) from site_profile").fetchone()
    print(f"DONE sites={t[0]} with_sitemap={t[1]} urls={db.execute('select count(*) from site_pages').fetchone()[0]}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
