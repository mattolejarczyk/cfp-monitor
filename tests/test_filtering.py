"""Offline tests for the conservative deadline parser + windowing (filtering.py)."""
from datetime import date

from cfp_monitor.filtering import closing_within, days_until, parse_deadline

TODAY = date(2026, 7, 18)


def test_parses_only_fully_specified_dates():
    assert parse_deadline("Thursday, September 10, 2026, by 5:00 p.m. PT") == date(2026, 9, 10)
    assert parse_deadline("2026-12-20") == date(2026, 12, 20)


def test_partial_or_undated_returns_none_never_guesses():
    assert parse_deadline(None) is None
    assert parse_deadline("") is None
    assert parse_deadline("September 2026") is None      # no day
    assert parse_deadline("29-May") is None              # no year
    assert parse_deadline("9-Sep-26") is None            # 2-digit year is not trusted
    assert parse_deadline("04.17.() 17:00") is None      # no real year


def test_days_until_and_windows():
    assert days_until("2026-08-01", today=TODAY) == 14
    assert closing_within("2026-08-01", 30, today=TODAY) is True
    assert closing_within("2026-08-01", 7, today=TODAY) is False      # outside the window
    assert closing_within("2026-07-01", 30, today=TODAY) is False     # already past
    assert closing_within("September 2026", 90, today=TODAY) is False  # undated -> excluded


def test_past_due_detection():
    assert days_until("2026-06-01", today=TODAY) < 0
    assert days_until("undated string", today=TODAY) is None
