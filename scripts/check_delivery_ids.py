"""Do the ids in a delivery (full CSV or sparse patch) exist HERE, and is each event where upstream says it put it?

    python scripts/check_delivery_ids.py <delivery.csv> [--market Utility] [--strict]

WHY (2026-10-03). Three times in two days upstream reported an edit that was not on this machine: rows "added to Cybersecurity_input.csv" that
were not there, a script that does not exist here, and a sparse patch whose ids (for example 2026-carbon-capture-usa-houston-speaking)
exist in none of our files (ours is 2026-carbon-capture-usa-houston). Each time I found it by hand. A sparse patch cannot be applied on an id
we do not hold (contract 5.4: their id space is not ours to extend silently), so this is the FIRST thing to run on any delivery that arrives,
before the gate, and its answer goes in the reply to upstream.

For every EVENT_ID (as sent, and translated through the seed map) it says whether the id is in: the database, this week's research output,
the approved file, and the research input list. A row whose id is in none of them is UNKNOWN; a row in the database but not on the input
list is NOT QUEUED for Saturday's research. Exit 1 with --strict when any id is unknown. Reads only."""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LIVE = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor")
MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")


def locate(ids: list[str], sources: dict[str, set[str]], to_canon: dict[str, str]) -> list[dict]:
    """For each id, which sources hold it (as sent, or through the seed map). Pure."""
    out = []
    for i in ids:
        c = to_canon.get(i, i)
        found = {name: (i in held or c in held) for name, held in sources.items()}
        out.append({"id": i, "canonical": c, "found": found, "unknown": not any(found.values()),
                    "not_queued": found.get("database", False) and not found.get("input list", False)})
    return out


def read_ids(path: Path, col: str) -> set[str]:
    if not path.exists():
        return set()
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return {(r.get(col) or "").strip() for r in csv.DictReader(fh)} - {""}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("csv_path")
    ap.add_argument("--market", help="Cybersecurity or Utility (default: the Market column of the delivery)")
    ap.add_argument("--db", default=str(LIVE / "cfp_monitor.db"))
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    with open(a.csv_path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    ids = [(r.get("EVENT_ID") or "").strip() for r in rows if (r.get("EVENT_ID") or "").strip()]
    market = a.market or next((r.get("Market") for r in rows if r.get("Market")), "")
    market = {"cybersecurity": "Cybersecurity", "arnica": "Cybersecurity", "utility": "Utility", "utility global": "Utility"}.get((market or "").lower(), market)
    if market not in ("Cybersecurity", "Utility"):
        print(f"cannot tell the market ({market!r}); pass --market Cybersecurity|Utility", file=sys.stderr)
        return 2
    from src.cfp_monitor.identity import seed_map
    up_to_canon, _ = seed_map(a.db)
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    db_ids = {r[0] for r in con.execute("select event_id from grounding_facts")}
    con.close()
    m = Path(a.markets_dir)
    sources = {"database": db_ids,
               "this week's research": read_ids(m / f"{market}_audited.csv", "EVENT_ID"),
               "approved file": read_ids(m / f"{market}_audited.final.csv", "EVENT_ID"),
               "input list": read_ids(m / f"{market}_input.csv", "EVENT_ID_CANON")}
    res = locate(ids, sources, up_to_canon)
    names = list(sources)
    print(f"{len(ids)} id(s) in {Path(a.csv_path).name}, market {market}\n")
    print(f"{'id':72s} " + " ".join(f"{n[:9]:9s}" for n in names))
    for r in res:
        print(f"{r['id'][:72]:72s} " + " ".join(f"{'yes' if r['found'][n] else 'NO':9s}" for n in names) + ("   <- UNKNOWN HERE" if r["unknown"] else "   <- not queued for research" if r["not_queued"] else ""))
    unk = [r["id"] for r in res if r["unknown"]]
    nq = [r["id"] for r in res if r["not_queued"]]
    print(f"\nunknown here: {len(unk)} of {len(res)}   |   in the database but not on the input list: {len(nq)}")
    if unk:
        print("A sparse patch cannot apply on an unknown id (contract 5.4). Tell upstream which ids we hold; do not rewrite theirs to match.")
    return 1 if (a.strict and unk) else 0


if __name__ == "__main__":
    raise SystemExit(main())
