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


# Every URL the review page can put in front of the customer. The sweep must cover all of
# them, not just the one we started with: on 2026-08-12 the page offered 24 dead evidence
# links and 2 dead event sites, because only submission_url had ever been checked and the
# page had nothing to consult about the rest.
CUSTOMER_FACING = ("submission_url", "deadline_evidence_url", "main_info_url", "url")


def check_all_submission_links(
        db: str, use_browser: bool = True
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """Check EVERY link the customer can click, regardless of what verification concluded.

    verify_grounding stops at the first layer that resolves a row, so a conference that
    verifies at L0 ("the page says the call is open") never reaches the L1 link check. On
    2026-08-08 that hid 9 dead links out of 46, including CES 2027 - verified open, submit
    link dead. The customer-facing link is too important to be checked only as a fallback.

    Widened 2026-08-12 from submission_url alone to every field in CUSTOMER_FACING. The
    review page renders all of them; checking one and rendering four is how we shipped a
    working-looking link to a page we already knew was gone.

    Returns TWO lists of (event_id, name, url): links that went dead SINCE THE LAST RUN, and
    the standing backlog that was already dead. A plain-HTTP 404 is never sufficient on its own
    (contract 5.2), so the browser confirms before anything is recorded.

    The split exists because on 2026-08-27 the digest reported 119 dead links of which ZERO
    were new - all 80 distinct URLs had been in the 2026-08-16 digest too. A weekly report that
    re-sends the same backlog trains the reader to skip it, which is precisely when a genuinely
    new failure gets missed.
    """
    import asyncio
    import sqlite3 as _sq

    sys.path.insert(0, str(ROOT / "scripts"))
    from src.cfp_monitor.verify import link_status                  # noqa: PLC0415
    from recheck_dead_links import browser_check                    # noqa: PLC0415

    con = _sq.connect(db)
    con.row_factory = _sq.Row
    # url -> {event_id: name}. A DICT, not a list, and this is the whole of the duplicate fix:
    # one URL commonly sits in several of the four fields of the SAME row (Biomass and Argus
    # each hold theirs in all four), and appending per field emitted the same event four times.
    # On 2026-08-27 that turned 80 dead URLs into a 119-line report. The report is about which
    # EVENT has a broken link, so (event, url) is the unit - the field it came from is
    # provenance, tracked separately below rather than by repeating the line.
    by_url: dict[str, dict[str, str]] = {}
    url_fields: dict[str, set[str]] = {}
    for r in con.execute("select * from grounding_facts"):
        keys = r.keys()
        for field in CUSTOMER_FACING:
            if field not in keys:
                continue
            u = (r[field] or "").strip()
            if u.startswith("http"):
                by_url.setdefault(u, {})[r["event_id"]] = r["name"] or r["event_id"]
                url_fields.setdefault(u, set()).add(field)
    con.close()

    def expand(urls) -> list[tuple[str, str, str]]:
        return [(eid, name, u) for u in urls for eid, name in by_url[u].items()]

    print(f"  checking {len(by_url)} distinct customer-facing link(s) "
          f"across {len(CUSTOMER_FACING)} field(s)")

    # Keep the fast-pass status instead of discarding it - it is the difference between
    # "this URL 404s" and "we have no idea what this URL does", and the history table below
    # cannot answer the operator's question without it.
    status: dict[str, int] = {u: link_status(u)[0] for u in by_url}
    suspect = [u for u in by_url if status[u] in (404, 410)]
    print(f"  {len(suspect)} returned 404/410 on the fast pass")

    # NOTE the absence of an early return. Until 2026-08-27 a run with no 404s returned before
    # writing anything, so a week in which every link worked recorded NOTHING - and `last_alive`,
    # the column that distinguishes "broke recently" from "never worked", was only ever set on
    # weeks that happened to contain a failure. A clean week is data too.
    unconfirmed = False
    if suspect and not use_browser:
        print("  --no-browser: reporting fast-pass results unconfirmed")
        dead, unconfirmed = list(suspect), True
    elif suspect:
        res = asyncio.run(browser_check(suspect))
        dead = [u for u in suspect if res.get(u, ("", 0, 0))[0] != "ALIVE"]
        for u in suspect:                   # the browser's status beats the fast pass
            if res.get(u) and res[u][1]:
                status[u] = res[u][1]
        print(f"  {len(dead)} confirmed dead by browser; "
              f"{len(suspect) - len(dead)} were false 404s (blocked, not dead)")
    else:
        dead = []

    # Persist to a SIDE table. grounding_facts.verify_state cannot hold this: a row can have
    # a correctly verified deadline AND a dead submit link (CES 2027 does), and one state
    # column cannot say both. A separate table also leaves import and verify untouched.
    con = _sq.connect(db)
    con.execute("""create table if not exists link_checks (
                     url text primary key, state text, checked_at text)""")
    # HISTORY. Until 2026-08-27 this table was (url, state, checked_at) with url as the primary
    # key, so every run overwrote the row and the table could not answer the only two questions
    # anyone actually asks of it: did this break recently, or has it never worked? Of the 80
    # links reported dead that day, exactly 4 could be shown to have ever served us a quote -
    # and that came from the evidence table, not from here.
    have = {r[1] for r in con.execute("pragma table_info(link_checks)")}
    for col in ("http_status integer", "first_seen text", "last_alive text"):
        if col.split()[0] not in have:
            con.execute(f"alter table link_checks add column {col}")

    # Read the PREVIOUS dead set before overwriting it - this is what makes a "new since last
    # run" section possible. Without it the digest re-sent the same standing backlog every week
    # and a genuinely new failure was indistinguishable from 80 lines of old news.
    was_dead = {r[0] for r in con.execute("select url from link_checks where state != 'alive'")}

    now = datetime.now().isoformat(timespec="seconds")
    dead_set = set(dead)
    con.executemany(
        """insert into link_checks (url, state, checked_at, http_status, first_seen, last_alive)
           values (:u, :s, :t, :h, :t, case when :s = 'alive' then :t else null end)
           on conflict(url) do update set
             state       = excluded.state,
             checked_at  = excluded.checked_at,
             http_status = excluded.http_status,
             first_seen  = coalesce(link_checks.first_seen, excluded.first_seen),
             last_alive  = case when excluded.state = 'alive' then excluded.checked_at
                                else link_checks.last_alive end""",
        [{"u": u, "s": "dead" if u in dead_set else "alive", "t": now,
          "h": status.get(u)} for u in by_url])
    con.commit()
    con.close()

    # An unconfirmed (--no-browser) sweep must not silently reclassify the backlog as new, so
    # it reports everything as standing rather than inventing a week's worth of news.
    if unconfirmed:
        return [], expand(dead)
    newly = [u for u in dead if u not in was_dead]
    standing = [u for u in dead if u in was_dead]
    print(f"  {len(newly)} NEW since the last run, {len(standing)} standing backlog")
    return expand(newly), expand(standing)


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
    new_dead, standing_dead = check_all_submission_links(a.db, use_browser=not a.no_browser)
    dead_links = new_dead + standing_dead

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
    # NEW first and STANDING second, because they demand different things of the reader. A new
    # dead link is this week's news and needs a decision; the backlog needs a hand-back to
    # upstream, which is not a weekly-email-sized action.
    if new_dead or standing_dead:
        lines: list[str] = []
        if new_dead:
            lines += [f"## NEW dead links since the last run ({len(new_dead)})",
                      "**This is the week's actual news.** Browser-confirmed: a client clicking "
                      "these reaches nothing.", ""]
            lines += [f"- **{n}** - {u}" for _, n, u in sorted(new_dead, key=lambda x: x[1])]
            lines += [""]
        if standing_dead:
            lines += [f"## Standing backlog - already dead before this run ({len(standing_dead)})",
                      "Unchanged since last week. These are upstream's fields, so clearing them "
                      "is a hand-back,",
                      "not a re-check - re-running the sweep will not move this number.", ""]
            lines += [f"- **{n}** - {u}" for _, n, u in sorted(standing_dead, key=lambda x: x[1])]
            lines += [""]
        digest = digest.replace("## Current totals", "\n".join(lines) + "\n## Current totals")
        # Only NEW failures count as "issues" for the subject line. Counting the backlog made
        # every week look equally alarming, which is the same as no signal at all.
        changed += len(new_dead)
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
