"""Apply confirmed one-off record corrections (URL retarget + duplicate merge).

    python scripts/fix_records.py --db cfp_monitor.db [--apply]

A conference's identity key is derived from its URL, so retargeting a URL has to move the
key and every reference to it together, or the row detaches from its market membership and
the next crawl creates a second copy instead of updating the first.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cfp_monitor.storage import Store, normalize_key    # noqa: E402

# Point a record at the canonical event URL instead of a third-party/tracking one.
RETARGET = {
    # our key                                              -> canonical url
    "blackhat.informafestivals.com/asia/2026": "https://www.blackhat.com/asia-26/",
}
# Same event held twice under different URLs: keep the canonical one, drop the other.
# The ticketing page reports "open" because TICKETS are on sale, which is not the call for
# papers -- and it carries no deadline and no edition, while the official site carries both.
MERGE = {
    # loser key                                    -> winner key
    "events.humanitix.com/bsideslv-2026/tickets": "bsideslv.org",
}
# Human-owned columns: if the row being dropped holds any, move them to the survivor.
HUMAN_COLS = ("submission_status", "notes", "priority", "coordinator_email")


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply confirmed record corrections.")
    ap.add_argument("--db", default="cfp_monitor.db")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    store = Store(a.db)
    db = store.db
    db.row_factory = __import__("sqlite3").Row

    print("=== retarget to canonical URL ===")
    for prefix, new_url in RETARGET.items():
        rows = [r for r in db.execute("SELECT * FROM conferences WHERE key LIKE ?", (prefix + "%",))]
        for r in rows:
            new_key = normalize_key(new_url)
            clash = db.execute("SELECT 1 FROM conferences WHERE key=? AND key<>?",
                               (new_key, r["key"])).fetchone()
            print("  {!r}\n     -> {!r}  {}".format(
                r["key"][:60], new_key, "COLLIDES - skipped" if clash else "ok"))
            if a.apply and not clash:
                db.execute("UPDATE conference_markets SET conference_key=? WHERE conference_key=?",
                           (new_key, r["key"]))
                db.execute("UPDATE grounding_facts SET conference_key=? WHERE conference_key=?",
                           (new_key, r["key"]))
                db.execute("UPDATE conferences SET key=?, url=? WHERE key=?",
                           (new_key, new_url, r["key"]))

    print("\n=== merge duplicates ===")
    for loser, winner in MERGE.items():
        lrow = db.execute("SELECT * FROM conferences WHERE key=?", (loser,)).fetchone()
        wrow = db.execute("SELECT * FROM conferences WHERE key=?", (winner,)).fetchone()
        if not lrow or not wrow:
            print("  skip {!r} -> {!r} (one side missing)".format(loser[:40], winner))
            continue
        print("  drop  {!r}  name={!r} status={}".format(
            loser[:46], (lrow["name"] or "")[:34], lrow["cfp_status"]))
        print("  keep  {!r}  name={!r} status={}".format(
            winner[:46], (wrow["name"] or "")[:34], wrow["cfp_status"]))
        carried = {c: lrow[c] for c in HUMAN_COLS if lrow[c] and not wrow[c]}
        print("  human-entered values carried over:", carried or "none")
        if a.apply:
            for col, val in carried.items():
                db.execute("UPDATE conferences SET {}=? WHERE key=?".format(col), (val, winner))
            # Move market memberships the loser had that the winner lacks, then delete it.
            db.execute("INSERT OR IGNORE INTO conference_markets"
                       " (conference_key, market, source_list, first_seen)"
                       " SELECT ?, market, source_list, first_seen FROM conference_markets"
                       " WHERE conference_key=?", (winner, loser))
            db.execute("DELETE FROM conference_markets WHERE conference_key=?", (loser,))
            db.execute("UPDATE grounding_facts SET conference_key=? WHERE conference_key=?",
                       (winner, loser))
            db.execute("DELETE FROM conferences WHERE key=?", (loser,))

    if a.apply:
        db.commit()
        print("\nAPPLIED.")
    else:
        print("\nDry run. Re-run with --apply to write.")
    print("conferences now: {}".format(
        db.execute("SELECT COUNT(*) FROM conferences").fetchone()[0]))
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
