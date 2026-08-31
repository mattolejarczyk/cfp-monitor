"""The decision tree: where a conference sits in its life, and what follows from that.

THE PROBLEM THIS SOLVES
We hold three facts about time - when the EVENT is, when the CALL closes, and whether a later
edition exists - and until now each was read separately by whoever needed it. Edition state was
derived correctly but only inside the page builder, so the gate and the weekly job could not see
it. `STATUS` was STORED, so it went stale: on 2026-08-31 the gate failed on two rows reading
`STATUS=Open` whose deadlines had passed within 48 hours. Neither needed research. They needed
deriving.

Judgement rule 5 already said it - "a stored judgement goes stale; derive it instead" - and
judgement rule 1 already said what follows from a past event: "the row is 'watch for the next
edition', not 'find the deadline'." This module makes both executable rather than remembered.

THE ONE PRINCIPLE
Every output here is DERIVED at read time from facts we hold, and none of it is written back.
Deriving costs nothing and cannot go stale. Storing it means a row is only as fresh as the last
time somebody ran something.

WHAT IT DECIDES, AND FOR WHOM
    edition_state   which instalment of the series this is        (R13)
    call_state      whether a person can still submit             (derived, was stored)
    urgency         how loudly the customer page should say so
    action          what WE do next, and what it costs

The last is the point the others build to: a conference that ran last week needs almost nothing
from the customer for months, because the next one is a year out - but it needs a specific,
cheap thing from us, which is to watch for the successor rather than to keep hunting a call that
no longer exists.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

# Prose that says a series has ENDED. A lifecycle claim is the most consequential finding in the
# pipeline (R16), which is why it must be quoted, never inferred.
DEFUNCT = re.compile(
    r"discontinued|no longer (?:being )?(?:held|running)|has been cancell?ed|"
    r"final (?:edition|year)|last (?:edition|year) of", re.I)
# A rotating event is not a dead one. EMO Hannover 2027 says "will not be held in Hannover...
# the EMO cycle dictates" - the series is alive, it has moved venue.
ROTATION = re.compile(r"cycle dictates|rotat|alternat|moves to|held instead in", re.I)

URGENT_DAYS = 7
SOON_DAYS = 30
# Below this a passed event is still recent enough that the successor is unlikely to be
# announced. Chasing it weekly wastes requests; 9% of the delivery sits in this state.
SUCCESSOR_QUIET_DAYS = 60


@dataclass(frozen=True)
class Assessment:
    edition_state: str          # Active | Watching | Archived | Discontinued
    call_state: str             # Open | Closing | Closed | Not announced | Not applicable
    urgency: str                # closing this week | closing this month | open | none
    action: str                 # what WE do next
    cost: str                   # free | quota | human
    why: str                    # the reason, in words, always

    @property
    def customer_status(self) -> str:
        """What the customer's STATUS column would say if derived from dates alone."""
        if self.edition_state == "Discontinued":
            return "Closed"
        if self.edition_state in ("Watching", "Archived"):
            return "Upcoming"
        return {"Open": "Open", "Closing": "Open", "Closed": "Closed",
                "Not announced": "Upcoming", "Not applicable": "Upcoming"}[self.call_state]

    def overrides(self, stored: str) -> tuple[bool, str]:
        """Should the derived status REPLACE what the file already says?

        Deriving beats storing only where the derivation is better informed. It is not
        automatically better, and assuming otherwise nearly shipped a 126-row change on
        2026-08-31 of which most were not corrections at all.

        DERIVATION WINS when a date proves the stored value wrong. Dates are unambiguous and
        the file is frozen: a deadline that has passed, or an event that has already run,
        settles it.

        DERIVATION LOSES when it is reasoning from ABSENCE. A blank deadline does not mean the
        call has not opened - it equally means the call is shut and there is no date to record.
        Twenty-six rows read `STATUS=Closed` with no deadline: somebody established that, and
        overwriting it with "Upcoming" would replace a finding with an inference. Contract 2.1
        cuts both ways.

        DERIVATION ALSO LOSES when both answers are true and it is only a question of framing.
        For an edition that has already run, "Closed" (the call is shut) and "Upcoming" (we are
        watching for the next one) are both correct; that is a presentation choice for the
        customer page, not a data correction.
        """
        stored = (stored or "").strip()
        derived = self.customer_status
        if not stored:
            return True, "the file says nothing, so the derived value is all we have"
        if derived == stored:
            return False, "they agree"

        if self.call_state in ("Closed", "Open", "Closing"):
            return True, (f"a dated deadline settles it - {self.why[:96]}")
        if self.edition_state == "Watching" and stored == "Open":
            return True, ("this row's own START DATE is in the past, so the call cannot be "
                          "open whatever the file says")
        # ARCHIVED IS DELIBERATELY NOT AN OVERRIDE, though it is tempting. "Archived" is not a
        # fact about this row - it is inferred from a SIBLING row existing with a later year in
        # its EVENT_ID. On 2026-08-31 that inference was wrong: Decarb Connect North America
        # 2027 appears twice with the same name, track, opportunity and START DATE of
        # 2027-02-09, keyed `2026-...` and `2027-...`. One prefix is simply wrong, and the
        # mis-keyed row was being read as a superseded edition of a conference that has not
        # happened yet. Judgement rule 14: a key is a name, not a fact.
        #
        # Only a DATE ON THIS ROW justifies overwriting what the file says.
        if self.call_state == "Not announced":
            return False, (f"no deadline is recorded, so this is an inference from absence. "
                           f"The file's {stored!r} may be a finding somebody established - "
                           f"2.1 cuts both ways")
        return False, (f"{stored!r} and {derived!r} are both true; which to show is a "
                       f"presentation choice, not a correction")


