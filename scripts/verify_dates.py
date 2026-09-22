"""Verify conference DATES verbatim against their cited page - the same proof bar as deadlines.

THE GAP THIS CLOSES (found 2026-09-22 via the evidence matrix): conference dates were scraped
(origin=crawl) but never verbatim-verified - 0 of 547 date claims carried a proven quote, so the
evidence matrix showed the Dates column as unproven. This fetches each conference's page and, if
its start date is stated there IN AN EVENT CONTEXT ("the conference is held ..."), records a
VERIFIED conference_dates evidence row with the sentence found. Deterministic (no LLM, no quota);
report-only by default, `--apply` writes.

Idempotent: it replaces only its OWN prior rows (method='date-context'), never the original crawl
rows. The matrix then prefers the verified one. Reuses self_heal.find_conference_dates_sentence.
"""
import argparse
import sqlite3
import sys
import time
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.cfp_monitor.self_heal import find_conference_dates_sentence  # noqa: E402
from src.cfp_monitor.verify import fetch_text                         # noqa: E402


def candidates(con, limit):
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT event_id, name, start_date, deadline_evidence_url, url, main_info_url "
        "FROM grounding_facts WHERE COALESCE(start_date,'')<>'' "
        "AND (deadline_evidence_url LIKE 'http%' OR url LIKE 'http%' OR main_info_url LIKE 'http%') "
        "ORDER BY start_date").fetchall()
    return rows[:limit] if limit else rows


def verify_one(row):
    """(found, url, quote). Try the row's pages in order; stop at the first that proves the date."""
    for url in (row["deadline_evidence_url"], row["url"], row["main_info_url"]):
        if url and url.startswith("http"):
            text, _note = fetch_text(url)
            found, quote = find_conference_dates_sentence(text, row["start_date"])
            if found:
                return True, url, quote
    return False, "", ""


def write_verified(con, event_id, start_date, url, quote):
    """Upsert on the table's unique key (event_id, field, source_url, origin): if a crawl row for
    this date/page exists, promote it to verified; else insert. Idempotent, never a duplicate."""
    con.execute(
        "INSERT INTO evidence (event_id, field, value_claimed, source_url, quote, origin, method, "
        "fetched_at, verdict, found_quote, detail, call_type, exportable, export_block) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(event_id, field, source_url, origin) DO UPDATE SET "
        "verdict='verified', found_quote=excluded.found_quote, method=excluded.method, "
        "fetched_at=excluded.fetched_at, detail=excluded.detail, exportable=1, "
        "value_claimed=excluded.value_claimed",
        (event_id, "conference_dates", start_date, url, "", "crawl", "date-context",
         datetime.now().isoformat(timespec="seconds"), "verified", quote,
         "verbatim date on the cited page, in an event context", "", 1, ""))


def main() -> int:
    ap = argparse.ArgumentParser(description="Verbatim-verify conference dates against their pages.")
    ap.add_argument("--db", required=True)
    ap.add_argument("--limit", type=int, default=0, help="cap rows this run (0 = all)")
    ap.add_argument("--delay", type=float, default=0.3, help="polite gap between page fetches")
    ap.add_argument("--apply", action="store_true", help="write verified rows (default: report only)")
    a = ap.parse_args()

    con = sqlite3.connect(a.db)
    rows = candidates(con, a.limit)
    verified = unproven = unreadable = 0
    for row in rows:
        found, url, quote = verify_one(row)
        if found:
            verified += 1
            if a.apply:
                write_verified(con, row["event_id"], row["start_date"], url, quote)
        elif any((row[k] or "").startswith("http") for k in ("deadline_evidence_url", "url", "main_info_url")):
            unproven += 1
        else:
            unreadable += 1
        if a.delay:
            time.sleep(a.delay)
    if a.apply:
        con.commit()
    print(f"conference dates ({'APPLIED' if a.apply else 'report-only'}): {len(rows)} checked | "
          f"{verified} verified | {unproven} value-but-unproven")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
