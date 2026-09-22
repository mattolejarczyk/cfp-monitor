"""verify_dates promotes a conference_dates claim to verified against the table's unique key, and
never creates a duplicate (the bug that crashed the first run: INSERT collided with the crawl row).
"""
import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("_vd", ROOT / "scripts" / "verify_dates.py")
vd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vd)


def _evidence_db():
    con = sqlite3.connect(":memory:")
    con.execute("""CREATE TABLE evidence (id INTEGER PRIMARY KEY, event_id TEXT, field TEXT,
        value_claimed TEXT, source_url TEXT, quote TEXT, origin TEXT, method TEXT, fetched_at TEXT,
        verdict TEXT, found_quote TEXT, detail TEXT, call_type TEXT, exportable INT, export_block TEXT)""")
    con.execute("CREATE UNIQUE INDEX ux ON evidence(event_id, field, source_url, origin)")
    # the pre-existing crawl claim: scraped, not proven
    con.execute("INSERT INTO evidence (event_id, field, value_claimed, source_url, quote, origin, "
                "method, verdict, found_quote, exportable) VALUES "
                "('a','conference_dates','2027-04-05','http://x','','crawl','crawl','no_quote','',0)")
    con.commit()
    return con


def test_upsert_promotes_the_existing_crawl_row_no_duplicate():
    con = _evidence_db()
    vd.write_verified(con, "a", "2027-04-05", "http://x", "the conference is held April 5, 2027")
    rows = con.execute("SELECT verdict, found_quote, method, exportable FROM evidence "
                       "WHERE event_id='a' AND field='conference_dates'").fetchall()
    assert len(rows) == 1                                   # promoted, not duplicated
    assert rows[0][0] == "verified" and "April 5, 2027" in rows[0][1]
    assert rows[0][2] == "date-context" and rows[0][3] == 1


def test_upsert_on_a_new_page_inserts_a_second_row():
    con = _evidence_db()
    vd.write_verified(con, "a", "2027-04-05", "http://other", "held April 5, 2027")
    assert con.execute("SELECT COUNT(*) FROM evidence WHERE event_id='a'").fetchone()[0] == 2