def _iso(v) -> date | None:
    s = str(v or "").strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def edition_states(rows, today: date | str) -> dict[str, str]:
    """R13 - which instalment of its series each EVENT_ID is. Derived, never stored.

    Group by EVENT_ID FIRST: rows sharing one EVENT_ID are ONE edition in several markets, not
    several editions. Getting that backwards produced advice to merge 12 rows of correct data.

    Moved here from build_review_page.py on 2026-08-31 unchanged. It was correct, but living
    inside the page builder meant the gate and the weekly job could not ask the question.
    """
    t = today if isinstance(today, str) else today.isoformat()
    editions = defaultdict(list)
    for r in rows:
        editions[(r.get("EVENT_ID") or "").strip()].append(r)
    series = defaultdict(set)
    for eid in editions:
        p = eid.split("-", 1)
        series[p[1] if len(p) == 2 and re.fullmatch(r"(19|20)\d{2}", p[0]) else eid].add(eid)

    state = {}
    for _, eids in series.items():
        latest = max(eids, key=lambda e: e.split("-", 1)[0]
                     if re.fullmatch(r"(19|20)\d{2}", e.split("-", 1)[0]) else "0")
        for eid in eids:
            rs = editions[eid]
            blob = " ".join(f"{r.get('STATUS DETAILS','')} {r.get('NOTES','')}" for r in rs)
            defunct = bool(DEFUNCT.search(blob)) and not ROTATION.search(blob)
            start = (rs[0].get("START DATE") or "").strip()
            ran = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", start)) and start < t
            state[eid] = ("Archived" if eid != latest else
                          "Discontinued" if defunct else
                          "Watching" if ran else "Active")
    return state


