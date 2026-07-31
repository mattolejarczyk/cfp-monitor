"""Resolve grounding claims to verified / contradicted / not_found, cheapest layer first.

    python scripts/verify_grounding.py --db cfp_monitor.db [--market Cybersecurity]
                                       [--layers 01] [--limit N] [--apply]

--layers picks which layers run: 0 = cross-check our own crawl history (free),
1 = HTTP link check (fast), 2 = fresh crawl (slow, needs the browser + LLM).
Default '01' is the free/fast pass. Reports unless --apply is given.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cfp_monitor.storage import Store                      # noqa: E402
from src.cfp_monitor.verify import Outcome                     # noqa: E402
from src.cfp_monitor.verify import (                            # noqa: E402
    CONTRADICTED, NOT_FOUND, VERIFIED, check_link, cross_check, cross_check_status,
    fetch_text, l2_detail, no_page_detail, verify_against_page,
)


def market_event_ids(seed_csv: Path, market: str) -> set[str]:
    """Grounding's market lives in the seed CSV, not the facts table."""
    ids = set()
    if not seed_csv.exists():
        return ids
    with open(seed_csv, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if (row.get("Market") or "").strip().lower() == market.strip().lower():
                ids.add((row.get("EVENT_ID_CANON") or "").strip())
    return ids


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify grounding claims against evidence.")
    ap.add_argument("--db", default="cfp_monitor.db")
    ap.add_argument("--market", help="restrict to one market (via the seed CSV)")
    ap.add_argument("--seed-csv", default="market_sheets/grounding_seed.csv")
    ap.add_argument("--layers", default="01", help="which layers to run, e.g. 0, 01, 012")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--apply", action="store_true", help="write results back to the DB")
    a = ap.parse_args()

    today = date.today()
    store = Store(a.db)
    crawled = {r["key"]: r for r in store.all_records()}

    rows = [dict(r) for r in store.db.execute(
        "SELECT * FROM grounding_facts ORDER BY name")]
    if a.market:
        ids = market_event_ids(Path(a.seed_csv), a.market)
        rows = [r for r in rows if r["event_id"] in ids]
        print("Market {!r}: {} grounding claim(s)".format(a.market, len(rows)))
    if a.limit:
        rows = rows[:a.limit]

    results = {VERIFIED: [], CONTRADICTED: [], NOT_FOUND: [], "unresolved": []}
    layer_used = {}

    for r in rows:
        outcome = None
        if "0" in a.layers and r["conference_key"] in crawled:
            # STATUS first: whether the call is open settles more than the exact date does.
            outcome = cross_check_status(r["status"], crawled[r["conference_key"]],
                                         today, edition=r["edition"] or "")
            if outcome is None:
                outcome = cross_check(r["deadline"], r["status"],
                                      crawled[r["conference_key"]], today,
                                      edition=r["edition"] or "")
        if outcome is None and "1" in a.layers:
            outcome = check_link(r["submission_url"])
        if outcome is None and "2" in a.layers:
            # Prefer the page grounding cited for the deadline; fall back to the submit page.
            cited = (r["deadline_evidence_url"] or "").strip()
            for candidate in (cited, r["submission_url"], r["url"]):
                candidate = (candidate or "").strip()
                if not candidate:
                    continue
                text, note = fetch_text(candidate)
                if text:
                    outcome = verify_against_page(text, r["deadline"], r["status"])
                    outcome.detail = l2_detail(outcome, candidate, cited)
                    break
            else:
                outcome = Outcome(NOT_FOUND, no_page_detail(cited), "L2")
        if outcome is None:
            results["unresolved"].append((r, None))
            continue
        results[outcome.state].append((r, outcome))
        layer_used[outcome.layer] = layer_used.get(outcome.layer, 0) + 1
        if a.apply:
            store.db.execute(
                "UPDATE grounding_facts SET verify_state=?, verify_detail=? WHERE event_id=?",
                (outcome.state, "[{}] {}".format(outcome.layer, outcome.detail), r["event_id"]))
    if a.apply:
        store.db.commit()

    print("\n=== resolution (layers {}) ===".format(a.layers))
    for state in (VERIFIED, CONTRADICTED, NOT_FOUND, "unresolved"):
        print("  {:<14}{:>4}".format(state, len(results[state])))
    print("  resolved by layer:", layer_used or "-")

    for state, cap in ((CONTRADICTED, 14), (VERIFIED, 6)):
        if results[state]:
            print("\n--- {} ---".format(state.upper()))
            for r, o in results[state][:cap]:
                print("  {:<40} {}".format((r["name"] or "")[:38], o.detail[:78]))

    if results["unresolved"]:
        print("\n--- unresolved: need layer 2 (fresh crawl) ---  {} row(s)".format(
            len(results["unresolved"])))
        for r, _ in results["unresolved"][:8]:
            print("  {:<40} dl={}".format((r["name"] or "")[:38], (r["deadline"] or "-")[:12]))

    print("\n{}".format("WROTE results to the DB." if a.apply else "Report only. Use --apply to write."))
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
