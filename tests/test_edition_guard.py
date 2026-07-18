"""Offline tests for the edition / stale-page consistency guard (consolidate.py).

The guard must be conservative: fire only on unambiguous years, and only ever downgrade a
shaky Open to Needs Review (never fabricate an Open, never flag messy/ambiguous data).
"""
from datetime import date

from cfp_monitor.consolidate import _lone_year, edition_consistency
from cfp_monitor.models import CFPStatus


def test_lone_year_only_when_unambiguous():
    assert _lone_year("June 2026") == 2026
    assert _lone_year("Deadline: 2026-06-29") == 2026
    assert _lone_year(None) is None
    assert _lone_year("no year here") is None
    # Two distinct years -> ambiguous -> None (guard stays silent to avoid false flags).
    assert _lone_year("2025 and 2026 editions") is None


def test_rule_a_deadline_after_event_is_impossible():
    status, basis = edition_consistency(
        CFPStatus.open, "explicit_open",
        close_date_value="March 2027", event_dates_value="June 2026")
    assert status == CFPStatus.unclear
    assert basis == "deadline_after_event_conflict"


def test_rule_b_inferred_open_with_past_deadline_downgrades():
    status, basis = edition_consistency(
        CFPStatus.open, "inferred_from_live_submission_form",
        close_date_value="Jan 2023", event_dates_value=None,
        today=date(2026, 7, 18))
    assert status == CFPStatus.unclear
    assert basis == "inferred_open_but_deadline_past"


def test_explicit_open_with_past_deadline_is_left_alone():
    # An EXPLICIT open (page literally says open) is not second-guessed by rule B.
    status, basis = edition_consistency(
        CFPStatus.open, "explicit_open",
        close_date_value="Jan 2023", event_dates_value=None,
        today=date(2026, 7, 18))
    assert status == CFPStatus.open
    assert basis == "explicit_open"


def test_consistent_dates_unchanged():
    status, basis = edition_consistency(
        CFPStatus.open, "explicit_open",
        close_date_value="June 2026", event_dates_value="Sept 2026")
    assert status == CFPStatus.open
    assert basis == "explicit_open"


def test_ambiguous_years_do_not_fire():
    # Messy multi-year strings must not trigger a downgrade.
    status, basis = edition_consistency(
        CFPStatus.open, "explicit_open",
        close_date_value="2025 / 2027", event_dates_value="2026")
    assert status == CFPStatus.open
