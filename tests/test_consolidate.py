"""Regression tests for the reviewer-facing consolidation summary."""

from cfp_monitor.consolidate import _build_reason
from cfp_monitor.models import CFPStatus, ConferenceResult, Fact


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
