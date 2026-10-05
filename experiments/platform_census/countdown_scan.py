"""ACT-25 (2026-10-05): does a countdown timer on a page signal the next edition? READ-ONLY: opens the offline page library (mode=ro) and the database (mode=ro), fetches nothing.

    python experiments/platform_census/countdown_scan.py [--library <page_library.db>] [--db <cfp_monitor.db>]

Finds pages whose saved text holds a countdown ('Starts: 132 DAYS 13 HOURS 14 MIN'), turns it into the date it counts to (the page's last_fetched_at plus the remaining time, UTC) and sets that against the
start date we store for an event on the same host. Result and recommendation: experiments/platform_census/RESULT-countdown-timer.md."""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

PATTERNS = [re.compile(r"(?i)\b(\d{1,3})\s*(?:days?)\b[\s:,]{0,6}(\d{1,2})\s*(?:hours?|hrs?)\b[\s:,]{0,6}(\d{1,2})\s*(?:min(?:ute)?s?)\b"),
            re.compile(r"(?i)\b(\d{1,3})\s*\n?\s*days?\s*\n?\s*(\d{1,2})\s*\n?\s*hours?")]


def implied_date(fetched_at: str, days: int, hours: int, minutes: int = 0) -> datetime:
    """When a countdown that read `days` `hours` `minutes` at `fetched_at` (ISO, UTC) reaches zero."""
    return datetime.fromisoformat(fetched_at.replace("Z", "")) + timedelta(days=days, hours=hours, minutes=minutes)


def find_countdown(text: str) -> tuple[int, int, int, str] | None:
    """(days, hours, minutes, the words before it) for the first countdown in the text, or None. The words before it say WHAT it counts to ('Starts:', 'Pre-Registration Sales End In')."""
    for pat in PATTERNS:
        m = pat.search(text or "")
        if m:
            g = [int(x) for x in m.groups()]
            return g[0], g[1], (g[2] if len(g) > 2 else 0), re.sub(r"\s+", " ", text[max(0, m.start() - 60): m.start()]).strip()
    return None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--library", default=str(Path(__file__).resolve().parents[2] / "page_library" / "page_library.db"))
    ap.add_argument("--db", default=str(Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor" / "cfp_monitor.db"))
    a = ap.parse_args()
    lib = sqlite3.connect(f"file:{a.library.replace(chr(92), '/')}?mode=ro", uri=True)
    rows = lib.execute("select url, host, last_fetched_at, text from pages where coalesce(blocked,0)=0 and text is not null and length(text) > 200").fetchall()
    db = sqlite3.connect(f"file:{a.db.replace(chr(92), '/')}?mode=ro", uri=True)
    starts: dict[str, list] = {}
    for name, start, ed, st, u1, u2 in db.execute("select name, start_date, edition, status, url, main_info_url from grounding_facts"):
        for u in (u1, u2):
            h = urlparse(u).netloc.lower().removeprefix("www.") if u else ""
            if h:
                starts.setdefault(h, []).append((name, start, ed, st))
    hits = 0
    for url, host, fetched, text in rows:
        cd = find_countdown(text)
        if not cd:
            continue
        hits += 1
        when = implied_date(fetched, *cd[:3])
        print(f"{url}\n   '{cd[3]}' {cd[0]}d {cd[1]}h {cd[2]}m at {fetched} -> counts to {when:%Y-%m-%d %H:%M} UTC")
        for name, start, ed, st in starts.get(host.removeprefix("www."), [])[:3]:
            print(f"   stored: {name[:56]} | start {start} | edition {ed} | {st}")
    print(f"\n{hits} of {len(rows)} readable pages hold a countdown")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
