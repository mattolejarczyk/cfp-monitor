"""scripts/narrow_overlay.py: keep last week's fields the narrow prompt does not ask, never touch fresh answers."""
from scripts.narrow_overlay import CARRY_FIELDS, overlay_narrow

CANON = lambda eid, lookup: lookup.get(eid, eid)


def _row(**kw):
    base = {"EVENT_ID": "e1", "CONFERENCE": "Conf", "EDITION": "2027", "ORGANIZER": "", "CITY": "Marina Bay Sands",
            "LOCATION": "Marina Bay Sands, Singapore", "OVERVIEW": "input text", "STATUS": "Open",
            "SUBMISSION DEADLINE": "2026-11-01", "DEADLINE_QUOTE": "fresh quote", "SPONSOR_REQUIRED": "No"}
    base.update(kw)
    return base


def _prior(**kw):
    base = {"EVENT_ID": "e1", "EDITION": "2027", "ORGANIZER": "Informa", "CITY": "Singapore", "LOCATION": "Singapore",
            "OVERVIEW": "model text", "STATUS": "Upcoming", "SUBMISSION DEADLINE": "2026-09-01"}
    base.update(kw)
    return base


def test_carries_unasked_fields_and_keeps_fresh_ones():
    rows = [_row()]
    out, rep = overlay_narrow(rows, ["new"], {"e1": _prior()}, {}, CANON)
    r = out[0]
    assert (r["CITY"], r["LOCATION"], r["ORGANIZER"], r["OVERVIEW"]) == ("Singapore", "Singapore", "Informa", "model text")
    assert (r["STATUS"], r["SUBMISSION DEADLINE"], r["DEADLINE_QUOTE"], r["SPONSOR_REQUIRED"]) == ("Open", "2026-11-01", "fresh quote", "No")
    assert rep["overlaid"][0]["canonical"] == "e1" and rep["fields"]["CITY"] == 1


def test_blank_prior_value_never_blanks_this_weeks():
    out, _ = overlay_narrow([_row()], ["new"], {"e1": _prior(OVERVIEW="")}, {}, CANON)
    assert out[0]["OVERVIEW"] == "input text"


def test_new_edition_is_left_as_researched():
    out, rep = overlay_narrow([_row(EDITION="2028")], ["new"], {"e1": _prior()}, {}, CANON)
    assert out[0]["CITY"] == "Marina Bay Sands" and rep["skipped_new_edition"] == 1


def test_full_prompt_row_is_skipped():
    out, rep = overlay_narrow([_row(ORGANIZER="Full answer org")], ["new"], {"e1": _prior()}, {}, CANON)
    assert out[0]["ORGANIZER"] == "Full answer org" and out[0]["CITY"] == "Marina Bay Sands" and rep["skipped_full_prompt"] == 1


def test_no_prior_and_carried_rows_untouched():
    rows = [_row(), _row(EVENT_ID="e2")]
    out, rep = overlay_narrow(rows, ["prior", "new"], {"e1": _prior()}, {}, CANON)
    assert out[0]["CITY"] == "Marina Bay Sands" and out[1]["CITY"] == "Marina Bay Sands" and rep["skipped_no_prior"] == 1


def test_identity_and_customer_columns_never_carried():
    for banned in ("EVENT_ID", "CONFERENCE", "EDITION", "STATUS", "SUBMISSION DEADLINE", "NOTES", "PRIORITY", "SPONSOR_REQUIRED",
                   "DEADLINE_EVIDENCE_URL", "DEADLINE_QUOTE", "IS_PROJECTED", "START DATE", "FORMAT", "CONFERENCE DATES"):
        assert banned not in CARRY_FIELDS


