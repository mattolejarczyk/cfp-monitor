"""The business rules we keep re-deriving, in one place, as pure functions.

WHY THIS EXISTS
On 2026-08-29 the same three defects were introduced a second and third time in scripts written
hours apart, because each rule lived in one script's head rather than anywhere shared:

  * A withdrawal set IS_PROJECTED=true without downgrading GROUNDING_CONFIDENCE. Fixed in
    apply_phase1_mechanical.py in the morning (R11 went 8 -> 52), reintroduced in
    auto_trace_r3b_high.py in the afternoon (R11 went 0 -> 19).
  * A decision was applied to one customer-facing URL field while the review page renders four.
    Found on 2026-08-12, found again on 2026-08-28.
  * "We could not find it" was written into the data as "it is not there" - as the dead-site
    label, as link_checks with no history, as "no live page found" counting pages nobody
    searched, and finally as 14 citations withdrawn because their CFP page came down after the
    deadline passed, which is exactly what CFP pages do.

Every function here is pure and returns a REASON alongside its answer, so a caller cannot apply
a rule without being able to say why. Nothing in this module fetches, writes, or guesses.
"""
from __future__ import annotations

import re
from datetime import date

# Every URL a customer can click. The review page renders ALL of these, so a decision about a
# row must reach all of them - clearing one and leaving another is how a dead link reaches a
# client on a row we already decided about (2026-08-12, repeated 2026-08-28).
CUSTOMER_FACING_URLS = ("SUBMISSION URL", "CFP_SUBMISSION_URL", "MAIN_INFO_URL",
                        "CONFERENCE URL")

# Only these disprove a link. 403, 500, timeouts and empty bodies mean blocked-or-broken.
DISPROVING_STATUS = (404, 410)


def parse_date(s) -> date | None:
    try:
        return date.fromisoformat(str(s or "").strip()[:10])
    except Exception:                                                 # noqa: BLE001
        return None


def deadline_has_passed(row, today: date) -> bool:
    d = parse_date(row.get("SUBMISSION DEADLINE"))
    return bool(d and d < today)


def may_withdraw_citation(row, *, quote_found: bool, pages_read: int,
                          today: date) -> tuple[bool, str]:
    """May we clear this row's citation because we could not find its quote?

    THREE WAYS THE ANSWER IS NO, and each cost us something:

    1. We could not read any page. Absence of evidence is not evidence of absence (2.1). This
       is the failure that produced the "dead site" label, wrong for 4 of the 5 rows it fired on.
    2. The quote WAS found. Nothing to withdraw.
    3. THE DEADLINE HAS ALREADY PASSED. A call-for-papers page is routinely taken down once its
       deadline passes and the site rolls to the next edition, so the sentence being gone is
       expected and says nothing about whether the citation was sound when it was made. On
       2026-08-29 this described 14 of 18 proposed withdrawals - one deadline 317 days old.
       Withdrawing those picks the harsher reading with no evidence for it.
    """
    if quote_found:
        return False, "the quote was found - nothing to withdraw"
    if pages_read == 0:
        return False, ("no page could be read, so this says nothing about the citation (2.1) - "
                       "a fetch failure is not a finding")
    if deadline_has_passed(row, today):
        d = parse_date(row.get("SUBMISSION DEADLINE"))
        age = (today - d).days if d else 0
        return False, (f"deadline passed {age} day(s) ago - a CFP page coming down after its "
                       f"deadline is expected, and does not show the citation was ever wrong")
    return True, (f"the call is still open and the quote is not on the cited page after reading "
                  f"{pages_read} page(s)")


def bound_confidence(current: str, is_projected: bool) -> str:
    """R11: GROUNDING_CONFIDENCE and IS_PROJECTED must agree.

    A projection cannot be verified, and a verified claim is not a projection. The vocabulary
    already carries both forms for each year, so this is a rename, never a judgement.

    Call this WHENEVER IS_PROJECTED changes. Not calling it is the single most repeated defect
    in this codebase.
    """
    cur = (current or "").strip()
    if not cur:
        return cur
    if is_projected:
        return re.sub(r"^\s*Verified\b", "Projected", cur)
    return re.sub(r"^\s*Projected\b", "Verified", cur)


def withdrawal_changes(row, *, fetched: bool, today: date) -> dict:
    """Every field an R1 withdrawal touches - as one dict, so no caller can do half of it.

    R1: clear the citation URL and the quote, set IS_PROJECTED true, and LEAVE THE SUBMISSION
    DEADLINE ALONE. The confidence label travels with IS_PROJECTED (R11), which is the part
    that kept getting forgotten until it was folded in here.

    `fetched` IS REQUIRED, WITH NO DEFAULT, ON PURPOSE. On 2026-08-29 four rows were withdrawn
    after rendering 11 to 14 pages of each site, and their SOURCE_AS_OF was left at 2026-08-06 -
    asserting they had not been looked at in three weeks. `may_advance_source_as_of` already
    existed and returned the right answer; the caller simply never asked it. Upstream's own rule
    was correct and ours was not.

    Making the parameter mandatory means a withdrawal cannot be written without deciding whether
    a page was actually read - the same trick that fixed the confidence binding. The three-way
    rule both sides agreed:

        fetched, quote found      -> advance the stamp
        fetched, quote absent     -> ADVANCE - the site was inspected
        could not read any page   -> do not advance, nothing was inspected
    """
    out = {
        "DEADLINE_EVIDENCE_URL": "",
        "DEADLINE_QUOTE": "",
        "IS_PROJECTED": "true",
        "GROUNDING_CONFIDENCE": bound_confidence(row.get("GROUNDING_CONFIDENCE", ""), True),
    }
    advance, _why = may_advance_source_as_of(fetch_succeeded=fetched)
    if advance:
        out["SOURCE_AS_OF"] = today.isoformat()
    return out


def may_advance_source_as_of(*, fetch_succeeded: bool) -> tuple[bool, str]:
    """SOURCE_AS_OF advances only on a row we actually fetched and inspected.

    With SPONSOR_REQUIRED defaulting to Unknown, this stamp is the ONLY thing separating
    "inspected, nothing found" from "never looked at". Stamping a failed fetch destroys the
    distinction silently and cannot be recovered afterwards.
    """
    if fetch_succeeded:
        return True, "row was fetched and inspected"
    return False, "fetch did not succeed - stamping it would record a non-inspection"


def link_is_dead(status: int | None) -> tuple[bool, str]:
    """Only 404/410 disprove a link (contract 5.2)."""
    if status in DISPROVING_STATUS:
        return True, f"HTTP {status} - the page is gone"
    if status in (401, 403, 429):
        return False, f"HTTP {status} - the site is up and declining to talk to us"
    if not status:
        return False, "no status - we could not reach it, which is not the same as it being dead"
    return False, f"HTTP {status} - resolves"


def r8c_key(row) -> tuple:
    """EVENT_ID is unique per (event, MARKET), never globally.

    Section 10 excludes market from the key so one event stays ONE record across markets, which
    means a combined all-markets file repeats an ID once per market by design. Checking globally
    flagged 12 rows of correct data and produced advice to merge them, which would have deleted
    real market memberships.
    """
    return (row.get("EVENT_ID", ""), row.get("Market", ""))


def urls_to_update(row, old_url: str) -> list[str]:
    """Which customer-facing fields carry this URL, so a fix reaches all of them."""
    old = (old_url or "").strip()
    return [f for f in CUSTOMER_FACING_URLS if (row.get(f) or "").strip() == old]
