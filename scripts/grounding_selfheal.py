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
    BrowserLadderVerifier, DateContextVerifier, GroundedVerifier, apply_confirmations,
    discover_flagged, render, resolve_rows, select_unconfirmed, to_records)

DEFAULT_HELPER = r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets\grounded_ask.py"


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
    ap.add_argument("--grounded", action="store_true",
                    help="LAST resort: ground the FLAGGED residue (spends quota). Off by default.")
    ap.add_argument("--max-grounded", type=int, default=3,
                    help="budget: grounded requests to spend (small first, grow with proof)")
    ap.add_argument("--grounded-spike-guard", type=int, default=15,
                    help="refuse the grounded step if more rows are flagged than this - a spike "
                         "means an upstream break, not a discovery need")
    ap.add_argument("--grounded-python", default="py",
                    help="interpreter with google-genai for the upstream grounded_ask helper")
    ap.add_argument("--grounded-helper", default=DEFAULT_HELPER)
    ap.add_argument("--apply", action="store_true",
                    help="WRITE the proven confirmations (verify_state -> verified + quote); backs "
                         "up the DB first and logs every change. Default is report-only.")
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

    if a.grounded:
        gv = GroundedVerifier(a.grounded_helper, python=a.grounded_python)
        outcomes, note = discover_flagged(outcomes, gv, a.max_grounded,
                                           a.grounded_spike_guard, pace=human_pace(max(a.delay, 8)))
        print(f"[grounded] {note}\n")

    print(render(outcomes))

    if a.apply:
        log, backup = apply_confirmations(con, outcomes, db_path=a.db)
        print(f"\nAPPLIED {len(log)} confirmation(s) to the database"
              + (f" (backup: {Path(backup).name})" if backup else ""))
        for e in log:
            print(f"  {e['name'][:46]}: {e['before']['verify_state']} -> verified "
                  f"[{e['method']}]  {e['after']['url']}")
    else:
        n = sum(1 for o in outcomes if o.action == "confirm")
        if n:
            print(f"\n(report-only: {n} confirmation(s) NOT written - pass --apply to write them)")

    trail = Path(a.trail) if a.trail else Path(a.db).with_name("self_heal.jsonl")
    with open(trail, "w", encoding="utf-8") as fh:
        for rec in to_records(outcomes):
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"\ntrail -> {trail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
