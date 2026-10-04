"""Side by side (2026-10-04): the weekly GROUNDED call vs the REAL-URL path (menu/sitemap finder + cheap reader + main-call rule), same 14 events, same gold.

    python experiments/finder_reader_test/side_by_side.py

GROUNDED = the raw research output of the Saturday 2026-10-03 run (Markets/<Market>_audited.csv, narrow-first prompt: what Gemini returned BEFORE any overlay, pin or carry, so no
operator ruling can leak into it). Rows are matched to the gold through identity.to_canonical (contract 5.4; never a direct EVENT_ID join).
REAL-URL = experiments/finder_reader_test/results.json (run 2: pick = the main-call deadline, or none).
GOLD = customer-verified live dates that match ours + the operator's pinned deadlines (run.gold_events). Free: no model call, no research call; the only network is one plain fetch of each
page the grounded call cited, to see whether that page states the date it was cited for (verify.find_date).
Per event, each path is: exact (equals gold) | blank | different (a date that is not gold) ; the grounded path also: cited page states its date yes/no/unreadable.
Then the policy view: agree-and-right, disagree (which one was right), only one path answered."""
from __future__ import annotations

import csv
import json
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")


def outcome(value: str, gold: str) -> str:
    v = (value or "").strip()
    return "blank" if not v else ("exact" if v[:10] == gold else "different")


def policy(g: str, r: str) -> str:
    """How the two paths relate for one event (outcomes are exact | blank | different)."""
    if g == "exact" and r == "exact":
        return "both right (agree)"
    if "different" in (g, r) and "exact" in (g, r):
        return "disagree: the " + ("grounded" if g == "exact" else "real-URL") + " path was right"
    if g == "different" and r == "different":
        return "both different"
    if g == "exact":
        return "only grounded right"
    if r == "exact":
        return "only real-URL right"
    return "neither right"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from scripts.board_metrics import LIVE_DB
    from src.cfp_monitor.identity import seed_map, to_canonical
    from src.cfp_monitor.verify import fetch_text, find_date, is_block_page
    up_to_canon, _roots = seed_map(str(LIVE_DB))
    rows = {}
    for m in ("Cybersecurity", "Utility"):
        with open(MARKETS / f"{m}_audited.csv", encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                rows.setdefault(to_canonical(r.get("EVENT_ID", ""), up_to_canon), r)
    real = {e["id"]: e for e in json.loads((HERE / "results.json").read_text(encoding="utf-8")) if "pages" in e}
    out = []
    for cid, e in real.items():
        g = rows.get(cid)
        gv = (g or {}).get("SUBMISSION DEADLINE", "")
        ev, quote = (g or {}).get("DEADLINE_EVIDENCE_URL", ""), (g or {}).get("DEADLINE_QUOTE", "")
        cited = "-"
        if gv and ev:
            try:
                t, _n = fetch_text(ev)
                cited = "unreadable" if (not t or is_block_page(t)) else ("yes" if find_date(t, datetime.strptime(gv[:10], "%Y-%m-%d").date()) else "no")
            except Exception:                                              # noqa: BLE001
                cited = "unreadable"
        rec = {"event": e["event"], "gold": e["gold"], "researched": g is not None, "grounded": gv, "grounded_outcome": outcome(gv, e["gold"]) if g else "not researched",
               "grounded_cited_page_states_it": cited, "grounded_evidence": ev, "projected": (g or {}).get("IS_PROJECTED", ""),
               "real": e["pick"]["pick"], "real_outcome": outcome(e["pick"]["pick"], e["gold"])}
        rec["policy"] = policy(rec["grounded_outcome"], rec["real_outcome"])
        out.append(rec)
        print(f"{e['event'][:38]:38} gold {e['gold']} | grounded {gv or '-':10} {rec['grounded_outcome']:13} cited-page-states-it {cited:10} | real-URL {rec['real'] or '-':10} {rec['real_outcome']:9} | {rec['policy']}")
    from collections import Counter
    n = len(out)
    gc, rc, pc = (Counter(o["grounded_outcome"] for o in out), Counter(o["real_outcome"] for o in out), Counter(o["policy"] for o in out))
    print(f"\nEVENTS {n}\n GROUNDED  {dict(gc)}\n REAL-URL  {dict(rc)}\n POLICY    {dict(pc)}")
    cp = Counter(o["grounded_cited_page_states_it"] for o in out if o["grounded"])
    print(f" grounded: the page it cited states the date it gave: {dict(cp)}")
    (HERE / "side_by_side.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
