"""The substring guard on the LLM sentence selector.

This is the check that makes an LLM safe in this position at all, so it is tested by making it
fail on purpose. Every failure mode below is one we actually saw upstream: a composed sentence
that was never on the page (AAOS, twice, two different phrasings), and a real sentence carrying
the right date for the wrong fact (CCUS, "the deadline to withdraw your presentation").

A check nobody has seen fail is not yet a check.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("_ec", ROOT / "scripts" / "extract_citations.py")
ec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ec)

PAGE = (
    "CCUS 2026 Abstract Submission. "
    "Submission deadline: 1 July 2026. "
    "Please note that 1 July 2026 is also the deadline to withdraw your presentation. "
    "Abstracts must be formatted before 1 July 2026 using the template provided."
)


def _stub(monkeypatch, payload):
    """Pretend to be litellm returning `payload` as the model's JSON answer."""
    async def acompletion(**kwargs):
        msg = types.SimpleNamespace(content=json.dumps(payload))
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    monkeypatch.setitem(sys.modules, "litellm",
                        types.SimpleNamespace(acompletion=acompletion))


def pick(monkeypatch, payload, page=PAGE, deadline="2026-07-01"):
    _stub(monkeypatch, payload)
    return asyncio.run(ec.llm_pick_sentence(page, deadline, "CCUS 2026", ec.SETTINGS))


def test_accepts_a_sentence_that_is_verbatim_on_the_page(monkeypatch):
    q, _call, status = pick(monkeypatch, {"sentence": "Submission deadline: 1 July 2026."})
    assert status == "ok"
    assert q in PAGE                       # the property the whole design rests on


def test_rejects_a_sentence_that_is_not_on_the_page(monkeypatch):
    """The AAOS failure. Plausible, well-formed, correctly dated, and never written there."""
    q, _c, status = pick(monkeypatch,
                         {"sentence": "Abstract submissions are due 1 July 2026."})
    assert status == "not-on-page"
    assert q == ""


def test_rejects_a_paraphrase_of_a_real_sentence(monkeypatch):
    """Near-misses are the dangerous ones - a human reviewer would wave this through."""
    q, _c, status = pick(monkeypatch, {"sentence": "Submission deadline is 1 July 2026."})
    assert status == "not-on-page"
    assert q == ""


def test_rejects_the_right_date_for_the_wrong_fact(monkeypatch):
    """Verbatim, on the page, correctly dated - and about withdrawing, not submitting."""
    q, _c, status = pick(monkeypatch, {
        "sentence": "Please note that 1 July 2026 is also the deadline to "
                    "withdraw your presentation."})
    assert status == "wrong-purpose"
    assert q == ""


def test_rejects_a_real_sentence_carrying_the_wrong_date(monkeypatch):
    q, _c, status = pick(monkeypatch, {"sentence": "CCUS 2026 Abstract Submission."})
    assert status == "no-date"
    assert q == ""


def test_honest_blank_is_a_result_not_an_error(monkeypatch):
    q, _c, status = pick(monkeypatch, {"sentence": ""})
    assert (q, status) == ("", "blank")


def test_whitespace_differences_do_not_cause_a_false_reject(monkeypatch):
    """Page text arrives with HTML whitespace; a re-wrapped copy is still the same sentence."""
    q, _c, status = pick(monkeypatch, {"sentence": "Submission   deadline:\n  1 July 2026."})
    assert status == "ok"
    assert q == "Submission deadline: 1 July 2026."


def test_an_outage_is_reported_as_unavailable_not_as_a_blank(monkeypatch):
    """The distinction the fallback rule depends on: no answer must not read as 'no'."""
    async def boom(**kwargs):
        raise RuntimeError("provider down")
    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(acompletion=boom))
    q, _c, status = asyncio.run(
        ec.llm_pick_sentence(PAGE, "2026-07-01", "CCUS 2026", ec.SETTINGS))
    assert (q, status) == ("", "unavailable")


