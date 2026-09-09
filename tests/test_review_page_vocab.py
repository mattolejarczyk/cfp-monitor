"""Every reader-facing word that differs by kind actually differs.

The first awards page (2026-09-08) was headed "Awards & Entry Deadlines" and still told the
reader, in five other places, that it was about conferences: the browser tab said "Conference
Review", the first column said "Conference", the deadline column said "CFP deadline", the
legend explained that "the conference no longer exists", and every row carried a redundant
"Awards" badge. The heading had been given a vocabulary and nothing else had.

A placeholder that is never substituted is the other half of the same failure, so both
directions are asserted here.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("brp",
                                               ROOT / "scripts" / "build_review_page.py")
brp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(brp)

KEYS = ("title", "doctitle", "noun", "search", "col_name", "col_dates", "col_deadline", "gone")


def test_every_kind_defines_every_word():
    for kind, vocab in brp.VOCAB.items():
        missing = [k for k in KEYS if not (vocab.get(k) or "").strip()]
        assert not missing, f"{kind} is missing {missing}"


def test_the_two_kinds_disagree_on_every_word_that_matters():
    """If a word is identical across kinds it does not belong in VOCAB - and if it differs, a
    build must not be able to emit the wrong one."""
    c, a = brp.VOCAB["conference"], brp.VOCAB["awards"]
    for k in KEYS:
        assert c[k] != a[k], f"{k!r} is the same for both kinds"


def test_no_awards_word_says_conference():
    for k, v in brp.VOCAB["awards"].items():
        assert "conference" not in v.lower(), f"awards {k!r} still says conference: {v!r}"


def test_the_template_carries_a_placeholder_for_each_word():
    """The bug was a hardcoded string, not a wrong one. A literal here cannot be overridden."""
    for token in ("__DOCTITLE__", "__COL_NAME__", "__COL_DATES__", "__COL_DEADLINE__",
                  "__GONE__", "__TITLE__", "__NOUN__", "__SEARCHHINT__"):
        assert token in brp.PAGE, f"{token} is not in the template"


def test_the_template_has_no_leftover_hardcoded_conference_chrome():
    """The exact five strings that shipped wrong, so none can quietly come back."""
    for literal in ("<title>Conference Review",
                    '<th data-k="n">Conference</th>',
                    '<th data-k="dl">CFP deadline</th>',
                    "the conference no longer exists"):
        assert literal not in brp.PAGE, f"hardcoded again: {literal!r}"


def test_every_placeholder_in_the_template_is_substituted():
    """The other direction: an unsubstituted __TOKEN__ would render literally to a customer."""
    tokens = set(re.findall(r"__[A-Z_]+__", brp.PAGE))
    src = (ROOT / "scripts" / "build_review_page.py").read_text(encoding="utf-8")
    for t in sorted(tokens):
        assert f"replace('{t}'" in src, f"{t} appears in the template but is never replaced"


def test_the_opportunity_badge_is_suppressed_when_it_repeats_the_page_kind():
    """Every row on an awards page is an award, so an "Awards" badge on each one carries no
    information and reads as a stutter: "Golden Bridge Awards Awards"."""
    assert "r.op.toLowerCase()!==KIND" in brp.PAGE
