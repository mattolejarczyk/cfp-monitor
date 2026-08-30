"""The client layer must stay out of the shared industry list, in both directions.

Layer 1 (conferences + conference_markets) is SHARED - one canonical row per conference, joined
into one or more industries. Layer 2 is PER CLIENT. Two cybersecurity clients both tracking
Black Hat need their own status, priority and notes against that single conference.

The defect this guards against is concrete: `conferences.status_details` is 349/373 filled with
OUR crawl-derived text and looks exactly like the customer's STATUS DETAILS column. Loading
theirs into it would destroy 349 rows and merge two meanings under one name.
"""
import csv
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import clients          # noqa: E402

HEADERS = ["CONFERENCE", "CONFERENCE URL", "LOCATION", "EVENT START DATE", "LATEST UPDATE",
           "SUBMISSION DEADLINE", "SUBMISSION DATE VERIFIED", "PRIORITY", "STATUS",
           "STATUS DETAILS", "SUBMISSION URL", "SPEAKER & ABSTRACTS SUBMITTED",
           "NOTIFCATION DATE", "OVERVIEW", "CATEGORIES", "COORDINATOR CONTACT INFO",
           "NOTES", "LOGIN", "PW"]


def _row(name, **kw):
    d = dict.fromkeys(HEADERS, "")
    d["CONFERENCE"] = name
    d["CONFERENCE URL"] = f"https://{name.split()[0].lower()}.example/"
    for k, v in kw.items():
        d[k.replace("_", " ").upper()] = v
    return d


def _sheet(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADERS)
        w.writeheader()
        w.writerows(rows)
    return path


@pytest.fixture
def db(tmp_path):
    con = sqlite3.connect(tmp_path / "t.db")
    con.executescript("""
        create table conferences (id integer primary key, key text, status_details text,
                                  overview text, priority text);
        create table conference_markets (conference_key text, market text);
        create table industries (name text, norm text);
        insert into industries values ('Cybersecurity','cybersecurity'),('Utility','utility');
        insert into conferences (key, status_details) values ('blackhat.com','OUR crawl text');
        insert into conference_markets values ('blackhat.com','Cybersecurity');
    """)
    con.commit()
    clients.ensure_schema(con)
    return con


def test_two_clients_hold_different_state_for_the_same_conference(db, tmp_path):
    """The reason this layer exists at all."""
    a = _sheet(tmp_path / "a.csv", [_row("Black Hat USA", STATUS="Submitted", PRIORITY="High")])
    b = _sheet(tmp_path / "b.csv", [_row("Black Hat USA", STATUS="Closed", PRIORITY="Low")])
    clients.upsert_client(db, "arnica", "Arnica", industry="Cybersecurity")
    clients.upsert_client(db, "other", "Other Co", industry="Cybersecurity")
    clients.load_sheet(db, "arnica", a, industry="Cybersecurity")
    clients.load_sheet(db, "other", b, industry="Cybersecurity")

    got = dict(db.execute("select client_key, status from client_conferences "
                          "where their_name = 'Black Hat USA'").fetchall())
    assert got == {"arnica": "Submitted", "other": "Closed"}
    prio = dict(db.execute("select client_key, priority from client_conferences").fetchall())
    assert prio == {"arnica": "High", "other": "Low"}


def test_loading_never_touches_the_shared_tables(db, tmp_path):
    """conferences.status_details is OURS and 349/373 filled in production."""
    before = db.execute("select status_details from conferences where key='blackhat.com'"
                        ).fetchone()[0]
    s = _sheet(tmp_path / "a.csv",
               [_row("Black Hat USA", STATUS_DETAILS="4/28 - emailed the organiser")])
    clients.upsert_client(db, "arnica", "Arnica", industry="Cybersecurity")
    clients.load_sheet(db, "arnica", s, industry="Cybersecurity")

    after = db.execute("select status_details from conferences where key='blackhat.com'"
                       ).fetchone()[0]
    assert after == before == "OUR crawl text"
    assert db.execute("select status_details from client_conferences").fetchone()[0] \
        == "4/28 - emailed the organiser"
    assert db.execute("select count(*) from conference_markets").fetchone()[0] == 1