def assess(row, edition_state: str, today: date) -> Assessment:
    """The decision tree, in the order the cheapest disqualifier comes first (judgement rule 8).

    Read top to bottom; the first branch that matches decides.

        1  Discontinued  the series has ended, quoted    -> nothing, ever. Do not research it.
        2  Archived      a later edition exists          -> nothing. The successor carries it.
        3  Watching      the event has run               -> watch for the successor, NOT the call
        4  Active + no deadline                          -> find the call (this is discovery)
        5  Active + deadline passed                      -> the call closed; watch for the next
        6  Active + deadline near                        -> the customer must act
        7  Active + deadline ahead                       -> verify it still says what we hold
    """
    start = _iso(row.get("START DATE"))
    deadline = _iso(row.get("SUBMISSION DEADLINE"))
    raw_deadline = str(row.get("SUBMISSION DEADLINE") or "").strip()

    if edition_state == "Discontinued":
        return Assessment(
            edition_state, "Not applicable", "none",
            "nothing - do not spend a request on it", "free",
            "the series has ended and the claim is quoted (R16); researching it again would "
            "cost quota to re-learn something we already proved")

    if edition_state == "Archived":
        return Assessment(
            edition_state, "Not applicable", "none",
            "nothing - the successor edition carries the work", "free",
            "a later edition of this series exists, so this row is history and every question "
            "about the call belongs to the newer row")

    if edition_state == "Watching":
        days_since = (today - start).days if start else None
        if days_since is not None and days_since < SUCCESSOR_QUIET_DAYS:
            return Assessment(
                edition_state, "Not applicable", "none",
                "watch only - do not hunt the successor yet", "free",
                f"the event ran {days_since} day(s) ago and the next one is most of a year "
                f"out; organisers rarely announce that soon, so checking weekly spends "
                f"requests to be told nothing. Judgement rule 1: a past event has no call "
                f"to find")
        return Assessment(
            edition_state, "Not applicable", "none",
            "look for the successor edition (R14), not for this one's call", "quota",
            "the event has run and enough time has passed that a successor may be announced; "
            "R15 duplicate-checks anything found before it can be added")

    # ---- Active: this edition has not yet happened -------------------------------------
    if not raw_deadline:
        return Assessment(
            edition_state, "Not announced", "open",
            "find the call - this is DISCOVERY, not verification", "quota",
            "the event is ahead of us and no deadline is recorded. Verification cannot help: "
            "there is no claim to check. Only research finds a date that was never captured")

    if deadline is None:
        return Assessment(
            edition_state, "Not announced", "open",
            "read the deadline field by hand - it is prose, not a date", "human",
            f"the deadline field holds {raw_deadline[:48]!r}, which is not a date. It may be a "
            f"tiered set of rounds (R23) or a sponsorship note; a number invented from prose "
            f"is worse than no number")

    days = (deadline - today).days
    if days < 0:
        return Assessment(
            edition_state, "Closed", "none",
            "watch for the next round or the next edition", "free",
            f"the call closed {-days} day(s) ago. The customer cannot act, so this must not "
            f"show as Open - that is the staleness the gate caught on 2026-08-31. If the "
            f"conference runs tiered rounds, R23 should be showing the NEXT round instead")
    if days <= URGENT_DAYS:
        return Assessment(
            edition_state, "Closing", "closing this week",
            "surface it at the top of the customer page", "free",
            f"the call closes in {days} day(s). This is the only state where OUR delay costs "
            f"the customer a submission, so it outranks everything else on the page")
    if days <= SOON_DAYS:
        return Assessment(
            edition_state, "Closing", "closing this month",
            "surface it, and re-verify the date before relying on it", "free",
            f"the call closes in {days} day(s) - near enough to act on, far enough that a "
            f"moved deadline still matters")
    return Assessment(
        edition_state, "Open", "open",
        "re-verify weekly against the cited page", "free",
        f"the call closes in {days} day(s). Nothing is urgent, but a deadline that moves or a "
        f"link that dies is caught by the free weekly sweep")


def assess_all(rows, today: date) -> dict[str, Assessment]:
    """Assess every row, keyed by EVENT_ID. One call, so edition state is computed once."""
    states = edition_states(rows, today)
    out = {}
    for r in rows:
        eid = (r.get("EVENT_ID") or "").strip()
        out[eid] = assess(r, states.get(eid, "Active"), today)
    return out
