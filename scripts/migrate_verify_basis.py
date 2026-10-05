"""Add the `verify_basis` column and fill it from what each row already says (ACT-18, failure point C6). Report-only unless --apply.

    python scripts/migrate_verify_basis.py --db <db>                       # report: what each row would be classified as, nothing written
    python scripts/migrate_verify_basis.py --db <db> --apply [--backup-dir D]   # backup, ALTER both tables, fill, then PROVE nothing else moved

WHAT IT PROVES (and refuses to leave in place if it cannot). After the write, and before it keeps the result:
  1. both tables hold exactly the same number of rows;
  2. every OTHER column of every row is byte-identical to the backup (the only column that may differ is verify_basis);
  3. the board's figures (Complete %, Accurate %, proven, contradicted, customer agreement), computed with scripts/board_metrics.py on the database before and
     after, are identical (`--markets-dir` and `--today` are passed to both; they must not change).
If a proof fails the database is restored from the backup and the exit code is 1. The reviewer applies this live (a backup first, the sandbox rehearsal in the
worklog); the builder only ever runs it on a copy. See src/cfp_monitor/verify_basis.py for what the values mean."""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor.verify_basis import backfill, basis_from_detail, ensure_column, has_column   # noqa: E402

TABLES = ("grounding_facts", "award_grounding_facts")
MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")


def snapshot(db: str) -> dict:
    """Every row of both tables, keyed by event_id, WITHOUT the verify_basis column."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    out = {}
    for t in TABLES:
        rows = {}
        for r in con.execute(f"SELECT * FROM {t}"):
            d = dict(r)
            d.pop("verify_basis", None)
            rows[d["event_id"]] = d
        out[t] = rows
    con.close()
    return out


def board_figures(db: str, markets_dir: str, today: str) -> dict:
    """The figures the board shows, from board_metrics, as one comparable dict. Read only."""
    from scripts import board_metrics as bm
    fig = {}
    for kind in ("conference", "award"):
        fig[f"split_{kind}"] = bm.split_for(db, markets_dir, today, kind)
        fig[f"provable_{kind}"] = bm.provable_live(db, today, kind)
        fig[f"agreement_{kind}"] = bm.customer_agreement(db, today, kind)
    return json.loads(json.dumps(fig, default=str, sort_keys=True))


def report(db: str) -> dict:
    """What each row would be classified as, without writing. {table: Counter((state, basis))}."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out = {}
    for t in TABLES:
        c = Counter()
        for st, det in con.execute(f"SELECT verify_state, verify_detail FROM {t}"):
            c[(st or "", basis_from_detail(st, det) or "(unclassified)")] += 1
        out[t] = c
    con.close()
    return out


def apply(db: str, backup_dir: Path, markets_dir: str, today: str) -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{Path(db).stem}.pre-verify-basis-{stamp}.db"
    shutil.copy2(db, backup)
    print(f"backup: {backup}")
    before_rows, before_board = snapshot(str(backup)), board_figures(str(backup), markets_dir, today)
    con = sqlite3.connect(db)
    try:
        for t in TABLES:
            added = ensure_column(con, t)
            written = backfill(con, t)
            print(f"{t}: column {'added' if added else 'already there'}; classified {dict(sorted(written.items()))}")
        con.commit()
    finally:
        con.close()
    after_rows, after_board = snapshot(db), board_figures(db, markets_dir, today)
    problems = []
    for t in TABLES:
        if set(before_rows[t]) != set(after_rows[t]):
            problems.append(f"{t}: the set of rows changed")
        diff = [k for k in before_rows[t] if before_rows[t][k] != after_rows[t].get(k)]
        if diff:
            problems.append(f"{t}: {len(diff)} row(s) changed in a column other than verify_basis (first: {diff[0]})")
    if before_board != after_board:
        problems.append("the board figures changed: " + ", ".join(k for k in before_board if before_board[k] != after_board.get(k)))
    if problems:
        shutil.copy2(backup, db)
        print("PROOF FAILED, database restored from the backup:")
        for p in problems:
            print("  -", p)
        return 1
    n = {t: len(after_rows[t]) for t in TABLES}
    print(f"PROVED: row counts unchanged {n}; every other column identical; board figures identical ({len(after_board)} blocks compared)")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup-dir", help="default: beside the database")
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--today", default=date.today().isoformat())
    a = ap.parse_args()
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    have = {t: has_column(con, t) for t in TABLES}
    con.close()
    print(f"{a.db}: verify_basis column present: {have}")
    for t, c in report(a.db).items():
        print(f"\n{t}")
        for (st, b), n in sorted(c.items()):
            print(f"  {st or '(blank)':12s} basis {b:14s} {n:4d}")
    if not a.apply:
        print("\nreport only; add --apply (on a COPY first) to write")
        return 0
    return apply(a.db, Path(a.backup_dir or Path(a.db).parent), a.markets_dir, a.today)


if __name__ == "__main__":
    raise SystemExit(main())