def test_garbage_that_is_not_json_is_unavailable(monkeypatch):
    async def junk(**kwargs):
        msg = types.SimpleNamespace(content="I could not find a deadline on this page.")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])
    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(acompletion=junk))
    _q, _c, status = asyncio.run(
        ec.llm_pick_sentence(PAGE, "2026-07-01", "CCUS 2026", ec.SETTINGS))
    assert status == "unavailable"


# --- how a rejection flows through the row ------------------------------------------------

def _row():
    return {k: "" for k in ec.OUT_COLUMNS} | {
        "CONFERENCE": "CCUS 2026", "SUBMISSION DEADLINE": "2026-07-01", "IS_PROJECTED": "true"}


def test_a_considered_blank_does_not_fall_back_to_the_heuristic(monkeypatch):
    """The whole point. The heuristic WOULD have found a sentence here - the model says none of
    them is a submission deadline, and that judgement has to stand or we have bought nothing."""
    _stub(monkeypatch, {"sentence": ""})
    rec, stats = _row(), {}
    asyncio.run(ec.fill_row(rec, ["http://x"], {"http://x": PAGE}, True, stats))
    assert rec["DEADLINE_QUOTE"] == ""
    assert rec["IS_PROJECTED"] == "true"
    assert stats["blank"] == 1
    # ... and prove the heuristic really would have filled it, so the test cannot pass vacuously
    assert ec.best_quote(PAGE, "2026-07-01")[0]


def test_an_outage_does_fall_back_to_the_heuristic(monkeypatch):
    async def boom(**kwargs):
        raise RuntimeError("provider down")
    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(acompletion=boom))
    rec, stats = _row(), {}
    asyncio.run(ec.fill_row(rec, ["http://x"], {"http://x": PAGE}, True, stats))
    assert rec["DEADLINE_QUOTE"] in PAGE and rec["DEADLINE_QUOTE"]
    assert rec["EXTRACTED_FROM"].endswith("selected by heuristic")


def test_a_selected_quote_records_which_selector_chose_it(monkeypatch):
    _stub(monkeypatch, {"sentence": "Submission deadline: 1 July 2026.", "call": "abstract"})
    rec, stats = _row(), {}
    asyncio.run(ec.fill_row(rec, ["http://x"], {"http://x": PAGE}, True, stats))
    assert rec["EXTRACTED_FROM"].endswith("selected by llm")
    assert rec["CALL"] == "abstract"
    assert rec["IS_PROJECTED"] == "false"


def test_no_llm_mode_still_works_without_a_provider():
    rec, stats = _row(), {}
    asyncio.run(ec.fill_row(rec, ["http://x"], {"http://x": PAGE}, False, stats))
    assert rec["DEADLINE_QUOTE"] in PAGE
    assert stats == {}


@pytest.mark.parametrize("bad", [
    "Papers are due 1 July 2026.",                     # composed outright
    "Submission deadline: July 1, 2026.",              # real fact, reformatted date
    "The submission deadline is 1 July 2026.",         # real fact, reworded
    "Submission deadline: 1 July 2027.",               # one digit off
])
def test_every_shape_of_not_copied_is_rejected(monkeypatch, bad):
    _q, _c, status = pick(monkeypatch, {"sentence": bad})
    assert status == "not-on-page"


@pytest.mark.parametrize("sloppy", [
    "submission deadline: 1 july 2026.",               # case flattened
    "Submission deadline: 1 July 2026",                # closing stop dropped
    "  Submission deadline:  1 July 2026.  ",          # padded
])
def test_a_sloppy_copy_is_corrected_back_to_the_page(monkeypatch, sloppy):
    """Rejecting these would be pedantry - the model found the right sentence. Accept the
    judgement, then quote the page rather than the answer, so what we store is the source's
    own characters no matter how carelessly they were echoed back."""
    q, _c, status = pick(monkeypatch, {"sentence": sloppy})
    assert status == "ok"
    assert q == "Submission deadline: 1 July 2026."
    assert q in PAGE


# --- the call label, which the substring check does NOT cover -------------------------------

LABELLED = (
    "As the regular call for abstracts has now closed, we have opened the call for "
    "late-breaking posters. Late-breaking poster abstracts are reviewed on a rolling basis. "
    "Submission deadline: 1 July 2026. Main themes for the conference follow below."
)


