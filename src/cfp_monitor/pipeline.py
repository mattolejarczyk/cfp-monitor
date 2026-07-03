"""Orchestration — the core crawl loop (all features).

For each conference URL:
  1. Score-driven exploration from the start page (crawler.explore): follows the
     highest-value internal links + buttons/CTAs, records forms and external
     submission platforms, within budget.
  2. LLM extraction on the start page + the top opportunity/context pages.
  3. Evidence-backed consolidation into one ConferenceResult (labeled status,
     field-specific evidence, multi-edition flags).
Each conference is isolated behind a timeout + try/except; one browser is reused.
"""
from __future__ import annotations

import asyncio

from .config import Settings, DEFAULT
from .consolidate import consolidate
from .crawler import explore
from .extraction import extract_from_markdown
from .models import ConferenceResult
from .scoring import normalize_url, score_link
from .trace import Tracer


async def analyze_conference(crawler, start_url: str, settings: Settings, tracer: Tracer) -> ConferenceResult:
    ex = await explore(crawler, start_url, settings, tracer)
    if not ex.start_ok:
        r = ConferenceResult(start_url=start_url, error="start page could not be fetched")
        r.trace = tracer.dump()
        return r

    # Rank crawled pages for extraction: start page always, then our CFP score, then depth score.
    start_norm = normalize_url(start_url)
    ranked = sorted(
        ex.pages,
        key=lambda p: (p.url == start_norm, score_link(p.url), p.score),
        reverse=True,
    )
    to_extract = ranked[: settings.max_extract_pages]
    for p in to_extract:
        tracer.log("scored", p.url, f"selected for extraction (score={p.score:.2f})")

    pairs = []
    for p in to_extract:
        pe = await extract_from_markdown(p.markdown, p.url, settings, tracer)
        if pe:
            pairs.append((p.url, pe))

    result = consolidate(
        start_url,
        pairs,
        ex.forms,
        ex.external_submissions,
        tracer,
        pages_crawled=len(ex.pages),
        pages_skipped=tracer.counts().get("skipped", 0),
    )
    result.canonical_url = start_norm
    result.trace = tracer.dump()
    return result


async def run_urls(urls: list[str], settings: Settings | None = None) -> list[ConferenceResult]:
    """Analyze a fixed list of conference URLs. Reuses one browser for the batch."""
    settings = settings or DEFAULT
    settings.require_llm_key()
    from crawl4ai import AsyncWebCrawler, BrowserConfig

    results: list[ConferenceResult] = []
    async with AsyncWebCrawler(config=BrowserConfig(headless=settings.headless)) as crawler:
        for url in urls:
            url = url.strip()
            if not url or url.startswith("#"):
                continue
            tracer = Tracer()
            try:
                res = await asyncio.wait_for(
                    analyze_conference(crawler, url, settings, tracer),
                    timeout=settings.per_site_timeout_s,
                )
            except asyncio.TimeoutError:
                res = ConferenceResult(start_url=url, error="per-site timeout reached")
                res.trace = tracer.dump()
            except Exception as e:
                res = ConferenceResult(start_url=url, error=f"{type(e).__name__}: {e}")
                res.trace = tracer.dump()
            results.append(res)
    return results
