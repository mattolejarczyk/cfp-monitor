"""ACT-49: an ASCII hyphen in a quote must match the en dash (or other dash) on the page, in EVERY place a quote is compared with page text.

Upstream writes 'November 15, 2026 - February 18, 2027'; the World of Concrete page says '... 2026 <en dash> February 18, 2027' (note 29). Before this test the gate
(accept_delivery.norm) already folded en/em dash and minus, but locate_verbatim (extract_citations: sponsor quotes, investigate_event) turned a page dash into a space while
keeping the quote's hyphen, and pass_lib.norm folded nothing. Only dashes, spaces and quote marks are folded; never words or digits.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ad = _load("ad_dash", "scripts/accept_delivery.py")
ec = _load("ec_dash", "scripts/extract_citations.py")
from experiments.read_the_page_pass import pass_lib as P  # noqa: E402
from src.cfp_monitor.verify import fold_punctuation  # noqa: E402

QUOTE = "Submissions Period: November 15, 2026 - February 18, 2027"
PAGE_EN = "Intro text. Submissions Period: November 15, 2026 – February 18, 2027. Apply now."
DASHES = ["‐", "‑", "‒", "–", "—", "―", "−"]


def test_gate_criterion_3_comparison_accepts_hyphen_for_every_dash():
    for d in DASHES:
        assert ad.norm(QUOTE) in ad.norm(PAGE_EN.replace("–", d)), hex(ord(d))


def test_locate_verbatim_finds_a_hyphen_quote_on_a_page_with_an_en_dash_and_returns_the_pages_own_characters():
    found = ec.locate_verbatim(PAGE_EN, QUOTE)
    assert found is not None and "–" in found


def test_pass_lib_norm_folds_dashes_and_nbsp():
    for d in DASHES:
        assert P.norm(QUOTE) in P.norm(PAGE_EN.replace("–", d))


def test_folding_never_joins_words_or_changes_digits():
    assert fold_punctuation("15–17 Nov") == "15-17 Nov"
    assert fold_punctuation("it’s “x”") == "it's \"x\""
    assert ad.norm("2026 - 2027") not in ad.norm("2026 2027")           # a dash is not a space: the fold must not be looser than that
    assert ec.locate_verbatim("Deadline 15 June", "Deadline 16 June") is None
    assert ec.locate_verbatim("Call: 15–17 June", "Call: 1517 June") is None
