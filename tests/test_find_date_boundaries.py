"""verify.find_date: digit boundaries and the two-digit-year style (2026-10-02).

Two defects measured on the 350-page library (experiments/purpose_audit/find_date_recall_scan.py):

 1. FALSE POSITIVE. date_variants() produced "2 october 2026" and find_date did a bare substring test, so a claim of
    2026-10-02 was "found" on a page that only says "12 October 2026" (5 of 5 sampled cases on real pages, e.g. Black
    Hat's "12 October 2026"). A wrong date could be marked verified.
 2. MISSED STYLE. on-climate.com writes proposal periods as "19 October (26)". After normalisation that is
    "19 october 26", which no variant produced: 35 of 35 occurrences were missed.

Everything the old behaviour matched correctly must still match: the cases in tests/test_verify.py are unchanged.
"""
from datetime import date

from src.cfp_monitor.verify import find_date


# ---- false positives: a longer number must not satisfy a shorter one ------------------------------------
def test_day_two_is_not_found_inside_day_twelve():
    assert not find_date("Close date: 12 October 2026 (23:59 Singapore Time)", date(2026, 10, 2))


def test_month_first_day_is_not_a_suffix_match():
    assert not find_date("Deadline: October 12, 2026", date(2026, 10, 2))
    assert not find_date("Deadline: October 22, 2026", date(2026, 10, 2))
    assert not find_date("Deadline: October 12, 2026", date(2026, 10, 1))


def test_day_five_vs_twenty_five_and_one_vs_thirty_one():
    assert not find_date("25 September 2026", date(2026, 9, 5))
    assert not find_date("31 August 2026", date(2026, 8, 1))


def test_year_is_bounded_on_the_right():
    assert not find_date("12 October 20269", date(2026, 10, 12))
    assert not find_date("October 12, 20260", date(2026, 10, 12))


def test_numeric_forms_are_bounded_too():
    assert not find_date("on 12/10/2026", date(2026, 10, 2))       # day-first 12 Oct is not 2 Oct
    assert not find_date("1/12/2026", date(2026, 1, 2))
    assert find_date("on 2026-10-02", date(2026, 10, 2))
    assert not find_date("on 2026-10-021", date(2026, 10, 2))


# ---- the genuine matches still match ------------------------------------------------------------------
def test_real_renderings_still_match():
    d = date(2026, 10, 12)
    for text in ("Close date: 12 October 2026 (23:59 Singapore Time GMT/UTC +8)",
                 "Call for Briefings Closes: 12 October 2026 (23:59)",
                 "closes October 12, 2026.", "Oct. 12, 2026", "12th October 2026", "12 Oct 2026", "2026-10-12", "(12 October 2026)",
                 "deadline:12 October 2026", "Friday, October 12, 2026 at 5 p.m."):
        assert find_date(text, d), text
    assert find_date("Submission deadline : 15 October 2026", date(2026, 10, 15))
    assert find_date("Nominations are due by 5 p.m. PT on Friday, November 20, 2026.", date(2026, 11, 20))
    assert find_date("CALL FOR PAPERS CLOSES ON 30th October 2026", date(2026, 10, 30))
    assert find_date("Sept. 4, 2026", date(2026, 9, 4)) and find_date("December 04, 2026", date(2026, 12, 4))


def test_an_iso_timestamp_still_matches():
    assert find_date('"endDate": "2026-10-12T23:59:00Z"', date(2026, 10, 12))
    assert not find_date('"endDate": "2026-10-12T23:59:00Z"', date(2026, 10, 2))


def test_a_date_at_the_very_start_or_end_of_the_text_matches():
    assert find_date("12 October 2026", date(2026, 10, 12))
    assert find_date("Deadline 12 October 2026", date(2026, 10, 12))


# ---- the (yy) style -----------------------------------------------------------------------------------
def test_two_digit_year_in_brackets_matches():
    assert find_date("Regular | 20 June (26) to 19 October (26) | Late", date(2026, 10, 19))
    assert find_date("Regular | 20 June (26) to 19 October (26) | Late", date(2026, 6, 20))
    assert find_date("Launch to 19 June (26)", date(2026, 6, 19))
    assert find_date("October 19 (26)", date(2026, 10, 19))
    assert find_date("12 October 26", date(2026, 10, 12))


def test_two_digit_year_must_match_the_year_and_the_day():
    assert not find_date("19 October (27)", date(2026, 10, 19))
    assert not find_date("19 October (26)", date(2026, 10, 9))        # 9 is not 19
    assert not find_date("19 October (26)", date(2027, 10, 19))
    assert not find_date("19 October 260", date(2026, 10, 19))


def test_a_four_digit_year_is_not_misread_as_two_digit():
    # "19 october 2026" contains "19 october 20": the 2-digit variant for 2020 must not fire on it
    assert not find_date("19 October 2026", date(2020, 10, 19))
