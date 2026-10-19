"""LEAN WEEK rehearsal (2026-10-19), step 1 (offline, read-only on live data): build scratch folders for a skipped-research load of Saturday 2026-10-24 on TODAY's live state.

    python experiments/act33_rehearsal/prepare_lean.py [--plan-date 2026-10-24]

Same idea as prepare.py (the Oct 10 rehearsal) but on the CURRENT files: the live database and market_sheets are copied (never written), the input list carries the planner's REFRESH_SKIP marks for a
LEAN week (policy docs/operations/refresh_policy.json lean_until), and the audited file and its identity file have the marked rows dropped, which is what the audit would have produced.
The input rows that have no research yet (the new events added since Saturday's run) are removed from the scratch input, because Saturday's research will produce them and a list with an unresearched
row makes the import stop as 'short' (the 2026-10-17 lesson). Output: experiments/act33_rehearsal/lean/ (git-ignored, real data) and lean_live/ (the --live of the sandbox).
Then run:  python scripts/weekend_import.py --markets Cybersecurity Utility --research-exit 0 --sandbox <abs>/experiments/act33_rehearsal/sbx_lean --live <abs>/experiments/act33_rehearsal/lean_live \
           --markets-dir <abs>/experiments/act33_rehearsal/lean --report <abs>/experiments/act33_rehearsal/import_lean.json
and compare with compare_lean.py."""
import argparse
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
MARKETS = ("Cybersecurity", "Utility")


def copy_ro_db(src: Path, dst: Path) -> None:
    s = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    d = sqlite3.connect(dst)
    s.backup(d)
    d.close()
    s.close()


def read(p: Path):
    with open(p, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        return rd.fieldnames, list(rd)


def write(p: Path, cols, rows) -> None:
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan-date", default="2026-10-24")
    a = ap.parse_args()
    live = HERE / "lean_live"
    shutil.rmtree(live, ignore_errors=True)
    shutil.copytree(L / "market_sheets", live / "market_sheets", ignore=shutil.ignore_patterns("*.bak*", "*before-merge*", "*backup*", "*.pre-*", "*pre-weekend*", "*.tmp"))
    copy_ro_db(L / "cfp_monitor.db", live / "cfp_monitor.db")
    d = HERE / "lean"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir()
    out = HERE / f"reports_lean_{a.plan_date}"
    for m in MARKETS:
        for f in ("input.csv", "audited.csv", "audited.identity.csv", "audited.grounding.jsonl", "audited.health.json", "audited.final.csv"):
            shutil.copy2(M / f"{m}_{f}", d / f"{m}_{f}")
        os.utime(d / f"{m}_audited.csv", (time.time(), time.time()))                      # the importer refuses a research file older than 30 hours: this is a copy
        # input rows with no research yet (new events since the last run) leave the scratch input
        cols, inp = read(d / f"{m}_input.csv")
        researched = {r["CONFERENCE"].strip().lower() for r in read(d / f"{m}_audited.csv")[1]}
        keep = [r for r in inp if r["CONFERENCE"].strip().lower() in researched or (r.get("DUP_OF") or "").strip()]
        removed = [r["CONFERENCE"] for r in inp if r not in keep]
        write(d / f"{m}_input.csv", cols, keep)
        print(f"{m}: input rows {len(inp)} -> {len(keep)}; removed (no research yet): {removed}")
        base = [sys.executable, str(ROOT / "scripts" / "refresh_plan.py"), "--market", m, "--markets-dir", str(d), "--db", str(live / "cfp_monitor.db"), "--today", a.plan_date, "--out-dir", str(out)]
        subprocess.run(base, check=True)
        subprocess.run(base + ["--apply"], check=True)
        cols, inp = read(d / f"{m}_input.csv")
        marked_ids = {r["EVENT_ID_CANON"] for r in inp if (r.get("REFRESH_SKIP") or "").strip()}
        icols, ident = read(d / f"{m}_audited.identity.csv")
        drop_out_ids = {r["OUTPUT_EVENT_ID"] for r in ident if (r.get("EVENT_ID_CANON") or "").strip() in marked_ids}
        acols, rows = read(d / f"{m}_audited.csv")
        kept = [r for r in rows if (r.get("EVENT_ID") or "").strip() not in drop_out_ids]
        write(d / f"{m}_audited.csv", acols, kept)
        write(d / f"{m}_audited.identity.csv", icols, [r for r in ident if r["OUTPUT_EVENT_ID"] not in drop_out_ids])
        os.utime(d / f"{m}_audited.csv", (time.time(), time.time()))
        print(f"{m}: audited rows {len(rows)} -> {len(kept)} (dropped {len(rows) - len(kept)}; marked in the input {len(marked_ids)})")


if __name__ == "__main__":
    main()
