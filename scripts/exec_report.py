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

import csv                                            # noqa: E402
import re                                             # noqa: E402

from src.cfp_monitor.customer_format import (                    # noqa: E402
    CUSTOMER_HEADERS, to_customer_row, write_customer_csv,
)
from src.cfp_monitor.exec_report import build_report             # noqa: E402
from src.cfp_monitor.storage import Store                        # noqa: E402


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9&+ -]", "", name).strip() or "market"


def write_market_sheets(store: Store, out_dir: Path) -> list[tuple[str, int]]:
    """One customer-format CSV per market, plus a combined sheet.

    An event on several market lists appears in each of those markets' sheets -- that is the
    point of many-to-many membership: every client's sheet is complete on its own."""
    out_dir.mkdir(parents=True, exist_ok=True)
    exports = store.export_dicts()
    by_key = {e["key"]: e for e in exports}
    markets: dict[str, list[dict]] = {}
    for row in store.db.execute(
            "SELECT market, conference_key FROM conference_markets ORDER BY market"):
        rec = by_key.get(row[1])
        if rec:
            markets.setdefault(row[0], []).append(rec)
    written = []
    for market, recs in sorted(markets.items()):
        path = out_dir / f"{_safe(market)}.csv"
        written.append((path.name, write_customer_csv(recs, str(path))))
    # Combined sheet: one row per event-MARKET pair, grouped by market. An event on several
    # market lists therefore appears once under each of them -- that is what makes the sheet
    # sortable/filterable by market, and it mirrors the per-market sheets exactly.
    status_rank = {"open": 0, "upcoming": 1, "unclear": 2, "none": 3, "closed": 4}
    combined = []
    for market, recs in sorted(markets.items()):
        for rec in sorted(recs, key=lambda r: (status_rank.get((r.get("status") or "").lower(), 9),
                                               (r.get("name") or "").lower())):
            combined.append({"MARKET": market, **to_customer_row(rec)})
    # Events not on any market list still belong in the combined view.
    assigned = {r["key"] for recs in markets.values() for r in recs}
    for rec in exports:
        if rec["key"] not in assigned:
            combined.append({"MARKET": "(unassigned)", **to_customer_row(rec)})

    all_path = out_dir / "All markets.csv"
    with open(all_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["MARKET"] + CUSTOMER_HEADERS)
        w.writeheader()
        w.writerows(combined)
    written.append((all_path.name, len(combined)))
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the customer opportunity report (HTML).")
    ap.add_argument("--db", default=os.getenv("CFP_DB_PATH", "cfp_monitor.db"))
    ap.add_argument("--out", default="opportunities.html")
    ap.add_argument("--new-days", type=int, default=7)
    ap.add_argument("--title", default="Speaking &amp; Awards Opportunities")
    ap.add_argument("--sheets-dir", help="also write one customer CSV per market into this folder")
    ap.add_argument("--sheets-note", default="",
                    help="text shown on the report for where the sheets live")
    ap.add_argument("--sheets-url", default="",
                    help="optional link for the sheets (a shared folder, Drive, etc.)")
    ap.add_argument("--detail", action="store_true",
                    help="include the new-this-run list and per-market event tables "
                         "(default is the executive summary only)")
    a = ap.parse_args()

    store = Store(a.db)
    note = a.sheets_note
    if a.sheets_dir:
        written = write_market_sheets(store, Path(a.sheets_dir))
        for name, n in written:
            print(f"  {name:<42}{n:>5} rows")
        # Never bake the operator's real filesystem path into a customer-facing page.
        note = note or "Saved to your computer: <path-on-your-local-computer>"
    html = build_report(store, title=a.title, new_since_days=a.new_days, detail=a.detail,
                        sheets_note=note, sheets_url=a.sheets_url)
    store.close()
    Path(a.out).write_text(html, encoding="utf-8")
    print(f"Wrote {a.out} ({len(html):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
