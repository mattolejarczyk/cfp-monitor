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
import time

from .aggregator import pick_event_link, score_event_link
from .config import Settings, DEFAULT
from .consolidate import consolidate
from .crawler import explore
from .extraction import extract_from_markdown
from .fetch import close_fallback_browser
from .models import ConferenceResult
from .scoring import normalize_url, score_link
from .trace import Tracer


async def analyze_conference(crawler, start_url: str, settings: Settings, tracer: Tracer,
                             context: dict | None = None, _depth: int = 0) -> ConferenceResult:
    t0 = time.monotonic()
    ex = await explore(crawler, start_url, settings, tracer)
    if not ex.start_ok:
        r = ConferenceResult(start_url=start_url, error="start page could not be fetched")
        r.trace = tracer.dump()
        return r

    start_norm = normalize_url(start_url)

    # Aggregator short-circuit (before spending LLM budget). When the row gives us context
    # (name / location / dates), decide whether we landed on the event's OWN site or on a
    # directory / org page that merely lists it. Signal: a discovered link matches the row
    # markedly better than the page we're on. If so, hop to that specific event ONCE and use
    # the resolved result, skipping the wasteful extraction of the directory's own pages.
    if _depth == 0 and context:
        target = pick_event_link(ex.all_links, context, start_url)
        if target and normalize_url(target) != start_norm:
            self_score = score_event_link(start_url, "", context)
            target_score = score_event_link(target, "", context)
            if target_score >= self_score + 1.0:
                tracer.log("aggregator", start_url,
                           f"directory page (self={self_score} < target={target_score}) -> {target}")
                sub = await analyze_conference(crawler, target, settings, tracer,
                                               context=context, _depth=1)
                if sub.name.value:
                    sub.aggregator_hop = True
                    return sub

    # Rank crawled pages for extraction: start page always, then our CFP score, then depth score.
    ranked = sorted(
        ex.pages,
        key=lambda p: (p.url == start_norm, score_link(p.url), p.score),
        reverse=True,
    )
    to_extract = ranked[: settings.max_extract_pages]
    for p in to_extract:
        tracer.log("scored", p.url, f"selected for extraction (score={p.score:.2f})")

    # Time-box extraction so we ALWAYS return within budget with the core facts. The start page
    # is ranked first, so even if a slow LLM lets us finish only a page or two, we still capture
    # the name/dates from the homepage instead of the whole conference being cancelled to nothing.
    extract_deadline = t0 + settings.per_site_timeout_s * 0.9
    pairs = []
    for p in to_extract:
        if pairs and time.monotonic() > extract_deadline:
            tracer.log("budget", p.url, "extraction time budget reached - consolidating pages done so far")
            break
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
    result.resolution_path = ex.start_via
    result.trace = tracer.dump()
    return result


async def run_urls(urls: list[str], settings: Settings | None = None,
                   contexts: list[dict] | None = None) -> list[ConferenceResult]:
    """Analyze a fixed list of conference URLs. Reuses one browser for the batch."""
    settings = settings or DEFAULT
    settings.require_llm_key()
    from crawl4ai import AsyncWebCrawler, BrowserConfig

    results: list[ConferenceResult] = []
    async with AsyncWebCrawler(config=BrowserConfig(headless=settings.headless)) as crawler:
        for i, url in enumerate(urls):
            url = url.strip()
            if not url or url.startswith("#"):
                continue
            ctx = contexts[i] if contexts and i < len(contexts) else None
            tracer = Tracer()
            try:
                res = await asyncio.wait_for(
                    analyze_conference(crawler, url, settings, tracer, context=ctx),
                    timeout=settings.per_site_timeout_s,
                )
            except asyncio.TimeoutError:
                res = ConferenceResult(start_url=url, error="per-site timeout reached")
                res.trace = tracer.dump()
            except Exception as e:
                res = ConferenceResult(start_url=url, error=f"{type(e).__name__}: {e}")
                res.trace = tracer.dump()
            results.append(res)
    await close_fallback_browser()
    return results
