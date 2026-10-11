"""ACT-33 rehearsal, step 1 (offline, read-only on live data): build the scratch folders for a full-research run and a skipped-research run of Saturday 2026-10-10's load.

    python experiments/act33_rehearsal/prepare.py

Reads (never writes) C:\\Users\\matts\\Desktop\\Nicolia-PR-Prime\\Markets and C:\\Users\\matts\\AppData\\Local\\CFP-Monitor. Everything it makes is under experiments/act33_rehearsal/ (git-ignored, real data):
  live_pre/          the database and seed sheets AS THEY WERE before Saturday's load (the weekend_import backups of 20261010-230054): the --live of the sandbox
  full/, skip/       a markets dir each: input, audited file, identity, grounding, health, and last week's approved final (the pre-promote files)
In skip/ the input carries the planner's REFRESH_SKIP marks (planned on that same pre-load state, as of 2026-10-10) and the audited file/identity have the marked rows dropped, which is exactly what the audit would have produced.
"""
import csv
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
M = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
L = Path(os.environ["LOCALAPPDATA"]) / "CFP-Monitor"
PLAN_DATE = sys.argv[1] if len(sys.argv) > 1 else "2026-10-10"
PRE = {"Cybersecurity": "20261010-233903", "Utility": "20261010-233904"}      # the final each market had before Saturday's promote


def copy_ro_db(src: Path, dst: Path) -> None:
    s = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    d = sqlite3.connect(dst)
    s.backup(d)
    d.close()
    s.close()


def main() -> None:
    pre = HERE / "live_pre"
    shutil.rmtree(pre, ignore_errors=True)
    (pre / "market_sheets").mkdir(parents=True)
    copy_ro_db(L / "cfp_monitor.db.pre-weekend-20261010-230054", pre / "cfp_monitor.db")
    for src, dst in (("cyber_seed.csv.pre-weekend-20261010-230054", "cyber_seed.csv"), ("utility_seed.csv.pre-weekend-20261010-230054", "utility_seed.csv"),
                     ("held_rows.txt.pre-weekend-20261010-230054", "held_rows.txt")):
        shutil.copy2(L / "market_sheets" / src, pre / "market_sheets" / dst)
    for kind in ("full", "skip"):
        d = HERE / kind
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir()
        for m in PRE:
            for f in ("input.csv", "audited.csv", "audited.identity.csv", "audited.grounding.jsonl", "audited.health.json"):
                shutil.copy2(M / f"{m}_{f}", d / f"{m}_{f}")
            shutil.copy2(M / f"{m}_audited.final.pre-promote-{PRE[m]}.csv", d / f"{m}_audited.final.csv")
            os.utime(d / f"{m}_audited.csv", (time.time(), time.time()))                  # the importer refuses a research file older than 30 hours: this is a copy
    # the plan, on the pre-load state, as of PLAN_DATE (dry run first, then apply on the skip/ copy)
    out = HERE / f"reports_{PLAN_DATE}"
    for m in PRE:
        base = [sys.executable, str(ROOT / "scripts" / "refresh_plan.py"), "--market", m, "--markets-dir", str(HERE / "skip"), "--db", str(pre / "cfp_monitor.db"),
                "--today", PLAN_DATE, "--out-dir", str(out)]
        subprocess.run(base, check=True)
        subprocess.run(base + ["--apply"], check=True)
        # drop the marked rows from the audited file and its identity file
        inp = list(csv.DictReader(open(HERE / "skip" / f"{m}_input.csv", encoding="utf-8-sig", newline="")))
        marked_names = {r["CONFERENCE"] for r in inp if (r.get("REFRESH_SKIP") or "").strip()}
        marked_ids = {r["EVENT_ID_CANON"] for r in inp if (r.get("REFRESH_SKIP") or "").strip()}
        ident = list(csv.DictReader(open(HERE / "skip" / f"{m}_audited.identity.csv", encoding="utf-8-sig", newline="")))
        drop_out_ids = {r["OUTPUT_EVENT_ID"] for r in ident if (r.get("EVENT_ID_CANON") or "").strip() in marked_ids}
        with open(HERE / "skip" / f"{m}_audited.csv", encoding="utf-8-sig", newline="") as fh:
            rd = csv.DictReader(fh)
            cols, rows = rd.fieldnames, list(rd)
        keep = [r for r in rows if (r.get("EVENT_ID") or "").strip() not in drop_out_ids]
        with open(HERE / "skip" / f"{m}_audited.csv", "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL)
            w.writeheader()
            w.writerows(keep)
        kept_ident = [r for r in ident if r["OUTPUT_EVENT_ID"] not in drop_out_ids]
        with open(HERE / "skip" / f"{m}_audited.identity.csv", "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(ident[0].keys()), quoting=csv.QUOTE_ALL)
            w.writeheader()
            w.writerows(kept_ident)
        os.utime(HERE / "skip" / f"{m}_audited.csv", (time.time(), time.time()))
        print(f"{m}: audited rows {len(rows)} -> {len(keep)} (dropped {len(rows) - len(keep)}; marked in the input {len(marked_ids)})")


if __name__ == "__main__":
    main()
