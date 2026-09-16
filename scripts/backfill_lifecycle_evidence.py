"""Fill grounding_facts.lifecycle_evidence_url / lifecycle_quote from the deliveries.

    python scripts/backfill_lifecycle_evidence.py --db DB [--delivery CSV ...] [--apply]

R16 (v1.3) has required these two fields since the amendment. The delivery has carried them as
columns 37 and 38. The acceptance gate checks them. The customer page renders them. This table
had no column for either until 2026-09-16, so import read them and dropped them - and rows
imported before the column existed carry nothing. New imports store them themselves; this is
the one-time catch-up.

WHAT WAS LOST, and why it is the worst field to lose
Found through a duplicate that was not one. The database held a PROJECTED `ShmooCon 2027` for a
series whose last event was January 2025, and upstream had already told us so, in these two
fields, in a delivery we imported. What survived was a Wikipedia paraphrase in `deadline_quote`
- the one field R16.2 deliberately exempts these from, because a dead deadline citation is
withdrawn under R1 and the withdrawal would have erased the only trace that the event had ended.

So the most consequential claim upstream can make - this event is over, do not send a customer
at it - was the one claim the database could not hold. Everything reading the DB rather than
the delivery was blind to it.

NEWEST FILE WINS, and the pair travels together. A later delivery overwrites an earlier one, so
pass the freshest last. A row's URL and quote are one claim and are written as one: a new quote
beside an old URL is the split-citation defect in a field R1 cannot reach to correct.

WHAT IT REFUSES
A quote with no page, or a page with no quote, is NOT written. R16.1 requires both; half a
lifecycle claim is exactly the "unsourced" case `build_review_page` already has to caption, and
storing it would launder an assertion into evidence. Those rows are counted and named.

IT VERIFIES NOTHING. This moves what upstream supplied into the column it belongs in. Whether
each quote is really on the page it cites is a separate question that NOTHING ASKS YET: the gate
checks a lifecycle claim's presence, host (R22) and URL shape, never the quote against the page.
On 2026-09-16 one of the fifteen already failed that by hand - ShmooCon's "20th and final" sentence
does not appear on shmoocon.org. Check 16 in `check_invariants.py` asks only that a claim is
whole; the page check belongs to the weekly verification sweep and is an open item.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor.identity import seed_map, to_canonical           # noqa: E402

MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
DEFAULTS = ["ALL_MARKETS_REFRESHED_20260812.csv",
            "Cybersecurity_audited.final.csv", "Utility_audited.final.csv"]


def main() -> int:
    # Lifecycle quotes are organisers' own prose - curly quotes, en dashes, accented venues. The
    # Windows console is cp1252, and the first dry run crashed printing one AFTER the counts but
    # BEFORE --apply could run. A report that dies on the evidence it exists to show is no report.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--delivery", nargs="*", help="delivery CSVs, freshest LAST")
    ap.add_argument("--apply", action="store_true", help="write (default: report only)")
    a = ap.parse_args()

    files = [Path(p) for p in (a.delivery or [str(MARKETS / f) for f in DEFAULTS])]
    up2c, _roots = seed_map(a.db)
    con = sqlite3.connect(a.db)
    con.row_factory = sqlite3.Row
    known = {r["event_id"]: r["name"] for r in
             con.execute("SELECT event_id, name FROM grounding_facts")}
    have = {r["event_id"] for r in con.execute(
        "SELECT event_id FROM grounding_facts WHERE COALESCE(lifecycle_quote,'') <> ''")}

    found: dict[str, tuple[str, str]] = {}
    halves: list[str] = []
    unknown = 0
    for f in files:
        if not f.exists():
            print(f"  (skipped, not found) {f.name}")
            continue
        n = 0
        with open(f, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                url = (r.get("LIFECYCLE_EVIDENCE_URL") or "").strip()
                quote = (r.get("LIFECYCLE_QUOTE") or "").strip()
                if not url and not quote:
                    continue
                eid = to_canonical((r.get("EVENT_ID") or "").strip(), up2c)
                if eid not in known:
                    unknown += 1
                    continue
                if not (url and quote):
                    # R16.1 wants both. Half a claim is named, never stored.
                    halves.append(f"{(r.get('CONFERENCE') or eid)[:44]} "
                                  f"({'quote, no page' if quote else 'page, no quote'})")
                    continue
                found[eid] = (url, quote)          # later file wins; the pair moves as one
                n += 1
        print(f"  {f.name}: {n} complete lifecycle claim(s)")

    new = {k: v for k, v in found.items() if k not in have}
    print(f"\n{len(known)} row(s) in the database; {len(have)} already carry a lifecycle quote")
    print(f"  deliveries supply a complete claim for {len(found)}; {len(new)} of those are new")
    print(f"  {len(halves)} incomplete claim(s) refused; {unknown} delivery row(s) not in the DB")
    for h in halves:
        print(f"    - {h}")
    for eid, (_u, q) in sorted(new.items()):
        print(f"\n  {eid}\n    {known[eid][:70]}\n    \"{q[:100]}\"")

    if not a.apply:
        print("\nREPORT ONLY - re-run with --apply to write.")
        return 0
    for eid, (url, quote) in found.items():
        con.execute("UPDATE grounding_facts SET lifecycle_evidence_url=?, lifecycle_quote=?"
                    " WHERE event_id=? AND COALESCE(lifecycle_quote,'') = ''",
                    (url, quote, eid))
    con.commit()
    got = con.execute("SELECT COUNT(*) FROM grounding_facts"
                      " WHERE COALESCE(lifecycle_quote,'') <> ''").fetchone()[0]
    con.close()
    # Not "has ended": of the first fifteen, some ended, some were renamed, one moved city and
    # one merged into a sister event. R16 covers all four, and the wording should not overclaim.
    print(f"\nwrote lifecycle evidence; {got} row(s) now carry a lifecycle claim"
          f" (ended, merged, moved or superseded)")
    print("A mutation needs a reconciliation - run scripts/check_invariants.py next.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
