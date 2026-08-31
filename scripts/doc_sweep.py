"""Check the documentation against the system it describes, and report what has drifted.

    python scripts/doc_sweep.py                 # report
    python scripts/doc_sweep.py --strict        # exit non-zero on any drift, for a gate

WHY THIS EXISTS
On 2026-08-31 a hand sweep found three things that a week of careful work had missed:

  - the runbook AND the cfp-protocol skill still described a MONTHLY re-research, a day after
    it moved to weekly. The skill is loaded at the start of every session, so the next session
    would have been told the wrong schedule by the document written to orient it.
  - TOOLING.md was missing TEN entries, including two modules from the day before. A tooling
    index that does not list the tools is how a parallel implementation gets built - the exact
    failure the protocol exists to prevent.
  - contract amendment v1.6 was orphaned: nothing referenced it but itself.

None was found by remembering. Each was found by asking "what did today make untrue?" and
grepping for it. That question is mechanical, so it belongs in a script.

WHAT IT CANNOT DO
It cannot tell you whether prose is still WISE - only whether it still matches the system.
Judgement stays with the reader. Every check here is a fact that can be verified against the
repo or the machine, and nothing else has been added.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Docs a session is told to read. Drift here is worse than drift anywhere else, because these
# are what a cold start believes.
AUTHORITATIVE = [
    ".claude/skills/cfp-protocol/SKILL.md",
    "docs/operations/pipeline-contract.md",
    "docs/operations/market-runbook.md",
    "docs/operations/TOOLING.md",
    "docs/operations/DECISION-TREE.md",
    "docs/operations/JUDGEMENT.md",
    "HANDOFF.md",
]


def read(p: str) -> str:
    f = ROOT / p
    return f.read_text(encoding="utf-8", errors="replace") if f.exists() else ""


# Modules that DECIDE something a person would otherwise have to remember. These belong in the
# index; the rest of src/ is plumbing - storage, crawling, extraction - and listing all of it
# would bury the entries that matter.
#
# The first version of this check flagged all 24 modules in src/. A check that reports 22
# false positives is not a strict check, it is a check nobody reads - which is the failure this
# whole sweep exists to catch. Precision is the point.
RULES_LAYER = {"rules.py", "lifecycle.py", "sitewalk.py", "clients.py", "sheet_diff.py"}


def check_tooling_lists_every_tool() -> list[str]:
    """Every runnable script, and every module that makes a decision, must be in the index."""
    tooling = read("docs/operations/TOOLING.md")
    missing = [f"scripts/{f.name}" for f in sorted((ROOT / "scripts").glob("*.py"))
               if not f.name.startswith("_") and f.name not in tooling]
    missing += [f"src/cfp_monitor/{n}" for n in sorted(RULES_LAYER)
                if (ROOT / "src" / "cfp_monitor" / n).exists() and n not in tooling]
    return [f"TOOLING.md does not list {m}" for m in missing]


def check_amendments_are_referenced() -> list[str]:
    """A contract amendment nothing points at is one nobody will read."""
    out = []
    for f in sorted((ROOT / "docs" / "operations").glob("Contract_v*_Amendment_*.md")):
        m = re.search(r"v(\d+\.\d+)", f.name)
        if not m:
            continue
        ver = m.group(1)
        referenced = any(ver in read(d) for d in AUTHORITATIVE)
        if not referenced:
            out.append(f"amendment v{ver} ({f.name}) is not referenced by any doc a session "
                       f"is told to read")
    return out


def check_scheduled_jobs_match_the_docs() -> list[str]:
    """The docs name the scheduled jobs. If Task Scheduler disagrees, the docs are wrong."""
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                            "Get-ScheduledTask -TaskName 'CFP*' | "
                            "Select-Object -ExpandProperty TaskName"],
                           capture_output=True, text=True, timeout=60)
        live = {t.strip() for t in r.stdout.splitlines() if t.strip()}
    except Exception:                                                # noqa: BLE001
        return ["could not read Task Scheduler - skipped"]
    if not live:
        return ["no CFP scheduled tasks found at all"]
    out = []
    blob = " ".join(read(d) for d in AUTHORITATIVE)
    for name in sorted(live):
        if name not in blob:
            out.append(f"scheduled task {name!r} exists but no authoritative doc mentions it")
    # The trailing "(live markets)" is PART of the name. A pattern that stops at "Re-Research"
    # reports every correctly-named job as stale, which is how the first run of this check
    # produced four false positives against docs it had just been used to fix.
    for stale in set(re.findall(r"CFP [A-Za-z]+ Re-Research(?: \([a-z ]+\))?", blob)):
        if stale.strip() not in live:
            out.append(f"docs name a job {stale.strip()!r} that no longer exists")
    return out


def check_no_doc_claims_a_dead_script() -> list[str]:
    """A runbook naming a script that was renamed sends the reader nowhere."""
    out = []
    have = {f.name for f in (ROOT / "scripts").glob("*")} | \
           {f.name for f in (ROOT / "src" / "cfp_monitor").glob("*.py")}
    for d in AUTHORITATIVE:
        for named in set(re.findall(r"`?scripts/([A-Za-z0-9_]+\.(?:py|ps1|bat))`?", read(d))):
            if named not in have:
                out.append(f"{d} names scripts/{named}, which does not exist")
    return out


# DELIBERATELY NOT CHECKED: hard-coded test counts.
#
# The first version flagged any "NNN tests" in an authoritative doc, on the reasoning that such
# a number is wrong within a day. It fired twice, and both were right to be there: "112 tests
# reported as passing without ever running" and "everything passed: 467 tests" are DATED
# INCIDENT NARRATIVES, where the number is the whole point of the story.
#
# A check that cannot tell "467 tests passed on 2026-08-12" from "we have 467 tests" is not a
# strict check, it is noise - and noise is what makes a report stop being read. Four precise
# checks beat five with one that cries wolf. Removed rather than tuned, because tuning it would
# mean guessing at prose.


CHECKS = [
    ("every tool is in the index", check_tooling_lists_every_tool),
    ("every amendment is referenced", check_amendments_are_referenced),
    ("scheduled jobs match the docs", check_scheduled_jobs_match_the_docs),
    ("no doc names a dead script", check_no_doc_claims_a_dead_script),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Check the docs against the system.")
    ap.add_argument("--strict", action="store_true", help="exit non-zero on any drift")
    a = ap.parse_args()

    total = 0
    print("DOC SWEEP\n")
    for name, fn in CHECKS:
        try:
            found = fn()
        except Exception as e:                                       # noqa: BLE001
            found = [f"check failed: {type(e).__name__}: {e}"]
        mark = "ok  " if not found else "DRIFT"
        print(f"  [{mark}] {name}" + (f"  ({len(found)})" if found else ""))
        for f in found:
            print(f"          - {f}")
        total += len(found)

    print(f"\n{total} item(s) drifted." if total else "\nNothing has drifted.")
    if total:
        print("Drift is not automatically a bug - a deliberate change may simply need the doc\n"
              "updating. What it is never is: something to leave for later, because the next\n"
              "session reads these documents and believes them.")
    return 1 if (a.strict and total) else 0


if __name__ == "__main__":
    raise SystemExit(main())
