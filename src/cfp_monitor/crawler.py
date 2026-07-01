"""Relevance-prioritized internal crawling (feat 2, 5, 11).

Uses crawl4ai's native BestFirstCrawlingStrategy — it explores the site, scores
each discovered URL with our CFP keyword scorer, stays on-site, and honours the
page/depth budget. We just collect the pages it returns (with depth + score) for
extraction.
"""
from __future__ import annotations

from dataclasses import dataclass

from .scoring import build_scorer, build_filter_chain, normalize_url
from .trace import Tracer


@dataclass
class CrawledPage:
    url: str
    markdown: str
    depth: int
    score: float


async def deep_crawl(crawler, start_url: str, settings, tracer: Tracer) -> list[CrawledPage]:
    from crawl4ai import CrawlerRunConfig, CacheMode
    from crawl4ai.deep_crawling import BestFirstCrawlingStrategy

    strategy = BestFirstCrawlingStrategy(
        max_depth=settings.max_depth,
        max_pages=settings.max_pages,
        include_external=settings.include_external,
        url_scorer=build_scorer(),
        filter_chain=build_filter_chain(start_url),
    )
    cfg = CrawlerRunConfig(
        deep_crawl_strategy=strategy,
        stream=True,
        cache_mode=CacheMode.BYPASS,
        verbose=settings.verbose,
    )

    pages: list[CrawledPage] = []
    seen: set[str] = set()
    try:
        async for r in await crawler.arun(start_url, config=cfg):
            if not r:
                continue
            meta = getattr(r, "metadata", {}) or {}
            depth = int(meta.get("depth", 0) or 0)
            score = float(meta.get("score", 0.0) or 0.0)
            if getattr(r, "success", False):
                nu = normalize_url(r.url)
                if nu in seen:
                    continue
                seen.add(nu)
                pages.append(CrawledPage(nu, str(getattr(r, "markdown", "") or ""), depth, score))
                tracer.log("crawled", r.url, f"depth={depth} score={score:.2f}")
            else:
                tracer.log(
                    "skipped",
                    getattr(r, "url", ""),
                    f"status={getattr(r, 'status_code', '?')} depth={depth}",
                )
    except Exception as e:
        tracer.log("error", start_url, f"deep_crawl raised: {e}")
    return pages
