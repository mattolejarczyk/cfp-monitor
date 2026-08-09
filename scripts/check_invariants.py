"""Database integrity invariants - does the DB still agree with what was delivered?

This is NOT a second acceptance gate. `accept_delivery.py` decides whether a DELIVERY meets
the contract; this asks a different question about a different object: after importing,
verifying, re-keying and cleaning, does the DATABASE still hold exactly what it should?

Written 2026-08-08, after a session in which:
  * 4 rows were silently deleted during a multi-market import, because the clear-before-import
    step scoped by conference_markets and that table still held the PREVIOUS cycle's market
    memberships. Nothing complained. They were found only by hand-reconciling delivered ids
    against the DB.
  * 24 canonical keys carried a venue or a postcode (`...-tokyo-big-sight`, `...-69115-
    heidelberg`) because our own city repair corrupted the city the key derives from. Those
    keys then differed between cycles and the same conference imported twice.

Both were invisible to every existing check. The lesson is not "be careful" - it is that a
mutation needs a reconciliation, and reconciliation must not depend on somebody remembering.

    python scripts/check_invariants.py --db cfp_monitor.db [--seed-dir market_sheets]

Exit 0 = all invariants hold. Exit 1 = at least one violated. Intended to run at the end of
the weekly sweep, and by hand after any import or migration.

Rows deliberately kept in the DB but absent from the delivery (upstream dropped them without
declaring a reason, so contract 2.1 says we label rather than delete) are declared in
`market_sheets/held_rows.txt`: one `event_id  # reason` per line. An undeclared extra row is
a violation - that is the whole point.
"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import sys
from pathlib import Path

# Fragments that must never appear in a canonical key. Named venues and postcode shapes only.
#
# Deliberately NARROW, and it has already been narrowed twice. A loose pattern matches the
# year prefix on every key and reports the whole database as broken; `messe-\w+` flagged
# `2027-hannover-messe-hannover`, which is the conference Hannover Messe in Hannover and
# perfectly correct. A check that cries wolf gets ignored, which is worse than no check -
# so this lists venues by name and accepts that it will miss novel ones.
VENUE_MARKERS = re.compile(
    r"-(?:hilton|hyatt|marriott|intercontinental|sheraton|westin|radisson|novotel"
    r"|big-sight|marina-bay-sands|intex-\w+|makuhari-messe"
    r"|convention-cent(?:er|re)|exhibition-cent(?:er|re)|expo-cent(?:er|re))\b")
POSTCODE = re.compile(r"-(?:\d{5}|[a-z]\d{1,2}[a-z]?-?\d[a-z]{2})(?:-|$)")


class Result:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, list[str]]] = []

    def add(self, name: str, detail: str, offenders: list[str]) -> None:
        self.rows.append((name, detail, offenders))

    @property
    def failed(self) -> int:
        return sum(1 for _, _, o in self.rows if o)

    def report(self) -> int:
        for name, detail, off in self.rows:
            tag = "FAIL" if off else "ok  "
            print(f"  [{tag}] {name:<34} {detail}" + (f"  ({len(off)})" if off else ""))
            for o in off[:12]:
                print(f"            - {o}")
            if len(off) > 12:
                print(f"            ... and {len(off) - 12} more")
        print()
        if self.failed:
            print(f"RESULT: {self.failed} INVARIANT(S) VIOLATED")
            return 1
        print("RESULT: all invariants hold")
        return 0


def delivered_ids(seed_dir: Path) -> tuple[set[str], int]:
    """Canonical ids across every per-market seed. The stale combined grounding_seed.csv is
    skipped - it holds several markets and predates one-market-per-file imports."""
    ids: set[str] = set()
    files = 0
    for seed in sorted(seed_dir.glob("*_seed.csv")):
        if seed.name == "grounding_seed.csv":
            continue
        files += 1
        with open(seed, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                eid = (r.get("EVENT_ID_CANON") or "").strip()
                if eid:
                    ids.add(eid)
    return ids, files


def held_rows(seed_dir: Path) -> dict[str, str]:
    p = seed_dir / "held_rows.txt"
    out: dict[str, str] = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        eid, _, reason = line.partition("#")
        out[eid.strip()] = reason.strip() or "no reason recorded"
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Check database integrity invariants.")
    ap.add_argument("--db", default="cfp_monitor.db")
    ap.add_argument("--seed-dir", default="market_sheets")
    a = ap.parse_args()

    db, seed_dir = Path(a.db), Path(a.seed_dir)
    if not db.exists():
        print(f"ERROR: no database at {db.resolve()}")
        return 2

    ids, n_seeds = delivered_ids(seed_dir)
    if not ids:
        print(f"ERROR: no per-market *_seed.csv found in {seed_dir} - nothing to reconcile "
              f"against. Refusing to report success.")
        return 2
    held = held_rows(seed_dir)

    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = list(con.execute("select event_id, name, verify_state, submission_url "
                            "from grounding_facts"))
    db_ids = {r["event_id"] for r in rows}

    print(f"Invariants - {db.resolve().name}")
    print(f"  {len(rows)} DB row(s) | {len(ids)} delivered id(s) across {n_seeds} seed file(s)"
          f" | {len(held)} declared hold(s)\n")

    res = Result()

    # 1. THE ONE THAT CAUGHT REAL DATA LOSS. Every delivered row must be present.
    res.add("1  no delivered row is missing", "every EVENT_ID_CANON in a seed exists in the DB",
            sorted(ids - db_ids))

    # 2. Extra rows must be declared. Silence here is how a stale duplicate survives a cycle.
    res.add("2  no undeclared extra rows", "DB rows absent from the delivery must be in "
            "held_rows.txt", sorted(db_ids - ids - set(held)))

    # 3. Keys derive from the city, so a corrupted city is a corrupted identity.
    res.add("3  no venue or postcode in a key", "canonical keys hold a city, not a venue",
            sorted(k for k in db_ids if VENUE_MARKERS.search(k) or POSTCODE.search(k)))

    # 4. A row nobody verified is a row nobody can act on.
    res.add("4  every row has a verify state", "no blank or 'unverified' rows left behind",
            sorted(f"{r['name'] or r['event_id']}" for r in rows
                   if (r["verify_state"] or "") in ("", "unverified")))

    # 5. Duplicate identity: the failure that put RSA Conference in the file twice.
    seen: dict[str, int] = {}
    for r in rows:
        seen[r["event_id"]] = seen.get(r["event_id"], 0) + 1
    res.add("5  event_id is unique", "one row per canonical id",
            sorted(f"{k} x{v}" for k, v in seen.items() if v > 1))

    # 6. link_checks should have been populated by the weekly sweep. Absent or empty means
    #    the dead-link picture is stale, and every consumer of it is reporting old news.
    try:
        n_links = con.execute("select count(*) from link_checks").fetchone()[0]
        stale = [] if n_links else ["link_checks is empty - has the weekly sweep run?"]
    except sqlite3.OperationalError:
        stale = ["link_checks table does not exist - weekly sweep has never run"]
    res.add("6  link check results present", "dead-link picture is populated", stale)

    con.close()
    rc = res.report()
    if held:
        print("\nDeclared holds (present in the DB by decision, not by accident):")
        for eid, why in sorted(held.items()):
            mark = "" if eid in db_ids else "   [WARNING: declared but NOT in the DB]"
            print(f"  {eid}  - {why}{mark}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
