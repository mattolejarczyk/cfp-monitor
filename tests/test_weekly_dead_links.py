"""The three defects the 2026-08-27 weekly digest exposed, pinned so they cannot come back.

That run emailed 119 dead submission links. Every line was individually TRUE - I probed ten of
them independently and all ten were genuine 404s - and the report was still close to useless:

  1. 119 lines described only 80 distinct URLs, because a URL living in several of the four
     customer-facing fields of one row was emitted once per FIELD.
  2. ZERO of the 80 were new. All had been in the 2026-08-16 digest. The report was a static
     backlog re-sent weekly, which teaches the reader to skip it.
  3. `link_checks` was (url primary key, state, checked_at), overwritten every run, so it could
     not say whether a link broke this week or had never worked. Of the 80, only 4 could be
     shown to have ever served us a quote, and that came from the evidence table instead.

These tests assert the fixes AND that healthy input is unaffected - the `clean_city` lesson of
2026-08-08, where every test asserted that bad input got repaired and none that good input was
left alone, so a corruption of 26 rows passed a full suite.
"""
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location("_wv", ROOT / "scripts" / "weekly_verify.py")
wv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wv)

FIELDS = ("submission_url", "deadline_evidence_url", "main_info_url", "url")
DEAD = "https://gone.example.com/cfp"
LIVE = "https://fine.example.com/cfp"


def _db(tmp_path, rows, link_checks=None):
    """rows: list of (event_id, name, {field: url}). link_checks: pre-existing rows."""
    p = tmp_path / "w.db"
    con = sqlite3.connect(p)
    con.execute(f"""create table grounding_facts (
                      event_id text primary key, name text,
                      {', '.join(f'{f} text' for f in FIELDS)})""")
    for eid, name, urls in rows:
        cols = ", ".join(["event_id", "name"] + list(urls))
        marks = ", ".join("?" * (2 + len(urls)))
        con.execute(f"insert into grounding_facts ({cols}) values ({marks})",
                    [eid, name] + list(urls.values()))
    if link_checks is not None:
        con.execute("""create table link_checks (url text primary key, state text,
                       checked_at text, http_status integer, first_seen text, last_alive text)""")
        con.executemany("insert into link_checks values (?,?,?,?,?,?)", link_checks)
    con.commit()
    con.close()
    return str(p)


@pytest.fixture
def fake_net(monkeypatch):
    """DEAD 404s, everything else is fine. No network in a unit test.

    Patch the SOURCE modules, not `wv`: check_all_submission_links imports link_status and
    browser_check inside the function body, so a name bound on this module is ignored.
    """
    import recheck_dead_links as rdl

    import src.cfp_monitor.verify as verify

    monkeypatch.setattr(verify, "link_status",
                        lambda u: (404 if u.startswith("https://gone.") else 200, ""))

    async def _browser(urls):
        return {u: ("DEAD", 404, 0) for u in urls}
    monkeypatch.setattr(rdl, "browser_check", _browser)


# ---------------------------------------------------------------- 1. the duplicate defect --
def test_one_url_in_four_fields_reports_the_event_once(tmp_path, fake_net):
    """Biomass and Argus each held the same dead URL in all four fields and appeared 4x."""
    db = _db(tmp_path, [("e1", "Four Fields Conf", dict.fromkeys(FIELDS, DEAD))],
             link_checks=[])
    new, standing = wv.check_all_submission_links(db)
    assert len(new) == 1, f"expected one line for one event and one URL, got {new}"
    assert new[0] == ("e1", "Four Fields Conf", DEAD)
    assert standing == []


def test_two_different_events_sharing_one_dead_url_are_both_reported(tmp_path, fake_net):
    """Dedupe is per (event, url). Collapsing to the URL alone would HIDE an affected event."""
    db = _db(tmp_path, [("e1", "First Conf", {"submission_url": DEAD}),
                        ("e2", "Second Conf", {"submission_url": DEAD})], link_checks=[])
    new, _ = wv.check_all_submission_links(db)
    assert sorted(e for e, _n, _u in new) == ["e1", "e2"]


def test_one_event_with_several_distinct_dead_urls_reports_each(tmp_path, fake_net):
    """GOOD INPUT SURVIVES: distinct URLs are distinct findings, not duplicates to collapse."""
    other = "https://gone.example.com/cfp2"
    db = _db(tmp_path, [("e1", "Multi URL Conf",
                         {"submission_url": DEAD, "deadline_evidence_url": other})],
             link_checks=[])
    new, _ = wv.check_all_submission_links(db)
    assert sorted(u for _e, _n, u in new) == sorted([DEAD, other])


