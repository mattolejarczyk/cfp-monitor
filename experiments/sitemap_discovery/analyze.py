"""Offline analysis (no network): apply rules_v2 to the stored sitemap URLs + homepage links and compare MENU vs MAP vs USEFUL.

Reads site_inventory.db. Writes analysis.json. For every site:
  map   = URLs from the sitemap(s)            menu = homepage links in a nav/header/menu zone
  useful = URLs the v2 rules keep (P1 call/submission, P2 programme/dates/awards, P3 sponsorship index, P4 next-edition hint)
"""
import json, sqlite3, statistics, sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rules_v2 as r

db = sqlite3.connect(HERE / "site_inventory.db")
prof = {h: dict(zip(("markets", "sitemap_found", "has_lastmod"), v)) for h, *v in
        db.execute("select host, markets, sitemap_found, has_lastmod from site_profile")}
menu_status = {h: (chars, links, menu) for h, chars, links, menu in
               db.execute("select host, homepage_chars, links, menu_links from site_menu_status")} \
    if db.execute("select 1 from sqlite_master where name='site_menu_status'").fetchone() else {}

sites = []
for host, p in sorted(prof.items()):
    maps = [u for (u,) in db.execute("select url from site_pages where host=? and source='map'", (host,))]
    menu = {u: z for u, z in db.execute("select url, menu_zone from site_pages where host=? and source='menu'", (host,))}
    menu_nav = {u for u, z in menu.items() if z in ("menu", "header")}
    universe = list(dict.fromkeys(maps + list(menu)))
    v = r.classify_all(universe)
    mapset, navset = set(maps), menu_nav
    rec = {"host": host, "markets": p["markets"], "sitemap": bool(maps), "map_urls": len(maps), "menu_links_nav": len(navset),
           "menu_links_all": len(menu), "homepage_rendered": host in menu_status and (menu_status[host][0] or 0) > 200}
    reasons = Counter(why for (verdict, why) in v.values() if verdict == "drop")
    keep = {u: t for u, (vd, t) in v.items() if vd == "keep"}
    rec["dropped_reasons"] = dict(reasons)
    rec["kept_by_tier"] = dict(Counter(keep.values()))
    # where each kept page was found
    where = defaultdict(Counter)
    for u, t in keep.items():
        w = "both" if (u in mapset and u in navset) else "map only" if u in mapset else "menu only" if u in navset else "homepage body/footer only"
        where[t][w] += 1
    rec["kept_where"] = {t: dict(c) for t, c in where.items()}
    sel = r.select(v)
    rec["selected"] = len(sel)
    rec["selected_by_tier"] = dict(Counter(t for _u, t in sel))
    rec["selected_sample"] = [u for u, _t in sel[:6]]
    # how useful is the menu: share of nav links that the rules keep
    rec["menu_nav_kept"] = sum(1 for u in navset if u in keep)
    rec["p1_in_menu"] = sum(1 for u, t in keep.items() if t.startswith("P1") and u in navset)
    rec["p1_in_map"] = sum(1 for u, t in keep.items() if t.startswith("P1") and u in mapset)
    rec["p1_total"] = sum(1 for t in keep.values() if t.startswith("P1"))
    sites.append(rec)

S = sites
have_map = [s for s in S if s["sitemap"]]
no_map = [s for s in S if not s["sitemap"]]
sel = [s["selected"] for s in S]


def dist(xs):
    xs = sorted(xs)
    return {"min": xs[0], "median": statistics.median(xs), "p75": xs[int(len(xs) * .75)] if xs else 0, "max": xs[-1]} if xs else {}


summary = {
    "sites": len(S), "with_sitemap": len(have_map), "without_sitemap": len(no_map),
    "homepage_rendered": sum(s["homepage_rendered"] for s in S),
    "pages_selected_per_site": dist(sel), "total_pages_selected": sum(sel),
    "sites_selecting_0": sum(x == 0 for x in sel), "sites_1_to_10": sum(1 <= x <= 10 for x in sel),
    "sites_11_to_50": sum(11 <= x <= 50 for x in sel),
    "selected_by_tier_total": dict(sum((Counter(s["selected_by_tier"]) for s in S), Counter())),
    "dropped_reasons_total": dict(sum((Counter(s["dropped_reasons"]) for s in S), Counter())),
    "p1_pages_total": sum(s["p1_total"] for s in S),
    "sites_with_any_p1": sum(s["p1_total"] > 0 for s in S),
    "sites_p1_reachable_from_menu": sum(s["p1_in_menu"] > 0 for s in S),
    "sites_p1_in_map": sum(s["p1_in_map"] > 0 for s in S),
    "sites_p1_only_via_menu": sum(s["p1_in_menu"] > 0 and s["p1_in_map"] == 0 for s in S),
    "sites_p1_only_via_map": sum(s["p1_in_map"] > 0 and s["p1_in_menu"] == 0 for s in S),
    "sites_p1_in_both": sum(s["p1_in_menu"] > 0 and s["p1_in_map"] > 0 for s in S),
    "kept_where_total": {t: dict(sum((Counter(s["kept_where"].get(t, {})) for s in S), Counter()))
                         for t in r.BUDGET},
    "menu_nav_links_per_site": dist([s["menu_links_nav"] for s in S if s["homepage_rendered"]]) if any(s["homepage_rendered"] for s in S) else {},
    "by_market": {m: {"sites": sum(m in s["markets"] for s in S),
                      "pages_selected": sum(s["selected"] for s in S if m in s["markets"]),
                      "sites_with_sitemap": sum(m in s["markets"] and s["sitemap"] for s in S)} for m in ("Cybersecurity", "Utility")},
}
(HERE / "analysis.json").write_text(json.dumps({"summary": summary, "sites": S}, indent=1), encoding="utf-8")
print(json.dumps(summary, indent=1))
