"""Weekly re-verification sweep.

Re-checks every loaded grounding claim against live pages and reports what CHANGED since
the last sweep. It answers the two questions that actually hurt a customer:

    * has a submission link died?          - a client clicks through to a 404
    * does a page now contradict a date?   - the deadline moved and we were not told

**This job makes no LLM calls and spends no API quota.** Discovery - finding conferences we
do not track, and calls that have newly opened on pages we never cited - is the separate
MONTHLY grounded audit (`run_market_audit.py` in the upstream working area). Splitting them
this way was decided 2026-08-08: weekly verification is free and safe to automate, weekly
re-research is ~400 grounded requests and is what exhausted quota on 2026-08-04.

Reuses the existing tools rather than reimplementing them:
    scripts/verify_grounding.py    layers 0/1/2, once per market
    scripts/recheck_dead_links.py  the browser rung, for anything the fast pass called dead
    src/cfp_monitor/alerts.py      digest formatting and SMTP

Markets are discovered from `market_sheets/*_seed.csv` rather than hard-coded, so adding a
market to the pipeline does not require editing this file.

    python scripts/weekly_verify.py --db cfp_monitor.db [--dry-run] [--no-browser]
"""
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor.alerts import maybe_send_email                  # noqa: E402

# A verify_detail containing this is layer 1 reporting a dead SUBMISSION link, as opposed to
# a contradicted date. The two need different responses, so the digest separates them.
DEAD_LINK_MARK = "submission link returns"


def discover_markets(seed_dir: Path) -> list[tuple[str, Path]]:
    """(upstream market label, seed csv) for every *_seed.csv holding exactly one market.

    verify_grounding.py's --market takes UPSTREAM's spelling (`ConsumerElectronics`), not our
    canonical name, because it filters through the seed CSV. Reading the label out of the file
    keeps the two spellings from drifting.
    """
    found = []
    for seed in sorted(seed_dir.glob("*_seed.csv")):
        with open(seed, encoding="utf-8-sig", newline="") as fh:
            labels = {(r.get("Market") or "").strip()
                      for r in csv.DictReader(fh)} - {""}
        if len(labels) == 1:
            found.append((labels.pop(), seed))
        elif labels:
            print(f"  ! {seed.name} holds {len(labels)} markets - skipped "
                  f"(verify runs one market at a time)")
    return found


def snapshot(db: str) -> dict[str, tuple[str, str]]:
    con = sqlite3.connect(db)
    try:
        return {r[0]: (r[1] or "", r[2] or "") for r in con.execute(
            "select event_id, verify_state, verify_detail from grounding_facts")}
    finally:
        con.close()


def names(db: str) -> dict[str, str]:
    con = sqlite3.connect(db)
    try:
        return {r[0]: r[1] or r[0]
                for r in con.execute("select event_id, name from grounding_facts")}
    finally:
        con.close()


def run(cmd: list[str], cwd: Path) -> int:
    print("    $ " + " ".join(cmd[1:]))
    return subprocess.run(cmd, cwd=str(cwd)).returncode


