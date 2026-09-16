"""Duplicate detection classifies by WHICH key component moved - and leaves the data alone.

The risk here is not missing a duplicate. It is calling two real editions of a series one
event, because the fix for that mistake is a merge and a merge destroys evidence. So these
pin the separations as hard as the detections.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("fde",
                                               ROOT / "scripts" / "find_duplicate_events.py")
fde = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fde)

from src.cfp_monitor.storage import Store              # noqa: E402


def _row(event_id, name="Big Conference 2027", city="Houston", edition="2027",
         deadline="", verify_state="not_found", source_as_of="2026-09-12"):
    return {"event_id": event_id, "name": name, "city": city, "edition": edition,
            "deadline": deadline, "verify_state": verify_state, "source_as_of": source_as_of}


def _db(tmp_path, rows):
    p = tmp_path / "t.db"
    Store(str(p)).db.close()
    con = sqlite3.connect(str(p))
    for r in rows:
        con.execute(f"insert into grounding_facts ({', '.join(r)})"
                    f" values ({', '.join('?' for _ in r)})", list(r.values()))
    con.commit()
    con.close()
    return str(p)


def _one_group(tmp_path, rows):
    con = sqlite3.connect(_db(tmp_path, rows))
    con.row_factory = sqlite3.Row
    found = fde.groups(con, "grounding_facts")
    con.close()
    assert len(found) == 1, found
    return next(iter(found.values()))


def test_a_key_minted_earlier_is_the_same_event_today(tmp_path):
    """The commonest case and the least obvious. Both rows now say edition 2027, Houston, same
    name - so both would mint 2027-...-houston. Only the key one was BORN with differs, which
    is fix_edition.py's frozen key_year doing its job, not a second event."""
    rows = _one_group(tmp_path, [_row("2026-big-conference-houston", source_as_of="2026-08-07"),
                                 _row("2027-big-conference-houston")])
    assert fde.classify(rows) == "SAME_TODAY"


def test_two_real_editions_are_not_called_one_event(tmp_path):
    """The inversion that matters: GOOD input must survive. A 2026 edition and a 2027 edition
    of the same series are two events, and merging them would destroy one."""
    rows = _one_group(tmp_path, [_row("2026-big-conference-houston", edition="2026"),
                                 _row("2027-big-conference-houston", edition="2027")])
    assert fde.classify(rows) == "YEAR"


def test_a_city_that_went_missing_is_place_drift(tmp_path):
    rows = _one_group(tmp_path, [_row("2027-big-conference-houston"),
                                 _row("2027-big-conference-tbd", city="")])
    assert fde.classify(rows) == "PLACE"


def test_a_suburb_is_place_drift_not_a_second_event(tmp_path):
    """St. Louis -> Clayton, live on 2026-09-12. The runbook's clean_city hazard, from the
    other direction: the venue's town replaced the city and the key moved with it."""
    rows = _one_group(tmp_path, [_row("2026-secureworld-st-louis-st-louis", name="SecureWorld St. Louis 2026",
                                      city="St. Louis", edition="2026"),
                                 _row("2026-secureworld-st-louis-clayton", name="SecureWorld St. Louis 2026",
                                      city="Clayton", edition="2026")])
    assert fde.classify(rows) == "PLACE"


def test_an_opportunity_suffix_is_flagged_but_named_as_itself(tmp_path):
    """event_id() adds OPPORTUNITY on purpose - CEDIA Expo runs a call for presentations AND a
    Best of Show awards entry, two submissions with two deadlines. So this is surfaced for a
    human, never assumed to be a duplicate."""
    rows = _one_group(tmp_path, [_row("2027-big-conference-houston"),
                                 _row("2027-big-conference-houston-awards")])
    assert fde.classify(rows) == "OPPORTUNITY"


def test_more_than_two_rows_is_never_auto_classified(tmp_path):
    rows = _one_group(tmp_path, [_row("2026-big-conference-houston", edition="2026"),
                                 _row("2027-big-conference-houston"),
                                 _row("2027-big-conference-tbd", city="")])
    assert fde.classify(rows) == "MIXED"


def test_a_lone_row_is_not_a_group(tmp_path):
    con = sqlite3.connect(_db(tmp_path, [_row("2027-big-conference-houston")]))
    con.row_factory = sqlite3.Row
    assert fde.groups(con, "grounding_facts") == {}
    con.close()


