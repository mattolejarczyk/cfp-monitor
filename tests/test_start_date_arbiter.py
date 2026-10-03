"""scripts/start_date_arbiter.py: year-specific proof of a start date, range expansion, year checks."""
from datetime import date

from scripts.start_date_arbiter import arbitrate_row, expand_ranges, first_date, year_checks

T = date(2026, 10, 3)


def _row(**kw):
    base = {"CONFERENCE": "Conf", "EDITION": "2026", "STATUS": "Open", "START DATE": "2026-02-11",
            "CONFERENCE DATES": "October 21 - October 23, 2026", "SUBMISSION DEADLINE": "2026-07-01"}
    base.update(kw)
    return base


def test_first_date_formats():
    assert first_date("October 21 - October 23, 2026") == date(2026, 10, 21)
    assert first_date("June 23 - 24, 2026") == date(2026, 6, 23)
    assert first_date("21-23 October 2026") == date(2026, 10, 21)
    assert first_date("") is None and first_date("TBD") is None and first_date("March 3") is None   # no year: never invented


def test_expand_ranges_keeps_year():
    assert "october 21, 2026 - october 23, 2026" in expand_ranges("The conference takes place October 21-23, 2026.").lower()
    assert "21 october 2026 - 23 october 2026" in expand_ranges("held 21-23 October 2026").lower()
    assert expand_ranges("October 21-23") == "October 21-23"      # no year, left alone


def test_page_proves_b_in_event_context_and_year_specific():
    pages = [("u", "The conference takes place October 21-23, 2026 at the Convention Center.")]
    r = arbitrate_row(_row(), pages)
    assert r["verdict"] == "B" and r["use"] == "2026-10-21" and r["url"] == "u"
    # the same text but another year must NOT prove a 2027 candidate
    r2 = arbitrate_row(_row(**{"START DATE": "2027-10-21", "CONFERENCE DATES": "October 22 - 23, 2027", "EDITION": "2027"}),
                       [("u", "The conference takes place October 21-23, 2026.")])
    assert r2["verdict"] == "neither"


def test_a_only_both_neither_and_agree():
    page_a = [("u", "The conference is held February 11-13, 2026 in Denver.")]
    assert arbitrate_row(_row(), page_a)["verdict"] == "A"
    both = page_a + [("v", "The conference takes place October 21-23, 2026.")]
    r = arbitrate_row(_row(), both)
    assert r["verdict"] == "both" and r["use"] == "2026-02-11"          # status quo kept, flagged
    assert arbitrate_row(_row(), [("u", "nothing here")])["verdict"] == "neither"
    assert arbitrate_row(_row(**{"START DATE": "2026-10-21"}), [])["verdict"] == "agree"


def test_year_checks():
    assert year_checks(_row(**{"START DATE": "2026-10-21"}), T) == []
    f = year_checks(_row(**{"START DATE": "2027-02-11"}), T)
    assert any(x.startswith("Y1") for x in f) and any(x.startswith("Y2") for x in f)
    assert any(x.startswith("Y3") for x in year_checks(_row(), T))                    # Feb 2026 start, Open on 2026-10-03
    assert any(x.startswith("Y4") for x in year_checks(_row(**{"START DATE": "2026-10-21", "SUBMISSION DEADLINE": "2026-11-01"}), T))
    assert any(x.startswith("Y4") for x in year_checks(_row(**{"START DATE": "2026-10-21", "SUBMISSION DEADLINE": "2024-01-01"}), T))
