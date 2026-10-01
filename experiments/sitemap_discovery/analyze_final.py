"""Final offline numbers for the frozen v3.1 selection on the corrected inventory. Writes analysis_final.json."""
import json, sqlite3, statistics, sys
from collections import Counter
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import rules_v31 as r
db = sqlite3.connect(HERE / "site_inventory.db", timeout=60)
S = []
for host, markets, sm in db.execute("select host, markets, sitemap_found from site_profile order by host").fetchall():
    maps = [u for (u,) in db.execute("select url from site_pages where host=? and source='map'", (host,))]
    menu = {u: (z, l) for u, z, l in db.execute("select url, menu_zone, label from site_pages where host=? and source='menu'", (host,))}
    labels = {u: l for u, (z, l) in menu.items() if l}; nav = {u for u, (z, l) in menu.items() if z in ("menu", "header")}
    plan = r.plan(list(dict.fromkeys(maps + list(menu))), labels); ms = set(maps)
    p1 = [u for u, t in plan if t.startswith("P1")]
    S.append({"host": host, "markets": markets, "sitemap": bool(sm), "n": len(plan), "tiers": dict(Counter(t[:2] for _, t in plan)),
              "p1": len(p1), "p1_menu": sum(u in nav for u in p1), "p1_map": sum(u in ms for u in p1),
              "where": dict(Counter(("both" if (u in ms and u in nav) else "map only" if u in ms else "menu only" if u in nav else "body/footer only") for u, _ in plan))})
n = [s["n"] for s in S]
out = {"sites": len(S), "total_pages": sum(n), "per_site": {"median": statistics.median(n), "p75": sorted(n)[int(len(n) * .75)], "max": max(n)},
       "sites_0": sum(x == 0 for x in n), "sites_1_10": sum(1 <= x <= 10 for x in n), "sites_11_plus": sum(x > 10 for x in n),
       "tiers": dict(sum((Counter(s["tiers"]) for s in S), Counter())),
       "sites_with_call_page": sum(s["p1"] > 0 for s in S), "call_pages": sum(s["p1"] for s in S),
       "call_via_menu_sites": sum(s["p1_menu"] > 0 for s in S), "call_via_map_sites": sum(s["p1_map"] > 0 for s in S),
       "call_menu_only_sites": sum(s["p1_menu"] > 0 and s["p1_map"] == 0 for s in S), "call_map_only_sites": sum(s["p1_map"] > 0 and s["p1_menu"] == 0 for s in S),
       "call_both_sites": sum(s["p1_menu"] > 0 and s["p1_map"] > 0 for s in S),
       "selected_where": dict(sum((Counter(s["where"]) for s in S), Counter())),
       "by_market": {m: {"sites": sum(m in s["markets"] for s in S), "pages": sum(s["n"] for s in S if m in s["markets"]),
                         "with_call_page": sum(m in s["markets"] and s["p1"] > 0 for s in S)} for m in ("Cybersecurity", "Utility")}}
(HERE / "analysis_final.json").write_text(json.dumps({"summary": out, "sites": S}, indent=1), encoding="utf-8")
print(json.dumps(out, indent=1))
