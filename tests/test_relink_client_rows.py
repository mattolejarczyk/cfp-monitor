"""scripts/relink_client_rows.py: a person's re-link of a customer row, with guards. A wrong link puts another conference's deadline in front of a customer, so the refusals matter most."""
import csv
import sqlite3
from pathlib import Path

import pytest

from scripts import relink_client_rows as rcr

TODAY = "2026-11-08"


def _db(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.executescript("""
        create table client_conferences (client_key text, their_name text, event_id text, match_method text, match_justification text, matched_at text,
                                         location text, event_start_date text, withdrawn_by_customer integer default 0);
        create table grounding_facts (event_id text, name text, city text, start_date text);
        create table conferences (id integer); create table conference_markets (conference_key text); create table evidence (id integer);
        insert into grounding_facts values ('2026-cyberuk-glasgow', 'CYBERUK 2026', 'Glasgow', '2026-04-21');
        insert into grounding_facts values ('2027-cyberuk-manchester-speaking', 'CYBERUK 2027', 'Manchester', '2027-05-11');
        insert into grounding_facts values ('2026-gastech-bangkok', 'Gastech 2026', 'Bangkok', '2026-09-14');
        insert into grounding_facts values ('2027-gastech-milan-speaking', 'Gastech 2027', 'Milan', '2027-09-14');
        insert into grounding_facts values ('2027-ces-las-vegas', 'CES 2027', 'Las Vegas', '2027-01-06');
        insert into conferences values (1); insert into conference_markets values ('x'); insert into evidence values (1);
        insert into client_conferences values ('arnica', 'CYBERUK', '2026-cyberuk-glasgow', 'match_customer_sheet', 'old why', '2026-09-16', 'Liverpool, UK', '05/11/2027', 0);
        insert into client_conferences values ('utility-global', 'Gastech', '2026-gastech-bangkok', 'match_customer_sheet', '', '2026-09-16', 'Houston, United States', '2027-09-14', 0);
        insert into client_conferences values ('utility-global', 'CES', '2027-ces-las-vegas', 'match_customer_sheet', '', '2026-09-16', 'Las Vegas', '2028-01-11', 0);
        insert into client_conferences values ('arnica', 'Untouched', '2026-cyberuk-glasgow', 'human review', 'kept', '2026-09-16', 'Glasgow', '2026-04-21', 0);
    """)
    con.commit()
    return con


def _plan(path: Path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["client", "their_name", "from_event_id", "to_event_id", "note"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return path


CYBERUK = {"client": "arnica", "their_name": "CYBERUK", "from_event_id": "2026-cyberuk-glasgow", "to_event_id": "2027-cyberuk-manchester-speaking", "note": "D2"}
GASTECH = {"client": "utility-global", "their_name": "Gastech", "from_event_id": "2026-gastech-bangkok", "to_event_id": "2027-gastech-milan-speaking", "note": "D2"}


def test_a_next_edition_move_passes_and_a_place_difference_is_only_reported(tmp_path):
    con = _db(tmp_path / "t.db")
    ok, refused = rcr.check(con, [CYBERUK, GASTECH])
    assert refused == [] and [m["their_name"] for m in ok] == ["CYBERUK", "Gastech"]
    assert ok[0]["gap_days"] == 0 and ok[0]["place_note"].startswith("place:")        # Liverpool vs Manchester: allowed, named
    assert ok[1]["place_note"].startswith("place:") and "Houston" in ok[1]["place_note"]


def test_apply_moves_only_the_planned_rows_and_records_how(tmp_path):
    con = _db(tmp_path / "t.db")
    ok, _ = rcr.check(con, [CYBERUK])
    assert rcr.apply(con, ok, "D2 on Daily Review", TODAY) == 1
    row = con.execute("select event_id, match_method, match_justification, matched_at from client_conferences where their_name = 'CYBERUK'").fetchone()
    assert row == ("2027-cyberuk-manchester-speaking", f"operator re-link {TODAY} (D2 on Daily Review)", "was 2026-cyberuk-glasgow; D2", TODAY)
    untouched = con.execute("select event_id, match_method, match_justification from client_conferences where their_name = 'Untouched'").fetchone()
    assert untouched == ("2026-cyberuk-glasgow", "human review", "kept")             # same old id on another row: left alone
    assert con.execute("select event_id from client_conferences where their_name = 'Gastech'").fetchone()[0] == "2026-gastech-bangkok"


def test_refuses_when_the_held_link_is_not_the_one_the_plan_names(tmp_path):
    con = _db(tmp_path / "t.db")
    moved = {**CYBERUK, "from_event_id": "2026-somewhere-else"}
    ok, refused = rcr.check(con, [moved, GASTECH])
    assert len(refused) == 1 and "holds 2026-cyberuk-glasgow, not 2026-somewhere-else" in refused[0]
    assert [m["their_name"] for m in ok] == ["Gastech"]                              # the caller writes nothing when anything is refused


def test_refuses_a_target_whose_date_is_another_edition(tmp_path):
    """CES: the customer tracks 2028-01-11; 2027-ces-las-vegas is 370 days away. That is D1's case (add a row), never a re-link."""
    con = _db(tmp_path / "t.db")
    ok, refused = rcr.check(con, [{"client": "utility-global", "their_name": "CES", "from_event_id": "2027-ces-las-vegas", "to_event_id": "2026-gastech-bangkok", "note": ""}])
    assert ok == [] and "days from the customer's 2028-01-11" in refused[0]


def test_refuses_an_event_we_do_not_hold_a_missing_row_and_a_withdrawn_row(tmp_path):
    con = _db(tmp_path / "t.db")
    con.execute("update client_conferences set withdrawn_by_customer = 1 where their_name = 'Gastech'")
    ok, refused = rcr.check(con, [{**CYBERUK, "to_event_id": "2027-nowhere"}, {**CYBERUK, "their_name": "Nobody"}, GASTECH])
    assert ok == [] and len(refused) == 3
    assert "not an event we hold" in refused[0] and "no such customer row" in refused[1] and "withdrawn" in refused[2]


def test_read_plan_refuses_a_blank_cell(tmp_path):
    p = _plan(tmp_path / "plan.csv", [{**CYBERUK, "to_event_id": ""}])
    with pytest.raises(ValueError, match="blank to_event_id"):
        rcr.read_plan(p)


def test_main_dry_run_writes_nothing_and_apply_backs_up_first(tmp_path, monkeypatch, capsys):
    db = tmp_path / "t.db"
    _db(db).close()
    plan = _plan(tmp_path / "plan.csv", [CYBERUK])
    monkeypatch.setattr("sys.argv", ["relink", "--db", str(db), "--plan", str(plan), "--reason", "D2 test"])
    assert rcr.main() == 0
    assert "report only" in capsys.readouterr().out
    assert sqlite3.connect(db).execute("select event_id from client_conferences where their_name = 'CYBERUK'").fetchone()[0] == "2026-cyberuk-glasgow"
    monkeypatch.setattr("sys.argv", ["relink", "--db", str(db), "--plan", str(plan), "--reason", "D2 test", "--apply"])
    assert rcr.main() == 0
    out = capsys.readouterr().out
    assert "applied 1 move(s)" in out and "shared tables unchanged" in out
    backups = list(tmp_path.glob("t.backup-pre-relink-*.db"))
    assert len(backups) == 1
    assert sqlite3.connect(backups[0]).execute("select event_id from client_conferences where their_name = 'CYBERUK'").fetchone()[0] == "2026-cyberuk-glasgow"
    assert sqlite3.connect(db).execute("select event_id from client_conferences where their_name = 'CYBERUK'").fetchone()[0] == "2027-cyberuk-manchester-speaking"


def test_main_refusal_is_all_or_nothing(tmp_path, monkeypatch, capsys):
    db = tmp_path / "t.db"
    _db(db).close()
    plan = _plan(tmp_path / "plan.csv", [CYBERUK, {**GASTECH, "from_event_id": "2026-wrong"}])
    monkeypatch.setattr("sys.argv", ["relink", "--db", str(db), "--plan", str(plan), "--reason", "D2 test", "--apply"])
    assert rcr.main() == 2
    assert "NOTHING WRITTEN" in capsys.readouterr().out
    assert sqlite3.connect(db).execute("select event_id from client_conferences where their_name = 'CYBERUK'").fetchone()[0] == "2026-cyberuk-glasgow"
    assert list(tmp_path.glob("*.backup-pre-relink-*")) == []
