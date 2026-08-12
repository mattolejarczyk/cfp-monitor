"""The whole pipeline, end to end, in the one order that is correct.

WHY A SCRIPT AND NOT A CHECKLIST
Every stage of this already existed as a documented command. Running them by hand still went
wrong repeatedly on 2026-08-11: a page built without --checks reported zeros as findings, a
merge run from the wrong directory reported data rejections for a path fault, an extraction ran
without CDP and under-reported by a third. Prose cannot enforce an order or a precondition.

Reports by default. Writes nothing without --apply, so it doubles as a status check.

    python scripts/run_full_cycle.py --db <live.db> --delivery <csv> [--apply]

Stages, and why each sits where it does:

  0  preflight    CDP up, database reachable, seeds present, inputs exist. Every one of these
                  has silently degraded a run.
  1  invariants   the state BEFORE we touch anything. A run that starts broken must not be
                  blamed on what we do next.
  2  evidence     rebuild the queryable evidence table from stored crawl results.
  3  audit        re-verify claims against their own cited pages, escalating through the ladder.
  4  refresh      carry verified database values into the delivery CSV.
  5  page         rebuild the customer HTML from the refreshed CSV, evidence inputs required.
  6  invariants   the state AFTER. Compared against stage 1 - a change here we did not intend
                  is the whole reason this stage is duplicated.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


class Stage:
    def __init__(self, key: str, title: str, why: str):
        self.key, self.title, self.why = key, title, why
        self.rc: int | None = None
        self.secs = 0.0
        self.note = ""


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 3600) -> tuple[int, str]:
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=str(cwd or ROOT), capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {time.time() - t0:.0f}s"
    except Exception as e:
        return 1, f"{type(e).__name__}: {e}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the full CFP cycle in the correct order.")
    ap.add_argument("--db", required=True)
    ap.add_argument("--delivery", required=True, help="the delivered CSV - the merge base")
    ap.add_argument("--dead-links", required=True)
    ap.add_argument("--checks", required=True)
    ap.add_argument("--page-builder", help="build_review_page.py in the upstream working area")
    ap.add_argument("--out-dir", help="where the refreshed CSV and HTML go (default: beside "
                                      "the delivery)")
    ap.add_argument("--apply", action="store_true", help="actually write")
    ap.add_argument("--skip-audit", action="store_true",
                    help="skip stages 2-3. They are the slow ones and need the browser.")
    a = ap.parse_args()

    stamp = datetime.now().strftime("%Y%m%d")
    out_dir = Path(a.out_dir) if a.out_dir else Path(a.delivery).parent
    refreshed = out_dir / f"ALL_MARKETS_REFRESHED_{stamp}.csv"
    page = out_dir / f"Conference_Review_{stamp}.html"

    print("=" * 88)
    print(f"FULL CYCLE  {'APPLY' if a.apply else 'REPORT ONLY'}   {datetime.now():%Y-%m-%d %H:%M}")
    print("=" * 88)

    # ---- stage 0: preflight ------------------------------------------------------------
    print("\n[0] preflight")
    problems = []
    for label, p in (("database", a.db), ("delivery", a.delivery),
                     ("dead-links", a.dead_links), ("checks", a.checks)):
        ok = Path(p).exists()
        print(f"    {'ok  ' if ok else 'MISS'}  {label:<12} {p}")
        if not ok:
            problems.append(f"{label} not found: {p}")

    seeds = list((Path(a.db).resolve().parent / "market_sheets").glob("*_seed.csv"))
    print(f"    {'ok  ' if seeds else 'MISS'}  seeds        {len(seeds)} file(s) beside the database")
    if not seeds:
        problems.append("no *_seed.csv beside the database - EVENT_ID mapping will match nothing")

    rc, out = run([PY, "scripts/cdp_ctl.py", "check"])
    cdp = "reachable" in out
    print(f"    {'ok  ' if cdp else 'WARN'}  CDP          {out.strip() or 'no output'}")
    if not cdp and not a.skip_audit:
        problems.append("CDP is not running - hard anti-bot sites are SKIPPED, not failed, and "
                        "the audit will under-report. Start Chrome or pass --skip-audit.")

    if problems:
        print("\nREFUSING TO RUN:")
        for p in problems:
            print(f"  - {p}")
        return 2

    stages: list[Stage] = []

    def stage(key, title, why, cmd, cwd=None, timeout=3600, optional=False):
        s = Stage(key, title, why)
        print(f"\n[{key}] {title}\n    {why}")
        t0 = time.time()
        s.rc, out = run(cmd, cwd, timeout)
        s.secs = time.time() - t0
        tail = [ln for ln in out.strip().splitlines() if ln.strip()][-4:]
        for ln in tail:
            print(f"    | {ln[:150]}")
        print(f"    -> rc={s.rc} in {s.secs:.0f}s")
        if s.rc != 0 and not optional:
            s.note = "FAILED"
        stages.append(s)
        return s

    # ---- stage 1: invariants BEFORE ----------------------------------------------------
    s1 = stage("1", "invariants (before)",
               "the state we started in - so a later failure is not blamed on this run",
               [PY, "scripts/check_invariants.py", "--db", a.db])
    if s1.rc != 0:
        print("\nSTOPPING: the database is already failing its invariants. Fix that first.")
        return 2

    # ---- stages 2-3: evidence + audit --------------------------------------------------
    # build_evidence and audit_evidence have NO dry-run - they write whenever they run. So in
    # report mode they are skipped rather than invoked with a flag they do not have, which is
    # what a first draft of this script did.
    if a.skip_audit:
        print("\n[2-3] SKIPPED (--skip-audit)")
    elif not a.apply:
        print("\n[2-3] SKIPPED - these stages always write, so they need --apply")
    else:
        stage("2", "rebuild evidence table",
              "promotes stored crawl results into one queryable claim-per-row table",
              [PY, "scripts/build_evidence.py", "--db", a.db], timeout=1800, optional=True)
        stage("3", "audit claims against their cited pages",
              "fetches each cited page through the ladder and records what it actually says",
              [PY, "scripts/audit_evidence.py", "--db", a.db], timeout=7200, optional=True)

    # ---- stage 3b: DNS ------------------------------------------------------------------
    # Runs whether or not --apply, because it writes nothing and costs seconds. Deliberately
    # BEFORE the page build so the page can withhold links to hosts that have gone away.
    dead_hosts = out_dir / f"dead_hosts_{stamp}.txt"
    s3b = stage("3b", "do all cited hosts still exist",
                "DNS only. A lapsed domain never reaches a server, so the ladder reads it as "
                "'blocked, not disproven' and nothing else in the pipeline notices",
                [PY, "scripts/check_dns.py", "-i", a.delivery, "--db", a.db,
                 "-o", str(dead_hosts)], timeout=600, optional=True)
    if s3b.rc != 0:
        s3b.note = "dead hosts found - see above"

    # ---- stage 3c: export the verdicts the page reads -----------------------------------
    # Without this the audit updates the DATABASE and the page keeps showing the previous
    # run's numbers, because it reads a CSV nothing regenerated. That gap was live on
    # 2026-08-11: 43 of the 96 rows the page called "Need to Verify" had been verified hours
    # earlier. Only meaningful after stage 3, so it is skipped when the audit is.
    checks_path = Path(a.checks)
    if a.apply and not a.skip_audit:
        fresh = out_dir / f"deadline_checks_{stamp}.csv"
        s3c = stage("3c", "export deadline verdicts for the page",
                    "carries the audit into the file the page reads - the audit alone does not",
                    [PY, "scripts/export_checks.py", "--db", a.db, "-o", str(fresh)],
                    timeout=600, optional=True)
        if s3c.rc == 0 and fresh.exists():
            checks_path = fresh
        else:
            print("    ! keeping the existing checks file - the page will show stale verdicts")
    else:
        print("
[3c] SKIPPED - needs --apply and the audit stage")

    # ---- stage 4: refresh the delivery -------------------------------------------------
    cmd = [PY, "scripts/refresh_delivery.py", "-i", a.delivery, "--db", a.db,
           "-o", str(refreshed), "--only-verified"]
    if a.apply:
        cmd.append("--apply")
    stage("4", "refresh the delivery CSV",
          "carries VERIFIED database values into the customer file; upstream columns untouched",
          cmd, timeout=1800)

    # ---- stage 5: rebuild the page -----------------------------------------------------
    # The page builder has no dry-run either, and it writes the file the customer is shown.
    # A first version of this happily rebuilt that page during a REPORT-ONLY run.
    if a.page_builder and not a.apply:
        print("\n[5] SKIPPED - the page builder always writes, so it needs --apply")
    elif a.page_builder:
        pb = Path(a.page_builder)
        src = refreshed if refreshed.exists() else Path(a.delivery)
        if src == Path(a.delivery):
            print("\n[5] NOTE: building from the ORIGINAL delivery - the refresh produced no "
                  "file, so this page will NOT contain today's corrections.")
        stage("5", "rebuild the customer page",
              "evidence inputs are REQUIRED - without them the page reports zeros as findings",
              [PY, str(pb.name), "-i", str(src), "--dead-links", str(Path(a.dead_links).resolve()),
               "--checks", str(checks_path.resolve()), "--date", f"{datetime.now():%Y-%m-%d}",
               "--dead-hosts", str(dead_hosts.resolve()), "-o", str(page)],
              cwd=pb.parent, timeout=1800)
    else:
        print("\n[5] SKIPPED (no --page-builder given)")

    # ---- stage 6: invariants AFTER -----------------------------------------------------
    stage("6", "invariants (after)",
          "same checks as stage 1 - a difference here is a change this run made and did not intend",
          [PY, "scripts/check_invariants.py", "--db", a.db])

    # ---- summary -----------------------------------------------------------------------
    print("\n" + "=" * 88)
    print("SUMMARY")
    print("=" * 88)
    worst = 0
    for s in stages:
        mark = "ok  " if s.rc == 0 else ("FIND" if s.key == "3b" else "FAIL")
        worst = max(worst, 0 if s.rc == 0 else 1)
        print(f"  [{s.key}] {mark}  {s.title:<44} {s.secs:>6.0f}s"
              + (f"   {s.note}" if s.note else ""))
    if a.apply:
        for label, p in (("refreshed CSV", refreshed), ("customer page", page)):
            print(f"  {label:<16} {'written  ' if p.exists() else 'not built'} {p}")
    else:
        print("\n  REPORT ONLY - nothing was written. Re-run with --apply.")
    print("\n  Before reading anything into the numbers above, see docs/operations/JUDGEMENT.md")
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
