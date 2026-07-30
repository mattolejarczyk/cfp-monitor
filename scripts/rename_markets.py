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
        # The legacy single-value `conferences.industry` column MUST move too. Store._migrate()
        # backfills membership from it on every DB open, so leaving stale names there
        # resurrects the old markets the moment anything reopens the database.
        db.execute("UPDATE conferences SET industry=? WHERE industry=?", (new, old))
    # Sweep up any membership row whose name the registry no longer recognizes -- e.g. rows
    # already resurrected from the legacy column by an earlier reopen. Resolve through the
    # alias table so they land on the right canonical market instead of being dropped.
    MarketRegistry(db, seed=DEFAULT_MARKETS)
    registry = MarketRegistry(db)
    orphaned = [r[0] for r in db.execute(
        "SELECT DISTINCT market FROM conference_markets WHERE market NOT IN"
        " (SELECT name FROM industries)")]
    for name in orphaned:
        target = registry.resolve(name)
        if target:
            db.execute(
                "DELETE FROM conference_markets WHERE market=? AND conference_key IN"
                " (SELECT conference_key FROM conference_markets WHERE market=?)",
                (name, target))
            db.execute("UPDATE conference_markets SET market=? WHERE market=?", (target, name))
            db.execute("UPDATE conferences SET industry=? WHERE industry=?", (target, name))
            print("  swept orphaned membership {!r} -> {!r}".format(name, target))
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