def check_all_submission_links(db: str, use_browser: bool = True) -> list[tuple[str, str, str]]:
    """Check EVERY submission link, regardless of what the layered verification concluded.

    verify_grounding stops at the first layer that resolves a row, so a conference that
    verifies at L0 ("the page says the call is open") never reaches the L1 link check. On
    2026-08-08 that hid 9 dead links out of 46, including CES 2027 - verified open, submit
    link dead. The customer-facing link is too important to be checked only as a fallback.

    Returns (event_id, name, url) for links confirmed dead. A plain-HTTP 404 is never
    sufficient on its own (contract 5.2), so the browser confirms before anything is recorded.
    """
    import asyncio
    import sqlite3 as _sq

    sys.path.insert(0, str(ROOT / "scripts"))
    from src.cfp_monitor.verify import link_status                  # noqa: PLC0415
    from recheck_dead_links import browser_check                    # noqa: PLC0415

    con = _sq.connect(db)
    rows = [(e, n or e, (u or "").strip()) for e, n, u in con.execute(
        "select event_id, name, submission_url from grounding_facts")
        if (u or "").strip().startswith("http")]
    con.close()

    by_url: dict[str, list[tuple[str, str]]] = {}
    for eid, name, url in rows:
        by_url.setdefault(url, []).append((eid, name))
    print(f"  checking {len(by_url)} distinct submission link(s)")

    suspect = [u for u in by_url if link_status(u)[0] in (404, 410)]
    print(f"  {len(suspect)} returned 404/410 on the fast pass")
    if not suspect:
        return []
    if not use_browser:
        print("  --no-browser: reporting fast-pass results unconfirmed")
        return [(e, n, u) for u in suspect for e, n in by_url[u]]

    res = asyncio.run(browser_check(suspect))
    dead = [u for u in suspect if res.get(u, ("", 0, 0))[0] != "ALIVE"]
    print(f"  {len(dead)} confirmed dead by browser; "
          f"{len(suspect) - len(dead)} were false 404s (blocked, not dead)")

    # Persist to a SIDE table. grounding_facts.verify_state cannot hold this: a row can have
    # a correctly verified deadline AND a dead submit link (CES 2027 does), and one state
    # column cannot say both. A separate table also leaves import and verify untouched.
    con = _sq.connect(db)
    con.execute("""create table if not exists link_checks (
                     url text primary key, state text, checked_at text)""")
    now = datetime.now().isoformat(timespec="seconds")
    con.executemany("insert or replace into link_checks values (?,?,?)",
                    [(u, "dead" if u in set(dead) else "alive", now) for u in by_url])
    con.commit()
    con.close()
    return [(e, n, u) for u in dead for e, n in by_url[u]]


