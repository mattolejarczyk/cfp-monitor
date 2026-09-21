"""R16 fails an ASSERTED ending without evidence, and allows a declared doubt.

WHY THIS CHANGED, 2026-09-20 (operator decision)
R16 used to fail ANY row whose prose read as a discontinuation and carried no citation. That
included a row the generator had itself downgraded to "Needs Verification" precisely because
it could not evidence the claim - so the two halves of the pipeline disagreed by design. The
generator deliberately keeps an unproven finding visible for a person to go cite
(downgrade_unevidenced_discontinuation), and the gate then rejected the delivery for it.

The cost was measured, not hypothetical. Two such rows, on conferences nobody at the customer
was tracking, blocked all 112 rows of a week's research from reaching them. Re-researching
them under a deliberately tightened prompt did not clear it either: the model still wrote
"ShmooCon has permanently ended" with no citation to offer. Prompt work could not fix a
disagreement between two rules.

So the check now asks the question that matters: is this row ASSERTING an event is over, or
REPORTING that it could not confirm the event is alive?

THE PROTECTION THAT MATTERS IS UNCHANGED, and the second test here is the one that guards it:
nothing reaches a customer labelled "Closed" on prose alone.
"""
import csv
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "_ad_r16", ROOT / "scripts" / "accept_delivery.py")
ad = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ad)

COLS = ["EVENT_ID", "CONFERENCE", "SUBMISSION DEADLINE", "DEADLINE_EVIDENCE_URL",
        "DEADLINE_QUOTE", "LIFECYCLE_EVIDENCE_URL", "LIFECYCLE_QUOTE", "SPONSOR_URL",
        "SPONSOR_REQUIRED", "IS_PROJECTED", "GROUNDING_CONFIDENCE", "STATUS", "STATUS DETAILS"]

ENDED = "ShmooCon has permanently ended and will not have a 2027 edition."


def _r16(tmp_path, row):
    p = tmp_path / "d.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerow({c: row.get(c, "") for c in COLS})
    g = ad.Gate(str(p), network=False)
    with open(p, encoding="utf-8-sig", newline="") as fh:
        g.rows = list(csv.DictReader(fh))
    g.check_schema_rules()
    return {num: (ok, fails) for num, _name, ok, fails in g.results}


def _row(**kw):
    base = {"EVENT_ID": "2027-x-speaking", "CONFERENCE": "Test Event 2027",
            "STATUS DETAILS": ENDED, "IS_PROJECTED": "true"}
    base.update(kw)
    return base


def test_declared_doubt_is_allowed(tmp_path):
    """The row says only that it could not confirm the event is alive. That ships."""
    res = _r16(tmp_path, _row(STATUS="Needs Verification"))
    ok, fails = res["R16"]
    assert ok, f"a downgraded row must not fail R16: {fails}"


def test_asserting_closed_without_evidence_still_fails(tmp_path):
    """THE INVERSION, and the whole point. 'Closed' on prose alone is the dangerous claim."""
    res = _r16(tmp_path, _row(STATUS="Closed"))
    ok, fails = res["R16"]
    assert not ok, "Closed with no lifecycle citation must still be rejected"


def test_an_evidenced_ending_passes(tmp_path):
    res = _r16(tmp_path, _row(STATUS="Closed",
                              LIFECYCLE_EVIDENCE_URL="https://shmoocon.org/",
                              LIFECYCLE_QUOTE="ShmooCon has come to an end."))
    ok, fails = res["R16"]
    assert ok, f"an evidenced discontinuation must pass: {fails}"


def test_needs_verification_but_not_projected_still_fails(tmp_path):
    """Both halves of the downgrade are required. A row claiming a verified edition while
    its prose says the event ended is the contradiction 2.1b exists for."""
    res = _r16(tmp_path, _row(STATUS="Needs Verification", IS_PROJECTED="false"))
    ok, _ = res["R16"]
    assert not ok, "Needs Verification without IS_PROJECTED=true must not slip through"


def test_a_row_saying_nothing_about_endings_is_untouched(tmp_path):
    """GOOD INPUT SURVIVES: an ordinary open call is not this check's business."""
    res = _r16(tmp_path, _row(STATUS="Open",
                              **{"STATUS DETAILS": "The call for papers is open until March."}))
    ok, fails = res["R16"]
    assert ok, f"an ordinary row must not be caught by R16: {fails}"


def test_a_rotation_is_not_an_ending(tmp_path):
    """Pre-existing behaviour that must survive the rewrite: an event that moves venue on a
    cycle is alive, not discontinued."""
    res = _r16(tmp_path, _row(STATUS="Closed",
                              **{"STATUS DETAILS": "The final edition in Hannover; the cycle "
                                                   "dictates it alternates to Milan in 2027."}))
    ok, _ = res["R16"]
    assert ok, "a rotation must not be read as a discontinuation"
