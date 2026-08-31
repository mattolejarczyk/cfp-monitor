"""R22 (inadmissible citation sources) and R23 (which of several rounds is THE deadline).

Both came out of the same afternoon, 2026-08-31, working the customer's "Needs Verification"
queue - the first time a real person's corrections reached our rules.
"""
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import rules              # noqa: E402

TODAY = date(2026, 8, 31)

# The real case: on-climate.com, read from the page on 2026-08-31.
CLIMATE = [("Early", "2026-06-19"), ("Regular", "2026-10-19"), ("Late", "2026-12-20")]


# --------------------------------------------------------------------- R23

def test_the_deadline_shown_is_the_next_one_a_person_can_act_on():
    """Their sheet held 19 October (Regular), ours held 20 December (Late). Both correct.
    19 October is the answer, because it is the next one still open."""
    got, why, _notes = rules.next_actionable_deadline(CLIMATE, TODAY)
    assert got == "2026-10-19"
    assert "Regular" in why
    assert "1 earlier round(s) already passed" in why
    assert "1 later round(s) remain" in why


def test_a_passed_round_is_skipped_not_shown():
    """Early closed 19 June. Showing it would say the opportunity is gone when it is not."""
    got, _why, _n = rules.next_actionable_deadline(CLIMATE, date(2026, 6, 20))
    assert got == "2026-10-19"


def test_the_last_round_is_only_shown_once_everything_has_closed():
    got, why, _n = rules.next_actionable_deadline(CLIMATE, date(2027, 1, 5))
    assert got == "2026-12-20"
    assert "every round has closed" in why and "what was missed" in why


def test_every_round_survives_into_the_notes():
    """A passed round explains what was missed; a later one is the fallback. Nothing is
    discarded just because it is not the headline date."""
    _got, _why, notes = rules.next_actionable_deadline(CLIMATE, TODAY)
    body = " | ".join(notes)
    for lab in ("Early", "Regular", "Late"):
        assert lab in body
    assert "2026-06-19" in body and "2026-10-19" in body and "2026-12-20" in body
    assert "(passed)" in body, "a closed round must be marked closed"
    assert "next actionable" in body


def test_rounds_out_of_order_are_sorted_not_trusted():
    got, _why, _n = rules.next_actionable_deadline(
        [("Late", "2026-12-20"), ("Early", "2026-06-19"), ("Regular", "2026-10-19")], TODAY)
    assert got == "2026-10-19"


def test_a_single_round_behaves_exactly_as_before():
    """GOOD INPUT MUST SURVIVE. Most conferences have one deadline and must be unaffected."""
    got, why, notes = rules.next_actionable_deadline([("Deadline", "2026-11-01")], TODAY)
    assert got == "2026-11-01"
    assert "earlier round" not in why and "later round" not in why
    assert len(notes) == 1


def test_no_rounds_returns_nothing_rather_than_inventing_a_date():
    got, why, notes = rules.next_actionable_deadline([], TODAY)
    assert got is None and notes == [] and "no dated rounds" in why


def test_an_unparseable_round_is_dropped_not_guessed():
    got, _why, notes = rules.next_actionable_deadline(
        [("Early", "sometime in spring"), ("Regular", "2026-10-19")], TODAY)
    assert got == "2026-10-19"
    assert len(notes) == 1, "a date we cannot read is not a date"


# --------------------------------------------------------------------- R22

@pytest.mark.parametrize("url", [
    "https://www.facebook.com/InfoSecWorld/",          # the real 2026-08-31 case
    "https://twitter.com/someconf/status/123",
    "https://x.com/someconf",
    "https://www.linkedin.com/posts/abc",
    "https://bit.ly/3xyz",
    "https://hubs.ly/Q04sFNT-0",
])
def test_social_and_shortener_hosts_cannot_evidence_a_deadline(url):
    ok, why = rules.citation_source_admissible(url)
    assert ok is False and why


@pytest.mark.parametrize("url", [
    "https://defcon.org/html/defcon-34/dc-34-cfp.html",
    "https://on-climate.com/2027-conference/call-for-papers",
    "https://pretalx.com/troopers26/cfp",              # a real submission platform is fine
    "https://www.oxfordabstracts.com/stages/1234/submitter",
])
def test_a_real_event_or_submission_platform_is_admissible(url):
    """GOOD INPUT MUST SURVIVE. The rule targets a HOST CATEGORY, not third parties in
    general - plenty of legitimate calls are hosted on pretalx or Oxford Abstracts."""
    ok, why = rules.citation_source_admissible(url)
    assert ok is True, why


def test_matching_is_anchored_to_a_host_boundary():
    """`x.com` unanchored also matches matrix.com - the same bug already fixed once in
    sitewalk's NOT_A_PAGE."""
    assert rules.citation_source_admissible("https://matrix.com/cfp")[0] is True
    assert rules.citation_source_admissible("https://notfacebook.com/cfp")[0] is True
    assert rules.citation_source_admissible("https://m.facebook.com/cfp")[0] is False


def test_an_inadmissible_source_is_withdrawable_even_on_a_passed_deadline():
    """The passed-deadline refusal exists because the PAGE changed. It says nothing when the
    objection is to the host: a Facebook page could not evidence a deadline the day it was
    cited, and the deadline passing does not improve it."""
    row = {"SUBMISSION DEADLINE": "2026-04-03",
           "DEADLINE_EVIDENCE_URL": "https://www.facebook.com/InfoSecWorld/",
           "DEADLINE_QUOTE": "Call for Presentations closes soon on April 3!"}
    may, why = rules.may_withdraw_citation(row, quote_found=False, pages_read=6, today=TODAY)
    assert may is True
    assert "facebook.com" in why and "R22" in why


def test_the_passed_deadline_refusal_is_otherwise_untouched():
    """The 14-row mistake must stay prevented for every admissible source."""
    row = {"SUBMISSION DEADLINE": "2026-06-17",
           "DEADLINE_EVIDENCE_URL": "https://www.mrs.org/meetings-events/",
           "DEADLINE_QUOTE": "Abstract deadline June 17, 2026"}
    may, why = rules.may_withdraw_citation(row, quote_found=False, pages_read=50, today=TODAY)
    assert may is False and "deadline passed" in why


def test_a_found_quote_on_a_bad_host_is_still_withdrawn():
    """R22 is judged before the page content, on purpose. What a social post says does not
    make it a source."""
    row = {"SUBMISSION DEADLINE": "2027-04-03",
           "DEADLINE_EVIDENCE_URL": "https://www.facebook.com/InfoSecWorld/"}
    may, _why = rules.may_withdraw_citation(row, quote_found=True, pages_read=1, today=TODAY)
    assert may is True
