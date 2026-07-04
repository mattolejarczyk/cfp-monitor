"""Crawl quality gate — classify every crawl into an explicit verdict so nothing
fails silently (VOC: "blocked/partial pages must be classified and routed; no
silent failures").

Verdicts:
- PASS    : usable content retrieved and a real result extracted.
- PARTIAL : content retrieved but thin / incomplete — usable but not trusted.
- BLOCKED : the site refused us (anti-bot / 4xx-5xx / no content).
- ERROR   : an unexpected failure — surfaced, never swallowed.

Pure logic over signals; it does no crawling itself, so it is fully unit-testable
offline. crawl4ai (or the local runner) fills in `CrawlSignals`; this module is
the single place that decides pass/fail.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .models import ConferenceResult


class Quality(str, Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


# HTTP statuses that mean "the site turned us away", not "page missing content".
_BLOCK_STATUS = {401, 403, 407, 429, 503}
# Substrings that betray an anti-bot interstitial even behind a 200.
_BLOCK_MARKERS = (
    "just a moment", "cf-chl", "cf-browser-verification", "attention required",
    "access denied", "are you a robot", "captcha", "enable javascript and cookies",
    "request unsuccessful", "ddos protection",
)
# Below this many chars of usable text, a 200 is really an empty / JS-shell page.
_MIN_USABLE_CHARS = 400


@dataclass
class CrawlSignals:
    """Minimal signals a crawl produces, decoupled from crawl4ai so the gate is
    testable without a browser."""
    url: str
    fetched: bool = False              # did we get any HTTP response at all?
    status_code: Optional[int] = None
    content_chars: int = 0             # usable text length (markdown / cleaned)
    body_sample: str = ""              # small sample used for anti-bot marker checks
    error: Optional[str] = None        # transport / exception message, if any
    pages_crawled: int = 0


@dataclass
class QualityReport:
    url: str
    verdict: Quality
    reason: str
    signals: CrawlSignals


def _has_block_marker(sample: str) -> bool:
    s = (sample or "").lower()
    return any(m in s for m in _BLOCK_MARKERS)


def classify(sig: CrawlSignals) -> QualityReport:
    """Deterministically map crawl signals to a verdict. Order matters: hard
    failures first, then blocking, then thinness, then success."""
    def rep(v: Quality, why: str) -> QualityReport:
        return QualityReport(url=sig.url, verdict=v, reason=why, signals=sig)

    if sig.error:
        return rep(Quality.ERROR, f"crawl raised an error: {sig.error}")
    if not sig.fetched:
        return rep(Quality.BLOCKED, "no HTTP response was obtained")
    if sig.status_code in _BLOCK_STATUS:
        return rep(Quality.BLOCKED, f"anti-bot / refused status {sig.status_code}")
    if sig.status_code is not None and sig.status_code >= 500:
        return rep(Quality.BLOCKED, f"server error status {sig.status_code}")
    if _has_block_marker(sig.body_sample):
        return rep(Quality.BLOCKED, "anti-bot interstitial detected in page body")
    if sig.status_code is not None and 400 <= sig.status_code < 500:
        # 404 / 410 etc: reachable network-wise but no content for us.
        return rep(Quality.PARTIAL, f"page unavailable status {sig.status_code}")
    if sig.content_chars < _MIN_USABLE_CHARS:
        return rep(Quality.PARTIAL, f"thin content ({sig.content_chars} chars < {_MIN_USABLE_CHARS})")
    return rep(Quality.PASS, f"usable content ({sig.content_chars} chars)")


def classify_result(result: ConferenceResult, signals: Optional[CrawlSignals] = None) -> QualityReport:
    """Derive a verdict for a finished ConferenceResult. Explicit crawl signals win;
    otherwise infer conservatively from the result itself (never silently 'pass')."""
    if signals is not None:
        return classify(signals)
    if result.error:
        return QualityReport(result.start_url, Quality.ERROR, f"pipeline error: {result.error}",
                             CrawlSignals(url=result.start_url, error=result.error))
    if result.pages_crawled == 0:
        return QualityReport(result.start_url, Quality.BLOCKED, "no pages were crawled",
                             CrawlSignals(url=result.start_url, fetched=False))
    has_core = bool(result.name.value or result.conference_dates.value
                    or result.cfp_close_date.value or result.submission_url.value)
    if result.status_basis == "insufficient_evidence" and not has_core:
        return QualityReport(result.start_url, Quality.PARTIAL, "crawled but too little was extracted",
                             CrawlSignals(url=result.start_url, fetched=True, pages_crawled=result.pages_crawled))
    return QualityReport(result.start_url, Quality.PASS, "crawled and extracted core facts",
                         CrawlSignals(url=result.start_url, fetched=True, pages_crawled=result.pages_crawled,
                                      content_chars=_MIN_USABLE_CHARS))
