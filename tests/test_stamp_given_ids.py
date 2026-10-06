"""scripts/stamp_given_ids.py: stamp the ids upstream gave us onto blank-id input rows by URL (ACT-51)."""
import csv
import sqlite3
import sys
from pathlib import Path

from scripts import stamp_given_ids as sgi

COLS = ["CONFERENCE", "CONFERENCE URL", "START DATE", "Market", "EVENT_ID_CANON", "DUP_OF"]


def _row(name, url, start="", cid="", dup=""):
    return {"CONFERENCE": name, "CONFERENCE URL": url, "START DATE": start, "Market": "Cybersecurity", "EVENT_ID_CANON": cid, "DUP_OF": dup}


def _u(i, url, sheet="Cybersecurity", start=""):
    return {"sheet": sheet, "id": i, "url": url, "start": start}


def test_norm_url_ignores_scheme_www_slash_and_tracking_but_keeps_a_page_key():
    assert sgi.norm_url("https://www.Upfront.com/summit/?stream=top") == "upfront.com/summit"
    assert sgi.norm_url("http://upfront.com/summit") == "upfront.com/summit"
    assert "eventkey=x" in sgi.norm_url("https://imis.aist.org/e.aspx?EventKey=X")


def test_plan_stamps_by_url_and_notes_a_start_date_that_differs():
    inputs = {"Cybersecurity": [_row("Alpha Summit", "https://alpha.example/", "11/3/2026"), _row("Beta", "https://beta.example/")], "Utility": []}
    pl = sgi.plan([_u("2026-alpha-summit-paris-speaking", "http://www.alpha.example", start="2026-11-04")], inputs, set(), {})
    assert pl["stamp"] == [("Cybersecurity", 0, "2026-alpha-summit-paris-speaking")]
    assert any("differs" in w for _, w in pl["notes"])


def test_plan_refuses_ids_already_held_already_stamped_or_with_no_row():
    inputs = {"Cybersecurity": [_row("Alpha", "https://alpha.example/"), _row("Done", "https://done.example/", cid="2026-done-x")], "Utility": []}
    ids = [_u("2026-held-x", "https://alpha.example/"), _u("2026-done-x", "https://done.example/"), _u("2026-ghost-x", "https://ghost.example/")]
    pl = sgi.plan(ids, inputs, {"2026-held-x"}, {})
    assert pl["stamp"] == []
    why = dict(pl["notes"])
    assert "already an id in our database" in why["2026-held-x"] and "already stamped" in why["2026-done-x"] and "no blank-id row" in why["2026-ghost-x"]


def test_two_rows_sharing_a_url_need_a_pick_and_the_other_becomes_dup_of():
    inputs = {"Cybersecurity": [_row("Event", "https://e.example/"), _row("Event Days", "https://e.example/")], "Utility": []}
    ids = [_u("2026-event-x-speaking", "https://e.example/")]
    pl = sgi.plan(ids, inputs, set(), {})
    assert pl["stamp"] == [] and "name the survivor" in pl["notes"][0][1]
    pl = sgi.plan(ids, inputs, set(), {"2026-event-x-speaking": "Event"})
    assert pl["stamp"] == [("Cybersecurity", 0, "2026-event-x-speaking")] and pl["dup"] == [("Cybersecurity", 1, "2026-event-x-speaking")]


def test_an_id_resembling_one_we_hold_is_reported_not_rewritten():
    inputs = {"Cybersecurity": [], "Utility": [{**_row("Industrial Net Zero", "https://inz.example/"), "Market": "Utility"}]}
    pl = sgi.plan([_u("2026-industrial-net-zero-conference-sydney-speaking", "https://inz.example/", sheet="Utility")], inputs,
                  {"2026-industrial-net-zero-conference-sydney"}, {})
    assert pl["resemble"] == [("2026-industrial-net-zero-conference-sydney-speaking", "2026-industrial-net-zero-conference-sydney")]


def test_apply_writes_only_the_stamped_cells(tmp_path, monkeypatch, capsys):
    for m in ("Cybersecurity", "Utility"):
        with open(tmp_path / f"{m}_input.csv", "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLS, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
            w.writeheader()
            if m == "Cybersecurity":
                w.writerows([_row("Alpha Summit", "https://alpha.example/"), _row("Other", "https://other.example/")])
    db = tmp_path / "t.db"
    con = sqlite3.connect(db)
    con.execute("create table grounding_facts (event_id text)")
    con.commit()
    con.close()
    ids = tmp_path / "ids.csv"
    ids.write_text("sheet,id,start,url\nCybersecurity,2026-alpha-summit-paris-speaking,,https://alpha.example/\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["x", "--ids-csv", str(ids), "--markets-dir", str(tmp_path), "--db", str(db), "--apply"])
    assert sgi.main() == 0
    rows = list(csv.DictReader(open(tmp_path / "Cybersecurity_input.csv", encoding="utf-8-sig", newline="")))
    assert [r["EVENT_ID_CANON"] for r in rows] == ["2026-alpha-summit-paris-speaking", ""] and rows[1] == _row("Other", "https://other.example/")
    assert list(tmp_path.glob("Cybersecurity_input.pre-stampids-*.bak.csv"))


def test_allow_held_stamps_an_id_that_is_already_in_the_database():
    inputs = {"Cybersecurity": [_row("Held Event", "https://h.example/")], "Utility": []}
    ids = [_u("2026-held-event-x-speaking", "https://h.example/")]
    assert sgi.plan(ids, inputs, {"2026-held-event-x-speaking"}, {})["stamp"] == []
    assert sgi.plan(ids, inputs, {"2026-held-event-x-speaking"}, {}, allow_held=True)["stamp"] == [("Cybersecurity", 0, "2026-held-event-x-speaking")]


def test_the_ledger_records_given_ids_once_and_stamp_input_ids_keeps_them(tmp_path):
    from scripts import stamp_input_ids as sii
    led = tmp_path / "given_ids.csv"
    assert sgi.record_given(led, [("2027-new-x-speaking", "Cybersecurity")], "note 30", "2026-10-05") == 1
    assert sgi.record_given(led, [("2027-new-x-speaking", "Cybersecurity")], "note 30", "2026-10-05") == 0      # no duplicates
    assert sii.load_given("Cybersecurity", led) == {"2027-new-x-speaking"} and sii.load_given("Utility", led) == set()
    known = sii.load_given("Cybersecurity", led)
    assert sii.resolve("Brand New Event 2027", "2027-new-x-speaking", known, [{}, {}, {}]) == ("2027-new-x-speaking", "kept")
    assert sii.resolve("Brand New Event 2027", "2027-new-x-speaking", set(), [{}, {}, {}])[0] == ""             # without the ledger the stamp was cleared
