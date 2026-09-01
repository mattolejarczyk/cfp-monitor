"""The "Check against your sheet" view: framing, the id crossing, and what must not ship.

Three separate things are asserted here because each has already gone wrong once.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SRC = (ROOT / "scripts" / "build_review_page.py").read_text(encoding="utf-8")


def _js_template() -> str:
    """Everything that reaches the browser: the view list and the row renderer.

    Approximated as the text from the VIEWS array to the end of the detail row, which is where
    all the customer-visible template lives.
    """
    i = SRC.index("const VIEWS = [")
    j = SRC.index("def main(", i) if "def main(" in SRC[i:] else len(SRC)
    return SRC[i:j]


def test_the_view_is_not_called_errors():
    """Naming it after the customer's mistakes would be wrong on the facts - we are the wrong
    side on two of the twelve - and it repeats the framing rejected on 2026-08-31 that put our
    own coverage gap on them."""
    assert "Check against your sheet" in SRC
    js = _js_template()
    for bad in ("sheet error", "your errors", "mistakes", "wrong on your"):
        assert bad.lower() not in js.lower(), f"{bad!r} must not appear in customer-facing text"


def test_our_internal_reasoning_does_not_ship_to_the_customer():
    """The first version put the rationale in a `//` comment inside the view list. JS comments
    reach the browser: anyone opening view-source would have read our notes about which rows WE
    had got wrong, in a file sent to the customer. Python comments do not ship."""
    js = _js_template()
    assert "we are the wrong side" not in js
    assert "Troopers" not in js, "no specific row should be named in the template"
    # And the rationale must still exist somewhere - in Python.
    assert "THIS RATIONALE LIVES IN PYTHON" in SRC


def test_the_id_crossing_happens_once_in_the_caller():
    """build() takes `recon` already keyed by the DELIVERY's EVENT_ID and does a plain lookup.
    Every time the upstream/canonical translation has been done at the point of use instead, it
    has been done wrong - contract 5.4, JUDGEMENT rule 17, twice on 2026-09-01."""
    assert "identity.seed_map(a.db)" in SRC
    assert "identity.index_by_canonical" in SRC
    i = SRC.index("def build(")
    body = SRC[i:SRC.index("MARKET_LABEL", i)] if "MARKET_LABEL" in SRC[i:] else SRC[i:i + 4000]
    assert "seed_map" not in body, "build() must not translate ids itself"


def test_an_empty_seed_map_is_refused_not_reported_as_agreement():
    """A path fault makes the map empty, every row falls through untranslated, and the result is
    zero findings - which reads as two records that agree. assert_mapped refuses instead."""
    assert "identity.assert_mapped(" in SRC


def test_the_row_says_when_we_are_the_wrong_side():
    js = _js_template()
    assert "ours_wrong" in js
    assert "Ours looks like the wrong one here" in js


def test_an_already_actioned_row_is_marked_not_hidden():
    """A conflict on a row they have submitted is worth seeing and is not urgent. Hiding it
    loses the audit trail; ranking it equally buries the live ones."""
    assert re.search(r"x\.acted\?", _js_template())


def test_reconcile_is_opt_in_and_needs_the_database():
    assert "--reconcile" in SRC
    assert "--reconcile needs --db" in SRC
