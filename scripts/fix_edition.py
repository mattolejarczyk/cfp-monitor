"""Separate the row's IDENTITY from its EDITION, and derive the edition from a real date.

THE DEFECT
`EDITION` is downstream's field under contract section 3, but in practice we import it verbatim
from upstream's column (grounding.py `_COL`). Nothing ever checked it against a date. On
2026-08-12, 71 of 392 rows carried an edition that disagreed with the year in the event's own
name - "AWE USA 2027" with edition 2026.

That would be cosmetic except for one thing: `event_id()` builds the canonical key out of the
edition, so the key inherits the error. Two live duplicates were created exactly this way -
Decarb Connect North America 2027 and Carbon Capture Technology Expo North America 2027 each
exist twice, once under a 2026- key and once under a 2027- key, same name, same city. The same
event arriving with two different EDITION values becomes two records.

THE FIX, AND WHY IT IS NOT "RECOMPUTE THE KEYS"
The instinct is to correct the edition and re-derive every key. That is the wrong move and it
is the 2026-08-08 accident waiting to happen again - a tidy-up that rewrites hundreds of
canonical keys while every test still passes.

A key is a NAME, not a fact. It has to be stable and unique; it does not have to be true. So:

    key_year   frozen at creation, never recomputed. Keeps every existing key byte-identical.
    edition    derived from the date the conference starts. This is what the customer sees
               and what the L0 guard compares.

Splitting them fixes what Nicolia reads and unblocks verification without moving a single key.
The odd-looking 2026- prefix on a 2027 event is the price, and it is worth paying.

WHERE THE TRUE YEAR COMES FROM
Measured, not assumed. Our crawl records were useless here - NONE of the 71 had a matching
`conferences` row carrying dates. The delivery has carried `START DATE` all along and we simply
never imported it:

    66 of 71   START DATE confirms the year in the name; the edition is wrong
     1 of 71   START DATE and edition agree, and the NAME is the misleading one
     4 of 71   no date in the delivery at all

So the rule is "the edition is the calendar year the conference starts" - a fact we hold - and
NOT "read the year out of the name", which would be a guess. Where no date exists we change
nothing and say so (contract 2.5, decline rather than guess; 2.6, an honest blank).

    python scripts/fix_edition.py --db <db> --delivery <csv> [--apply]
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

YEAR = re.compile(r"\b(20\d\d)\b")


def _year(*texts) -> str | None:
    """The latest year stated in any of these, or None. Never invents one."""
    for t in texts:
        found = YEAR.findall(str(t or ""))
        if found:
            return max(found)
    return None


def _seed_map(db: str) -> dict:
    """Upstream EVENT_ID -> our canonical id, reusing the one implementation we have."""
    spec = importlib.util.spec_from_file_location("_ar", ROOT / "scripts" / "apply_resolutions.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    class _S:
        path = db

    up_to_canon, _roots = mod._seed_map(_S())
    return up_to_canon


def plan(db: str, delivery: Path) -> tuple[list, dict]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    up = _seed_map(db)

    by_id = {}
    with open(delivery, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            raw = (r.get("EVENT_ID") or "").strip()
            by_id[up.get(raw, raw)] = r

    out, tally = [], {"already right": 0, "would change": 0,
                      "no date - left alone": 0, "not in delivery": 0}
    for g in con.execute("select event_id, name, edition from grounding_facts"):
        d = by_id.get(g["event_id"])
        if not d:
            tally["not in delivery"] += 1
            continue
        true_year = _year(d.get("START DATE"), d.get("CONFERENCE DATES"))
        cur = str(g["edition"] or "").strip()
        if not true_year:
            tally["no date - left alone"] += 1
            out.append((g["event_id"], g["name"], cur, None, "no date"))
            continue
        if cur == true_year:
            tally["already right"] += 1
            continue
        tally["would change"] += 1
        out.append((g["event_id"], g["name"], cur, true_year, "change"))
    return out, tally


def apply(db: str, changes: list) -> None:
    """Freeze the key year, then correct the edition. Never touches event_id."""
    con = sqlite3.connect(db)
    cols = [c[1] for c in con.execute("pragma table_info(grounding_facts)")]
    if "key_year" not in cols:
        con.execute("alter table grounding_facts add column key_year text")
        print("  added column key_year")

    # Freeze FIRST and for EVERY row, not just the ones changing: the whole point is that the
    # key's year stops depending on a field we are about to start correcting.
    con.execute("update grounding_facts set key_year = substr(edition,1,4) "
                "where key_year is null or key_year = ''")
    frozen = con.total_changes
    print(f"  froze key_year on {frozen} row(s)")

    n = 0
    for eid, _name, _cur, new, kind in changes:
        if kind != "change":
            continue
        con.execute("update grounding_facts set edition = ? where event_id = ?", (new, eid))
        n += 1
    con.commit()
    print(f"  corrected edition on {n} row(s)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Freeze the key year; derive edition from the date.")
    ap.add_argument("--db", required=True)
    ap.add_argument("--delivery", required=True, help="the delivery CSV carrying START DATE")
    ap.add_argument("--apply", action="store_true", help="write. Reports only without it.")
    a = ap.parse_args()

    print("=" * 84)
    print(f"EDITION / KEY-YEAR SPLIT   {datetime.now():%Y-%m-%d %H:%M}   "
          f"{'APPLY' if a.apply else 'REPORT ONLY'}")
    print("=" * 84)

    changes, tally = plan(a.db, Path(a.delivery))
    print()
    for k, v in tally.items():
        print(f"   {v:>4}  {k}")

    show = [c for c in changes if c[4] == "change"]
    if show:
        print(f"\n--- {len(show)} edition(s) to correct ---")
        for _eid, name, cur, new, _k in show[:40]:
            print(f"   {name[:52]:<52} {cur} -> {new}")
        if len(show) > 40:
            print(f"   ... and {len(show)-40} more")

    blank = [c for c in changes if c[4] == "no date"]
    if blank:
        print(f"\n--- {len(blank)} row(s) with no date anywhere: left exactly as they are ---")
        for _eid, name, cur, _n, _k in blank[:15]:
            print(f"   {name[:52]:<52} edition={cur or '(blank)'}")

    if not a.apply:
        print("\nREPORT ONLY - nothing written.")
        print("Re-run with --apply once this reads correctly. It will:")
        print("  1. add key_year and freeze it from the CURRENT edition, so no key can move")
        print("  2. correct edition from the conference start date")
        print("It never touches event_id.")
        return 0

    bak = f"{a.db}.bak-{datetime.now():%Y%m%d-%H%M%S}-edition"
    shutil.copy2(a.db, bak)
    print(f"\nbackup: {bak}")
    apply(a.db, changes)
    print("\nRun scripts/check_invariants.py now - a mutation needs a reconciliation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
