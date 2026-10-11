"""ACT-33: what would the policy skip on each coming Saturday, if nothing about the events changed (their last accepted rows stay as they are today)? Read-only, offline.

    python experiments/act33_rehearsal/savings.py [first Saturday YYYY-MM-DD] [weeks]

Uses the scratch copies made for the rehearsal (work_markets = the live files of 2026-10-11, live/ = a mode=ro copy of the database). An ESTIMATE: statuses do not change here, new events are
never skipped, and the real input list will have grown. The dead-link override uses the link_checks of the copied database."""
import csv
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from scripts import refresh_plan as rp   # noqa: E402
from scripts.sponsor_prefill import read_link_states   # noqa: E402
from src.cfp_monitor.identity import seed_map   # noqa: E402


def main() -> None:
    first = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(2026, 10, 17)
    weeks = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    pol = rp.load_policy()
    db = HERE / "live" / "cfp_monitor.db"
    up, _ = seed_map(str(db))
    states = read_link_states(db)
    print(f"policy: {pol}")
    print("Saturday     market          rows  researched  g1  g2  g3  g4  ovr  skipped  saving USD (est.)")
    tot = 0.0
    for w in range(weeks):
        d = first + timedelta(days=7 * w)
        row_tot = 0
        for m in rp.CONF_MARKETS:
            rows = list(csv.DictReader(open(HERE / "work_markets" / f"{m}_input.csv", encoding="utf-8-sig", newline="")))
            prior = rp.prior_rows_by_canon(HERE / "work_markets" / f"{m}_audited.final.csv", up)
            pl = rp.conference_plan(rows, prior, states, rp.read_overrides(), d, pol)
            c = pl["counts"]
            s = len(pl["skip"])
            row_tot += s
            print(f"{d}  {m:14} {pl['rows']:5} {pl['researched']:10} {c['g1']:3} {c['g2']:3} {c['g3']:3} {c['g4']:3} {c['overrides']:4} {s:8}  {s * pol['cost_per_row_usd']:.2f}{'  ' + pl['fuse'][:40] if pl['fuse'] else ''}")
        tot += row_tot * pol["cost_per_row_usd"]
    print(f"average saving per Saturday over {weeks} Saturdays (both markets): {tot / weeks:.2f} USD (estimate)")


if __name__ == "__main__":
    main()
