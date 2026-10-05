"""scripts/pinned_rows.py: a person's ruling holds over the research, lapses after the call closes, and only touches the cells a ruling may set."""
from datetime import date

import pytest

from scripts.pinned_rows import ALLOWED, apply_pins, load_pins

T = date(2026, 10, 3)
CANON = lambda eid, lookup: lookup.get(eid, eid)
PIN = {"canonical": "c1", "event": "Conf", "ruled_on": "2026-10-03", "why": "operator read the page", "until": "2026-11-17",
       "set": {"SUBMISSION DEADLINE": "2026-11-16", "DEADLINE_QUOTE": "Abstract submission deadline: November 16, 2026", "IS_PROJECTED": "false"}}


def _row(**kw):
    base = {"EVENT_ID": "up-1", "CONFERENCE": "Conf", "EDITION": "2027", "SUBMISSION DEADLINE": "2026-11-23", "DEADLINE_QUOTE": "Research paper submission deadline: November 23, 2026",
            "IS_PROJECTED": "true", "GROUNDING_CONFIDENCE": "Projected (2027)", "STATUS DETAILS": "x"}
    base.update(kw)
    return base


def test_a_pin_overrides_the_research_and_reports_what_the_research_said():
    rows, rep = apply_pins([_row()], {"up-1": "c1"}, CANON, [PIN], T)
    r = rows[0]
    assert r["SUBMISSION DEADLINE"] == "2026-11-16" and r["DEADLINE_QUOTE"].startswith("Abstract") and r["IS_PROJECTED"] == "false"
    assert r["GROUNDING_CONFIDENCE"] == "Verified (2027)"                      # R11 stays bound to IS_PROJECTED
    ch = rep["applied"][0]["changed"]
    assert ch["SUBMISSION DEADLINE"] == {"research": "2026-11-23", "pinned": "2026-11-16"}


def test_a_row_that_already_agrees_is_unchanged_and_other_rows_are_untouched():
    rows, rep = apply_pins([_row(**{"SUBMISSION DEADLINE": "2026-11-16", "DEADLINE_QUOTE": PIN["set"]["DEADLINE_QUOTE"], "IS_PROJECTED": "false",
                                    "GROUNDING_CONFIDENCE": "Verified (2027)"}), _row(EVENT_ID="other")], {"up-1": "c1"}, CANON, [PIN], T)
    assert rep["applied"] == [] and rep["unchanged"] == 1 and rows[1]["SUBMISSION DEADLINE"] == "2026-11-23"


def test_a_pin_lapses_after_its_until_date():
    rows, rep = apply_pins([_row()], {"up-1": "c1"}, CANON, [PIN], date(2026, 11, 18))
    assert rows[0]["SUBMISSION DEADLINE"] == "2026-11-23" and rep["lapsed"] == ["Conf"] and not rep["applied"]


def test_a_pin_may_not_set_identity_or_customer_columns():
    for col in ("EVENT_ID", "CONFERENCE", "EDITION", "STATUS", "NOTES", "PRIORITY", "SUBMISSION URL"):
        assert col not in ALLOWED
        with pytest.raises(ValueError):
            apply_pins([_row()], {}, CANON, [{**PIN, "set": {col: "x"}}], T)


def test_the_real_pin_file_is_valid_and_each_pin_names_why_and_until():
    pins = load_pins()
    assert len(pins) >= 2
    for p in pins:
        assert p["canonical"] and p["until"] and p["why"] and p["ruled_on"] and set(p["set"]) <= set(ALLOWED)
        if "DEADLINE_EVIDENCE_URL" in p["set"]:
            assert p["set"]["DEADLINE_EVIDENCE_URL"].startswith("https://")


