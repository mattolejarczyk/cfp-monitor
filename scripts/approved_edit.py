"""Safe edits of an approved delivery file (`<Market>_audited.final.csv`) and of a database copy, shared by scripts/withdraw_citations.py (ACT-46) and scripts/retire_duplicates.py (ACT-47).

    from scripts.approved_edit import read_approved, write_approved, backup_db

Rules this module enforces so no caller can forget them (QA-REGISTER C7, `apply_pins_live.py` is the pattern):
  - a backup `<name>.pre-<tag>-<stamp>.bak.csv` is written beside the file BEFORE anything changes;
  - the new file is written to `<file>.tmp` with the original BOM and line endings, QUOTE_ALL, then READ BACK and compared with the original: exactly the expected cells changed, or exactly the expected
    rows were removed, nothing else, row order kept; any other difference raises and the original is left in place;
  - then `os.replace`. The caller must re-gate (with the network) and re-promote afterwards or Monday's page refuses to publish (it says so).
A database is copied with SQLite's online backup API (never a raw file copy of a live database). Nothing here decides WHAT to change."""
from __future__ import annotations

import csv
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


def read_approved(path: Path) -> tuple[list[str], list[dict], bool, bool]:
    """(columns, rows, has_bom, uses_crlf)."""
    raw = Path(path).read_bytes()
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        return list(rd.fieldnames), list(rd), raw.startswith(b"\xef\xbb\xbf"), b"\r\n" in raw


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def write_approved(path: Path, cols: list[str], before: list[dict], after: list[dict], bom: bool, crlf: bool, tag: str,
                   expect_cells: set[tuple[int, str]] | None = None, expect_removed: set[int] | None = None) -> Path:
    """Write `after` over `path` (backup first) and prove the change. `expect_cells` = {(row index in before, column)} for a cell edit (same row count);
    `expect_removed` = {row index in before} for a row removal (every kept row identical, order kept). Returns the backup path."""
    path = Path(path)
    if (expect_cells is None) == (expect_removed is None):
        raise ValueError("give exactly one of expect_cells and expect_removed")
    bak = path.with_name(path.name.replace(".csv", "") + f".pre-{tag}-{stamp()}.bak.csv")
    shutil.copy2(path, bak)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL, lineterminator="\r\n" if crlf else "\n")
        w.writeheader()
        w.writerows(after)
    with open(tmp, encoding="utf-8-sig", newline="") as fh:
        read_back = list(csv.DictReader(fh))
    try:
        if expect_cells is not None:
            changed = {(i, c) for i, (a, b) in enumerate(zip(before, read_back)) for c in a if a[c] != b.get(c)}
            if len(read_back) != len(before) or changed != expect_cells:
                raise AssertionError(f"unexpected change in {path.name}: rows {len(before)}->{len(read_back)}, cells {sorted(changed ^ expect_cells)[:6]}")
        else:
            kept = [r for i, r in enumerate(before) if i not in expect_removed]
            if read_back != kept:
                raise AssertionError(f"unexpected change in {path.name}: expected exactly rows {sorted(expect_removed)} removed ({len(before)}->{len(kept)}), got {len(read_back)} rows")
    except AssertionError:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, path)
    return bak


def backup_db(db_path: Path, tag: str) -> Path:
    """A consistent copy of a database next to it (`<name>.pre-<tag>-<stamp>.db`), made with SQLite's backup API."""
    db_path = Path(db_path)
    dest = db_path.with_name(db_path.stem + f".pre-{tag}-{stamp()}.db")
    src = sqlite3.connect(f"file:{str(db_path).replace(chr(92), '/')}?mode=ro", uri=True)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return dest
