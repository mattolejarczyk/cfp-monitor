"""Offline tests for grounding verification.

The rule under test throughout: "we couldn't find it" is NEVER a disproof. Only positive
contrary evidence may override a grounding claim, and our own stored data has to be current
and well-crawled before it counts as contrary evidence at all.
"""
from datetime import date

from cfp_monitor.verify import (
    CONTRADICTED, NOT_FOUND, VERIFIED, cross_check, date_variants, find_date,
    other_deadline_dates, verify_against_page,
)

TODAY = date(2026, 7, 29)


# ---- date-token matching ---------------------------------------------------
def test_matches_every_common_rendering_of_a_date():
    d = date(2026, 3, 15)
    for text in ("Submissions close March 15, 2026", "deadline 15 March 2026",
                 "due 2026-03-15", "by 3/15/2026", "closes March 15th, 2026",
                 "DEADLINE:  MARCH 15,  2026"):
        assert find_date(text, d), text


def test_does_not_match_a_neighbouring_date():
    d = date(2026, 3, 15)
    assert not find_date("March 16, 2026", d)
    assert not find_date("March 15, 2027", d)


def test_variants_are_normalized_for_comparison():
    assert all(v == v.lower().strip() for v in date_variants(date(2026, 3, 15)))


# ---- page verification: three outcomes -------------------------------------
def test_page_stating_the_date_verifies():
    assert verify_against_page("Papers due March 15, 2026", "3/15/2026").state == VERIFIED


def test_page_stating_a_different_deadline_contradicts():
    out = verify_against_page("Abstract submission deadline: April 30, 2026.", "3/15/2026")
    assert out.state == CONTRADICTED and "april 30 2026" in out.detail.lower()


def test_silent_page_is_not_found_so_grounding_stands():
    out = verify_against_page("Welcome to the conference. Register now.", "3/15/2026")
    assert out.state == NOT_FOUND


def test_unreadable_page_is_not_found():
    assert verify_against_page("", "3/15/2026").state == NOT_FOUND


def test_a_date_elsewhere_on_the_page_is_not_a_contradiction():
    """Only DEADLINE-labelled dates count; the event's own dates must not trigger one."""
    out = verify_against_page("The conference runs June 2, 2026 in Berlin.", "3/15/2026")
    assert out.state == NOT_FOUND


def test_other_deadline_dates_ignores_the_target_itself():
    assert other_deadline_dates("deadline March 15, 2026", exclude=date(2026, 3, 15)) == []


# ---- cross-check against our own crawl: conservative -----------------------
def _ours(deadline, quality="PASS"):
    return {"cfp_close_date": deadline, "quality": quality}


def test_agreement_verifies():
    out = cross_check("3/15/2026", "Open", _ours("March 15, 2026"), TODAY, "2026")
    assert out.state == VERIFIED


def test_our_stale_value_must_not_override_grounding():
    """Regression: our stored deadline is often from a previous edition. Overriding a current
    grounding claim with it would make the data worse, so we decline instead."""
    assert cross_check("4/6/2026", "Open", _ours("November 24, 2024"), TODAY, "2026") is None
    assert cross_check("7/15/2026", "Open", _ours("August 26, 2025"), TODAY, "2026") is None


def test_our_non_date_value_cannot_contradict():
    """Prose and yearless fragments are not firm enough to disprove a grounding claim."""
    assert cross_check("7/15/2026", "Open", _ours("closed"), TODAY, "2026") is None
    assert cross_check("4/30/2026", "Open", _ours("May 8th"), TODAY, "2026") is None
    assert cross_check("4/30/2026", "Open", _ours("TBD"), TODAY, "2026") is None


def test_a_poor_quality_crawl_cannot_contradict():
    assert cross_check("3/15/2027", "Open", _ours("June 1, 2027", quality="PARTIAL"),
                       TODAY, "2027") is None


def test_current_well_crawled_disagreement_does_contradict():
    out = cross_check("3/15/2027", "Open", _ours("June 1, 2027"), TODAY, "2027")
    assert out.state == CONTRADICTED and "June 1, 2027" in out.detail


def test_declines_when_either_side_has_no_deadline():
    assert cross_check("", "Open", _ours("June 1, 2027"), TODAY, "2027") is None
    assert cross_check("3/15/2027", "Open", _ours(""), TODAY, "2027") is None


def test_archive_noise_does_not_create_a_false_contradiction():
    """Regression: pages carry old dates near deadline wording (archives, copyright lines).
    Citing those as a contradiction would wrongly override the discovery layer."""
    page = "Submission deadline January 1, 2018 (archived). Register now."
    assert verify_against_page(page, "3/15/2027").state == NOT_FOUND


def test_a_plausible_current_cycle_date_still_contradicts():
    page = "Submission deadline April 30, 2027."
    assert verify_against_page(page, "3/15/2027").state == CONTRADICTED
