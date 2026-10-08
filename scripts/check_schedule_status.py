"""Which published statuses rest only on the typical schedule? (ACT-54 e). READ-ONLY; always exits 0.

    python scripts/check_schedule_status.py [--file delivery.csv ...] [--markets-dir <dir>]

Default input: Markets/<Market>_audited.final.csv for Cybersecurity and Utility (what the customer pages are built from). Rule: src/cfp_monitor/schedule_only.py.
Output (read by the recap once it is hooked in): `SCHEDULE-ONLY STATUS: <n> row(s) say Open/Closed/Upcoming with no page behind them (should read Needs Verification)`
then one line per row. Nothing is written; a missing file is reported, not fatal."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.cfp_monitor.schedule_only import find_schedule_only          # noqa: E402

MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")


def scan(paths: list[Path]) -> tuple[list[dict], list[str]]:
    found, missing = [], []
    for p in paths:
        if not Path(p).exists():
            missing.append(str(p))
            continue
        with open(p, encoding="utf-8-sig", newline="") as fh:
            for x in find_schedule_only(list(csv.DictReader(fh))):
                found.append({**x, "file": Path(p).name})
    return found, missing


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", action="append", default=[], help="a delivery CSV (repeatable); default the two published files")
    ap.add_argument("--markets-dir", default=str(MARKETS))
    a = ap.parse_args()
    paths = [Path(f) for f in a.file] or [Path(a.markets_dir) / f"{m}_audited.final.csv" for m in ("Cybersecurity", "Utility")]
    try:
        found, missing = scan(paths)
    except Exception as e:                                                  # a check must never stop the Saturday job
        print(f"SCHEDULE-ONLY STATUS: UNKNOWN - {type(e).__name__}: {e}")
        return 0
    for m in missing:
        print(f"SCHEDULE-ONLY STATUS DEGRADED: file not found ({m})")
    print(f"SCHEDULE-ONLY STATUS: {len(found)} row(s) say Open/Closed/Upcoming with no page behind them (should read Needs Verification)")
    for x in found:
        print(f"  {x['file']}: {x['name']} | {x['status']} -> {x['proposed_status']} | rests on \"{x['phrase']}\" | {x['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
