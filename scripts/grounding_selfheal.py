"""Self-heal Phase 1 (REPORT-ONLY): confirm not_found deadlines against their cited pages.

Verification-first: only rows that already carry a deadline AND a cited URL, so this spends no
grounded requests. It writes NOTHING to the database - it shows what it would confirm, and every
result is labelled with the method that produced it. Applying is a later, separately-verified
phase; there is deliberately no --apply here yet.

    python scripts/grounding_selfheal.py --db <live.db> [--max-rows 3] [--delay 8]

Budget: --max-rows starts small (default 3) and grows with proof. --delay spaces each check
sequentially and human-paced, so we never hammer a site (matters more once the grounded
fallback exists). See docs/design/self-heal-verification-proposal.md.
"""
import argparse
import json
import random
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.cfp_monitor.self_heal import (                                 # noqa: E402
    BrowserLadderVerifier, DateContextVerifier, render, resolve_rows,
    select_unconfirmed, to_records)


def human_pace(delay: float):
    """A random gap around `delay` seconds, one request at a time - as a person would."""
    def _wait():
        if delay > 0:
            time.sleep(delay * (0.6 + 0.8 * random.random()))
    return _wait


def main() -> int:
    ap = argparse.ArgumentParser(description="Self-heal Phase 1 - report-only deadline confirmation.")
    ap.add_argument("--db", required=True)
    ap.add_argument("--max-rows", type=int, default=3,
                    help="budget: rows to check this run (small first, grow with proof)")
    ap.add_argument("--delay", type=float, default=8.0,
                    help="seconds between checks, human-paced and sequential")
    ap.add_argument("--no-browser", action="store_true",
                    help="plain fetch only; skip the real-Chrome escalation (free but slower)")
    ap.add_argument("--trail", help="write the machine trail (jsonl) here")
    a = ap.parse_args()

    con = sqlite3.connect(a.db)
    rows = select_unconfirmed(con, a.max_rows)
    if not rows:
        print("SELF-HEAL: nothing to do - no not_found row carries both a deadline and a cited URL.")
        return 0
    print(f"SELF-HEAL: checking {len(rows)} of the not_found+cited rows "
          f"(budget --max-rows {a.max_rows}), one at a time...\n")
    verifiers = [DateContextVerifier()]
    if not a.no_browser:
        verifiers.append(BrowserLadderVerifier())    # free escalation for JS/403 pages
    outcomes = resolve_rows(con, rows, verifiers, pace=human_pace(a.delay))
    print(render(outcomes))

    trail = Path(a.trail) if a.trail else Path(a.db).with_name("self_heal.jsonl")
    with open(trail, "w", encoding="utf-8") as fh:
        for rec in to_records(outcomes):
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"\ntrail -> {trail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
