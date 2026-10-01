"""Measure each v3.1 fix alone, then all four, against v3 on all 84 sites (offline). Writes analysis_v31.json."""
import json, sqlite3, sys
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rules_v3 as r3
import rules_v31 as r31

db = sqlite3.connect(HERE / "site_inventory.db", timeout=60)
hosts = [h for (h,) in db.execute("select host from site_profile order by host")]
FLAGSETS = {"F1 board/review noise": {"F1"}, "F2 de-duplicate": {"F2"}, "F3 join-as-speaker/contribution": {"F3"},
            "F4 two-digit years": {"F4"}, "ALL four": {"F1", "F2", "F3", "F4"}}
res = {k: {"removed": [], "added": []} for k in FLAGSETS}
tot3 = 0
totals = {k: 0 for k in FLAGSETS}
for host in hosts:
    maps = [u for (u,) in db.execute("select url from site_pages where host=? and source='map'", (host,))]
    menu = {u: l for u, l in db.execute("select url, label from site_pages where host=? and source='menu'", (host,))}
    labels = {u: l for u, l in menu.items() if l}
    universe = list(dict.fromkeys(maps + list(menu)))
    base = r3.classify_all(universe, labels)
    base_sel = {u: t for u, t in r3.select3(base)}
    tot3 += len(base_sel)
    for name, fl in FLAGSETS.items():
        new = r31.classify_all(universe, labels, frozenset(fl))
        sel = {u: t for u, t in r31.select31(new, frozenset(fl))}
        totals[name] += len(sel)
        for u in set(base_sel) - set(sel):
            res[name]["removed"].append((host, urlparse(u).path[:70], base_sel[u][:2]))
        for u in set(sel) - set(base_sel):
            res[name]["added"].append((host, urlparse(u).path[:70], sel[u][:2]))
out = {"v3_total": tot3, "totals": totals, "changes": {k: {"removed": len(v["removed"]), "added": len(v["added"])} for k, v in res.items()}}
(HERE / "analysis_v31.json").write_text(json.dumps({"summary": out, "detail": res}, indent=1), encoding="utf-8")
print("v3 selected pages:", tot3)
for k, v in res.items():
    print(f"\n== {k}: total {totals[k]}  (removed {len(v['removed'])}, added {len(v['added'])})")
    for x in v["removed"][:14]:
        print("   - removed", x)
    for x in v["added"][:8]:
        print("   + added  ", x)
