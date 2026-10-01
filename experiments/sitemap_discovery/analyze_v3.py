"""Offline (no network): rules v3 + menu link text vs rules v2, menu vs map vs useful pages. Reads site_inventory.db. Writes analysis_v3.json."""
import json, sqlite3, statistics, sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rules_v2 as r2
import rules_v3 as r3

db = sqlite3.connect(HERE / "site_inventory.db", timeout=60)
has_label = "label" in [c[1] for c in db.execute("pragma table_info(site_pages)")]
prof = {h: (m, sm) for h, m, sm in db.execute("select host, markets, sitemap_found from site_profile")}
status = {h: c for h, c in db.execute("select host, homepage_chars from site_menu_status")}
S = []
for host, (markets, sm) in sorted(prof.items()):
    maps = [u for (u,) in db.execute("select url from site_pages where host=? and source='map'", (host,))]
    if has_label:
        menu = {u: (z, l) for u, z, l in db.execute("select url, menu_zone, label from site_pages where host=? and source='menu'", (host,))}
    else:
        menu = {u: (z, "") for u, z in db.execute("select url, menu_zone from site_pages where host=? and source='menu'", (host,))}
    labels = {u: l for u, (z, l) in menu.items() if l}
    nav = {u for u, (z, l) in menu.items() if z in ("menu", "header")}
    universe = list(dict.fromkeys(maps + list(menu)))
    old = r2.classify_all(universe)
    old_sel = r2.select(old)
    new = r3.classify_all(universe, labels)
    new_sel = r3.select3(new)
    keep = {u: (t, via) for u, (v, t, via) in new.items() if v == "keep"}
    mapset = set(maps)

    def where(u):
        return "both" if (u in mapset and u in nav) else "map only" if u in mapset else "menu only" if u in nav else "body/footer only"
    p1 = [u for u, (t, _v) in keep.items() if t.startswith("P1")]
    S.append({"host": host, "markets": markets, "sitemap": bool(sm), "readable": (status.get(host) or 0) > 200,
              "labels": len(labels), "v2_selected": len(old_sel), "v3_selected": len(new_sel),
              "v3_by_tier": dict(Counter(t for _u, t in new_sel)),
              "kept_where": {t: dict(Counter(where(u) for u, (tt, _v) in keep.items() if tt == t)) for t in r3.BUDGET},
              "via": dict(Counter(v for _t, v in keep.values())),
              "p1_total": len(p1), "p1_via_label_only": sum(1 for u in p1 if keep[u][1] == "label"),
              "p1_in_menu": sum(1 for u in p1 if u in nav), "p1_in_map": sum(1 for u in p1 if u in mapset),
              "v2_had_p1": any(t.startswith("P1") for _u, t in old_sel),
              "dropped": dict(Counter(why for (v, why, _x) in new.values() if v == "drop")),
              "sample": [(urlparse(u).path[:60], t[:2]) for u, t in new_sel[:6]],
              "p1_label_examples": [(labels.get(u, "")[:40], urlparse(u).path[:40]) for u in p1 if keep[u][1] == "label"][:3]})


def dist(xs):
    xs = sorted(xs)
    return {"min": xs[0], "median": statistics.median(xs), "p75": xs[int(len(xs) * .75)], "max": xs[-1]}


tot = lambda key: dict(sum((Counter(s[key]) for s in S), Counter()))
summary = {
    "sites": len(S), "labels_captured_sites": sum(s["labels"] > 0 for s in S), "link_labels_total": sum(s["labels"] for s in S),
    "v2_total_pages": sum(s["v2_selected"] for s in S), "v3_total_pages": sum(s["v3_selected"] for s in S),
    "v3_pages_per_site": dist([s["v3_selected"] for s in S]),
    "v3_sites_selecting_0": sum(s["v3_selected"] == 0 for s in S),
    "v3_sites_1_to_10": sum(1 <= s["v3_selected"] <= 10 for s in S),
    "v3_sites_11_to_50": sum(s["v3_selected"] > 10 for s in S),
    "v3_selected_by_tier": tot("v3_by_tier"),
    "sites_with_p1_v2": sum(s["v2_had_p1"] for s in S), "sites_with_p1_v3": sum(s["p1_total"] > 0 for s in S),
    "p1_pages_v3": sum(s["p1_total"] for s in S),
    "p1_found_only_through_link_text": sum(s["p1_via_label_only"] for s in S),
    "sites_where_label_found_p1": sum(s["p1_via_label_only"] > 0 for s in S),
    "p1_in_menu_sites": sum(s["p1_in_menu"] > 0 for s in S), "p1_in_map_sites": sum(s["p1_in_map"] > 0 for s in S),
    "p1_only_via_menu_sites": sum(s["p1_in_menu"] > 0 and s["p1_in_map"] == 0 for s in S),
    "p1_only_via_map_sites": sum(s["p1_in_map"] > 0 and s["p1_in_menu"] == 0 for s in S),
    "p1_in_both_sites": sum(s["p1_in_menu"] > 0 and s["p1_in_map"] > 0 for s in S),
    "sites_no_p1_at_all": sum(s["p1_total"] == 0 for s in S),
    "kept_where": {t: dict(sum((Counter(s["kept_where"].get(t, {})) for s in S), Counter())) for t in r3.BUDGET},
    "kept_via_total": tot("via"), "dropped_total": tot("dropped"),
    "by_market": {m: {"sites": sum(m in s["markets"] for s in S), "pages": sum(s["v3_selected"] for s in S if m in s["markets"])}
                  for m in ("Cybersecurity", "Utility")},
}
(HERE / "analysis_v3.json").write_text(json.dumps({"summary": summary, "sites": S}, indent=1), encoding="utf-8")
print(json.dumps(summary, indent=1))
for h in ("nullcon.net", "isc2.org", "sans.org", "hydrogenexpo.com", "actexpo.com", "blackhat.com", "gartner.com"):
    for s in S:
        if s["host"].endswith(h):
            print(f"\n{s['host']}: v2={s['v2_selected']} v3={s['v3_selected']} labels={s['labels']} {s['v3_by_tier']}\n   {s['sample']}\n   label-found P1: {s['p1_label_examples']}")
