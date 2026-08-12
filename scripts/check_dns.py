"""Does every host we cite still exist? The cheapest check we were not doing.

WHY THIS IS SEPARATE FROM THE LINK CHECKER
`link_checks` asks what a page RETURNS. This asks whether the host exists at all, and those
fail differently. A domain that has lapsed does not 404 - the request never reaches a server,
so it surfaces as a timeout or a connection error, which the ladder is deliberately built to
treat as "blocked, not disproven" (contract 5.2). That rule is right for a site defending
itself against automation and exactly wrong for a domain that is gone. So a dead host looked
identical to a live one behind a firewall, and nothing ever said otherwise.

Found on 2026-08-11: 6 of 403 hosts in the delivery did not resolve, across 15 customer-facing
URL fields. Those are links a customer clicks and gets nothing - worse than a 404, which at
least shows a page.

DNS is nearly free. A whole delivery sweeps in seconds and needs no browser, so there is no
reason not to run it before every send.

    python scripts/check_dns.py -i <delivery.csv> [--db <live.db>] [-o dead_hosts.txt]

Exits non-zero when anything fails to resolve, so it can gate a delivery.

ONE TRAP, LEARNED THE HARD WAY. A host resolving is not a host being the right one. `ablc.co`
resolves, loads, and reads fine - it is a medspa, not the Advanced Bioeconomy Leadership
Conference. This check answers "does it exist", never "is it the right site".
"""
from __future__ import annotations

import argparse
import csv
import socket
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

URL_COLUMNS = ("SUBMISSION URL", "CFP_SUBMISSION_URL", "DEADLINE_EVIDENCE_URL", "MAIN_INFO_URL",
               "CONFERENCE URL", "VENUE_EVIDENCE_URL", "LIFECYCLE_EVIDENCE_URL", "URL")
DB_COLUMNS = ("submission_url", "deadline_evidence_url", "main_info_url", "url")


def resolves(host: str) -> bool:
    try:
        socket.getaddrinfo(host, None)
        return True
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Check every cited host still resolves.")
    ap.add_argument("-i", "--input", help="delivery CSV")
    ap.add_argument("--db", help="also sweep the database")
    ap.add_argument("-o", "--output", help="write the dead hosts here, one per line")
    ap.add_argument("--also", action="append",
                    help="another dead-host list to fold in. Repeatable. Use for hosts known "
                         "dead from earlier runs whose URLs still sit in stored evidence.")
    ap.add_argument("--timeout", type=float, default=5.0)
    a = ap.parse_args()
    if not a.input and not a.db:
        ap.error("give -i, --db, or both")
    socket.setdefaulttimeout(a.timeout)

    uses: dict[str, set] = defaultdict(set)

    if a.input:
        with open(a.input, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        for r in rows:
            for c in URL_COLUMNS:
                u = (r.get(c) or "").strip()
                if u.startswith("http"):
                    h = urlparse(u).netloc.lower()
                    if h:
                        uses[h].add((r.get("CONFERENCE", "?")[:44], f"csv:{c}"))
        print(f"csv : {len(rows)} rows")

    if a.db:
        con = sqlite3.connect(a.db)
        con.row_factory = sqlite3.Row
        n = 0
        for r in con.execute(f"select name, {', '.join(DB_COLUMNS)} from grounding_facts"):
            n += 1
            for c in DB_COLUMNS:
                u = (r[c] or "").strip()
                if u.startswith("http"):
                    h = urlparse(u).netloc.lower()
                    if h:
                        uses[h].add((r["name"][:44], f"db:{c}"))
        print(f"db  : {n} rows")

    print(f"\n{len(uses)} distinct host(s) to resolve...\n")
    dead = {h: v for h, v in uses.items() if not resolves(h)}

    # THE LIST ACCUMULATES. A host that stopped resolving does not come back, and a URL
    # recorded against it stays unclickable forever - "Page we checked" keeps pointing at the
    # page an audit read on the day. Overwriting with today's findings emptied the list the
    # moment we fixed the live data, which would have let the page offer those dead links
    # again. Found before the first full run, not after.
    prior: set[str] = set()
    if a.output and Path(a.output).exists():
        prior = {ln.strip().lower() for ln in Path(a.output).read_text(encoding="utf-8").splitlines()
                 if ln.strip()}
    for extra in (a.also or []):
        p = Path(extra)
        if p.exists():
            prior |= {ln.strip().lower() for ln in p.read_text(encoding="utf-8").splitlines()
                      if ln.strip()}

    def _write(found: dict) -> None:
        if not a.output:
            return
        allhosts = sorted(prior | set(found))
        Path(a.output).write_text("\n".join(allhosts) + ("\n" if allhosts else ""),
                                  encoding="utf-8")
        carried = len(allhosts) - len(found)
        print(f"\nwrote {a.output}  ({len(found)} found now"
              f"{f', {carried} carried from previous runs' if carried > 0 else ''})")

    if not dead:
        print(f"OK - all {len(uses)} hosts resolve.")
        _write({})
        return 0

    fields = sum(len(v) for v in dead.values())
    print(f"{len(dead)} HOST(S) DO NOT RESOLVE, across {fields} field(s):\n")
    for h, v in sorted(dead.items()):
        print(f"  {h}")
        for conf, col in sorted(v):
            print(f"      {conf:<46} {col}")
    print("\nThese are links a customer clicks and gets nothing. Find the replacement by")
    print("AUTHORITY - the organiser's own site linking to it - not by a name that looks right.")

    _write(dead)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
