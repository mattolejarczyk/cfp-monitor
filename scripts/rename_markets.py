"""Migrate market names to the concise canonical set (aligned with the grounding sheet).

    python scripts/rename_markets.py --db cfp_monitor.db [--apply]

Without --apply this only reports. Market names appear in two places -- the `industries`
registry and the `conference_markets` junction -- and both must move together or membership
rows orphan themselves against a name the registry no longer knows.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cfp_monitor.markets import DEFAULT_MARKETS, MarketRegistry   # noqa: E402
from src.cfp_monitor.storage import Store                            # noqa: E402

# old canonical name -> new canonical name
RENAMES = {
    "Additive Manufacturing & 3D Printing": "Additive Mfg",
    "Bioeconomy & Biofuels": "Bioeconomy",
    "Biotech & MedTech": "BioMedTech",
    "Arnica": "Cybersecurity",
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Rename markets to the canonical concise set.")
    ap.add_argument("--db", default="cfp_monitor.db")
    ap.add_argument("--apply", action="store_true", help="write changes (default: report only)")
    a = ap.parse_args()

    store = Store(a.db)
    db = store.db
    print("Market membership before:")
    for m, n in db.execute("SELECT market, COUNT(*) FROM conference_markets"
                           " GROUP BY market ORDER BY market"):
        arrow = "  ->  {}".format(RENAMES[m]) if m in RENAMES else ""
        print("  {:<40}{:>4}{}".format(m, n, arrow))

    if not a.apply:
        print("\nDry run. Re-run with --apply to write.")
        store.close()
        return 0

    for old, new in RENAMES.items():
        # Membership is (conference_key, market) PRIMARY KEY: if a conference somehow already
        # holds the new name, the rename would collide, so drop the redundant old row instead.
        db.execute(
            "DELETE FROM conference_markets WHERE market=? AND conference_key IN"
            " (SELECT conference_key FROM conference_markets WHERE market=?)", (old, new))
        db.execute("UPDATE conference_markets SET market=? WHERE market=?", (new, old))
        db.execute("DELETE FROM industries WHERE name=?", (old,))
    # Re-seed the registry with the new canonical vocabulary.
    MarketRegistry(db, seed=DEFAULT_MARKETS)
    db.commit()

    print("\nMarket membership after:")
    for m, n in db.execute("SELECT market, COUNT(*) FROM conference_markets"
                           " GROUP BY market ORDER BY market"):
        print("  {:<40}{:>4}".format(m, n))
    orphans = [r[0] for r in db.execute(
        "SELECT DISTINCT market FROM conference_markets WHERE market NOT IN"
        " (SELECT name FROM industries)")]
    print("\nmembership names unknown to the registry: {} {}".format(
        len(orphans), orphans if orphans else "(none - consistent)"))
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