def test_conference_dates_restored_only_when_prior_agrees_with_start_date_year_included():
    r = _row(**{"START DATE": "2026-02-11", "CONFERENCE DATES": "October 21 - October 23, 2026"})
    p = _prior(**{"CONFERENCE DATES": "February 11 - February 13, 2026"})
    out, rep = overlay_narrow([r], ["new"], {"e1": p}, {}, CANON)
    assert out[0]["CONFERENCE DATES"] == "February 11 - February 13, 2026" and rep["fields"]["CONFERENCE DATES"] == 1
    # same month and day but a DIFFERENT YEAR in the prior: never restored (no mixing of editions)
    r2 = _row(**{"START DATE": "2027-02-11", "CONFERENCE DATES": "October 21 - October 23, 2027"})
    out2, _ = overlay_narrow([r2], ["new"], {"e1": _prior(**{"CONFERENCE DATES": "February 11 - February 13, 2026"})}, {}, CANON)
    assert out2[0]["CONFERENCE DATES"] == "October 21 - October 23, 2027"
    # this week's text already agrees: untouched
    r3 = _row(**{"START DATE": "2026-02-11", "CONFERENCE DATES": "February 11 - February 12, 2026"})
    out3, _ = overlay_narrow([r3], ["new"], {"e1": p}, {}, CANON)
    assert out3[0]["CONFERENCE DATES"] == "February 11 - February 12, 2026"


from datetime import date as _date

_T = _date(2026, 10, 3)


def _ev_prior(**kw):
    return _prior(**{"SUBMISSION DEADLINE": "2026-10-09", "DEADLINE_EVIDENCE_URL": "https://x/cfp", "DEADLINE_QUOTE": "closes 9 October 2026",
                     "IS_PROJECTED": "false", "GROUNDING_CONFIDENCE": "Verified (2027)", **kw})


def _ev_row(**kw):
    return _row(**{"SUBMISSION DEADLINE": "2026-10-09", "DEADLINE_EVIDENCE_URL": "", "DEADLINE_QUOTE": "", "IS_PROJECTED": "true",
                   "GROUNDING_CONFIDENCE": "Projected (2027)", **kw})


def test_evidence_kept_as_a_unit_when_same_deadline_and_no_quote_this_week():
    out, rep = overlay_narrow([_ev_row()], ["new"], {"e1": _ev_prior()}, {}, CANON, today=_T)
    r = out[0]
    assert (r["DEADLINE_EVIDENCE_URL"], r["DEADLINE_QUOTE"], r["IS_PROJECTED"], r["GROUNDING_CONFIDENCE"]) == \
        ("https://x/cfp", "closes 9 October 2026", "false", "Verified (2027)")
    assert rep["evidence_carried"] and r["SUBMISSION DEADLINE"] == "2026-10-09"


def test_blank_deadline_recovers_a_future_verified_one_but_not_a_passed_one():
    out, _ = overlay_narrow([_ev_row(**{"SUBMISSION DEADLINE": ""})], ["new"], {"e1": _ev_prior()}, {}, CANON, today=_T)
    assert out[0]["SUBMISSION DEADLINE"] == "2026-10-09" and out[0]["IS_PROJECTED"] == "false"
    out2, rep2 = overlay_narrow([_ev_row(**{"SUBMISSION DEADLINE": ""})], ["new"], {"e1": _ev_prior(**{"SUBMISSION DEADLINE": "2026-07-01"})}, {}, CANON, today=_T)
    assert out2[0]["SUBMISSION DEADLINE"] == "" and not rep2["evidence_carried"]


def test_fresh_answers_are_never_overridden():
    # a different deadline this week: fresh, not carried
    out, rep = overlay_narrow([_ev_row(**{"SUBMISSION DEADLINE": "2026-11-23"})], ["new"], {"e1": _ev_prior()}, {}, CANON, today=_T)
    assert out[0]["SUBMISSION DEADLINE"] == "2026-11-23" and out[0]["DEADLINE_QUOTE"] == "" and not rep["evidence_carried"]
    # this week returned its own quote: untouched
    out2, _ = overlay_narrow([_ev_row(**{"DEADLINE_QUOTE": "new quote", "DEADLINE_EVIDENCE_URL": "https://y"})], ["new"], {"e1": _ev_prior()}, {}, CANON, today=_T)
    assert out2[0]["DEADLINE_QUOTE"] == "new quote" and out2[0]["DEADLINE_EVIDENCE_URL"] == "https://y"


def test_projected_or_incomplete_prior_is_never_carried():
    for bad in ({"IS_PROJECTED": "true"}, {"DEADLINE_QUOTE": ""}, {"DEADLINE_EVIDENCE_URL": ""}):
        out, rep = overlay_narrow([_ev_row()], ["new"], {"e1": _ev_prior(**bad)}, {}, CANON, today=_T)
        assert out[0]["DEADLINE_QUOTE"] == "" and not rep["evidence_carried"]
