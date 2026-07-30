"""Summarize verification outcomes across markets, and export the rows needing attention.

    python scripts/verify_report.py --db cfp_monitor.db [--csv out.csv]

Reads the states written by verify_grounding.py. Contradicted rows are the actionable ones:
those are claims our own evidence disagrees with, so the customer sheet should not carry
them unchallenged.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cfp_monitor.storage import Store          # noqa: E402

STATES = ("verified", "contradicted", "not_found", "unverified")


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize grounding verification outcomes.")
    ap.add_argument("--db", default="cfp_monitor.db")
    ap.add_argument("--seed-csv", default="market_sheets/grounding_seed.csv")
    ap.add_argument("--csv", help="write the contradicted rows to this file")
    a = ap.parse_args()

    market_of: dict[str, str] = {}
    seed = Path(a.seed_csv)
    if seed.exists():
        with open(seed, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                market_of.setdefault((row.get("EVENT_ID_CANON") or "").strip(),
                                     (row.get("Market") or "").strip())

    store = Store(a.db)
    rows = [dict(r) for r in store.db.execute("SELECT * FROM grounding_facts")]
    for r in rows:
        r["market"] = market_of.get(r["event_id"], "(unknown)")

    overall = Counter(r["verify_state"] for r in rows)
    print("=== overall ({} claims) ===".format(len(rows)))
    for s in STATES:
        if overall.get(s):
            print("  {:<14}{:>4}".format(s, overall[s]))

    print("\n=== by market ===")
    print("  {:<24}{:>7}{:>10}{:>14}{:>11}".format(
        "MARKET", "claims", "verified", "contradicted", "not_found"))
    markets = sorted({r["market"] for r in rows})
    for m in markets:
        grp = [r for r in rows if r["market"] == m]
        c = Counter(r["verify_state"] for r in grp)
        print("  {:<24}{:>7}{:>10}{:>14}{:>11}".format(
            m[:23], len(grp), c.get("verified", 0), c.get("contradicted", 0),
            c.get("not_found", 0)))

    bad = [r for r in rows if r["verify_state"] == "contradicted"]
    print("\n=== contradicted: our evidence disagrees ({}) ===".format(len(bad)))
    for r in sorted(bad, key=lambda r: (r["market"], r["name"] or ""))[:40]:
        print("  [{}] {:<38} {}".format(r["market"][:12], (r["name"] or "")[:38],
                                        (r["verify_detail"] or "")[:74]))

    if a.csv and bad:
        cols = ["market", "name", "url", "deadline", "submission_url", "verify_state",
                "verify_detail", "issues"]
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(bad)
        print("\nWrote {} ({} rows)".format(a.csv, len(bad)))

    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
