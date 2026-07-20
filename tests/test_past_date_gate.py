"""Offline tests for the past-date quality gate.

Regression cover for a real leak: an event that has already happened was still shown as
Open/Upcoming in the customer sheets (the RESEARCH STATUS column never checked the date).
In July 2026 a 2025 event, or any 2026 event whose date has passed, must read Closed.
"""
from datetime import date

from cfp_monitor.customer_format import gated_status, is_past_edition, to_customer_row
from cfp_monitor.exec_report import bucket_of

TODAY = date(2026, 7, 20)


def _rec(**kw):
    base = dict(name="X", url="https://x.test", status="open", edition="", event_is_past=0)
    base.update(kw)
    return base


# ---- is_past_edition -------------------------------------------------------
def test_prior_year_edition_is_past():
    assert is_past_edition(_rec(edition="2025"), TODAY) is True
    assert is_past_edition(_rec(edition="2020"), TODAY) is True


def test_event_flagged_past_by_date_is_past():
    assert is_past_edition(_rec(edition="2026", event_is_past=1), TODAY) is True


def test_future_or_current_not_past():
    assert is_past_edition(_rec(edition="2027"), TODAY) is False
    assert is_past_edition(_rec(edition="2026", event_is_past=0), TODAY) is False
    assert is_past_edition(_rec(edition=""), TODAY) is False       # unknown is never "past"


# ---- gated_status ----------------------------------------------------------
def test_open_2025_event_becomes_closed():
    assert gated_status(_rec(status="open", edition="2025"), TODAY) == "closed"


def test_2026_event_already_held_becomes_closed():
    assert gated_status(_rec(status="open", edition="2026", event_is_past=1), TODAY) == "closed"


def test_live_future_event_keeps_its_status():
    assert gated_status(_rec(status="open", edition="2027"), TODAY) == "open"
    assert gated_status(_rec(status="upcoming", edition="2026"), TODAY) == "upcoming"


def test_no_opportunity_is_not_relabelled_closed():
    assert gated_status(_rec(status="none", edition="2025"), TODAY) == "none"


def test_upcoming_and_unclear_on_a_past_edition_also_close():
    assert gated_status(_rec(status="upcoming", edition="2025"), TODAY) == "closed"
    assert gated_status(_rec(status="unclear", edition="2024"), TODAY) == "closed"


# ---- customer sheet + rollup both honour the gate --------------------------
def test_research_status_column_shows_closed_for_past_edition():
    row = to_customer_row(_rec(status="open", edition="2025"), TODAY)
    assert row["RESEARCH STATUS"] == "Closed (2025)"
    assert "This edition (2025) has passed" in row["STATUS DETAILS"]


def test_rollup_buckets_a_past_open_event_as_closed():
    assert bucket_of(_rec(status="open", edition="2025"), TODAY) == "Closed"
    assert bucket_of(_rec(status="open", edition="2027"), TODAY) == "Open"
