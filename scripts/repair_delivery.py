"""Repair a delivery whose rows were emitted without RFC 4180 quoting.

    python scripts/repair_delivery.py <broken.csv> --out <fixed.csv>

An unquoted comma inside a text field splits one field into several, shifting every column
after it. The shift is deterministic: a row with N extra fields had its text field split into
N+1 pieces, so re-joining them restores the row.

THIS IS A STOPGAP, NOT AN ACCEPTANCE PATH. A repaired file still fails the gate, and upstream
must still fix its writer -- otherwise we quietly absorb the defect forever and every future
delivery arrives broken. Repair exists so a broken delivery cannot block our own work while
that is being fixed.

Refuses to guess: the rebuilt row must validate on fields we can check independently, and any
row that does not is left alone and reported.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

COLS = 35
SPLIT_FIELD = "STATUS DETAILS"        # the field that has broken every time so far
OPPORTUNITIES = {"Speaking", "Awards", "Exhibiting", "Registration"}
CFP_MODELS = {"Fixed Deadline", "Rolling Form", "Invite Only", "Not Announced"}


def validate(row: list[str], header: list[str]) -> list[str]:
    """Independent checks on a rebuilt row. These are fields whose shape we know, so if the
    re-join were wrong they would land on the wrong values and fail."""
    d = dict(zip(header, row))

    def g(k):
        return (d.get(k) or "").strip()

    bad = []
    if len(row) != COLS:
        bad.append(f"{len(row)} fields")
    if g("OPPORTUNITY_TYPE") not in OPPORTUNITIES:
        bad.append(f"OPPORTUNITY_TYPE={g('OPPORTUNITY_TYPE')!r}")
    if g("IS_PROJECTED").lower() not in ("true", "false"):
        bad.append(f"IS_PROJECTED={g('IS_PROJECTED')!r}")
    if not re.fullmatch(r"\d{4}", g("EDITION")):
        bad.append(f"EDITION={g('EDITION')!r}")
    if g("CFP MODEL TYPE") not in CFP_MODELS:
        bad.append(f"CFP MODEL TYPE={g('CFP MODEL TYPE')!r}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", g("START DATE")):
        bad.append(f"START DATE={g('START DATE')!r}")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description="Repair an unquoted-comma CSV delivery.")
    ap.add_argument("csv_path")
    ap.add_argument("--out", required=True)
    ap.add_argument("--field", default=SPLIT_FIELD, help="the text field that was split")
    a = ap.parse_args()

    rows = list(csv.reader(open(a.csv_path, encoding="utf-8-sig")))
    if not rows:
        print("empty file")
        return 1
    header, body = rows[0], rows[1:]
    if len(header) != COLS:
        print(f"header has {len(header)} columns, expected {COLS} - not a v4.2/4.3 file")
        return 1
    idx = header.index(a.field)

    out, failed, touched = [], [], 0
    for lineno, row in enumerate(body, start=2):
        if len(row) == COLS:
            out.append(row)
            continue
        extra = len(row) - COLS
        if extra < 1:
            failed.append((lineno, row[1][:40] if len(row) > 1 else "?", [f"{len(row)} fields"]))
            continue
        # The split pieces still carry the whitespace that followed each comma, so re-join on
        # the bare comma -- ", " would double the space and corrupt the text we are restoring.
        merged = ",".join(row[idx:idx + extra + 1])
        rebuilt = row[:idx] + [merged] + row[idx + extra + 1:]
        problems = validate(rebuilt, header)
        if problems:
            failed.append((lineno, row[1][:40], problems))
        else:
            out.append(rebuilt)
            touched += 1

    print(f"{Path(a.csv_path).name}: {len(body)} rows | repaired {touched} | "
          f"already valid {len(out) - touched} | REFUSED {len(failed)}")
    for lineno, name, problems in failed:
        print(f"   line {lineno:<4} {name:<40} {'; '.join(problems)}")
    if failed:
        print("\nRefusing to write a partially repaired file - fix upstream instead.")
        return 1

    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(out)
    print(f"\nwrote {a.out}")
    print("NOTE: this is a local stopgap. The delivery still FAILS the acceptance gate and")
    print("      upstream must fix its CSV writer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