def test_blank_start_pins_clear_the_database_and_ordinary_pins_do_not(tmp_path):
    """The importer keeps an old start_date when the new one is blank; 'the page states no date' must clear it explicitly."""
    import sqlite3
    from scripts.pinned_rows import clear_pinned_blank_starts
    db = tmp_path / "t.db"
    con = sqlite3.connect(db)
    con.execute("create table grounding_facts (event_id text primary key, start_date text)")
    con.executemany("insert into grounding_facts values (?,?)", [("a", "2026-04-01"), ("b", "2027-01-01"), ("c", None)])
    con.commit(); con.close()
    pins = [{"canonical": "a", "until": "2026-12-31", "set": {"START DATE": ""}},          # a blank ruling: clears
            {"canonical": "b", "until": "2027-02-01", "set": {"START DATE": "2027-01-01"}},   # a dated ruling: untouched
            {"canonical": "c", "until": "2026-12-31", "set": {"START DATE": ""}}]            # already blank: nothing to clear
    assert clear_pinned_blank_starts(db, pins, T) == ["a"]
    rows = sqlite3.connect(db).execute("select event_id, start_date from grounding_facts order by 1").fetchall()
    assert rows == [("a", None), ("b", "2027-01-01"), ("c", None)]
    assert clear_pinned_blank_starts(db, [{"canonical": "a", "until": "2026-01-01", "set": {"START DATE": ""}}], T) == []   # a lapsed pin does nothing


def test_every_pin_records_the_pages_it_was_verified_on():
    for p in load_pins():
        assert p.get("links") and all(u.startswith("https://") for u in p["links"]), p["canonical"]
        assert p["by"] == "operator" and p["ruled_on"]


# ---- ACT-11: pins apply to awards (their own id crossing) and survive a blank/different research answer ----------------
def test_award_pin_applies_through_the_awards_crossing():
    pin = {"canonical": "2026-gl-energy-show-awards", "event": "Global Energy Show Awards", "ruled_on": "2026-10-05", "until": "2026-12-31",
           "set": {"SUBMISSION DEADLINE": "2026-11-01", "SUBMISSION_OPENS": "2026-09-01", "ANNOUNCEMENT_DATE": "2027-01-15"}}
    row = {"EVENT_ID": "up-award-9", "CONFERENCE": "Global Energy Show Awards", "EDITION": "2026", "SUBMISSION DEADLINE": "",
           "SUBMISSION_OPENS": "", "ANNOUNCEMENT_DATE": "2027-03-01"}
    rows, rep = apply_pins([row], {"up-award-9": "2026-gl-energy-show-awards"}, CANON, [pin], T)       # award_lookup: upstream id -> ours
    assert (rows[0]["SUBMISSION DEADLINE"], rows[0]["SUBMISSION_OPENS"], rows[0]["ANNOUNCEMENT_DATE"]) == ("2026-11-01", "2026-09-01", "2027-01-15")
    assert rep["applied"][0]["changed"]["ANNOUNCEMENT_DATE"] == {"research": "2027-03-01", "pinned": "2027-01-15"}


def test_award_status_is_still_not_pinnable():
    with pytest.raises(ValueError):
        apply_pins([_row()], {}, CANON, [{"canonical": "x", "set": {"STATUS": "Closed"}}], T)


def test_the_weekend_import_applies_pins_to_awards_too():
    """The load used to skip awards (`if market != AWARDS`); a pin must reach every market's rows before the gate."""
    import inspect
    from scripts import weekend_import
    src = inspect.getsource(weekend_import.resolve_market)
    assert "apply_pins(rows, lookup, to_canonical, load_pins())" in src
    assert "if market != AWARDS:\n        from scripts.pinned_rows" not in src


def test_board_panel_lists_an_award_pin(monkeypatch):
    from scripts import pinned_rows, status_dashboard
    monkeypatch.setattr(pinned_rows, "load_pins", lambda: [{"canonical": "a-awards", "event": "Some Award", "ruled_on": "2026-10-05", "until": "2026-12-01",
                                                          "links": ["https://x.example/award"], "set": {"ANNOUNCEMENT_DATE": "2027-01-15", "SUBMISSION DEADLINE": "2026-11-01"}}])
    out = status_dashboard.verified_by_operator()
    assert out[0]["event"] == "Some Award" and "winners announced: 2027-01-15" in out[0]["what"] and "deadline: 2026-11-01" in out[0]["what"]