def test_two_rounds_of_one_call_are_reported_as_a_deadline_conflict(tmp_path):
    """Live on 2026-09-14: both rows verified against the same page, one quoting the REGULAR
    round (19 Oct) and one the LATE round (20 Dec). Neither date is wrong, and the schema has
    no column that says which round a deadline belongs to - so it has to reach a person."""
    rows = _one_group(tmp_path, [_row("2026-big-conference-houston", deadline="2026-12-20",
                                      verify_state="verified", source_as_of="2026-08-07"),
                                 _row("2027-big-conference-houston", deadline="2026-10-19",
                                      verify_state="verified")])
    assert fde.conflicting(rows) is True


def test_one_side_having_no_deadline_is_not_a_conflict(tmp_path):
    """A blank is not a rival claim. Calling it one would bury the real conflicts in noise."""
    rows = _one_group(tmp_path, [_row("2026-big-conference-houston", deadline="2026-12-20"),
                                 _row("2027-big-conference-houston", deadline="")])
    assert fde.conflicting(rows) is False


def test_agreeing_deadlines_are_not_a_conflict(tmp_path):
    rows = _one_group(tmp_path, [_row("2026-big-conference-houston", deadline="2026-09-10"),
                                 _row("2027-big-conference-houston", deadline="2026-09-10")])
    assert fde.conflicting(rows) is False


def test_a_registration_suffix_is_not_a_second_opportunity(tmp_path):
    """Decided 2026-09-14. Attending is not something the customer submits to, so a key split
    by it is one event held twice. None of the seven live suffix pairs had a deadline on either
    row - and two deadlines is the whole reason OPPORTUNITY is in the key."""
    rows = _one_group(tmp_path, [_row("2027-big-conference-houston"),
                                 _row("2027-big-conference-houston-registration")])
    assert fde.classify(rows) == "NON_OPPORTUNITY"


def test_exhibiting_remains_a_real_opportunity(tmp_path):
    """A stand is a commercial opportunity the pipeline already tracks, and what a customer
    looks at when speaking is unavailable. It is surfaced, never merged on assumption."""
    rows = _one_group(tmp_path, [_row("2026-it-sa-expo-congress-nuremberg",
                                      name="it-sa Expo & Congress 2026", edition="2026",
                                      city="Nuremberg"),
                                 _row("2026-it-sa-expo-congress-nuremberg-exhibiting",
                                      name="it-sa Expo & Congress 2026", edition="2026",
                                      city="Nuremberg")])
    assert fde.classify(rows) == "OPPORTUNITY"


def _con(tmp_path, rows):
    import sqlite3
    p = _db(tmp_path, rows)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    return con


def _row2(event_id, name, city="Houston", start="2027-02-10", edition="2027"):
    r = _row(event_id, name=name, city=city, edition=edition)
    r["start_date"] = start
    return r


def test_it_finds_the_duplicate_the_name_grouping_cannot_see(tmp_path):
    """`&` against `and` produces two different name slugs, so slug grouping never groups them.
    Two rows for one event always share its city and its dates. Live on 2026-09-15: IEEE
    Symposium on Security & Privacy beside IEEE Symposium on Security and Privacy."""
    con = _con(tmp_path, [
        _row2("2026-ieee-sp-sf", "IEEE Symposium on Security & Privacy 2026", "San Francisco",
              "2026-05-18", "2026"),
        _row2("2026-ieee-security-and-privacy-sf", "IEEE Symposium on Security and Privacy 2026",
              "San Francisco", "2026-05-18", "2026")])
    pairs = fde.city_date_pairs(con, "grounding_facts", set())
    con.close()
    assert len(pairs) == 1


def test_a_satellite_event_is_not_called_a_duplicate(tmp_path):
    """THE INVERSION THAT MATTERS. 50 pairs in our data share a city and start within a day,
    because big shows carry satellites - AppSec Village sits inside DEF CON, ShowStoppers inside
    CES, and Berlin ran four IFA events on one morning. City and date alone would merge them."""
    con = _con(tmp_path, [
        _row2("2026-def-con-34-las-vegas", "DEF CON 34", "Las Vegas", "2026-08-06", "2026"),
        _row2("2026-appsec-village-las-vegas", "AppSec Village at DEF CON 34", "Las Vegas",
              "2026-08-06", "2026")])
    pairs = fde.city_date_pairs(con, "grounding_facts", set())
    con.close()
    assert pairs == []


