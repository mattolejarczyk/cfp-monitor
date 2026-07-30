"""Normalize a grounding master list (v4) into a clean, auditable seed CSV.

    python scripts/import_grounding.py <master_v4.csv> [--out clean.csv] [--issues-only]

Writes every original column verbatim (nothing is destroyed) plus our derived columns:
    EVENT_ID_CANON   recomputed key (year-name-city, market excluded)
    CITY_CLEAN       venue-vs-city repair
    CFP_MODEL_CANON  controlled enum
    GATED_STATUS_CALC past-date gate, computed at run time
    ISSUES_CALC      deterministic contradictions found without crawling
    VERIFY_STATE     seed state for the verification pass (always 'unverified' here)
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cfp_monitor.grounding import (                              # noqa: E402
    gated_status, load_master_csv, seed_store,
)
from src.cfp_monitor.storage import Store                            # noqa: E402

DERIVED = ["EVENT_ID_CANON", "CITY_CLEAN", "CFP_MODEL_CANON",
           "GATED_STATUS_CALC", "ISSUES_CALC", "VERIFY_STATE"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize a grounding master list into a seed CSV.")
    ap.add_argument("csv_path")
    ap.add_argument("--out", default="grounding_seed.csv")
    ap.add_argument("--issues-only", action="store_true", help="write only rows with an issue")
    ap.add_argument("--seed", metavar="DB", help="also seed the discovery table in this DB")
    a = ap.parse_args()

    today = date.today()
    rows, rep = load_master_csv(a.csv_path, today)

    print("Normalized {} row(s) from {}".format(rep["input"], Path(a.csv_path).name))
    print("  kept                 {}".format(rep["kept"]))
    print("  exact duplicates     {}".format(rep["duplicates"]))
    print("  distinct events      {}".format(rep["distinct_events"]))
    print("  CITY repaired        {}  (venue -> real city)".format(rep["city_repaired"]))
    print("  CFP model normalized {}".format(rep["model_normalized"]))
    print("  markets              {}".format(", ".join(rep["markets"])))
    print("\n  Deterministic issues (found WITHOUT crawling):")
    for label, n in sorted(rep["issue_counts"].items(), key=lambda kv: -kv[1]):
        print("    {:>4}  {}".format(n, label))

    out_rows = [r for r in rows if r.issues] if a.issues_only else rows
    src_cols = list(rows[0].raw.keys()) if rows else []
    fields = src_cols + [c for c in DERIVED if c not in src_cols]
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in out_rows:
            rec = dict(r.raw)
            rec.update({
                "EVENT_ID_CANON": r.event_id,
                "CITY_CLEAN": r.city,
                "CFP_MODEL_CANON": r.cfp_model,
                "GATED_STATUS_CALC": gated_status(r, today),
                "ISSUES_CALC": "; ".join(r.issues),
                "VERIFY_STATE": "unverified",
            })
            w.writerow(rec)
    print("\nWrote {} ({} rows, {} columns)".format(a.out, len(out_rows), len(fields)))

    if a.seed:
        store = Store(a.seed)
        s = seed_store(store, rows)
        total_g = store.db.execute("SELECT COUNT(*) FROM grounding_facts").fetchone()[0]
        joined = store.db.execute(
            "SELECT COUNT(*) FROM conferences WHERE event_id IS NOT NULL AND event_id<>''"
        ).fetchone()[0]
        store.close()
        print("\nSeeded discovery layer in {}".format(a.seed))
        print("  inserted {} | updated {}".format(s["inserted"], s["updated"]))
        print("  already in our verified DB   {}".format(s["matched_existing"]))
        print("  NEW to us (grounding only)   {}".format(s["new_to_us"]))
        print("  market memberships added     {}".format(s["markets_added"]))
        print("  grounding_facts rows total   {}".format(total_g))
        print("  verified records now joined  {}".format(joined))
        if s["unmapped_markets"]:
            print("\n  UNMAPPED market labels (no membership recorded - needs a decision):")
            for label, n in sorted(s["unmapped_markets"].items(), key=lambda kv: -kv[1]):
                print("    {:>4}  {!r}".format(n, label))
            print("    Map each in markets.ALIASES, or register it:")
            print('      python scripts/run_batch.py markets --add "<Name>"')
        print("\n  Verified crawl data untouched: grounding lives in its own table.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
