"""Offline tests for grounding verification.

The rule under test throughout: "we couldn't find it" is NEVER a disproof. Only positive
contrary evidence may override a grounding claim, and our own stored data has to be current
and well-crawled before it counts as contrary evidence at all.
"""
from datetime import date

from cfp_monitor.verify import (
    CONTRADICTED, NOT_FOUND, VERIFIED, closure_evidence, cross_check,
    Outcome, cross_check, cross_check_status, date_variants, find_date, l2_detail, no_page_detail,
    other_deadline_dates, page_status,
    verify_against_page,
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


def test_a_failed_crawl_cannot_CONFIRM_either():
    """Regression: a record populated FROM the discovery layer (because our own crawl failed)
    made cross_check 'verify' grounding against grounding's own data -- circular
    self-confirmation. A non-PASS crawl must decline both ways."""
    assert cross_check("8/31/2026", "Open", _ours("8/31/2026", quality="ERROR"),
                       TODAY, "2026") is None
    assert cross_check("8/31/2026", "Open", _ours("August 31, 2026", quality="BLOCKED"),
                       TODAY, "2026") is None
    # ...but a real successful crawl that agrees still verifies
    out = cross_check("8/31/2026", "Open", _ours("August 31, 2026", quality="PASS"),
                      TODAY, "2026")
    assert out.state == VERIFIED


def test_zero_padded_day_matches():
    """Regression: 'December 04, 2026' failed to match a 12/4/2026 claim, producing a false
    contradiction against a date that was printed on the page."""
    d = date(2026, 12, 4)
    for text in ("Submission deadline: December 04, 2026", "deadline 04 December 2026",
                 "Submission deadline: December 4, 2026", "due 12/04/2026"):
        assert find_date(text, d), text


def test_padding_does_not_create_false_matches():
    assert not find_date("December 14, 2026", date(2026, 12, 4))
    assert not find_date("December 04, 2027", date(2026, 12, 4))


# ---- status verification: the question that actually matters ---------------
def test_closure_language_is_detected():
    """The real SEMICON Europa page text: definitive closure with no date at all."""
    real = ("The deadline has expired, and submissions will no longer be accepted. "
            "We thank all authors who have submitted their abstracts.")
    assert page_status(real) == "closed"
    assert "deadline has expired" in closure_evidence(real).lower()


def test_open_language_is_detected():
    assert page_status("The Call for Papers is now open. Submit your abstract today.") == "open"


def test_closed_wins_when_both_phrases_appear():
    """Pages keep their 'submit your abstract' banner above an expiry notice."""
    assert page_status("Submit your abstract. NOTE: the deadline has passed.") == "closed"


def test_neutral_page_yields_no_status():
    assert page_status("Welcome to the conference. Register now.") is None
    assert page_status("") is None


def test_page_saying_closed_contradicts_a_claim_of_open():
    out = verify_against_page("The deadline has expired; submissions are no longer accepted.",
                              "", "Open")
    assert out.state == CONTRADICTED and "CLOSED" in out.detail


def test_page_saying_closed_verifies_when_no_date_is_claimed():
    """A closed call with no date is fully actionable - that is a verification, not a gap."""
    out = verify_against_page("Call for papers is now closed.", "", "Closed")
    assert out.state == VERIFIED


def _crawled(status, basis, quality="PASS"):
    import json
    return {"cfp_status": status, "quality": quality,
            "result_json": json.dumps({"status_basis": basis})}


def test_explicit_page_status_contradicts_a_wrong_claim():
    out = cross_check_status("Open", _crawled("closed", "explicit_closed"))
    assert out.state == CONTRADICTED and "CLOSED" in out.detail


def test_explicit_page_status_verifies_a_matching_claim():
    assert cross_check_status("Closed", _crawled("closed", "explicit_closed")).state == VERIFIED


def test_open_and_upcoming_are_not_treated_as_a_conflict():
    """Both mean the opportunity is still live; that is not a disagreement worth flagging."""
    assert cross_check_status("Upcoming", _crawled("open", "explicit_open")).state == VERIFIED


def test_inferred_status_is_not_firm_enough_to_contradict():
    assert cross_check_status("Open", _crawled("closed", "inferred_from_live_submission_form")) is None
    assert cross_check_status("Open", _crawled("closed", "explicit_closed", quality="ERROR")) is None


# ---- PDF citations ---------------------------------------------------------
def test_unparseable_pdf_yields_no_text_not_a_false_disproof():
    """A PDF we cannot read must return empty text, which resolves to not_found. It must
    never raise, and must never be mistaken for 'the deadline is absent from the page'."""
    from cfp_monitor.verify import _pdf_text

    text, note = _pdf_text(b"%PDF-1.4 this is not actually a valid pdf body")
    assert text == "" and "pdf" in note.lower()


def test_pdf_text_never_raises_on_junk():
    from cfp_monitor.verify import _pdf_text

    for junk in (b"", b"\x00\x01\x02", b"%PDF-"):
        text, note = _pdf_text(junk)
        assert text == ""


def test_a_pdf_with_no_extractable_text_is_reported_as_such():
    """Scanned/image-only PDFs parse fine but yield nothing; say so rather than implying
    the page was silent about the deadline."""
    from cfp_monitor.verify import _pdf_text

    text, note = _pdf_text(b"%PDF-1.4 garbage")
    assert text == ""
    assert "pdf" in note


# ---- provenance: label the result by the page we actually read -------------
def test_cited_page_result_is_reported_verbatim():
    out = Outcome(NOT_FOUND, "deadline not stated on the page - grounding value stands", "L2")
    d = l2_detail(out, "https://x.org/cfp", "https://x.org/cfp")
    assert "cited page" in d
    assert "deadline not stated on the page" in d


def test_trailing_slash_does_not_make_the_cited_page_look_like_a_fallback():
    out = Outcome(NOT_FOUND, "deadline not stated on the page", "L2")
    assert "cited page" in l2_detail(out, "https://x.org/cfp/", "https://x.org/cfp")


def test_silent_fallback_page_is_never_reported_as_a_silent_citation():
    """The bug this guards: a homepage that never carried the deadline was being
    reported as 'deadline not stated on the page', which reads like we checked
    the cited source and found it silent."""
    out = Outcome(NOT_FOUND, "deadline not stated on the page - grounding value stands", "L2")
    d = l2_detail(out, "https://x.org/", "")
    assert "no evidence URL supplied" in d
    assert "unverifiable" in d
    assert "deadline not stated on the page" not in d


def test_fallback_distinguishes_missing_citation_from_unreadable_one():
    out = Outcome(NOT_FOUND, "deadline not stated on the page", "L2")
    assert "no evidence URL supplied" in l2_detail(out, "https://x.org/", "")
    assert "cited page unreadable" in l2_detail(out, "https://x.org/", "https://x.org/gone")


def test_positive_evidence_survives_a_fallback_but_is_marked_as_such():
    """A homepage saying the call is closed IS evidence -- keep it, but say where it came from."""
    out = Outcome(CONTRADICTED, "the page states the call is CLOSED", "L2")
    d = l2_detail(out, "https://x.org/", "")
    assert "the page states the call is CLOSED" in d
    assert "not the cited page" in d


def test_no_page_read_separates_missing_citation_from_dead_citation():
    assert "no evidence URL supplied" in no_page_detail("")
    assert "could not be read" in no_page_detail("https://x.org/gone")
    assert "x.org/gone" in no_page_detail("https://x.org/gone")


def test_a_fallback_never_changes_the_verdict_itself():
    """Relabelling is cosmetic: state must be untouched, so no row flips on this fix."""
    for state in (VERIFIED, CONTRADICTED, NOT_FOUND):
        out = Outcome(state, "detail", "L2")
        l2_detail(out, "https://x.org/", "")
        assert out.state == state


# ---- status cross-check must be as conservative as the deadline cross-check --
def _status_rec(**kw):
    base = {"quality": "PASS", "result_json": '{"status_basis": "explicit_text"}',
            "cfp_status": "open", "cfp_close_date": "", "edition": ""}
    base.update(kw)
    return base


def test_status_check_declines_across_editions():
    """Real case: our 2026 embedded world row was used to contradict a 2027 claim."""
    assert cross_check_status("upcoming", _status_rec(cfp_status="closed", edition="2026"),
                              TODAY, edition="2027") is None


def test_status_check_still_works_when_editions_agree():
    out = cross_check_status("upcoming", _status_rec(cfp_status="closed", edition="2027"),
                             TODAY, edition="2027")
    assert out.state == CONTRADICTED


def test_status_check_declines_when_our_own_record_has_expired():
    """Real case: an IBC row reading 'open' whose own close date was 5 Dec 2025."""
    stale = _status_rec(cfp_status="open", cfp_close_date="5 December 2025")
    assert cross_check_status("closed", stale, TODAY) is None


def test_status_check_accepts_a_record_whose_deadline_is_still_ahead():
    fresh = _status_rec(cfp_status="open", cfp_close_date="December 5, 2026")
    assert cross_check_status("open", fresh, TODAY).state == VERIFIED


def test_status_check_ignores_editions_when_one_side_is_unknown():
    """A missing edition must not silently suppress a real conflict."""
    out = cross_check_status("upcoming", _status_rec(cfp_status="closed", edition=""),
                             TODAY, edition="2027")
    assert out.state == CONTRADICTED
