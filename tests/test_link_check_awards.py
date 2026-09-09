"""The awards link-check collector.

The three behaviours pinned here were each a bug on the conference side first, and copying
them without a test would be copying the shape and not the reason.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("lca", ROOT / "scripts" / "link_check_awards.py")
lca = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lca)

from src.cfp_monitor.storage import Store              # noqa: E402


def _db(tmp_path, awards=(), conferences=()):
    p = tmp_path / "t.db"
    Store(str(p)).db.close()
    con = sqlite3.connect(str(p))
    for a in awards:
        cols = ", ".join(a)
        marks = ", ".join("?" for _ in a)
        con.execute(f"insert into award_grounding_facts ({cols}) values ({marks})",
                    list(a.values()))
    for c in conferences:
        cols = ", ".join(c)
        marks = ", ".join("?" for _ in c)
        con.execute(f"insert into grounding_facts ({cols}) values ({marks})", list(c.values()))
    con.commit()
    con.close()
    return str(p)


# ---- collection ------------------------------------------------------------------------
def test_collects_all_four_customer_facing_fields(tmp_path):
    db = _db(tmp_path, awards=[{
        "event_id": "a1", "name": "An Award",
        "submission_url": "https://a.test/enter",
        "deadline_evidence_url": "https://a.test/dates",
        "main_info_url": "https://a.test/about",
        "url": "https://a.test/",
    }])
    by_url, fields = lca.collect(db)
    assert len(by_url) == 4
    assert fields["https://a.test/enter"] == {"submission_url"}


def test_one_url_in_several_fields_of_one_row_is_ONE_entry(tmp_path):
    """The 2026-08-27 bug: appending per field turned 80 dead URLs into a 119-line report."""
    same = "https://a.test/"
    db = _db(tmp_path, awards=[{
        "event_id": "a1", "name": "An Award", "submission_url": same,
        "deadline_evidence_url": same, "main_info_url": same, "url": same,
    }])
    by_url, fields = lca.collect(db)
    assert list(by_url) == [same]
    assert by_url[same] == {"a1": "An Award"}, "one event, once"
    assert len(fields[same]) == 4, "but provenance keeps all four field names"


def test_one_url_shared_by_two_awards_keeps_both(tmp_path):
    same = "https://cloud-awards.test/programs/"
    db = _db(tmp_path, awards=[
        {"event_id": "a1", "name": "Security Awards", "main_info_url": same},
        {"event_id": "a2", "name": "SaaS Awards", "main_info_url": same},
    ])
    by_url, _ = lca.collect(db)
    assert by_url[same] == {"a1": "Security Awards", "a2": "SaaS Awards"}


def test_non_http_and_blank_values_are_ignored(tmp_path):
    db = _db(tmp_path, awards=[{"event_id": "a1", "name": "An Award",
                                "submission_url": "", "main_info_url": "TBD",
                                "url": "mailto:x@y.test"}])
    by_url, _ = lca.collect(db)
    assert by_url == {}


def test_conference_rows_are_not_collected(tmp_path):
    """The separation, asserted rather than assumed."""
    db = _db(tmp_path,
             awards=[{"event_id": "a1", "name": "An Award",
                      "url": "https://award.test/"}],
             conferences=[{"event_id": "c1", "name": "A Conference",
                           "url": "https://conference.test/"}])
    by_url, _ = lca.collect(db)
    assert list(by_url) == ["https://award.test/"]


# ---- writing ---------------------------------------------------------------------------
def test_a_clean_run_still_writes(tmp_path):
    """No early return: a week in which every link works is data too, and it is the only way
    last_alive ever gets set."""
    db = _db(tmp_path, awards=[{"event_id": "a1", "name": "An Award",
                                "url": "https://a.test/"}])
    by_url, _ = lca.collect(db)
    new, _ = lca.write(db, by_url, {"https://a.test/": 200}, dead=[])
    con = sqlite3.connect(db)
    row = con.execute("select state, http_status, first_seen, last_alive "
                      "from link_checks").fetchone()
    con.close()
    assert new == 1
    assert row[0] == "alive" and row[1] == 200
    assert row[3] is not None, "an alive result must set last_alive"


def test_a_dead_url_records_its_status_and_leaves_last_alive_null(tmp_path):
    db = _db(tmp_path, awards=[{"event_id": "a1", "name": "An Award",
                                "url": "https://a.test/"}])
    by_url, _ = lca.collect(db)
    lca.write(db, by_url, {"https://a.test/": 404}, dead=["https://a.test/"])
    con = sqlite3.connect(db)
    row = con.execute("select state, http_status, last_alive from link_checks").fetchone()
    con.close()
    assert row[0] == "dead" and row[1] == 404 and row[2] is None


def test_a_url_that_recovers_keeps_its_first_seen_and_gains_last_alive(tmp_path):
    """first_seen answers 'has this ever worked', which one overwriting row cannot."""
    db = _db(tmp_path, awards=[{"event_id": "a1", "name": "An Award",
                                "url": "https://a.test/"}])
    by_url, _ = lca.collect(db)
    lca.write(db, by_url, {"https://a.test/": 404}, dead=["https://a.test/"])
    con = sqlite3.connect(db)
    first = con.execute("select first_seen from link_checks").fetchone()[0]
    con.close()

    lca.write(db, by_url, {"https://a.test/": 200}, dead=[])
    con = sqlite3.connect(db)
    row = con.execute("select state, first_seen, last_alive from link_checks").fetchone()
    n = con.execute("select count(*) from link_checks").fetchone()[0]
    con.close()
    assert n == 1, "url is the primary key; a recheck updates rather than appends"
    assert row[0] == "alive" and row[1] == first and row[2] is not None


def test_writing_awards_links_does_not_disturb_conference_ones(tmp_path):
    db = _db(tmp_path, awards=[{"event_id": "a1", "name": "An Award",
                                "url": "https://award.test/"}])
    con = sqlite3.connect(db)
    con.execute("""create table if not exists link_checks (
                     url text primary key, state text, checked_at text)""")
    con.execute("insert into link_checks (url, state, checked_at) "
                "values ('https://conference.test/', 'dead', '2026-09-01')")
    con.commit()
    con.close()

    by_url, _ = lca.collect(db)
    lca.write(db, by_url, {"https://award.test/": 200}, dead=[])
    con = sqlite3.connect(db)
    states = dict(con.execute("select url, state from link_checks"))
    con.close()
    assert states["https://conference.test/"] == "dead", "one shared table, no cross-traffic"
    assert states["https://award.test/"] == "alive"