def test_a_label_the_page_supports_is_kept(monkeypatch):
    q, call, status = pick(monkeypatch,
                           {"sentence": "Submission deadline: 1 July 2026.",
                            "call": "late-breaking poster"}, page=LABELLED)
    assert (status, call) == ("ok", "late-breaking poster")
    assert q in LABELLED


def test_a_label_the_page_does_not_support_is_dropped(monkeypatch):
    """The quote survives - it is verified. The unverifiable claim attached to it does not."""
    q, call, status = pick(monkeypatch,
                           {"sentence": "Submission deadline: 1 July 2026.",
                            "call": "keynote proposal"}, page=LABELLED)
    assert status == "ok"
    assert q                                  # evidence kept
    assert "keynote" not in call              # unsupported label discarded


def test_a_label_supported_only_far_away_on_the_page_is_dropped(monkeypatch):
    far = "Workshop proposals are invited. " + ("filler text. " * 200) + LABELLED
    _q, call, _s = pick(monkeypatch, {"sentence": "Submission deadline: 1 July 2026.",
                                      "call": "workshop proposal"}, page=far)
    assert "workshop" not in call


# --- depth: R3 runs both ways ---------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://wccus.org/", True),
    ("https://wccus.org", True),
    ("http://example.org//", True),
    ("https://wccus.org/abstract-submission", False),
    ("https://wccus.org/?page=cfp", False),
])
def test_homepage_detection(url, expected):
    assert ec.is_homepage(url) is expected


def test_deep_candidates_are_tried_before_homepages():
    cands = ["https://wccus.org/", "https://wccus.org/abstract-submission"]
    assert ec.deep_first(cands)[0] == "https://wccus.org/abstract-submission"


def test_upstream_order_is_kept_within_each_group():
    cands = ["https://a.org/one", "https://a.org/", "https://a.org/two"]
    assert ec.deep_first(cands) == ["https://a.org/one", "https://a.org/two", "https://a.org/"]


def test_a_deep_page_wins_even_when_the_homepage_also_carries_the_date(monkeypatch):
    """The coin flip this removes: both pages carry the sentence, only one is a citation."""
    _stub(monkeypatch, {"sentence": "Submission deadline: 1 July 2026."})
    rec, stats = _row(), {}
    pages = {"https://wccus.org/": PAGE, "https://wccus.org/abstract-submission": PAGE}
    asyncio.run(ec.fill_row(rec, ["https://wccus.org/",
                                  "https://wccus.org/abstract-submission"], pages, True, stats))
    assert rec["DEADLINE_EVIDENCE_URL"] == "https://wccus.org/abstract-submission"
    assert rec["NOTE"] == ""


def test_falling_back_to_a_homepage_is_recorded_not_hidden(monkeypatch):
    _stub(monkeypatch, {"sentence": "Submission deadline: 1 July 2026."})
    rec, stats = _row(), {}
    asyncio.run(ec.fill_row(rec, ["https://wccus.org/"], {"https://wccus.org/": PAGE},
                            True, stats))
    assert rec["DEADLINE_EVIDENCE_URL"] == "https://wccus.org/"
    assert "homepage" in rec["NOTE"]


@pytest.mark.parametrize("url", [
    "https://example.org/index.html", "https://example.org/index.php",
    "https://example.org/Index.HTML", "https://example.org/home",
    "https://example.org/default.asp", "https://example.org/",
])
def test_landing_pages_count_as_homepages_however_they_are_spelled(url):
    """Upstream strips index/home pages too, but case-sensitively. Our guard must not depend
    on theirs being exhaustive - whatever arrives has to be classified correctly here, or a
    landing page slips through as 'deep' and is allowed to replace a real citation."""
    assert ec.is_homepage(url) is True


@pytest.mark.parametrize("url", [
    "https://example.org/call-for-papers",
    "https://example.org/index.php?page=call-for-papers",
    "https://example.org/2026/abstracts",
])
def test_real_deep_links_are_not_mistaken_for_homepages(url):
    assert ec.is_homepage(url) is False