def build_digest(before: dict, after: dict, label: dict[str, str], today: date,
                 open_issues: int = 0) -> tuple[str, int]:
    """Digest of CHANGES only. A steady-state week should produce a short, boring email.

    `open_issues` is the count of standing problems found outside the before/after diff -
    today that means dead submission links. Without it the digest printed "Nothing changed"
    directly above a list of 45 dead links, because the diff and the link check run at
    different times and neither knew about the other.
    """
    newly_dead, newly_contradicted, recovered = [], [], []
    for eid, (state, detail) in after.items():
        was_state, _ = before.get(eid, ("", ""))
        if state == was_state:
            continue
        name = label.get(eid, eid)
        if state == "contradicted":
            (newly_dead if DEAD_LINK_MARK in detail else newly_contradicted).append(
                (name, detail))
        elif was_state == "contradicted" and state in ("verified", "not_found"):
            recovered.append((name, detail))

    lines = [f"# Weekly verification - {today.isoformat()}", ""]
    total = len(newly_dead) + len(newly_contradicted)
    if not total and not recovered:
        lines += ["No CHANGE since the last sweep - nothing newly broken, nothing recovered."
                  + (f" {open_issues} standing issue(s) remain open, listed below."
                     if open_issues else " Nothing outstanding."), ""]
    if newly_dead:
        lines += [f"## Submission links that have died ({len(newly_dead)})",
                  "A client clicking these reaches a 404. Confirmed by browser, not just HTTP.",
                  ""]
        lines += [f"- **{n}** - {d}" for n, d in newly_dead] + [""]
    if newly_contradicted:
        lines += [f"## Deadlines a page now contradicts ({len(newly_contradicted)})", ""]
        lines += [f"- **{n}** - {d}" for n, d in newly_contradicted] + [""]
    if recovered:
        lines += [f"## Recovered since last week ({len(recovered)})", ""]
        lines += [f"- {n}" for n, _ in recovered] + [""]

    counts: dict[str, int] = {}
    for state, _ in after.values():
        counts[state or "(blank)"] = counts.get(state or "(blank)", 0) + 1
    lines += ["## Current totals", ""]
    lines += [f"- {k}: {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]
    return "\n".join(lines) + "\n", total


def main() -> int:
    ap = argparse.ArgumentParser(description="Weekly re-verification sweep (no API calls).")
    ap.add_argument("--db", default="cfp_monitor.db")
    ap.add_argument("--seed-dir", default="market_sheets")
    ap.add_argument("--out-dir", default="runs_out")
    ap.add_argument("--layers", default="012")
    ap.add_argument("--no-browser", action="store_true",
                    help="skip the browser rung (faster; plain HTTP only)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report without writing to the DB or sending mail")
    a = ap.parse_args()

    cwd = Path.cwd()
    db_path = Path(a.db)
    if not db_path.exists():
        print(f"ERROR: no database at {db_path.resolve()}")
        return 2

    markets = discover_markets(Path(a.seed_dir))
    if not markets:
        print(f"ERROR: no single-market *_seed.csv found in {a.seed_dir}")
        return 2

    today = date.today()
    print(f"Weekly verification sweep - {today.isoformat()}")
    print(f"  database {db_path.resolve()}")
    print(f"  markets  {', '.join(m for m, _ in markets)}\n")

    before, label = snapshot(a.db), names(a.db)

    py = sys.executable
    for market, seed in markets:
        print(f"--- {market} ---")
        cmd = [py, "scripts/verify_grounding.py", "--db", a.db, "--market", market,
               "--seed-csv", str(seed), "--layers", a.layers]
        if not a.dry_run:
            cmd.append("--apply")
        if run(cmd, cwd) != 0:
            print(f"  ! verify failed for {market} - continuing with the rest")

    # Every submission link, unconditionally - NOT just the ones layer 1 happened to reach.
    # The browser confirms before anything counts as dead (contract 5.2: only 404/410 disprove,
    # and a plain-HTTP 404 is never sufficient on its own).
    print("\n--- submission links (all rows, independent of verify_state) ---")
    dead_links = check_all_submission_links(a.db, use_browser=not a.no_browser)

    # Integrity BEFORE reporting. A digest computed over a database that lost rows is a
    # confident answer to the wrong question, so violations lead the digest.
    print("\n--- database invariants ---")
    inv = subprocess.run([py, "scripts/check_invariants.py", "--db", a.db,
                          "--seed-dir", a.seed_dir], cwd=str(cwd),
                         capture_output=True, text=True)
    print(inv.stdout.rstrip())
    invariants_ok = inv.returncode == 0

    after = snapshot(a.db)
    digest, changed = build_digest(before, after, label, today, open_issues=len(dead_links))
    if not invariants_ok:
        head = ["> **DATABASE INVARIANTS VIOLATED - read this before trusting anything below.**",
                "> The figures in this digest are computed over a database that failed its",
                "> integrity checks.", "", "```", inv.stdout.strip(), "```", ""]
        lines = digest.split("\n")
        digest = "\n".join(lines[:2] + head + lines[2:])
        changed += 1
    if dead_links:
        lines = [f"## Dead submission links ({len(dead_links)})",
                 "Browser-confirmed. A client clicking these reaches nothing.", ""]
        lines += [f"- **{n}** - {u}" for _, n, u in sorted(dead_links, key=lambda x: x[1])]
        digest = digest.replace("## Current totals", "\n".join(lines) + "\n\n## Current totals")
        changed += len(dead_links)
    print("\n" + digest)

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report = out / f"weekly_verify_{stamp}.md"
    report.write_text(digest, encoding="utf-8")
    print(f"wrote {report}")

    if not invariants_ok:
        print("\n*** INVARIANTS VIOLATED - see the digest. Do not act on these figures "
              "until the database is reconciled. ***")

    if a.dry_run:
        print("dry run - no email sent")
    elif os.getenv("CFP_SMTP_HOST"):
        subject = (f"CFP weekly verification - {changed} issue(s)" if changed
                   else "CFP weekly verification - all clear")
        print("emailed digest" if maybe_send_email(subject, digest)
              else "SMTP configured but send failed")
    else:
        print("no CFP_SMTP_HOST set - digest written to disk only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
