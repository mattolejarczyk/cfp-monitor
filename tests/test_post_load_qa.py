"""scripts/post_load_qa.py: the comparisons that found the 2026-10-03 regressions by hand, as rules."""
from datetime import date

from scripts.post_load_qa import blank_rates, date_checks, deadline_changes, guessed_dates

T = date(2026, 10, 3)


def _r(**kw):
    base = {"name": "Conf", "deadline": "2026-10-09", "is_projected": "false", "deadline_evidence_url": "https://x/cfp", "deadline_quote": "closes 9 October 2026",
            "submission_url": "https://x/submit", "status": "Open", "start_date": "2027-01-01", "city": "Paris", "organizer": "Org", "overview": "o",
            "categories": "c", "coordinator_email": "e@x"}
    base.update(kw)
    return base


def test_lost_evidence_on_a_future_deadline_is_a_regression():
    old, new = {"a": _r()}, {"a": _r(deadline_evidence_url="", deadline_quote="", is_projected="true")}
    rows, flags, _ = deadline_changes(old, new, T)
    assert flags and "evidence page LOST" in flags[0] and "quote LOST" in flags[0] and "verified -> projected" in flags[0]


def test_deadline_lost_and_link_lost_are_flagged_a_move_is_not():
    f = deadline_changes({"a": _r()}, {"a": _r(deadline="", submission_url="")}, T)[1]
    assert "deadline LOST" in f[0] and "submission link LOST" in f[0]
    rows, flags, _ = deadline_changes({"a": _r()}, {"a": _r(deadline="2026-11-23")}, T)
    assert rows and not flags


def test_passed_deadlines_are_listed_separately_never_flagged():
    old, new = {"a": _r(deadline="2026-07-01")}, {"a": _r(deadline="")}
    rows, flags, past = deadline_changes(old, new, T)
    assert not rows and not flags and past


def test_blank_rate_rise_and_venue_city_are_flagged():
    old = {str(i): _r() for i in range(20)}
    new = {str(i): _r(organizer="", city="Marina Bay Sands") for i in range(20)}
    _, flags = blank_rates(old, new)
    assert any("organizer" in f for f in flags) and any("venue" in f for f in flags)
    assert blank_rates(old, old)[1] == []


def test_date_checks_find_disagreement_and_year_mixing():
    rows = [{"CONFERENCE": "A", "START DATE": "2026-02-11", "CONFERENCE DATES": "October 21 - October 23, 2026", "EDITION": "2026", "STATUS": "Closed",
             "SUBMISSION DEADLINE": ""},
            {"CONFERENCE": "B", "START DATE": "2027-06-08", "CONFERENCE DATES": "June 8 - June 9, 2026", "EDITION": "2026", "STATUS": "Closed", "SUBMISSION DEADLINE": ""}]
    r, flags = date_checks("Utility", rows, T)
    assert r[3] == 2 and any("Y1" in f for f in flags) and any("disagree" in f for f in flags)


def test_guessed_start_date_only_when_the_load_introduced_it_on_an_unverified_row():
    unv = dict(status="Needs Verification", is_projected="true", deadline_evidence_url="", start_date="2027-05-10")
    assert guessed_dates({"o": _r(**{**unv, "start_date": ""})}, {"o": _r(**unv)})
    assert not guessed_dates({"o": _r(**unv)}, {"o": _r(**unv)})              # already there before: normal
    assert not guessed_dates({"o": _r()}, {"o": _r(start_date="2027-05-10")})  # verified row: not flagged
    upc = {**unv, "status": "Upcoming"}                                       # the real ODSC load also set the status: still flagged
    assert guessed_dates({"o": _r(**{**upc, "start_date": ""})}, {"o": _r(**upc)})


def test_a_pinned_event_is_not_flagged_for_an_introduced_start_date():
    unv = dict(status="Upcoming", is_projected="true", deadline_evidence_url="", start_date="2027-05-10")
    old, new = {"o": _r(**{**unv, "start_date": ""})}, {"o": _r(**unv)}
    assert guessed_dates(old, new)                       # unpinned: listed for a person to confirm
    assert not guessed_dates(old, new, {"o"})            # pinned (operator verified): nothing to confirm
