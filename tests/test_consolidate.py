"""Regression tests for the reviewer-facing consolidation summary."""

from cfp_monitor.consolidate import _build_reason, _date_key, consolidate
from cfp_monitor.models import CFPStatus, ConferenceResult, Fact, PageExtraction
from cfp_monitor.trace import Tracer


def _result(*, submission_url: str, form_found: bool, platform: str | None = None) -> ConferenceResult:
    result = ConferenceResult(start_url="https://event.example")
    result.cfp_status = CFPStatus.open
    result.status_basis = "explicit_open"
    result.submission_url = Fact(value=submission_url)
    result.submission_form_found = form_found
    result.submission_platform = platform
    return result


def test_reason_formats_unattributed_submit_link_without_stray_space_before_colon():
    reason = _build_reason(
        _result(submission_url="https://submit.example/proposal", form_found=True)
    )

    assert "Submit via: https://submit.example/proposal." in reason
    assert "Submit via :" not in reason


def test_reason_keeps_confirmed_submission_url_when_no_form_was_detected():
    reason = _build_reason(
        _result(submission_url="https://submit.example/proposal", form_found=False)
    )

    assert "Submission URL: https://submit.example/proposal." in reason


# --------------------------------------------------------------------------
# Multi-edition caution: pages must genuinely DISAGREE on the dates.
# Both directions are asserted on purpose - the bug was cosmetic differences
# raising a false "pages disagree" caution, and the risk of the fix is silencing
# a real disagreement. See the ABLC case in docs/operations.
# --------------------------------------------------------------------------
def _consolidated(*date_strings: str) -> ConferenceResult:
    pairs = [
        (f"https://event.example/p{i}", PageExtraction(conference_dates=d))
        for i, d in enumerate(date_strings)
    ]
    return consolidate(
        "https://event.example",
        pairs,
        forms=[],
        external_submissions=[],
        tracer=Tracer(),
        pages_crawled=len(date_strings),
        pages_skipped=0,
    )


def test_date_key_collapses_cosmetic_differences_only():
    canonical = _date_key("August 10-13, 2026")
    assert _date_key("AUGUST 10-13, 2026") == canonical      # case
    assert _date_key("Aug. 10-13, 2026") == canonical        # abbreviated month
    assert _date_key("August 10 - 13 2026") == canonical     # spacing / no comma
    assert _date_key("August 10–13, 2026") == canonical  # en-dash
    # A different date must NOT collapse.
    assert _date_key("August 10-13, 2027") != canonical
    assert _date_key("March 2-4, 2026") != canonical


def test_same_dates_written_differently_are_not_a_multi_edition_disagreement():
    res = _consolidated("AUGUST 10-13, 2026", "August 10-13, 2026", "Aug. 10 - 13 2026")

    assert res.possible_multi_edition_site is False
    assert "Caution" not in res.reason


def test_genuinely_different_dates_still_raise_the_multi_edition_caution():
    res = _consolidated("August 10-13, 2026", "March 2-4, 2027")

    assert res.possible_multi_edition_site is True
    assert "Caution: crawled pages disagree on dates" in res.reason
    # The competing values are reported verbatim for the reviewer.
    assert "August 10-13, 2026" in res.competing_event_mentions
    assert "March 2-4, 2027" in res.competing_event_mentions


def test_unparseable_date_strings_keep_their_own_identity():
    """An honest blank beats a confident guess: strings we cannot interpret are not
    force-merged, so a real disagreement between them is still reported."""
    res = _consolidated("Summer 2026", "Winter 2026")

    assert res.possible_multi_edition_site is True
