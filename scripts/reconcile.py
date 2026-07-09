"""Annotate a customer master .xlsx against our source-of-truth DB.

  python scripts/reconcile.py "Utility Global Conference List 2026.xlsx"
  python scripts/reconcile.py <sheet.xlsx> --db cfp_monitor.db -o reconciled.xlsx

Writes a copy of the sheet with our differences highlighted + commented, and a Reconciliation
summary tab. Prints the category counts.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cfp_monitor.reconcile_xlsx import annotate_from_db


def main() -> int:
    ap = argparse.ArgumentParser(description="Reconcile a customer sheet against our crawl DB")
    ap.add_argument("sheet", help="path to the customer master .xlsx")
    ap.add_argument("--db", default="cfp_monitor.db")
    ap.add_argument("-o", "--output", help="output path (default: <sheet>.reconciled.xlsx)")
    a = ap.parse_args()

    out = a.output or (os.path.splitext(a.sheet)[0] + ".reconciled.xlsx")
    counts = annotate_from_db(a.sheet, out, a.db)
    print(f"Wrote {out}")
    print("Summary:", {k: v for k, v in counts.items() if v})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
