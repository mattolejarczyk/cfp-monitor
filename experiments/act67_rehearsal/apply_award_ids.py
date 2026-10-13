"""One command for the 2026-10-12 upstream award-ids reply (ACT-67): check, relabel, stamp new ids, stamp existing ids, verify, set the switch.

    python experiments\\act67_rehearsal\\apply_award_ids.py            dry run: runs every CHECK, writes nothing
    python experiments\\act67_rehearsal\\apply_award_ids.py --apply    does it, in order, and STOPS at the first step whose result is not what was reviewed

It only calls the existing, tested commands (scripts/customer_awards.py and scripts/stamp_given_ids.py). Each step proves its own result; this wrapper checks the numbers the reviewer expected
(32 new ids, 2 existing ids, 7 relabels, 0 problems; afterwards 0 customer awards not in the queue and 0 waiting for an id). Backups are made by the commands themselves (beside the files they change).
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\matts\cfp-monitor")
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
REPLY = ROOT / "docs" / "operations" / "award_ids_reply_20261012.csv"
DB = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\matts\AppData\Local")) / "CFP-Monitor" / "cfp_monitor.db"
OUT = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\matts\AppData\Local")) / "CFP-Monitor" / "runs_out" / "qa" / "2026-10-13"
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def run(args):
    r = subprocess.run([PY, *[str(a) for a in args]], cwd=ROOT, capture_output=True, text=True, env=ENV)
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode, out


def stop(msg, out=""):
    print("\nSTOP:", msg)
    if out:
        print(out[-1500:])
    print("Nothing further was run. The commands make backups beside the files they change (names contain 'pre-'); tell Claude what you saw.")
    sys.exit(1)


def need(pattern, out, label):
    m = re.search(pattern, out)
    if not m:
        stop(f"{label}: expected '{pattern}' in the result", out)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    mode = "APPLY" if a.apply else "DRY RUN (writes nothing)"
    print(f"== award ids reply: {mode}")

    code, out = run(["scripts/customer_awards.py", "--reply-plan", "--reply", REPLY, "--db", DB, "--out-dir", OUT])
    print("1. plan:", out.strip().splitlines()[-1] if out.strip() else out)
    need(r"AWARDS REPLY: 32 new ids to stamp, 2 existing ids to stamp, 7 to relabel, 0 already done, 0 problems", out, "reply plan")

    code, out = run(["scripts/customer_awards.py", "--relabel", "--reply", REPLY] + (["--apply", "--live"] if a.apply else []))
    print("2. relabel:", out.strip().splitlines()[-1])
    need(r"AWARDS RELABEL: mode=(applied; 7 relabelled|dry-run; 7 to relabel)", out, "relabel")

    code, out = run(["scripts/stamp_given_ids.py", "--awards", "--ids-csv", OUT / "ids_new.csv"] + (["--apply"] if a.apply else []))
    print("3. stamp new ids:", next((ln.strip() for ln in out.splitlines() if "ids given" in ln), out[-200:]))
    need(r"32 ids given: 32 to stamp", out, "stamp new ids")

    code, out = run(["scripts/stamp_given_ids.py", "--awards", "--allow-held", "--ids-csv", OUT / "ids_existing.csv"] + (["--apply"] if a.apply else []))
    print("4. stamp existing ids:", next((ln.strip() for ln in out.splitlines() if "ids given" in ln), out[-200:]))
    need(r"2 ids given: 2 to stamp", out, "stamp existing ids")

    if a.apply:
        code, out = run(["scripts/customer_awards.py", "--reply-plan", "--reply", REPLY, "--db", DB, "--out-dir", OUT])
        print("5. plan again:", out.strip().splitlines()[-1])
        need(r"AWARDS REPLY: 0 new ids to stamp, 0 existing ids to stamp, 0 to relabel, 41 already done, 0 problems", out, "plan after apply")
        code, out = run(["scripts/customer_awards.py"])
        line = next((ln for ln in out.splitlines() if ln.startswith("AWARDS AUTOADD")), "")
        print("6. coverage:", next((ln for ln in out.splitlines() if ln.startswith("AWARDS COVERAGE:")), ""))
        print("   ", line)
        need(r"0 customer awards NOT in the queue after the step", line, "coverage")
        need(r"\b0 waiting for an id", line, "waiting for an id")
        ps = subprocess.run(["powershell", "-NoProfile", "-Command",
                             "[Environment]::SetEnvironmentVariable('CFP_AWARDS_NEW_EVENTS','1','User'); [Environment]::GetEnvironmentVariable('CFP_AWARDS_NEW_EVENTS','User')"],
                            capture_output=True, text=True)
        print("7. CFP_AWARDS_NEW_EVENTS (user level) =", ps.stdout.strip())
        if ps.stdout.strip() != "1":
            stop("could not set CFP_AWARDS_NEW_EVENTS", ps.stdout + ps.stderr)
        print("\nDONE. Tell Claude; it verifies the files, the ledger and the switch. Then restart nothing: the Friday task reads the variable when it starts.")
    else:
        print("\nDRY RUN OK: every check matched. Run again with --apply to do it.")


if __name__ == "__main__":
    main()
