"""Two gate checks that misfired on the first awards delivery, 2026-09-06.

Neither was an awards bug in the data. One was a regex with a single negation guard; the
other was a conference assumption stated as a universal rule. Both are pinned here so the
next person to touch them sees the cases that produced them.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("ad", ROOT / "scripts" / "accept_delivery.py")
ad = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ad)


# --------------------------------------------------- check 4: ACTIVE_PROSE negation --
# The real sentences from the 2026-09-06 delivery. Three of the four hits were rows being
# honest about absence, and the check accused them of asserting a live call.
NEGATED = [
    "No active 2026 cycle or landing page was found for the Renewable Energy World Awards.",
    "The Energy Storage North America Innovation Awards have not been active since 2023.",
    "The Cyber Catalyst program is currently inactive with no active cycle announced.",
    "This programme was never active in the 2026 cycle.",
    "The last active edition was held in July 2024.",
]
ASSERTED = [
    "The Global Recognition Awards operate on a rolling, year-round basis and are active.",
    "The call is now open for submissions.",
    "The programme is currently accepting entries.",
]


def test_negated_absence_is_not_an_active_claim():
    for s in NEGATED:
        assert not ad.ACTIVE_PROSE.search(s), f"false positive on: {s}"


def test_a_real_active_claim_still_fires():
    for s in ASSERTED:
        assert ad.ACTIVE_PROSE.search(s), f"missed a genuine active claim: {s}"


def test_inactive_never_matched_and_still_does_not():
    """\\b requires a boundary before 'active'; there is none inside 'inactive'."""
    assert not ad.ACTIVE_PROSE.search("The programme is inactive.")


# ------------------------------------------------------- 6b: awards are exempt --
def _gate_with(rows):
    g = ad.Gate.__new__(ad.Gate)
    g.rows = rows
    g.results = []
    return g


def _row(**kw):
    base = {"CONFERENCE": "X", "OPPORTUNITY_TYPE": "Speaking", "SUBMISSION DEADLINE": "",
            "START DATE": "", "CITY": "", "STATE_PROVINCE": "", "STATUS DETAILS": "",
            "NOTES": "", "DEADLINE_QUOTE": "", "IS_PROJECTED": "true",
            "GROUNDING_CONFIDENCE": "", "SUBMISSION URL": "", "EDITION": "2026"}
    base.update(kw)
    return base


def _check_6b(rows):
    """6b lives in check_schema_rules. Asserted, not probed - a test that silently
    skips because it could not find its subject is a guard that does nothing."""
    g = _gate_with(rows)
    g.check_schema_rules()
    res = next((r for r in g.results if r[0] == "6b"), None)
    assert res is not None, "check 6b did not run - has it been renamed or moved?"
    return res


def test_an_award_may_close_entries_during_its_own_ceremony():
    """The real case: Cyber Defense Global InfoSec, quoted verbatim.

    "Late Entry Deadline: March 25, 2026 (final cut-off)" against an event running
    March 23-26. For an award START DATE is the ceremony, not a gate to beat.
    """
    rows = [_row(CONFERENCE="Cyber Defense Global InfoSec", OPPORTUNITY_TYPE="Awards",
                 **{"SUBMISSION DEADLINE": "2026-03-25", "START DATE": "2026-03-23"})]
    res = _check_6b(rows)
    assert res[3] == [], "an awards row must not fail 6b"


def test_a_conference_still_cannot_close_its_call_after_it_starts():
    rows = [_row(CONFERENCE="Some Conference", OPPORTUNITY_TYPE="Speaking",
                 **{"SUBMISSION DEADLINE": "2026-03-25", "START DATE": "2026-03-23"})]
    res = _check_6b(rows)
    assert res[3], "a Speaking row with a deadline after its start must still fail 6b"


def test_the_exemption_is_named_in_the_criterion():
    """So a reader of the gate output knows the rule is narrower than it was."""
    src = (ROOT / "scripts" / "accept_delivery.py").read_text(encoding="utf-8")
    assert "Awards exempt" in src
