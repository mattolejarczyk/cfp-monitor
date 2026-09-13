"""Quality by design: a run knows when it could not look, and says so.

Replays 2026-09-13: a 14-site crawl whose page reads were rate-limited reported "nothing found"
eleven times, and the truth was found afterwards in 112 suppressed error banners.
"""
import asyncio
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import extraction                                # noqa: E402
from src.cfp_monitor import run_health as rh                          # noqa: E402


@pytest.fixture
def health(monkeypatch):
    h = rh.RunHealth("test")
    monkeypatch.setattr(extraction, "HEALTH", h)
    return h


class RateLimitError(Exception):
    pass


class BadRequestError(Exception):
    pass


def fake_litellm(outcomes):
    """acompletion() raises or returns according to `outcomes`, recording each call's kwargs."""
    calls = []

    async def acompletion(**kw):
        calls.append(kw)
        o = outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return types.SimpleNamespace(choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(content=o))])
    return types.SimpleNamespace(acompletion=acompletion), calls


def no_sleep(record):
    async def sleep(s):
        record.append(s)
    return sleep


# ---------------------------------------------------------------- verdicts

def test_a_mostly_failing_check_is_degraded():
    h = rh.RunHealth()
    h.ok("page_read", 3)
    for _ in range(12):
        h.fail("page_read", "rate_limited", "u")
    status, reasons = h.verdict()
    assert status == "DEGRADED" and "12 of 15 failed" in reasons[0] and "rate_limited" in reasons[0]


def test_an_ordinary_stray_failure_is_healthy():
    h = rh.RunHealth()
    h.ok("page_read", 19)
    h.fail("page_read", "no_json", "u")
    assert h.verdict()[0] == "HEALTHY"


def test_too_few_attempts_are_not_judged_on_rate():
    h = rh.RunHealth()
    h.fail("site_crawl", "could_not_read")
    assert h.verdict()[0] == "HEALTHY"


def test_a_hard_failure_degrades_regardless_of_rate():
    h = rh.RunHealth()
    h.ok("gate_run", 50)
    h.fail("gate_run", "gate_crashed", "exit 1")
    status, reasons = h.verdict()
    assert status == "DEGRADED" and "gate_crashed" in reasons[0]


def test_health_from_another_process_merges():
    a, b = rh.RunHealth(), rh.RunHealth()
    b.ok("gemini_call")
    for _ in range(5):
        b.fail("gemini_call", "http_504", "London")
    a.merge(b.to_dict())
    assert a.attempts("gemini_call") == 6 and a.verdict()[0] == "DEGRADED"


def test_the_report_leads_with_the_verdict():
    h = rh.RunHealth()
    h.fail("gate_run", "gate_crashed")
    assert h.report_lines()[0] == "## Run health: DEGRADED"


# ---------------------------------------------------------------- retries

def test_a_rate_limit_is_retried_after_a_pause_and_then_succeeds(health):
    mod, calls = fake_litellm([RateLimitError("429 rate-limited upstream"),
                               RateLimitError("429 rate-limited upstream"), "{}"])
    slept = []
    asyncio.run(extraction.acomplete_with_retry(mod, {"model": "m"}, "u", (5, 15, 30),
                                                no_sleep(slept)))
    assert len(calls) == 3 and slept == [5, 15]
    assert all("response_format" in c for c in calls)        # never mistaken for "no JSON mode"
    assert health.notes["page_read"]["retried_rate_limit"] == 2


def test_a_rate_limit_that_never_clears_raises_after_every_delay(health):
    mod, calls = fake_litellm([RateLimitError("429")] * 4)
    slept = []
    with pytest.raises(RateLimitError):
        asyncio.run(extraction.acomplete_with_retry(mod, {}, "u", (5, 15, 30), no_sleep(slept)))
    assert len(calls) == 4 and slept == [5, 15, 30]


