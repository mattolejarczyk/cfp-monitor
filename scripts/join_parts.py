"""Join a delivery that arrived as several chat-pasted parts into one valid CSV.

    python scripts/join_parts.py part1.txt part2.txt ... --out Market_v4-3.csv
    python scripts/join_parts.py parts_dir/ --out Market_v4-3.csv

Upstream runs on a chat surface whose file links do not reliably resolve, so the practical
delivery route is pasted text in numbered parts. That is fine as long as parts are split on
ROW boundaries: this joins them, drops any repeated header, strips code-fence lines, and
refuses to write unless every row has the expected field count.

Refusing beats repairing here. A part boundary that landed mid-row is not recoverable by
guesswork, and a silently truncated market is worse than an obvious failure.
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

COLS = 35


def read_part(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("```") or s.startswith("### PART") or s.startswith("#### PART"):
            continue                      # fence or part marker pasted along with the data
        out.append(line)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Join pasted CSV parts into one file.")
    ap.add_argument("parts", nargs="+", help="part files in order, or one directory")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cols", type=int, default=COLS)
    a = ap.parse_args()

    paths: list[Path] = []
    for p in a.parts:
        q = Path(p)
        paths.extend(sorted(q.iterdir()) if q.is_dir() else [q])
    paths = [p for p in paths if p.is_file()]
    if not paths:
        print("no part files found")
        return 1

    lines: list[str] = []
    for p in paths:
        got = read_part(p)
        print(f"  {p.name:<34} {len(got)} line(s)")
        lines.extend(got)

    rows = list(csv.reader(io.StringIO("\n".join(lines))))
    if not rows:
        print("nothing to write")
        return 1

    # A header repeated at the top of each part is common; keep only the first.
    header = rows[0]
    body = [r for r in rows[1:] if r != header]

    bad = [(i, len(r)) for i, r in enumerate(body, start=2) if len(r) != a.cols]
    print(f"\nheader fields: {len(header)}   data rows: {len(body)}")
    if len(header) != a.cols:
        print(f"HEADER has {len(header)} fields, expected {a.cols} - wrong file or a bad split")
        return 1
    if bad:
        print(f"REFUSING: {len(bad)} row(s) do not have {a.cols} fields. A part boundary"
              f" probably landed mid-row; ask for those parts again.")
        for i, n in bad[:10]:
            print(f"   row {i}: {n} fields")
        return 1

    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(body)
    print(f"\nwrote {a.out}  ({len(body)} rows, {a.cols} columns)")
    print("Next: python scripts/accept_delivery.py \"" + a.out + "\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
