"""Gap 4a experiment: if Saturday had followed the existing decision tree, what would it have
skipped, what would that have saved, and what would have been lost?

READ-ONLY. No AI, no database writes. Measures the 2026-09-27 research (the Saturday run re-run
that day) against the rule in docs/operations/DECISION-TREE.md, applied through
src/cfp_monitor/lifecycle.py - the existing rule, not a new one.

The skip rule under test: do not research a row whose edition the tree says costs nothing -
    Discontinued   the series has ended (quoted)
    Archived       a later edition exists
    Watching       the event ran < 60 days ago (do not hunt the successor yet)
Everything else is researched exactly as today. Assessed on LAST WEEK'S approved file (what was
known going into Saturday), as of the Saturday the run should have happened.

    python experiments/gap4_stubs/gap4a_measure.py
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.cfp_monitor import lifecycle                                   # noqa: E402
from src.cfp_monitor.identity import seed_map, to_canonical            # noqa: E402

MARKETS_DIR = Path(os.environ.get("CFP_MARKETS_DIR", "."))   # upstream Markets working folder: set CFP_MARKETS_DIR (kept out of this public repo)
LIVE_DB = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor\cfp_monitor.db")
RUN_DAY = date(2026, 9, 26)          # the Saturday the research belongs to
LAST_WEEK = {"Cybersecurity": "Cybersecurity_audited.final.pre-promote-20260927-221106.csv",
             "Utility": "Utility_audited.final.pre-promote-20260927-221107.csv"}
OUT = Path(__file__).resolve().parent


def read(p: Path) -> list[dict]:
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    up, _ = seed_map(str(LIVE_DB))
    report = {"run_day": RUN_DAY.isoformat(), "markets": {}}
    skipped_names: list[str] = []
    lines = []
    for m, lw_name in LAST_WEEK.items():
        last = read(MARKETS_DIR / lw_name)
        assess = lifecycle.assess_all(last, RUN_DAY)
        by_canon = {to_canonical(r["EVENT_ID"], up): (r, assess[r["EVENT_ID"]]) for r in last}

        inputs = read(MARKETS_DIR / f"{m}_input.csv")
        out_rows = read(MARKETS_DIR / f"{m}_audited.csv")
        ledger = [l.strip() for l in (MARKETS_DIR / f"{m}_audited.progress.txt")
                  .read_text(encoding="utf-8").splitlines() if l.strip()]
        out_by_input = dict(zip(ledger, out_rows)) if len(ledger) == len(out_rows) else {}
        attempts = Counter()
        for line in open(MARKETS_DIR / f"{m}_audited.grounding.jsonl", encoding="utf-8"):
            e = json.loads(line)
            if e.get("pass") == "research" and e["kind"] == "attempt":
                attempts[e["row"]] += 1

        stats = Counter()
        for r in inputs:
            name, canon = r["CONFERENCE"].strip(), (r.get("EVENT_ID_CANON") or "").strip()
            hit = by_canon.get(canon)
            if not hit:
                stats["no last-week row to assess (researched as today)"] += 1
                continue
            lw, a = hit
            skip = a.edition_state in ("Discontinued", "Archived") or \
                   (a.edition_state == "Watching" and a.cost == "free")
            if not skip:
                stats["researched (tree says quota or active)"] += 1
                continue
            stats["SKIPPED by the tree"] += 1
            stats["requests saved"] += attempts.get(name, 0)
            o = out_by_input.get(name, {})
            stub = "Audit Exception" in (o.get("STATUS DETAILS") or "")
            stats["of which were failed (stub) rows"] += stub
            # did this weekend's research learn anything the page would show?
            changed = [f for f in ("SUBMISSION DEADLINE", "CONFERENCE DATES", "START DATE",
                                   "EDITION", "STATUS")
                       if not stub and (o.get(f) or "").strip() != (lw.get(f) or "").strip()]
            if changed:
                stats["of which research CHANGED a shown field"] += 1
            skipped_names.append(name)
            lines.append(f"{m[:5]} | {a.edition_state:<12} | {'STUB' if stub else 'ok  '} | "
                         f"requests {attempts.get(name, 0)} | changed: {', '.join(changed) or '-'}"
                         f" | {name[:60]}")
            for f in changed:
                lines.append(f"        {f}: {lw.get(f, '')!r} -> {o.get(f, '')!r}")
        report["markets"][m] = dict(stats)

    # Customer check: is anyone at the customer working on a row the rule would skip?
    cc = subprocess.run([sys.executable, str(ROOT / "scripts" / "customer_context.py"),
                         "--db", str(LIVE_DB), "--names", *skipped_names],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    (OUT / "gap4a_customer_context.txt").write_text(cc.stdout + cc.stderr, encoding="utf-8")
    (OUT / "gap4a_rows.txt").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "gap4a_result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