def test_credentials_are_never_loaded(db, tmp_path):
    s = _sheet(tmp_path / "a.csv", [_row("Black Hat USA", LOGIN="user@x.com", PW="secret123")])
    clients.upsert_client(db, "arnica", "Arnica", industry="Cybersecurity")
    clients.load_sheet(db, "arnica", s, industry="Cybersecurity")
    body = " ".join(str(v) for r in db.execute("select * from client_conferences")
                    for v in r if v is not None)
    assert "secret123" not in body and "user@x.com" not in body


def test_the_misspelled_notification_header_still_maps(db, tmp_path):
    """The two real sheets disagree: NOTIFCATION in one, NOTIFICATION in the other. An exact
    match drops the column from one client and nothing reports it."""
    assert clients.COLUMN_MAP["NOTIFCATION DATE"] == "notification_date"
    assert clients.COLUMN_MAP["NOTIFICATION DATE"] == "notification_date"
    s = _sheet(tmp_path / "a.csv", [_row("Black Hat USA", NOTIFCATION_DATE="2027-01-05")])
    clients.upsert_client(db, "arnica", "Arnica", industry="Cybersecurity")
    clients.load_sheet(db, "arnica", s, industry="Cybersecurity")
    assert db.execute("select notification_date from client_conferences").fetchone()[0] \
        == "2027-01-05"


def test_an_unknown_column_is_reported_not_silently_dropped(db, tmp_path):
    rows = [dict(_row("Black Hat USA"), **{"SPONSOR TIER": "Gold"})]
    p = tmp_path / "a.csv"
    with open(p, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADERS + ["SPONSOR TIER"])
        w.writeheader()
        w.writerows(rows)
    clients.upsert_client(db, "arnica", "Arnica", industry="Cybersecurity")
    s = clients.load_sheet(db, "arnica", p, industry="Cybersecurity")
    assert "SPONSOR TIER" in s["unmapped_columns"]


def test_a_row_leaving_the_sheet_is_kept_and_flagged(db, tmp_path):
    """Rule C4 / contract 2.1: absence is not disproof. They may have filtered or sorted."""
    clients.upsert_client(db, "arnica", "Arnica", industry="Cybersecurity")
    clients.load_sheet(db, "arnica", _sheet(tmp_path / "a.csv",
                                            [_row("Black Hat USA"), _row("BSides LV")]),
                       industry="Cybersecurity")
    s = clients.load_sheet(db, "arnica", _sheet(tmp_path / "b.csv", [_row("Black Hat USA")]),
                           industry="Cybersecurity")
    assert s["withdrawn"] == 1 and s["withdrawn_names"] == ["BSides LV"]
    row = db.execute("select withdrawn_by_customer from client_conferences "
                     "where their_name = 'BSides LV'").fetchone()
    assert row is not None, "a withdrawn row is KEPT"
    assert row[0] == 1


def test_a_returning_row_clears_the_withdrawn_flag(db, tmp_path):
    clients.upsert_client(db, "arnica", "Arnica", industry="Cybersecurity")
    both = [_row("Black Hat USA"), _row("BSides LV")]
    clients.load_sheet(db, "arnica", _sheet(tmp_path / "a.csv", both), industry="Cybersecurity")
    clients.load_sheet(db, "arnica", _sheet(tmp_path / "b.csv", both[:1]),
                       industry="Cybersecurity")
    clients.load_sheet(db, "arnica", _sheet(tmp_path / "c.csv", both), industry="Cybersecurity")
    assert db.execute("select withdrawn_by_customer from client_conferences "
                      "where their_name = 'BSides LV'").fetchone()[0] == 0


