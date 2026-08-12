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

    if not dead:
        print(f"OK - all {len(uses)} hosts resolve.")
        if a.output:
            Path(a.output).write_text("", encoding="utf-8")
        return 0

    fields = sum(len(v) for v in dead.values())
    print(f"{len(dead)} HOST(S) DO NOT RESOLVE, across {fields} field(s):\n")
    for h, v in sorted(dead.items()):
        print(f"  {h}")
        for conf, col in sorted(v):
            print(f"      {conf:<46} {col}")
    print("\nThese are links a customer clicks and gets nothing. Find the replacement by")
    print("AUTHORITY - the organiser's own site linking to it - not by a name that looks right.")

    if a.output:
        Path(a.output).write_text("\n".join(sorted(dead)) + "\n", encoding="utf-8")
        print(f"\nwrote {a.output}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
