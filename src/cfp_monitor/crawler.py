"""Score-driven site exploration (feat 2, 3, 4, 5, 6, 7, 11).

The start URL is only the entry point. We run our OWN best-first crawl: a priority
frontier ordered by the custom CFP/opportunity scorer (scoring.score_link), fetching
each page with crawl4ai. This guarantees high-value pages (Speakers, Call for
Papers, Best of Show, Submit…) are crawled FIRST within budget — regardless of
crawl4ai's generic link score, which we found rates conference pages ~0.

On every page we harvest links, buttons/CTAs, and forms; internal high-value links
go back on the frontier, and links to known external submission platforms are
recorded (not deep-crawled) as opportunity evidence.
"""
from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field

from .discovery import extract_clickables, detect_forms
from .scoring import normalize_url, same_site, score_link, detect_submission_platform
from .trace import Tracer


@dataclass
class CrawledPage:
    url: str
    markdown: str
    depth: int
    score: float


@dataclass
class ExploreResult:
    pages: list[CrawledPage] = field(default_factory=list)
    forms: list[dict] = field(default_factory=list)              # {url, platform, context}
    external_submissions: list[dict] = field(default_factory=list)  # {url, platform, text}
    start_ok: bool = False


async def explore(crawler, start_url: str, settings, tracer: Tracer) -> ExploreResult:
    from crawl4ai import CrawlerRunConfig, CacheMode

    # Native popup/consent handling: strip the GDPR "Manage Consent" (CMP) modal and
    # any promo overlay BEFORE extracting, so blocking popups don't stall the crawl.
    cfg = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        verbose=settings.verbose,
        remove_consent_popups=settings.remove_consent_popups,
        remove_overlay_elements=settings.remove_overlay_elements,
        magic=settings.crawl_magic,
    )
    start_norm = normalize_url(start_url)

    counter = itertools.count()
    # Min-heap on negative score → highest opportunity-score first. Start page wins.
    frontier: list[tuple] = [(-1e9, next(counter), start_url, 0)]
    visited: set[str] = set()
    out = ExploreResult()
    ext_seen: set[str] = set()

    while frontier and len(out.pages) < settings.max_pages:
        neg, _, url, depth = heapq.heappop(frontier)
        nu = normalize_url(url)
        if nu in visited:
            continue
        visited.add(nu)

        try:
            r = await crawler.arun(url, config=cfg)
        except Exception as e:
            tracer.log("skipped", url, f"fetch raised: {e}")
            continue
        if not r or not getattr(r, "success", False):
            tracer.log("skipped", url, f"status={getattr(r, 'status_code', '?')} depth={depth}")
            continue

        if nu == start_norm:
            out.start_ok = True
        md = str(getattr(r, "markdown", "") or "")
        html = getattr(r, "html", "") or ""
        page_score = 0.0 if depth == 0 else round(-neg, 3)
        out.pages.append(CrawledPage(nu, md, depth, page_score))
        tracer.log("crawled", url, f"depth={depth} score={page_score:.2f}", chars=len(md))

        # Forms on this page are opportunity evidence.
        for fo in detect_forms(html, url):
            if fo["url"] not in ext_seen:
                out.forms.append(fo)
                tracer.log("found", fo["url"], f"form: {fo['platform']}", context=fo["context"])

        if depth >= settings.max_depth:
            continue

        links = getattr(r, "links", {}) or {}
        internal_links = links.get("internal", []) or []
        external_links = links.get("external", []) or []
        clickables = extract_clickables(html, url)

        # Internal high-value targets → prioritized frontier.
        for l in internal_links + clickables:
            href = (l.get("href") or "").strip()
            text = (l.get("text") or "").strip()
            if not href or not href.lower().startswith("http"):
                continue
            cu = normalize_url(href)
            if cu in visited or not same_site(cu, start_url):
                continue
            s = score_link(cu, text)
            heapq.heappush(frontier, (-s, next(counter), cu, depth + 1))
            if s > 0:
                tracer.log("found", cu, f"score={s}", text=text[:60])

        # External links to known submission platforms → record (feat 4), don't crawl the site.
        for l in external_links + clickables:
            href = (l.get("href") or "").strip()
            plat = detect_submission_platform(href)
            if plat and href not in ext_seen:
                ext_seen.add(href)
                out.external_submissions.append(
                    {"url": href, "platform": plat, "text": (l.get("text") or "")[:80]}
                )
                tracer.log("found", href, f"external submission platform: {plat}")

    return out
