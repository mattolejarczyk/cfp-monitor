"""Export the source-of-truth DB to the customer 15-column feed (CSV + JSON).

This is OUR end of the Brandable integration: Brandable (or any consumer) PULLS this
feed. We don't push to Brandable (no access/creds yet) — we produce the files it reads.
Filter by market tag so a per-market customer dashboard gets only its rows.

CLI:  python -m cfp_monitor.export --db cfp_monitor.db --out feed [--tag Cyber]
"""
from __future__ import annotations

import json
import os

from .customer_format import CUSTOMER_HEADERS, to_customer_rows, write_customer_csv
from .storage import Store


def _filter_by_tag(records: list[dict], tag: str | None) -> list[dict]:
    if not tag:
        return records
    t = tag.strip().lower()
    return [r for r in records if t in (r.get("categories") or "").lower()]


def export_rows(db_path: str, tag: str | None = None) -> list[dict]:
    """Internal export dicts from the DB, optionally filtered to one market tag."""
    store = Store(db_path)
    try:
        recs = store.export_dicts()
    finally:
        store.close()
    return _filter_by_tag(recs, tag)


def write_feed(db_path: str, out_dir: str, tag: str | None = None) -> dict:
    """Write customer.csv + feed.json (Brandable-pull format). Returns {csv, json, count}."""
    recs = export_rows(db_path, tag)
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "customer.csv")
    json_path = os.path.join(out_dir, "feed.json")
    write_customer_csv(recs, csv_path)
    rows = to_customer_rows(recs)
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump({"columns": CUSTOMER_HEADERS, "rows": rows}, fh, indent=2, ensure_ascii=False)
    return {"csv": csv_path, "json": json_path, "count": len(rows)}


def _cli():
    import argparse

    p = argparse.ArgumentParser(description="Export the source-of-truth DB to the customer feed")
    p.add_argument("--db", default="cfp_monitor.db")
    p.add_argument("--out", default="feed")
    p.add_argument("--tag", default=None, help="filter to one market tag, e.g. Cyber")
    a = p.parse_args()
    res = write_feed(a.db, a.out, a.tag)
    print(f"wrote {res['count']} rows -> {res['csv']} , {res['json']}")


if __name__ == "__main__":
    _cli()
