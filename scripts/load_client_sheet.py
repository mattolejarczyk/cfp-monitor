"""Load a client's snapshotted sheet into the client layer.

    python scripts/load_client_sheet.py --db cfp_monitor.db \
        --client utility-global --name "Utility Global" --industry Utility \
        --csv <snapshot.csv> [--subindustry Decarbonization] [--dry-run]

Stage 0 takes the snapshot; this puts it where it can be queried and diffed. It is ADDITIVE:
it creates three new tables and writes only to those. `conferences`, `grounding_facts` and
`conference_markets` are never touched, because a client's status and priority are per-client
and those tables are shared and single-valued.

Rows we cannot place in the industry list land in `industry_candidates` with no decision
recorded. Nothing joins an industry list without Nicolia's team saying so.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import clients          # noqa: E402

PROTECTED = ("conferences", "grounding_facts", "conference_markets", "evidence")


def counts(con: sqlite3.Connection) -> dict:
    out = {}
    for t in PROTECTED:
        try:
            out[t] = con.execute(f"select count(*) from [{t}]").fetchone()[0]
        except sqlite3.Error:
            out[t] = None
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Load a client sheet into the client layer.")
    ap.add_argument("--db", required=True)
    ap.add_argument("--csv", required=True, help="a snapshot from snapshot_customer_sheet.py")
    ap.add_argument("--client", required=True, help="client key, e.g. utility-global")
    ap.add_argument("--name", required=True, help="client display name, e.g. Utility Global")
    ap.add_argument("--industry", required=True, help="industry list this client draws from")
    ap.add_argument("--subindustry", default="")
    ap.add_argument("--sheet-url", default="")
    ap.add_argument("--sheet-gid", default="")
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    a = ap.parse_args()

    db, src = Path(a.db), Path(a.csv)
    if not db.exists():
        print(f"ERROR: no database at {db.resolve()}")
        return 2
    if not src.exists():
        print(f"ERROR: no such snapshot: {src}")
        return 2

    con = sqlite3.connect(db)
    known = {r[0] for r in con.execute("select name from industries")}
    if known and a.industry not in known:
        print(f"REFUSED: '{a.industry}' is not one of our industries.\n  known: "
              f"{sorted(known)}\n  A typo here files the client's rows against an industry "
              "list that does not exist, and nothing would report it.")
        con.close()
        return 3

    if a.dry_run:
        rows, unmapped = clients.read_sheet(src)
        print(f"DRY RUN - {len(rows)} row(s) would load for {a.name} ({a.industry})")
        if unmapped:
            print(f"  columns we do not map: {unmapped}")
        con.close()
        return 0

    # A mutation needs a reconciliation, and a backup before it. The delivery import learned
    # this the expensive way: four rows were deleted silently and nothing complained.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = db.with_name(f"{db.stem}.backup-pre-clientlayer-{stamp}.db")
    shutil.copy2(db, backup)

    before = counts(con)
    clients.ensure_schema(con)
    clients.upsert_client(con, a.client, a.name, industry=a.industry,
                          subindustry=a.subindustry, sheet_url=a.sheet_url,
                          sheet_gid=a.sheet_gid)
    s = clients.load_sheet(con, a.client, src, industry=a.industry)
    after = counts(con)

    print(f"{a.name}  [{a.client}]  industry={a.industry}"
          + (f" / {a.subindustry}" if a.subindustry else ""))
    print(f"  rows in sheet        {s['rows']}")
    print(f"  added                {s['added']}")
    print(f"  updated              {s['updated']}")
    print(f"  withdrawn by client  {s['withdrawn']}"
          + ("  (kept, not deleted - rule C4)" if s["withdrawn"] else ""))
    for n in s["withdrawn_names"][:10]:
        print(f"      {n}")
    if s["unmapped_columns"]:
        print(f"  UNMAPPED COLUMNS     {s['unmapped_columns']}")
        print("      Their sheet has a column we do not read. Add it to COLUMN_MAP or "
              "decide explicitly to ignore it.")
    print(f"  not yet matched      {s['not_yet_matched']}  (no event_id)")
    print("      Loading does not decide whether these exist in the industry list - matching")
    print("      is a separate stage. Run scripts/match_customer_sheet.py, then raise")
    print("      promotion candidates from what it could not place.")

    # The protected tables must be byte-for-byte untouched. This is the check the delivery
    # import did not have on 2026-08-08.
    drift = {t: (before[t], after[t]) for t in PROTECTED if before[t] != after[t]}
    if drift:
        print(f"\n  *** SHARED TABLES MOVED: {drift}\n"
              f"  *** The client layer must never write to them. Restore: {backup.name}")
        con.close()
        return 4
    print(f"\n  shared tables unchanged: "
          + ", ".join(f"{t}={after[t]}" for t in PROTECTED))
    print(f"  backup: {backup.name}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
