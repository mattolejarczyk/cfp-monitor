"""Is docs/operations/WEEKEND-PROCESS.md still describing the scripts it describes?

    python scripts/check_process_doc.py            report: which scripts changed since confirmed
    python scripts/check_process_doc.py --confirm  after re-reading and correcting the document,
                                                   record the current fingerprints

WHY (2026-09-28). The operator asked for a plain-English record of the weekend process that
stays current as the process changes. Prose drifts silently - WEEKLY-CYCLE.md still described
Step 4 as a Monday-morning manual step a day after it was automated. So the document carries a
fingerprint of every script it describes (docs/operations/weekend-process.fingerprint.json), and
tests/test_process_doc.py fails while any of them has changed since the document was last
confirmed. The fix is never to re-stamp blindly: read the changed script, correct the document,
then --confirm.

Scripts outside the repo (the upstream Markets folder) are checked when present and skipped when
not, so the test still runs on a machine without that folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "operations" / "WEEKEND-PROCESS.md"
FINGERPRINT = ROOT / "docs" / "operations" / "weekend-process.fingerprint.json"
MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")

# Every script whose behaviour WEEKEND-PROCESS.md describes, step by step.
DESCRIBED = {
    "run_monthly.ps1": MARKETS / "run_monthly.ps1",
    "run_canary.ps1": MARKETS / "run_canary.ps1",
    "run_overnight.ps1": MARKETS / "run_overnight.ps1",
    "run_all.ps1": MARKETS / "run_all.ps1",
    "scripts/weekly_intake.py": ROOT / "scripts" / "weekly_intake.py",
    "scripts/stamp_input_ids.py": ROOT / "scripts" / "stamp_input_ids.py",
    "scripts/weekend_import.py": ROOT / "scripts" / "weekend_import.py",
    "scripts/weekend_recap.py": ROOT / "scripts" / "weekend_recap.py",
    "scripts/shadow_finder.py": ROOT / "scripts" / "shadow_finder.py",
    "scripts/refresh_plan.py": ROOT / "scripts" / "refresh_plan.py",
    "scripts/run_weekly.bat": ROOT / "scripts" / "run_weekly.bat",
    "scripts/weekly_verify.py": ROOT / "scripts" / "weekly_verify.py",
    "scripts/weekly_discovery.py": ROOT / "scripts" / "weekly_discovery.py",
    "scripts/apply_resolutions.py": ROOT / "scripts" / "apply_resolutions.py",
    "scripts/weekly_deliverable.py": ROOT / "scripts" / "weekly_deliverable.py",
    "scripts/qa_build.py": ROOT / "scripts" / "qa_build.py",
    "scripts/import_awards.py": ROOT / "scripts" / "import_awards.py",
    "scripts/export_checks.py": ROOT / "scripts" / "export_checks.py",
    "scripts/post_load_qa.py": ROOT / "scripts" / "post_load_qa.py",
    "scripts/narrow_overlay.py": ROOT / "scripts" / "narrow_overlay.py",
    "scripts/start_date_arbiter.py": ROOT / "scripts" / "start_date_arbiter.py",
    "scripts/pinned_rows.py": ROOT / "scripts" / "pinned_rows.py",
}


def digest(p: Path) -> str:
    # line endings normalised: git's CRLF conversion must not read as a process change
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def current() -> dict[str, str]:
    return {k: digest(p) for k, p in DESCRIBED.items() if p.exists()}


def changed() -> list[str]:
    """Scripts that differ from the confirmed fingerprint (absent-here scripts are skipped)."""
    if not FINGERPRINT.exists():
        return sorted(DESCRIBED)
    saved = json.loads(FINGERPRINT.read_text(encoding="utf-8")).get("scripts", {})
    return sorted(k for k, h in current().items() if saved.get(k) != h)


def main() -> int:
    ap = argparse.ArgumentParser(description="Keep WEEKEND-PROCESS.md in step with its scripts.")
    ap.add_argument("--confirm", action="store_true",
                    help="record the current fingerprints - only after re-reading the document")
    a = ap.parse_args()
    if a.confirm:
        missing = [k for k, p in DESCRIBED.items() if not p.exists()]
        if missing:
            print(f"REFUSING: cannot confirm without every described script present: {missing}")
            return 2
        FINGERPRINT.write_text(json.dumps({"document": DOC.name, "scripts": current()},
                                          indent=2) + "\n", encoding="utf-8")
        print(f"confirmed {DOC.name} against {len(DESCRIBED)} scripts")
        return 0
    diff = changed()
    if not diff:
        print(f"{DOC.name} is confirmed against the current scripts.")
        return 0
    print(f"{DOC.name} may be out of date - these changed since it was last confirmed:")
    for k in diff:
        print(f"  - {k}")
    print("Re-read each, correct the document, then run: python scripts/check_process_doc.py --confirm")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
