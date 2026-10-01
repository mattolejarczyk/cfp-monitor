"""The merge guard must not treat an anti-bot wall as the page (found 2026-10-01 on Global Energy Show Canada)."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("apply_resolutions", Path(__file__).resolve().parents[1] / "scripts" / "apply_resolutions.py")
ar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ar)


def test_incapsula_notice_is_a_block_page():
    assert ar._is_block_page(" Request unsuccessful. Incapsula incident ID: 260000060773792091-441289197983367596 ") is True


def test_cloudflare_challenge_is_a_block_page():
    assert ar._is_block_page("Just a moment... Enable JavaScript and cookies to continue") is True


def test_empty_is_not_flagged_here():
    # empty text is already handled by the existing `if not text` branch
    assert ar._is_block_page("") is False
    assert ar._is_block_page(None) is False


def test_real_page_mentioning_the_phrase_is_not_a_block_page():
    real = ("Call for submissions. All submissions must be completed through the online form by December 4, 2026. " * 20
            + " Access denied is not a phrase we use. Incapsula is a vendor name.")
    assert len(real) > 600 and ar._is_block_page(real) is False


def test_short_real_text_without_markers_is_not_a_block_page():
    assert ar._is_block_page("Submission deadline : 15 October 2026") is False
