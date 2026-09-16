"""Build the two customer-facing HTML pages for the week, in one step.

    python scripts/weekly_deliverable.py [--db DB] [--out-dir DIR] [--date YYYY-MM-DD]
        [--skip-evidence] [--markets "Cybersecurity,Utility"]

WHAT IT DOES, in the runbook's order (section 5):
    1. audit_evidence.py --field deadline --recheck   re-read every cited page   (no API cost)
    2. export_checks.py                               verdicts -> the CSV the page reads
    2a. check_award_deadlines.py --apply              BOTH of the above, for awards (no API cost)
    2b. weekly_verify.check_all_submission_links      refresh the dead-link flags the page shows
        link_check_awards.py --apply                  the same, for the awards rows
    3. combine the live markets' accepted deliveries into one input
    4. build_review_page.py --kind conference         the conferences page
    5. build_review_page.py --kind awards             the awards page
    6. publish both into <out-dir>/<date>/ with a MANIFEST

WHY IT EXISTS. Step 2 is the one that gets missed by hand: without it the audit refreshes the
database and the page still shows last week's numbers - measured once at 43 of 96 rows reading
"Need to Verify" hours after they had been verified. And on 2026-09-14 the pages the customer
had were from 2026-08-31, two weeks and two accepted deliveries out of date, because building
them was a five-command manual sequence nobody had scheduled.

QUALITY BY DESIGN. Every step's outcome is recorded (src/cfp_monitor/run_health.py). **Nothing
is published from a DEGRADED run**: the pages stay in the work folder, the manifest says why, and
the exit code is 2. A page built from a failed evidence pass looks exactly like a good one and
would tell Nicolia's team that nothing was verified.

    exit 0  published    exit 1  a step failed outright    exit 2  DEGRADED, nothing published
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor.run_health import HEALTH                        # noqa: E402

PY = sys.executable
MARKETS_DIR = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
OUT_DIR = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\handoff-files\weekly")
LIVE_DB = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor\cfp_monitor.db")
RUNS_OUT = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor\runs_out")
LIVE_MARKETS = "Cybersecurity,Utility"


def step(name: str, cmd: list[str], log: Path, timeout: int = 7200) -> bool:
    """Run one step, record its outcome, keep its log. True when it succeeded."""
    print(f"\n=== {name} ===\n{' '.join(str(c) for c in cmd)}", flush=True)
    with open(log, "w", encoding="utf-8") as fh:
        try:
            code = subprocess.run([str(c) for c in cmd], stdout=fh, stderr=subprocess.STDOUT,
                                  timeout=timeout,
                                  env={**os.environ, "PYTHONIOENCODING": "utf-8"}).returncode
        except subprocess.TimeoutExpired:
            HEALTH.fail("weekly_step", "timed_out", f"{name} after {timeout}s")
            print(f"  TIMED OUT after {timeout}s - see {log.name}")
            return False
    if code == 0:
        HEALTH.ok("weekly_step")
        print(f"  ok ({log.name})")
        return True
    HEALTH.fail("weekly_step", "step_failed", f"{name}: exit {code}, see {log.name}")
    print(f"  FAILED exit {code} - see {log.name}")
    return False


def combine(sources: list[Path], out: Path) -> int:
    """One input file for the conferences page. Headers must match exactly - a delivery written
    to a different schema would silently drop columns the page reads."""
    rows, cols = [], None
    for s in sources:
        with open(s, encoding="utf-8-sig", newline="") as fh:
            rd = csv.DictReader(fh)
            if cols is None:
                cols = rd.fieldnames
            if rd.fieldnames != cols:
                raise SystemExit(f"header mismatch: {s.name} does not match {sources[0].name}")
            rows += list(rd)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def newest(pattern: str, where: Path) -> Path | None:
    hits = sorted(where.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return hits[0] if hits else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--markets-dir", default=str(MARKETS_DIR))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--markets", default=LIVE_MARKETS, help="markets the conferences page covers")
    ap.add_argument("--skip-evidence", action="store_true",
                    help="reuse the existing checks CSV (for a rebuild the same day)")
    ap.add_argument("--skip-links", action="store_true",
                    help="skip the dead-link re-check (it runs a browser over every link)")
    ap.add_argument("--awards-input", help="awards delivery CSV (default: newest Awards_*_out.csv)")
    a = ap.parse_args()

    md, stamp = Path(a.markets_dir), a.date
    work = Path(a.out_dir) / f"work_{stamp}"
    work.mkdir(parents=True, exist_ok=True)
    checks = RUNS_OUT / f"checks_{stamp.replace('-', '')}.csv"
    award_checks = RUNS_OUT / f"award_checks_{stamp.replace('-', '')}.csv"
    hosts = RUNS_OUT / "hosts_final.txt"

    # 1 + 2. Evidence, then the export that turns it into what the page reads.
    if not a.skip_evidence:
        step("evidence re-read", [PY, ROOT / "scripts/audit_evidence.py", "--db", a.db,
                                  "--field", "deadline", "--recheck"], work / "1_evidence.log")
    # ALWAYS exported, even with --skip-evidence: this is the step that gets missed, it costs a
    # second, and skipping it is what makes a page show last week's verdicts.
    step("export checks", [PY, ROOT / "scripts/export_checks.py", "--db", a.db,
                           "-o", checks], work / "2_export_checks.log")
    if not checks.exists():
        HEALTH.fail("weekly_step", "missing_input", f"no checks CSV at {checks}")

    # 2a. STEPS 1 AND 2 AGAIN, FOR AWARDS. audit_evidence/export_checks read the `evidence`
    # table joined to `grounding_facts` - the CONFERENCES table - so they have nothing to say
    # about an award, and this one pass does both jobs for them.
    #
    # It runs AFTER step 2 rather than beside step 1, and the number says so. The two are
    # independent - export_checks is conference-only and this CSV is not read until the page
    # build - so the order is a free choice, and a step numbered for where it actually runs is
    # worth more than one numbered for where it conceptually belongs.
    #
    # It is here because of what happened without it. On 2026-09-14 the awards page was built
    # with the CONFERENCE checks CSV, whose 162 rows contain zero awards. Nothing failed, the
    # run reported HEALTHY, and the page shipped reading "0 Deadline confirmed - we read it on
    # their page" - an omission rendered as a result, which is the exact failure the builder's
    # --no-evidence guard exists to prevent. A CSV that matches no rows walks around that guard.
    # No API cost: it re-opens cited pages, it does not ask a model anything.
    if not a.skip_evidence:
        step("awards evidence", [PY, ROOT / "scripts/check_award_deadlines.py", "--db", a.db,
                                 "-o", award_checks, "--apply"], work / "2a_award_evidence.log")
    if not award_checks.exists():
        HEALTH.fail("weekly_step", "missing_input", f"no awards checks CSV at {award_checks}")

    # 2b. Refresh the dead-link flags the pages render.
    #
    # These live in `link_checks`, written by the Sunday sweep - so on Monday they predate the
    # week's corrections: on 2026-09-14 the flags were from Sunday 01:23 and a link fixed on
    # Saturday would still have rendered as dead. This re-checks every customer-clickable link
    # (browser-confirmed, contract 5.2) so the flags match the file being sent. No API cost.
    if not a.skip_links:
        try:
            from scripts.weekly_verify import check_all_submission_links
            newly, standing = check_all_submission_links(a.db, use_browser=True)
            HEALTH.ok("weekly_step")
            HEALTH.note("link_check", f"newly_dead_{len(newly)}")
            HEALTH.note("link_check", f"standing_dead_{len(standing)}")
            print(f"\nlink re-check: {len(newly)} newly dead, {len(standing)} already dead")
            (work / "2b_links.log").write_text(
                "newly dead:\n" + "\n".join(f"  {n} | {u}" for _i, n, u in newly)
                + "\n\nstanding dead:\n" + "\n".join(f"  {n} | {u}" for _i, n, u in standing),
                encoding="utf-8")
        except Exception as e:                                           # noqa: BLE001
            HEALTH.fail("weekly_step", "step_failed", f"link re-check: {type(e).__name__}: {e}")
            print(f"  link re-check FAILED: {e}")
        step("awards link check", [PY, ROOT / "scripts/link_check_awards.py", "--db", a.db,
                                   "--apply"], work / "2c_awards_links.log", timeout=3600)

    # 2d. RECONCILE, BECAUSE THIS RUN MUTATED. Steps 2a and 2c both write to the database
    # (verify_state, dead-link flags) and nothing here has ever checked the result. "A mutation
    # needs a reconciliation" is the oldest rule in this repo and the weekly build was quietly
    # exempt from it.
    #
    # RECORDED, NOT BLOCKING. An invariant failure is a statement about the DATABASE; the
    # conference page is built from the delivery CSVs, so a database fault does not
    # automatically make the page wrong. Blocking here would mean the customer gets nothing on
    # a Monday over a fault that may not touch what they read - and the agreed rule is to
    # publish what is accepted and say what is unresolved.
    # 3. The conferences page reads one file; the live markets are delivered separately.
    sources = [md / "Cybersecurity_audited.final.csv", md / "Utility_audited.final.csv"]
    missing = [s.name for s in sources if not s.exists()]
    if missing:
        HEALTH.fail("weekly_step", "missing_input", f"delivery not found: {', '.join(missing)}")
        combined, n_rows = None, 0
    else:
        combined = work / f"live_markets_{stamp}.csv"
        n_rows = combine(sources, combined)
        HEALTH.ok("weekly_step")
        print(f"\ncombined {n_rows} row(s) -> {combined.name}")

    awards_in = Path(a.awards_input) if a.awards_input else newest("Awards_*_out.csv", md)
    conf_page = work / f"Conference Review {stamp} - Live Markets.html"
    awards_page = work / f"Awards Review {stamp}.html"

    # 2d. RECONCILE, BECAUSE THIS RUN MUTATED. Steps 2a and 2c both write to the database -
    # verify_state and the dead-link flags - and nothing here has ever checked the result. "A
    # mutation needs a reconciliation" is the oldest rule in this repo, and the weekly build
    # was quietly exempt from it.
    #
    # RECORDED, NOT BLOCKING. An invariant failure is a statement about the DATABASE, while the
    # conference page is built from the delivery CSVs, so a database fault does not by itself
    # make the page wrong. Blocking here would mean the customer gets nothing on a Monday over
    # a fault that may not touch what they read, and the agreed rule is to publish what is
    # accepted and say what is unresolved.
    inv = [PY, ROOT / "scripts/check_invariants.py", "--db", a.db]
    if awards_in and Path(awards_in).exists():
        inv += ["--awards-delivery", str(awards_in)]
    done = subprocess.run([str(c) for c in inv], capture_output=True, text=True,
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    (work / "2d_invariants.log").write_text(done.stdout + done.stderr, encoding="utf-8")
    HEALTH.note("invariants", "hold" if done.returncode == 0 else "VIOLATED")
    print(f"\ninvariants: {'hold' if done.returncode == 0 else 'VIOLATED'} "
          f"(2d_invariants.log)")

    # 4 + 5. The two pages. --reconcile adds the "check against your sheet" view.
    if combined:
        cmd = [PY, ROOT / "scripts/build_review_page.py", "-i", combined, "--kind", "conference",
               "--date", stamp, "--db", a.db, "--checks", checks, "--markets", a.markets,
               "--reconcile", "-o", conf_page]
        if hosts.exists():
            cmd += ["--dead-hosts", hosts]
        step("conferences page", cmd, work / "3_conference_page.log")
    if awards_in and awards_in.exists():
        cmd = [PY, ROOT / "scripts/build_review_page.py", "-i", awards_in, "--kind", "awards",
               "--date", stamp, "--db", a.db, "--checks", award_checks, "-o", awards_page]
        if hosts.exists():
            cmd += ["--dead-hosts", hosts]
        step("awards page", cmd, work / "4_awards_page.log")
    else:
        HEALTH.fail("weekly_step", "missing_input", "no awards delivery found")

    for page in (conf_page, awards_page):
        if page.exists() and page.stat().st_size > 20_000:
            HEALTH.ok("page_built")
        else:
            HEALTH.fail("page_built", "missing_or_tiny", page.name)

    # 6. Publish - but only from a healthy run.
    status, reasons = HEALTH.verdict()
    published = Path(a.out_dir) / stamp
    lines = [f"# Weekly customer pages - {stamp}", "", f"    HEALTH: {status}", ""]
    lines += HEALTH.report_lines() + ["", f"conference rows: {n_rows}",
                                      f"awards input: {awards_in.name if awards_in else '(none)'}",
                                      f"checks CSV: {checks.name}", ""]
    if status == "HEALTHY":
        published.mkdir(parents=True, exist_ok=True)
        for page in (conf_page, awards_page):
            if page.exists():
                shutil.copy2(page, published / page.name)
        lines += ["## Published", "", f"`{published}`", "",
                  "Send both HTML files to Nicolia and team."]
    else:
        lines += ["## NOT PUBLISHED", "",
                  "This run could not verify what the pages would claim, and a page built from a "
                  "failed evidence pass looks exactly like a good one. Fix the cause, re-run, and "
                  "only then send anything.", ""] + [f"- {r}" for r in reasons]
    (work / "MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwork folder: {work}")
    if status != "HEALTHY":
        return 2
    return 0 if HEALTH.failures("weekly_step") == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
