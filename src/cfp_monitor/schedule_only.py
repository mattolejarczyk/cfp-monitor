"""A status whose only support is the TYPICAL SCHEDULE is Needs Verification (ACT-54, fix e; failure point: no page, no status).

Hack In The Box: the customer page showed 'Closed - typically runs in late August' for a Phuket row nobody had seen a page for. Upstream guessed the edition from
what the event usually does, and the guess shipped as a fact. A status that asserts something about THIS edition (Open, Closed, Upcoming) needs a page behind it; the
typical schedule is a reason to go and look, never an answer.

THE RULE (pure functions, no I/O). A delivery row is SCHEDULE-ONLY when ALL hold:
  1. STATUS asserts something: Open, Closed or Upcoming (Needs Verification is the honest label and is never flagged);
  2. its prose (STATUS DETAILS plus NOTES) reasons from the usual calendar ('typically', 'usually', 'normally', 'historically', 'in past/previous years', 'based on past',
     'expected to', 'likely to' ...) or from silence ('the absence of active listings');
  3. it reports nothing a page SAYS about this edition (no 'confirms', 'announced', 'took place', 'scheduled to take place' ...): silence is not a page;
  4. it carries NO citation pair: neither DEADLINE_EVIDENCE_URL with DEADLINE_QUOTE nor LIFECYCLE_EVIDENCE_URL with LIFECYCLE_QUOTE (a quoted page is the evidence).
A flagged row should read Needs Verification; `proposed_status` says so and `phrase` names what was found. Nothing here rewrites a file: the gate reports it
(scripts/accept_delivery.py, advisory R16c) and scripts/check_schedule_status.py lists it for the recap.

Measured read-only on the published files 2026-10-08 (Markets/*_audited.final.csv): the rule flags Hack In The Box (Closed, 'typically runs in late August ... absence of
active 2026 listings') and does NOT flag Billington ('took place ... typically handled via direct contact') or ODSC East 2027 ('scheduled to take place ... Based on previous
cycles, the CFP is expected to open'), the two rows a bare phrase search wrongly caught."""
from __future__ import annotations

import re

ASSERTING = {"open", "closed", "upcoming"}
SCHEDULE_PHRASES = re.compile(
    r"\b(?:typically|usually|normally|historically|traditionally|generally runs|tends to (?:run|be held|take place)|"
    r"in (?:past|previous|prior|earlier) (?:years|editions)|based on (?:past|previous|prior|last year'?s?)|"
    r"(?:past|previous|prior) editions? (?:were|was|ran|took place)|"
    r"(?:is|are) expected to|expected (?:to|in)|likely (?:to|in)|annual(?:ly)? (?:event )?(?:held|runs?|takes? place) (?:in|every))\b", re.I)
ABSENCE = re.compile(r"\b(?:absence of|no active [a-z0-9 ]*listings?|not (?:currently )?listed|no (?:mention|listing|sign) of)\b", re.I)
POSITIVE = re.compile(r"\b(?:confirm[a-z]*|announc[a-z]*|states?|stated|took place|taking place|scheduled (?:for|to take place|to be held)|has (?:concluded|ended)|thank you|"
                      r"official (?:site|website|page) (?:lists|says|shows|messaging))\b", re.I)


def _g(row: dict, col: str) -> str:
    return (row.get(col) or "").strip()


def schedule_only(row: dict) -> tuple[bool, str]:
    """(flagged, the schedule phrase found or '')."""
    if _g(row, "STATUS").lower() not in ASSERTING:
        return False, ""
    prose = f'{_g(row, "STATUS DETAILS")} {_g(row, "NOTES")}'
    m = SCHEDULE_PHRASES.search(prose) or ABSENCE.search(prose)
    if not m or POSITIVE.search(prose):
        return False, ""
    cited = (_g(row, "DEADLINE_EVIDENCE_URL") and _g(row, "DEADLINE_QUOTE")) or (_g(row, "LIFECYCLE_EVIDENCE_URL") and _g(row, "LIFECYCLE_QUOTE"))
    return (False, "") if cited else (True, m.group(0))


def find_schedule_only(rows: list[dict]) -> list[dict]:
    """The flagged rows, each {name, event_id, status, proposed_status, phrase, detail}."""
    out = []
    for r in rows:
        bad, phrase = schedule_only(r)
        if bad:
            out.append({"name": _g(r, "CONFERENCE"), "event_id": _g(r, "EVENT_ID") or _g(r, "EVENT_ID_CANON"), "status": _g(r, "STATUS"), "proposed_status": "Needs Verification",
                        "phrase": phrase, "detail": _g(r, "STATUS DETAILS")[:160]})
    return out
