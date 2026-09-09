"""Link-check the awards rows, into the same `link_checks` table the customer page reads.

WHY THIS IS A SEPARATE SCRIPT AND NOT A FLAG ON weekly_verify.py
`weekly_verify.py` collects its URLs with `select * from grounding_facts` - conference rows,
and only conference rows. Awards live in `award_grounding_facts`, so none of their links has
ever been checked. That is why the awards page renders an em dash and "not yet checked": the
count is honestly absent, not zero.

The two pipelines stay apart by instruction, so this is a sibling rather than a branch.

WHAT IS DELIBERATELY SHARED
`link_checks` itself. **It is keyed by URL, not by event**, so it was already domain-neutral -
the conference scoping lived entirely in which rows got harvested. A second table would have
split one fact ("does this URL resolve") across two places and left the page having to ask
both. So: one table, two collectors.

Also shared: `verify.link_status` for the fast pass and `recheck_dead_links.browser_check` for
the escalation. A plain-HTTP 404 is never sufficient evidence that a page is gone - the awards
delivery proved it again on 2026-09-08, where three URLs that looked dead to a script were
genuinely dead, and where several conference URLs on other days looked dead and were merely
blocked. The browser settles it.

THREE BEHAVIOURS COPIED ON PURPOSE, EACH FROM A BUG
  * `by_url` is a DICT, not a list. One URL commonly sits in several of the four fields of the
    SAME row, and appending per field reported the same event four times over (2026-08-27: 80
    dead URLs became a 119-line report).
  * NO EARLY RETURN when nothing is dead. A run that finds every link healthy must still write,
    or `last_alive` is only ever set in weeks that happened to contain a failure. A clean week
    is data too.
  * The fast-pass HTTP status is KEPT, not discarded. It is the difference between "this URL
    404s" and "we have no idea what this URL does".

Reports by default. `--apply` backs the database up first, then writes.
"""
from __future__ import annotations

import argparse
import asyncio
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

# The same four fields weekly_verify checks, and they all exist on the award table. Named here
# rather than imported so a change to the conference list cannot silently change this one -
# which is the separation the two pipelines are kept apart for.
CUSTOMER_FACING = ("submission_url", "deadline_evidence_url", "main_info_url", "url")


def collect(db: str) -> tuple[dict[str, dict[str, str]], dict[str, set[str]]]:
    """url -> {event_id: name}, and url -> the fields it came from."""
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    by_url: dict[str, dict[str, str]] = {}
    url_fields: dict[str, set[str]] = {}
    for r in con.execute("select * from award_grounding_facts"):
        keys = r.keys()
        for field in CUSTOMER_FACING:
            if field not in keys:
                continue
            u = (r[field] or "").strip()
            if u.startswith("http"):
                by_url.setdefault(u, {})[r["event_id"]] = r["name"] or r["event_id"]
                url_fields.setdefault(u, set()).add(field)
    con.close()
    return by_url, url_fields


def write(db: str, by_url: dict, status: dict[str, int], dead: list[str]) -> tuple[int, int]:
    con = sqlite3.connect(db)
    con.execute("""create table if not exists link_checks (
                     url text primary key, state text, checked_at text)""")
    have = {r[1] for r in con.execute("pragma table_info(link_checks)")}
    for col in ("http_status integer", "first_seen text", "last_alive text"):
        if col.split()[0] not in have:
            con.execute(f"alter table link_checks add column {col}")

    before = {r[0] for r in con.execute("select url from link_checks")}
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
    after = {r[0] for r in con.execute("select url from link_checks")}
    con.close()
    return len(after - before), len(by_url) - len(after - before)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--no-browser", action="store_true",
                    help="skip the browser escalation; fast-pass 404s are then UNCONFIRMED")
    ap.add_argument("--limit", type=int, help="check only the first N distinct URLs")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    from src.cfp_monitor.verify import link_status                   # noqa: PLC0415

    by_url, url_fields = collect(a.db)
    if a.limit:
        by_url = dict(list(by_url.items())[:a.limit])
    if not by_url:
        print("no awards rows carry a customer-facing http link - nothing to check.")
        return 0

    events = {e for m in by_url.values() for e in m}
    print(f"{len(by_url)} distinct link(s) across {len(events)} award(s), "
          f"{len(CUSTOMER_FACING)} field(s)")

    status: dict[str, int] = {u: link_status(u)[0] for u in by_url}
    suspect = [u for u in by_url if status[u] in (404, 410)]
    print(f"  {len(suspect)} returned 404/410 on the fast pass")

    unconfirmed = False
    if suspect and a.no_browser:
        print("  --no-browser: reporting fast-pass results UNCONFIRMED")
        dead, unconfirmed = list(suspect), True
    elif suspect:
        from recheck_dead_links import browser_check                 # noqa: PLC0415
        res = asyncio.run(browser_check(suspect))
        dead = [u for u in suspect if res.get(u, ("", 0, 0))[0] != "ALIVE"]
        for u in suspect:                    # the browser's status beats the fast pass
            if res.get(u) and res[u][1]:
                status[u] = res[u][1]
        print(f"  {len(dead)} confirmed dead by browser; "
              f"{len(suspect) - len(dead)} were false 404s (blocked, not dead)")
    else:
        dead = []

    if dead:
        print(f"\ndead link(s) on {len({e for u in dead for e in by_url[u]})} award(s):")
        for u in sorted(dead):
            for _eid, name in sorted(by_url[u].items(), key=lambda kv: kv[1]):
                print(f"  {name[:46]:<46} {sorted(url_fields.get(u, ()))}")
                print(f"    {u[:104]}")
    if unconfirmed:
        print("\n  NOTE: unconfirmed. A plain-HTTP 404 is not sufficient evidence that a page "
              "is gone;\n  re-run without --no-browser before acting on any of these.")

    if not a.apply:
        print("\nreport only. Re-run with --apply to write to link_checks.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f"{a.db}.backup-pre-awardlinks-{stamp}.db"
    shutil.copy(a.db, backup)
    print(f"\nbackup   {Path(backup).name}")
    new, updated = write(a.db, by_url, status, dead)
    print(f"written  {new} new url(s), {updated} refreshed")
    print(f"         {len(dead)} dead, {len(by_url) - len(dead)} alive")
    return 0


if __name__ == "__main__":
    sys.exit(main())
