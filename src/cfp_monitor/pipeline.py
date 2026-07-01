"""Orchestration — the core crawl loop (feat, all).

For each conference URL:
  1. Fetch the start page + discover links/buttons/CTAs and submission platforms.
  2. Deep-crawl the highest-value internal pages within budget.
  3. Run LLM extraction on the top pages (start page + best opportunity/context pages).
  4. Consolidate into one evidence-backed ConferenceResult.
Each conference is isolated behind a wall-clock timeout and try/except so one bad
site never breaks the batch. One browser is reused across all conferences.
"""
from __future__ import annotations

import asyncio

from .config import Settings, DEFAULT
from .consolidate import consolidate
from .crawler import deep_crawl, CrawledPage
from .discovery import discover
from .extraction import extract_from_markdown
from .models import ConferenceResult
from .scoring import normalize_url, score_link
from .trace import Tracer


async def analyze_conference(crawler, start_url: str, settings: Settings, tracer: Tracer) -> ConferenceResult:
    disc = await discover(crawler, start_url, settings, tracer)
    if not disc.ok:
        r = ConferenceResult(start_url=start_url, error="start page could not be fetched")
        r.trace = tracer.dump()
        return r

    pages = await deep_crawl(crawler, start_url, settings, tracer)

    # Ensure the start page's content is available for extraction.
    have = {p.url for p in pages}
    if normalize_url(start_url) not in have and disc.start_markdown:
        pages.insert(0, CrawledPage(normalize_url(start_url), disc.start_markdown, 0, 99.0))

    # Rank pages for extraction: our CFP link score first, then crawl score.
    ranked = sorted(pages, key=lambda p: (score_link(p.url), p.score), reverse=True)
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
        disc.submission_links,
        tracer,
        pages_crawled=len(pages),
        pages_skipped=tracer.counts().get("skipped", 0),
    )
    result.canonical_url = normalize_url(start_url)
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
            except Exception as e:  # never let one site kill the batch
                res = ConferenceResult(start_url=url, error=f"{type(e).__name__}: {e}")
                res.trace = tracer.dump()
            results.append(res)
    return results