# ------------------------------------------------------------- 2. new vs standing backlog --
def test_a_link_already_dead_last_run_is_standing_not_new(tmp_path, fake_net):
    db = _db(tmp_path, [("e1", "Old Failure", {"submission_url": DEAD})],
             link_checks=[(DEAD, "dead", "2026-08-16T01:00:00", 404, "2026-08-01T01:00:00", None)])
    new, standing = wv.check_all_submission_links(db)
    assert new == [], "a link dead since last week is not this week's news"
    assert [u for _e, _n, u in standing] == [DEAD]


def test_a_link_that_was_alive_last_run_is_new(tmp_path, fake_net):
    db = _db(tmp_path, [("e1", "Fresh Failure", {"submission_url": DEAD})],
             link_checks=[(DEAD, "alive", "2026-08-16T01:00:00", 200,
                           "2026-08-01T01:00:00", "2026-08-16T01:00:00")])
    new, standing = wv.check_all_submission_links(db)
    assert [u for _e, _n, u in new] == [DEAD], "a link that just broke IS the week's news"
    assert standing == []


def test_a_link_never_seen_before_is_new(tmp_path, fake_net):
    db = _db(tmp_path, [("e1", "Never Checked", {"submission_url": DEAD})], link_checks=[])
    new, standing = wv.check_all_submission_links(db)
    assert len(new) == 1 and standing == []


# ------------------------------------------------------------------- 3. the history table --
def test_first_seen_survives_later_runs(tmp_path, fake_net):
    """Overwriting first_seen would destroy the only record of how long this has been broken."""
    db = _db(tmp_path, [("e1", "C", {"submission_url": DEAD})],
             link_checks=[(DEAD, "dead", "2026-08-16T01:00:00", 404, "2026-07-01T00:00:00", None)])
    wv.check_all_submission_links(db)
    row = sqlite3.connect(db).execute(
        "select first_seen from link_checks where url = ?", (DEAD,)).fetchone()
    assert row[0] == "2026-07-01T00:00:00"


def test_last_alive_is_kept_after_a_link_dies(tmp_path, fake_net):
    """This is the column that answers 'did it break recently or never work'."""
    db = _db(tmp_path, [("e1", "C", {"submission_url": DEAD})],
             link_checks=[(DEAD, "alive", "2026-08-16T01:00:00", 200,
                           "2026-07-01T00:00:00", "2026-08-16T01:00:00")])
    wv.check_all_submission_links(db)
    state, last_alive = sqlite3.connect(db).execute(
        "select state, last_alive from link_checks where url = ?", (DEAD,)).fetchone()
    assert state == "dead"
    assert last_alive == "2026-08-16T01:00:00", "the last time it worked must survive its death"


def test_never_alive_link_has_no_last_alive(tmp_path, fake_net):
    """A NULL last_alive with an old first_seen is how 'this never worked' is expressed."""
    db = _db(tmp_path, [("e1", "C", {"submission_url": DEAD})], link_checks=[])
    wv.check_all_submission_links(db)
    last_alive = sqlite3.connect(db).execute(
        "select last_alive from link_checks where url = ?", (DEAD,)).fetchone()[0]
    assert last_alive is None


def test_a_live_link_records_last_alive_and_its_status(tmp_path, fake_net):
    db = _db(tmp_path, [("e1", "C", {"submission_url": LIVE})], link_checks=[])
    new, standing = wv.check_all_submission_links(db)
    assert new == [] and standing == []
    state, status, last_alive = sqlite3.connect(db).execute(
        "select state, http_status, last_alive from link_checks where url = ?", (LIVE,)).fetchone()
    assert state == "alive" and status == 200 and last_alive is not None


def test_the_old_three_column_table_is_migrated_not_replaced(tmp_path, fake_net):
    """The live table held 662 rows. A migration that dropped them would erase the baseline."""
    p = tmp_path / "old.db"
    con = sqlite3.connect(p)
    con.execute("""create table grounding_facts (event_id text primary key, name text,
                   submission_url text, deadline_evidence_url text, main_info_url text,
                   url text)""")
    con.execute("insert into grounding_facts (event_id, name, submission_url) values (?,?,?)",
                ("e1", "C", DEAD))
    con.execute("create table link_checks (url text primary key, state text, checked_at text)")
    con.execute("insert into link_checks values (?,?,?)",
                ("https://legacy.example.com/", "alive", "2026-08-09T01:15:31"))
    con.commit()
    con.close()

    wv.check_all_submission_links(str(p))

    con = sqlite3.connect(p)
    cols = {r[1] for r in con.execute("pragma table_info(link_checks)")}
    assert {"http_status", "first_seen", "last_alive"} <= cols
    kept = con.execute("select state from link_checks where url = ?",
                       ("https://legacy.example.com/",)).fetchone()
    assert kept and kept[0] == "alive", "pre-existing rows must survive the migration"
