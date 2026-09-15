"""Fill grounding_facts.start_date from the deliveries that already carry it.

    python scripts/backfill_start_dates.py --db DB [--delivery CSV ...] [--apply]

Upstream has always shipped START DATE. Import read it for validation (DEADLINE_AFTER_EVENT_START)
and then dropped it, so the only date the table held was the submission deadline. Rows imported
before the column existed therefore have nothing, and this is the one-time catch-up; new imports
store it themselves.

WHY IT MATTERS, measured 2026-09-15. `match_customer_sheet` treats name+city+date as one of three
CERTAIN tests, and had to source our side of the date from whatever delivery CSV was passed on the
command line. The newest was five weeks old and did not contain the row being matched, so the
strongest test abstained for want of a date rather than on the evidence. A low score then reads
exactly like a disagreement.

NEWEST FILE WINS. Deliveries are processed in the order given and a later one overwrites an
earlier one, so pass the freshest last - the per-market `*_audited.final.csv` files are usually
newer than the combined ALL_MARKETS export.

WHAT IT REFUSES
An unparseable date is left NULL rather than guessed. `parse_loose_date` takes m/d/yyyy and
yyyy-mm-dd and nothing vaguer: "SEPTEMBER 27 - OCTOBER 1, 2026" is a real date to a reader and an
invitation to invent one for a program, and a wrong date inside a CERTAIN test is worse than no
date at all.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor.grounding import parse_loose_date                # noqa: E402
from src.cfp_monitor.identity import seed_map, to_canonical           # noqa: E402

MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
DEFAULTS = ["ALL_MARKETS_REFRESHED_20260812.csv",
            "Cybersecurity_audited.final.csv", "Utility_audited.final.csv"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--delivery", nargs="*", help="delivery CSVs, freshest LAST")
    ap.add_argument("--apply", action="store_true", help="write (default: report only)")
    a = ap.parse_args()

    files = [Path(p) for p in (a.delivery or [str(MARKETS / f) for f in DEFAULTS])]
    up2c, _roots = seed_map(a.db)
    con = sqlite3.connect(a.db)
    con.row_factory = sqlite3.Row
    known = {r["event_id"] for r in con.execute("SELECT event_id FROM grounding_facts")}
    have = {r["event_id"] for r in con.execute(
        "SELECT event_id FROM grounding_facts WHERE COALESCE(start_date,'') <> ''")}

    found: dict[str, str] = {}
    unparseable, unknown = 0, 0
    for f in files:
        if not f.exists():
            print(f"  (skipped, not found) {f.name}")
            continue
        n = 0
        with open(f, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                eid = to_canonical((r.get("EVENT_ID") or "").strip(), up2c)
                if eid not in known:
                    unknown += 1
                    continue
                raw = (r.get("START DATE") or "").strip()
                if not raw:
                    continue
                d = parse_loose_date(raw)
                if not d:
                    unparseable += 1
                    continue
                found[eid] = d.isoformat()          # later file wins
                n += 1
        print(f"  {f.name}: {n} parseable start date(s)")

    new = {k: v for k, v in found.items() if k not in have}
    print(f"\n{len(known)} row(s) in the database; {len(have)} already have a start date")
    print(f"  deliveries supply a date for {len(found)}; {len(new)} of those are new")
    print(f"  {unparseable} unparseable date(s) left NULL; {unknown} delivery row(s) not in the DB")
    still = len(known) - len(have) - len(new)
    print(f"  after this, {still} row(s) would still have no start date")

    if not a.apply:
        print("\nREPORT ONLY - re-run with --apply to write.")
        return 0
    for eid, iso in found.items():
        con.execute("UPDATE grounding_facts SET start_date=? WHERE event_id=?"
                    "  AND COALESCE(start_date,'') = ''", (iso, eid))
    con.commit()
    got = con.execute("SELECT COUNT(*) FROM grounding_facts"
                      " WHERE COALESCE(start_date,'') <> ''").fetchone()[0]
    con.close()
    print(f"\nwrote start dates; {got} of {len(known)} row(s) now carry one")
    print("A mutation needs a reconciliation - run scripts/check_invariants.py next.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
