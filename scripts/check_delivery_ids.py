"""Do the ids in a delivery (full CSV or sparse patch) exist HERE, and is each event where upstream says it put it?

    python scripts/check_delivery_ids.py <delivery.csv> [--market Utility] [--strict]

WHY (2026-10-03). Three times in two days upstream reported an edit that was not on this machine: rows "added to Cybersecurity_input.csv" that
were not there, a script that does not exist here, and a sparse patch whose ids (for example 2026-carbon-capture-usa-houston-speaking)
exist in none of our files (ours is 2026-carbon-capture-usa-houston). Each time I found it by hand. A sparse patch cannot be applied on an id
we do not hold (contract 5.4: their id space is not ours to extend silently), so this is the FIRST thing to run on any delivery that arrives,
before the gate, and its answer goes in the reply to upstream.

ACT-16 (2026-10-05). Two additions. (1) For every UNKNOWN id the script now prints the closest id we DO hold (same year, most shared slug words,
at least half) with its city, name and status: the table note 27 needed by hand. It is a suggestion for the reply to upstream, never a rewrite
of their id (5.4). (2) A SPARSE PATCH (fewer columns than the 43/45 of a full delivery) with any unknown id now exits 1 without --strict: it
cannot be applied. accept_delivery.py runs this check first (check_delivery_ids -> Gate.check_ids).

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


ROLE_WORDS = {"speaking", "exhibiting", "sponsoring", "awards", "tbd", "attending"}
FULL_WIDTHS = {43, 45}


def slug_tokens(event_id: str) -> set[str]:
    """Words of an id slug without the year and the role suffix. Pure."""
    parts = [t for t in event_id.lower().split("-") if t]
    if parts and parts[0].isdigit() and len(parts[0]) == 4:
        parts = parts[1:]
    return {t for t in parts if t not in ROLE_WORDS}


def suggest(unknown_id: str, held: dict[str, dict], min_score: float = 0.5) -> dict | None:
    """The id we hold that most resembles an unknown one, or None. Same year, Jaccard of slug words, ties broken by id. Pure.

    A SUGGESTION for the operator's reply (what we hold, in which city); it never decides identity (5.4)."""
    year = unknown_id.split("-")[0]
    a = slug_tokens(unknown_id)
    best, best_score = None, 0.0
    for hid in sorted(held):
        if hid.split("-")[0] != year:
            continue
        b = slug_tokens(hid)
        if not a or not b:
            continue
        score = len(a & b) / len(a | b)
        if score > best_score:
            best, best_score = hid, score
    if best is None or best_score < min_score:
        return None
    return {"id": best, "score": round(best_score, 2), **held[best]}


def is_sparse(fieldnames: list[str] | None) -> bool:
    """A patch that carries fewer columns than a full delivery (43 or 45). Pure."""
    return len(fieldnames or []) not in FULL_WIDTHS


def analyse(rows: list[dict], market: str, db: str, markets_dir: str) -> dict:
    """Locate every id of a delivery; attach a suggestion to each unknown one. Reads only."""
    from src.cfp_monitor.identity import seed_map
    ids = [(r.get("EVENT_ID") or "").strip() for r in rows if (r.get("EVENT_ID") or "").strip()]
    up_to_canon, _ = seed_map(db)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    held: dict[str, dict] = {}
    for table in ("grounding_facts", "award_grounding_facts"):
        try:
            for eid, name, city, status in con.execute(f"select event_id, name, city, status from {table}"):
                held[eid] = {"name": name or "", "city": city or "", "status": status or "", "table": table}
        except sqlite3.OperationalError:
            pass
    con.close()
    m = Path(markets_dir)
    sources = {"database": set(held),
               "this week's research": read_ids(m / f"{market}_audited.csv", "EVENT_ID"),
               "approved file": read_ids(m / f"{market}_audited.final.csv", "EVENT_ID"),
               "input list": read_ids(m / f"{market}_input.csv", "EVENT_ID_CANON")}
    res = locate(ids, sources, up_to_canon)
    for r in res:
        r["suggestion"] = suggest(r["id"], held) if r["unknown"] else None
    return {"results": res, "sources": list(sources)}


def format_table(res: list[dict]) -> str:
    """The note-27 table: their id -> the id we hold, with its city, for every unknown id. Pure."""
    lines = []
    for r in res:
        if not r["unknown"]:
            continue
        s = r.get("suggestion")
        if s:
            lines.append(f"   - {r['id']} -> {s['id']}   ({s['city'] or 'no city'}; {s['name'][:50]}; {s['status'] or 'no status'}; match {s['score']})")
        else:
            lines.append(f"   - {r['id']} -> no id we hold resembles it (new event? say so and send the page)")
    return chr(10).join(lines)


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
        rd = csv.DictReader(fh)
        rows = list(rd)
        sparse = is_sparse(rd.fieldnames)
    market = a.market or next((r.get("Market") for r in rows if r.get("Market")), "")
    market = {"cybersecurity": "Cybersecurity", "arnica": "Cybersecurity", "utility": "Utility", "utility global": "Utility"}.get((market or "").lower(), market)
    if market not in ("Cybersecurity", "Utility"):
        print(f"cannot tell the market ({market!r}); pass --market Cybersecurity|Utility", file=sys.stderr)
        return 2
    out = analyse(rows, market, a.db, a.markets_dir)
    res, names = out["results"], out["sources"]
    print(f"{len(res)} id(s) in {Path(a.csv_path).name}, market {market}" + ("  [SPARSE PATCH]" if sparse else "") + chr(10))
    print(f"{'id':72s} " + " ".join(f"{n[:9]:9s}" for n in names))
    for r in res:
        print(f"{r['id'][:72]:72s} " + " ".join(f"{'yes' if r['found'][n] else 'NO':9s}" for n in names) + ("   <- UNKNOWN HERE" if r["unknown"] else "   <- not queued for research" if r["not_queued"] else ""))
    unk = [r["id"] for r in res if r["unknown"]]
    nq = [r["id"] for r in res if r["not_queued"]]
    print(f"{chr(10)}unknown here: {len(unk)} of {len(res)}   |   in the database but not on the input list: {len(nq)}")
    if unk:
        print(chr(10) + "Your id -> the id we hold (closest by slug words; a suggestion for the reply, never a rewrite of their id):")
        print(format_table(res))
        print("A sparse patch cannot apply on an unknown id (contract 5.4). Tell upstream which ids we hold; do not rewrite theirs to match.")
    refuse = bool(unk) and (a.strict or sparse)
    if refuse and sparse and not a.strict:
        print("REFUSED: a sparse patch keyed on ids we do not hold cannot be applied (exit 1).")
    return 1 if refuse else 0


if __name__ == "__main__":
    raise SystemExit(main())
