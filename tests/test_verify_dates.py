"""Date rendering coverage for verification.

A missed rendering does not fail loudly - it silently records a row as unverified when the
page states the date plainly. That is the worst shape of bug here, because it looks like a
data problem on the other side.
"""
import datetime

from src.cfp_monitor.verify import find_date


def test_september_is_abbreviated_sept_as_often_as_sep():
    """Regression 2026-08-11. AMP's page reads "Case Study Submission Closes: 11:59 p.m. ET,
    Friday, Sept. 4, 2026". strftime("%b") yields "Sep", so the claim did not match and the
    row was recorded unverified while the page said it plainly."""
    d = datetime.date(2026, 9, 4)
    for text in ("Closes Friday, Sept. 4, 2026", "Closes Sept 4, 2026",
                 "Closes Sep. 4, 2026", "Closes Sep 4, 2026",
                 "Closes September 4, 2026", "Closes 4 September 2026"):
        assert find_date(text, d), text


def test_common_renderings_still_match():
    assert find_date("Abstracts due March 15, 2026", datetime.date(2026, 3, 15))
    assert find_date("Abstracts due 15 March 2026", datetime.date(2026, 3, 15))
    assert find_date("Abstracts due 2026-03-15", datetime.date(2026, 3, 15))
    assert find_date("Abstracts due 3/15/2026", datetime.date(2026, 3, 15))
    assert find_date("Abstracts due Mar. 15, 2026", datetime.date(2026, 3, 15))


def test_zero_padded_day_matches():
    """A page reading "December 04, 2026" once failed to match a claim of 12/4/2026 and was
    reported as a CONTRADICTION against a date printed on the page."""
    assert find_date("Deadline December 04, 2026", datetime.date(2026, 12, 4))


def test_a_different_date_does_not_match():
    assert not find_date("Deadline September 5, 2026", datetime.date(2026, 9, 4))
    assert not find_date("Deadline Sept. 5, 2026", datetime.date(2026, 9, 4))