def test_unsupported_json_mode_falls_back_to_plain_once_without_waiting(health):
    mod, calls = fake_litellm([BadRequestError("response_format json_object not supported"), "{}"])
    slept = []
    asyncio.run(extraction.acomplete_with_retry(mod, {}, "u", (5,), no_sleep(slept)))
    assert "response_format" in calls[0] and "response_format" not in calls[1] and slept == []


def test_a_non_transient_error_is_not_retried(health):
    mod, calls = fake_litellm([ValueError("invalid api key")])
    with pytest.raises(ValueError):
        asyncio.run(extraction.acomplete_with_retry(mod, {}, "u", (5, 15), no_sleep([])))
    assert len(calls) == 1


def test_a_page_read_that_is_rate_limited_to_the_end_is_recorded_not_swallowed(health, monkeypatch):
    mod, _ = fake_litellm([RateLimitError("429 rate-limited upstream")] * 4)
    monkeypatch.setitem(sys.modules, "litellm", mod)
    monkeypatch.setattr(extraction, "RETRY_DELAYS", (0, 0, 0))

    async def instant(_s):
        return None
    monkeypatch.setattr(extraction.asyncio, "sleep", instant)
    settings = types.SimpleNamespace(llm_proxy_url=None, llm_provider="p", provider_key=lambda: "k",
                                     llm_temperature=0, llm_max_tokens=10)
    tracer = types.SimpleNamespace(log=lambda *a, **k: None)
    out = asyncio.run(extraction.extract_from_markdown("x" * 100, "https://site.test/cfp",
                                                       settings, tracer))
    assert out is None
    assert health.counts["page_read"]["rate_limited"] == 1


# ---------------------------------------------------------------- the crawl admits it could not read

def test_a_site_whose_every_read_failed_is_not_reported_as_nothing_found(monkeypatch):
    from scripts import find_replacement_links as frl
    h = rh.RunHealth()
    monkeypatch.setattr(frl, "HEALTH", h)

    async def run_urls(urls, settings):
        for _ in range(3):
            h.fail("page_read", "rate_limited", urls[0])
        return [types.SimpleNamespace(submission_url=None, status_basis="", evidence=[],
                                      submission_platform="")]

    async def close():
        return None
    monkeypatch.setattr(frl, "run_urls", run_urls)
    monkeypatch.setattr(frl, "close_fallback_browser", close)
    rows = [{"event_id": "e", "name": "Gartner IAM 2026", "submission_url": "https://g.test/cfp",
             "url": "https://g.test/", "main_info_url": ""}]
    rec = asyncio.run(frl.hunt(rows, types.SimpleNamespace()))[0]
    assert rec["OUTCOME"] == "Could not read the site"
    assert "3 page read(s) failed" in rec["NOTE"]
    assert h.counts["site_crawl"]["could_not_read"] == 1


def test_a_site_where_no_page_was_read_at_all_is_not_nothing_found(monkeypatch):
    """Rerun 2026-09-13: London reported "No live page found" with 0 pages read, 0 failed."""
    from scripts import find_replacement_links as frl
    h = rh.RunHealth()
    monkeypatch.setattr(frl, "HEALTH", h)

    async def run_urls(urls, settings):
        return [types.SimpleNamespace(submission_url=None, status_basis="", evidence=[],
                                      submission_platform="")]

    async def close():
        return None
    monkeypatch.setattr(frl, "run_urls", run_urls)
    monkeypatch.setattr(frl, "close_fallback_browser", close)
    rows = [{"event_id": "e", "name": "London 2027", "submission_url": "https://l.test/apply",
             "url": "https://l.test/", "main_info_url": ""}]
    rec = asyncio.run(frl.hunt(rows, types.SimpleNamespace()))[0]
    assert rec["OUTCOME"] == "Could not read the site" and "no page" in rec["NOTE"]
    assert h.counts["site_crawl"]["could_not_read"] == 1