def test_two_unrelated_conferences_in_one_city_are_not_a_duplicate(tmp_path):
    """Las Vegas really did hold D.I.C.E. Summit and the National Ethanol Conference on
    2027-02-16."""
    con = _con(tmp_path, [
        _row2("2027-dice-summit-las-vegas", "D.I.C.E. Summit 2027", "Las Vegas", "2027-02-16"),
        _row2("2027-national-ethanol-conference-las-vegas", "National Ethanol Conference 2027",
              "Las Vegas", "2027-02-16")])
    pairs = fde.city_date_pairs(con, "grounding_facts", set())
    con.close()
    assert pairs == []


def test_a_different_city_is_never_paired(tmp_path):
    con = _con(tmp_path, [
        _row2("2027-widget-expo-houston", "Widget Expo 2027", "Houston", "2027-02-10"),
        _row2("2027-widget-expo-boston", "Widget Expo 2027", "Boston", "2027-02-10")])
    pairs = fde.city_date_pairs(con, "grounding_facts", set())
    con.close()
    assert pairs == []


def test_dates_a_week_apart_are_not_the_same_event(tmp_path):
    con = _con(tmp_path, [
        _row2("2027-widget-expo-houston", "Widget Expo 2027", "Houston", "2027-02-10"),
        _row2("2027-widget-expo-houston-b", "Widget Expo 2027", "Houston", "2027-02-18")])
    pairs = fde.city_date_pairs(con, "grounding_facts", set())
    con.close()
    assert pairs == []


def test_a_pair_the_name_grouping_already_reported_is_not_repeated(tmp_path):
    """One finding, once. The name detector runs first and hands over what it grouped."""
    con = _con(tmp_path, [
        _row2("2026-widget-expo-houston", "Widget Expo 2027", "Houston", "2027-02-10", "2027"),
        _row2("2027-widget-expo-houston", "Widget Expo 2027", "Houston", "2027-02-10", "2027")])
    already = {frozenset(("2026-widget-expo-houston", "2027-widget-expo-houston"))}
    assert fde.city_date_pairs(con, "grounding_facts", already) == []
    con.close()


def test_a_row_without_a_date_is_simply_not_compared(tmp_path):
    """Undated rows are invisible here rather than wrongly paired - 36 rows still carry no
    start date, and a missing date must never read as an agreeing one."""
    con = _con(tmp_path, [
        _row2("2027-widget-expo-houston", "Widget Expo 2027", "Houston", "2027-02-10"),
        _row2("2027-widget-expo-houston-b", "Widget Expo 2027", "Houston", None)])
    pairs = fde.city_date_pairs(con, "grounding_facts", set())
    con.close()
    assert pairs == []


# ---------------------------------------------------------------------------------------------
# DECLARED DECISIONS. A pair a person read and kept as two rows must stop being reported as work
# outstanding - but must never stop being reported. The lesson from 2026-09-15 is that a check
# which cannot tell a reasoned decision from a fault teaches people to stop running it, and the
# failure mode on the other side is a decision that silently hides a real duplicate forever.

def _decisions(tmp_path, text):
    p = tmp_path / "duplicate_decisions.txt"
    p.write_text(text, encoding="utf-8")
    return fde.load_decisions(p)


def test_a_declared_pair_is_read_with_its_date_and_its_reason():
    """The real file must parse - the three live decisions are in it, and a silent parse failure
    would put a settled pair back in front of a person every week."""
    live = fde.load_decisions()
    assert frozenset(("2027-world-biogas-summit-birmingham",
                      "2027-world-biogas-expo-birmingham")) in live
    when, who, why = live[frozenset(("2027-world-biogas-summit-birmingham",
                                     "2027-world-biogas-expo-birmingham"))]
    assert when == "2026-09-15" and who == "operator" and "trade show" in why


def test_comments_and_blank_lines_decide_nothing(tmp_path):
    got = _decisions(tmp_path, "# a comment mentioning 2027-a and 2027-b\n\n   \n")
    assert got == {}


def test_a_line_naming_one_row_decides_nothing(tmp_path):
    """A decision is about a PAIR. One id cannot settle a group, and a typo that drops an id
    must fail closed - reporting the group again - not open."""
    assert _decisions(tmp_path, "2026-09-16 2027-only-one | operator | oops\n") == {}


def test_a_decision_settles_the_exact_set_it_names(tmp_path):
    """If a third row joins the group later, the set no longer matches and the group is reported
    again. New evidence reopens the question."""
    got = _decisions(tmp_path, "2026-09-16 2027-a 2027-b | operator | co-located\n")
    assert frozenset(("2027-a", "2027-b")) in got
    assert frozenset(("2027-a", "2027-b", "2027-c")) not in got
