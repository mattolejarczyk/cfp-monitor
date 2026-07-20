"""Generate the customer-facing executive rollup as a single HTML file.

    python scripts/exec_report.py [--db cfp_monitor.db] [--out opportunities.html]
                                  [--new-days 7] [--title "..."]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cfp_monitor.exec_report import build_report   # noqa: E402
from src.cfp_monitor.storage import Store              # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the customer opportunity report (HTML).")
    ap.add_argument("--db", default=os.getenv("CFP_DB_PATH", "cfp_monitor.db"))
    ap.add_argument("--out", default="opportunities.html")
    ap.add_argument("--new-days", type=int, default=7)
    ap.add_argument("--title", default="Speaking &amp; Awards Opportunities")
    a = ap.parse_args()

    store = Store(a.db)
    html = build_report(store, title=a.title, new_since_days=a.new_days)
    store.close()
    Path(a.out).write_text(html, encoding="utf-8")
    print(f"Wrote {a.out} ({len(html):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
