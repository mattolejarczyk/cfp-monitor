"""Report what a client changed in their sheet since the last snapshot, and what they did not.

    python scripts/diff_client_sheet.py --snapshots <dir> --client arnica [-o out.md]
    python scripts/diff_client_sheet.py --before a.csv --after b.csv --client arnica

With `--snapshots` it takes the two most recent snapshots for that client automatically, which
is what the weekly job wants. Naming both files is for re-running an older comparison.

Reports inaction ONLY where inaction costs something - an untouched row with no status set and a
deadline inside 30 days. Listing every untouched row every week is how a report stops being read.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import sheet_diff              # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="What the client changed since last week.")
    ap.add_argument("--client", required=True)
    ap.add_argument("--snapshots", help="the snapshot root; picks the two most recent")
    ap.add_argument("--before")
    ap.add_argument("--after")
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("-o", "--output")
    a = ap.parse_args()
    today = date.fromisoformat(a.today)

    if a.snapshots:
        found = sorted(glob.glob(os.path.join(a.snapshots, a.client, f"{a.client}_*.csv")))
        if len(found) < 2:
            print(f"Only {len(found)} snapshot(s) for {a.client}.\n"
                  "  A diff needs two. The first snapshot IS the baseline - there is nothing\n"
                  "  wrong here, it just means next week is the first comparison.")
            return 0
        before, after = Path(found[-2]), Path(found[-1])
    elif a.before and a.after:
        before, after = Path(a.before), Path(a.after)
    else:
        print("ERROR: pass --snapshots, or both --before and --after")
        return 2

    print(f"comparing\n  before {before.name}\n  after  {after.name}\n")
    d = sheet_diff.diff(before, after, today)
    report = sheet_diff.render(d, a.client, today)
    print(report)

    if d["rows_before"] != d["rows_after"]:
        print(f"note: row count moved {d['rows_before']} -> {d['rows_after']}")
    if a.output:
        Path(a.output).write_text(report, encoding="utf-8")
        print(f"wrote {a.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
