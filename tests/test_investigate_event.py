"""The two-pass investigator: agreement, and the guarantee that survives it."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_s = importlib.util.spec_from_file_location("ie", ROOT / "scripts" / "investigate_event.py")
ie = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ie)


def test_agreement_is_overlap_not_equality():
    """The passes see the page differently - one windows around a match, the other picks a
    sentence - so identical strings are the wrong test."""
    assert ie.agrees("Want to propose a speaker for 2027? Fill in the form below!",
                     "propose a speaker for 2027 Fill in the form")


def test_unrelated_sentences_do_not_agree():
    assert not ie.agrees("Want to propose a speaker for 2027?",
                         "Download the agenda for the networking dinner")


def test_navigation_and_a_real_sentence_do_not_agree():
    """The Decarb case: regex returned the menu, the model returned the answer. Reporting
    those as agreement would hide exactly the failure this design exists to catch."""
    nav = ("Home - Decarb Connect North America About Past Speakers Past Partners "
           "Sponsorship Opportunities Join the Waitlist")
    assert not ie.agrees(nav, "Want to propose a speaker for 2027? Fill in the form below!")


def test_an_empty_side_never_counts_as_agreement():
    assert not ie.agrees("", "anything at all here")
    assert not ie.agrees("anything at all here", "")


def test_chrome_detection_needs_several_DISTINCT_pages():
    """Fewer than three pages cannot tell repetition from coincidence."""
    assert ie.chrome_phrases({"a": "one two three four five six seven"}) == set()


def test_a_phrase_on_three_pages_is_chrome():
    nav = "about past speakers past partners sponsorship opportunities join the waitlist"
    bodies = {f"p{i}": f"{nav} page {i} has its own content here" for i in range(3)}
    assert ie.chrome_phrases(bodies), "repeated menu text should be detected as chrome"
