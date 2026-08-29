"""The canary set: one record per way this pipeline has actually gone wrong.

Every canary is a REAL incident, dated, with the outcome that was correct. Any change to
crawling, gating or delivery logic runs against these before it runs against 406 rows.

The point is not coverage for its own sake. Each of these was found the expensive way - in a
document that had left the building, in advice that would have deleted data, or in a delivery
that was accepted on a check that never ran. A canary is cheaper than the second occurrence,
and several of these ARE second occurrences.
"""
from datetime import date

TODAY = date(2026, 8, 29)


def _row(**kw):
    base = {"EVENT_ID": "2027-x-city-speaking", "CONFERENCE": "X", "Market": "Utility",
            "SUBMISSION DEADLINE": "", "DEADLINE_EVIDENCE_URL": "", "DEADLINE_QUOTE": "",
            "MAIN_INFO_URL": "", "CONFERENCE URL": "", "SUBMISSION URL": "",
            "CFP_SUBMISSION_URL": "", "IS_PROJECTED": "true", "GROUNDING_CONFIDENCE": "",
            "SOURCE_AS_OF": "2026-08-06", "STATUS": "Open", "CFP MODEL TYPE": "Fixed Deadline"}
    base.update(kw)
    return base


CANARIES = [
    {
        "name": "passed-deadline citation must NOT be withdrawn",
        "incident": "2026-08-29. 14 of 18 proposed withdrawals had deadlines already passed, "
                    "one by 317 days. A CFP page comes down after its deadline; that is not "
                    "evidence the citation was ever wrong.",
        "row": _row(CONFERENCE="MRS Fall Meeting 2026",
                    **{"SUBMISSION DEADLINE": "2026-06-17",
                       "DEADLINE_EVIDENCE_URL": "https://www.mrs.org/meetings-events/",
                       "DEADLINE_QUOTE": "Abstract deadline June 17, 2026",
                       "GROUNDING_CONFIDENCE": "Verified (2026)"}),
        "quote_found": False, "pages_read": 50,
        "expect_withdraw": False,
    },
    {
        "name": "live call with a missing quote MAY be withdrawn",
        "incident": "2026-08-29. 4 of 18 had future deadlines - the call should still be live, "
                    "so a missing sentence is a real citation failure.",
        "row": _row(CONFERENCE="SEMICON China 2027",
                    **{"SUBMISSION DEADLINE": "2026-09-30",
                       "DEADLINE_EVIDENCE_URL": "https://www.semiconchina.org/",
                       "DEADLINE_QUOTE": "Abstract Submissions Deadline: September 30, 2026",
                       "GROUNDING_CONFIDENCE": "Verified (2027)"}),
        "quote_found": False, "pages_read": 12,
        "expect_withdraw": True,
    },
    {
        "name": "unreadable site must NOT be withdrawn",
        "incident": "2026-08-27. The 'dead site' label was wrong for 4 of the 5 rows it fired "
                    "on - two were 403s, two answered a plain request while our ladder came "
                    "back empty. A fetch failure is not a finding.",
        "row": _row(CONFERENCE="PDA Annual Meeting 2027",
                    **{"SUBMISSION DEADLINE": "2026-08-31",
                       "DEADLINE_EVIDENCE_URL": "https://www.pda.org/pda-week",
                       "DEADLINE_QUOTE": "Call for Abstracts Now Open - Submit by 31 August 2026",
                       "GROUNDING_CONFIDENCE": "Verified (2027)"}),
        "quote_found": False, "pages_read": 0,
        "expect_withdraw": False,
    },
    {
        "name": "withdrawal must downgrade the confidence label",
        "incident": "Twice on 2026-08-29. Morning: R11 went 8 -> 52. Afternoon, in a different "
                    "script: R11 went 0 -> 19. Same defect, hours apart.",
        "row": _row(**{"GROUNDING_CONFIDENCE": "Verified (2027)"}),
        "expect_confidence_after_withdrawal": "Projected (2027)",
    },
    {
        "name": "withdrawal must NOT touch the submission deadline",
        "incident": "R1 is a citation-only edit. The deadline is what the customer acts on.",
        "row": _row(**{"SUBMISSION DEADLINE": "2027-02-12",
                       "GROUNDING_CONFIDENCE": "Verified (2027)"}),
        "expect_deadline_untouched": True,
    },
    {
        "name": "SOURCE_AS_OF must not advance on a failed fetch",
        "incident": "2026-08-29. Upstream's draft stamped every attempted row, including the "
                    "NOT-FOUND branch. That stamp is the only thing separating 'inspected, "
                    "nothing found' from 'never looked at'.",
        "fetch_succeeded": False,
        "expect_may_advance": False,
    },
    {
        "name": "403 is not a dead link",
        "incident": "Contract 5.2, and 2026-08-27 where two live sites were reported dead.",
        "status": 403, "expect_dead": False,
    },
    {
        "name": "404 is a dead link",
        "incident": "Contract 5.2. 404 and 410 are the ONLY statuses that disprove a link - "
                    "the counterpart to the 403 canary above, so the rule cannot be loosened "
                    "into never calling anything dead.",
        "status": 404, "expect_dead": True,
    },
    {
        "name": "one event in several markets is not a duplicate",
        "incident": "2026-08-27. R8c compared EVENT_ID globally, flagged 12 rows of correct "
                    "data, and we advised upstream to MERGE them - which would have deleted "
                    "real market memberships. They had it queued before the retraction.",
        "rows": [_row(EVENT_ID="2027-ces-2027-las-vegas-speaking", Market="ConsumerElectronics"),
                 _row(EVENT_ID="2027-ces-2027-las-vegas-speaking", Market="Robotics"),
                 _row(EVENT_ID="2027-ces-2027-las-vegas-speaking", Market="Semiconductor")],
        "expect_duplicate": False,
    },
    {
        "name": "a real duplicate inside one market IS a duplicate",
        "incident": "2026-08-29, the other half of the R8c fix. Section 10 makes the key "
                    "per-market, but the check must still catch a genuine duplicate - a fix "
                    "that only loosens a rule has removed it.",
        "rows": [_row(EVENT_ID="2027-dupe-city-speaking", Market="Utility"),
                 _row(EVENT_ID="2027-dupe-city-speaking", Market="Utility")],
        "expect_duplicate": True,
    },
    {
        "name": "check 3 must not fire on a row with no deadline claimed",
        "incident": "Amendment v1.4, measured 2026-08-29. 108 of 186 check-3 failures (58%) "
                    "were rows carrying a DEADLINE_QUOTE and evidence URL while SUBMISSION "
                    "DEADLINE was blank - a citation for a claim the row never makes. The "
                    "quotes were event dates, calendar strips and site disclaimers.",
        "row": _row(**{"SUBMISSION DEADLINE": "",
                       "DEADLINE_EVIDENCE_URL": "https://example.org/",
                       "DEADLINE_QUOTE": "June 2-3, 2027 - Boston, MA."}),
        "expect_check3_applies": False,
    },
    {
        "name": "check 3 must not fire on a passed deadline",
        "incident": "Amendment v1.4, measured 2026-08-29. 50 of 186 (26%). A CFP page comes "
                    "down once its deadline passes; one of these had passed 317 days earlier.",
        "row": _row(**{"SUBMISSION DEADLINE": "2026-06-17",
                       "DEADLINE_EVIDENCE_URL": "https://example.org/cfp",
                       "DEADLINE_QUOTE": "Abstract deadline June 17, 2026"}),
        "expect_check3_applies": False,
    },
    {
        "name": "check 3 MUST still fire on a live call with a missing quote",
        "incident": "2026-08-29. The 28 live calls that remained after both v1.4 exemptions - "
                    "15% of 186. An exemption that also excuses the case the criterion exists "
                    "for has removed the criterion rather than scoped it.",
        "row": _row(**{"SUBMISSION DEADLINE": "2026-09-30",
                       "DEADLINE_EVIDENCE_URL": "https://example.org/cfp",
                       "DEADLINE_QUOTE": "Abstract Submissions Deadline: September 30, 2026"}),
        "expect_check3_applies": True,
    },
    {
        "name": "a fix must reach every field carrying the URL",
        "incident": "2026-08-12 and again 2026-08-28. Five rows had SUBMISSION URL cleared "
                    "while CFP_SUBMISSION_URL kept the dead address. The review page renders "
                    "four URL fields; clearing one puts the dead link in front of a client on "
                    "a row we already decided about.",
        "row": _row(**{"SUBMISSION URL": "https://gone.example.com/cfp",
                       "CFP_SUBMISSION_URL": "https://gone.example.com/cfp",
                       "MAIN_INFO_URL": "https://fine.example.com/"}),
        "old_url": "https://gone.example.com/cfp",
        "expect_fields": ["SUBMISSION URL", "CFP_SUBMISSION_URL"],
    },
]