def test_loading_raises_no_candidates_because_nothing_is_matched_yet(db, tmp_path):
    """The first version called every newly-loaded row a promotion candidate and reported 111
    on first load, when ~84 of them match lists we already hold. A row with no event_id BEFORE
    the matcher has run is unexamined, not unknown."""
    clients.upsert_client(db, "arnica", "Arnica", industry="Cybersecurity")
    s = clients.load_sheet(db, "arnica",
                           _sheet(tmp_path / "a.csv", [_row("Black Hat USA"), _row("KubeCon")]),
                           industry="Cybersecurity")
    assert db.execute("select count(*) from industry_candidates").fetchone()[0] == 0
    assert s["not_yet_matched"] == 2
    assert "pending_candidates" not in s, "loading must not report a number it cannot know"


def test_candidates_come_from_what_the_matcher_could_not_place(db, tmp_path):
    """The flywheel - and its safety catch. Nothing joins an industry list without a person."""
    clients.upsert_client(db, "arnica", "Arnica", industry="Cybersecurity")
    clients.load_sheet(db, "arnica",
                       _sheet(tmp_path / "a.csv", [_row("Black Hat USA"), _row("KubeCon")]),
                       industry="Cybersecurity")
    db.execute("update client_conferences set event_id = '2026-blackhat-lasvegas' "
               "where their_name = 'Black Hat USA'")          # the matcher placed this one
    db.commit()

    r = clients.refresh_candidates(db, "arnica", "Cybersecurity")
    assert r["raised"] == 1 and r["pending"] == 1
    got = db.execute("select their_name, industry, decision from industry_candidates"
                     ).fetchall()
    assert got == [("KubeCon", "Cybersecurity", None)], "a candidate starts undecided"
    assert db.execute("select count(*) from conference_markets").fetchone()[0] == 1


def test_a_withdrawn_row_is_not_proposed_for_promotion(db, tmp_path):
    clients.upsert_client(db, "arnica", "Arnica", industry="Cybersecurity")
    clients.load_sheet(db, "arnica", _sheet(tmp_path / "a.csv", [_row("KubeCon")]),
                       industry="Cybersecurity")
    clients.load_sheet(db, "arnica", _sheet(tmp_path / "b.csv", []), industry="Cybersecurity")
    assert clients.refresh_candidates(db, "arnica", "Cybersecurity")["raised"] == 0


def test_refreshing_candidates_twice_does_not_duplicate_them(db, tmp_path):
    clients.upsert_client(db, "arnica", "Arnica", industry="Cybersecurity")
    clients.load_sheet(db, "arnica", _sheet(tmp_path / "a.csv", [_row("KubeCon")]),
                       industry="Cybersecurity")
    clients.refresh_candidates(db, "arnica", "Cybersecurity")
    clients.refresh_candidates(db, "arnica", "Cybersecurity")
    assert db.execute("select count(*) from industry_candidates").fetchone()[0] == 1


def test_customer_values_are_stored_exactly_as_typed(db, tmp_path):
    """Rule C1: we do not normalise, reformat or 'correct' a field we do not own."""
    messy = "Call opens: 01/01/2026 12:00 AM, Call closes: 03/01/2026 11:59 PM (UTC+02:00)"
    clients.upsert_client(db, "arnica", "Arnica", industry="Cybersecurity")
    clients.load_sheet(db, "arnica",
                       _sheet(tmp_path / "a.csv",
                              [_row("Black Hat Asia", SUBMISSION_DEADLINE=messy)]),
                       industry="Cybersecurity")
    assert db.execute("select their_deadline from client_conferences").fetchone()[0] == messy


def test_reloading_the_same_sheet_changes_nothing(db, tmp_path):
    """Good input must survive - the 2026-08-08 inversion that corrupted 26 cities."""
    p = _sheet(tmp_path / "a.csv", [_row("Black Hat USA", STATUS="Submitted")])
    clients.upsert_client(db, "arnica", "Arnica", industry="Cybersecurity")
    clients.load_sheet(db, "arnica", p, industry="Cybersecurity")
    first = db.execute("select * from client_conferences").fetchall()
    s = clients.load_sheet(db, "arnica", p, industry="Cybersecurity")
    assert s["added"] == 0 and s["withdrawn"] == 0
    assert db.execute("select * from client_conferences").fetchall() == first
