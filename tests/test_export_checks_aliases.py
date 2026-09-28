"""A renamed event's check must reach the page under THIS week's id (2026-09-28).

Identity is carried through research, so one canonical id can have several upstream ids (old and
new names). export_checks used to emit one - the first found, usually an old one - and the page,
which joins on the delivery's current upstream id, found 10 of 36 checked conferences.
"""
import csv
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_every_upstream_alias_gets_the_check(tmp_path):
    db = tmp_path / "cfp_monitor.db"
    con = sqlite3.connect(db)
    con.execute("create table grounding_facts (event_id text, deadline_evidence_url text, deadline text)")
    con.execute("create table evidence (event_id text, field text, verdict text, source_url text, "
                "found_quote text, quote text, detail text, fetched_at text, origin text)")
    con.execute("insert into grounding_facts values ('zz-test-event-canon', 'https://wfcc.example/cfp', '2026-07-08')")
    con.execute("insert into evidence values ('zz-test-event-canon', 'deadline', 'verified', "
                "'https://wfcc.example/cfp', 'Abstracts due July 8, 2026', '', '', '2026-09-28', 'grounding')")
    con.commit(); con.close()
    (tmp_path / "market_sheets").mkdir()
    with open(tmp_path / "market_sheets" / "utility_seed.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["EVENT_ID", "EVENT_ID_CANON", "CONFERENCE"])
        w.writerow(["zz-old-name-speaking", "zz-test-event-canon", "WFCC 2026"])                     # old name
        w.writerow(["zz-new-name-speaking", "zz-test-event-canon", "World Fuel Cell Conference 2026"])  # this week
    out = tmp_path / "checks.csv"
    rc = subprocess.run([sys.executable, str(ROOT / "scripts" / "export_checks.py"), "--db", str(db),
                         "-o", str(out)], capture_output=True, text=True).returncode
    assert rc == 0
    ids = {r["EVENT_ID"] for r in csv.DictReader(open(out, encoding="utf-8"))}
    assert ids == {"zz-old-name-speaking",
                   "zz-new-name-speaking"}
