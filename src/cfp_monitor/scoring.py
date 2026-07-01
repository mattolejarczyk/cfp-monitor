"""Relevance scoring + URL utilities (feat 3, 4, 11).

Two jobs:
1. Build the crawl4ai scorer + filter chain that steer the deep crawl toward
   CFP/speaking pages and keep it on-site.
2. Our own lightweight link/button classifier used during prefetch discovery to
   rank clickable targets before we decide what to crawl.
"""
from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from .keywords import (
    CFP_KEYWORDS,
    CONTEXT_KEYWORDS,
    CFP_URL_HINTS,
    SUBMISSION_PLATFORMS,
)


# ---- URL helpers ------------------------------------------------------------
def normalize_url(url: str) -> str:
    """Drop fragments and trailing slashes so we don't crawl the same page twice."""
    try:
        p = urlparse(url.strip())
        path = p.path.rstrip("/") or "/"
        return urlunparse((p.scheme, p.netloc.lower(), path, "", p.query, "")).rstrip("/")
    except Exception:
        return url.strip()


def registrable_domain(url: str) -> str:
    """Best-effort eTLD+1 without extra deps. Good enough to keep crawls on-site."""
    host = urlparse(url).netloc.lower().split(":")[0]
    parts = [p for p in host.split(".") if p]
    if len(parts) <= 2:
        return host
    # handle common two-label public suffixes (co.uk, com.au, org.uk, ...)
    two_label = {"co", "com", "org", "net", "gov", "ac", "edu"}
    if parts[-2] in two_label and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def same_site(url: str, start_url: str) -> bool:
    return registrable_domain(url) == registrable_domain(start_url)


def detect_submission_platform(url: str) -> str | None:
    """Return a friendly platform name if the URL points at a known CFP platform."""
    low = url.lower()
    for host, name in SUBMISSION_PLATFORMS.items():
        if host in low:
            return name
    return None


# ---- Our link/button relevance score (0.0 .. ~1.0) --------------------------
def score_link(href: str, text: str = "") -> float:
    """Heuristic CFP relevance for a discovered link/button. Higher = more relevant."""
    href_l = (href or "").lower()
    text_l = (text or "").lower()
    score = 0.0
    for kw in CFP_KEYWORDS:
        if kw in text_l:
            score += 0.6
        if kw.replace(" ", "-") in href_l or kw.replace(" ", "") in href_l:
            score += 0.5
    for kw in CONTEXT_KEYWORDS:
        if kw in text_l:
            score += 0.25
    for hint in CFP_URL_HINTS:
        if hint in href_l:
            score += 0.35
    if detect_submission_platform(href_l):
        score += 1.0
    return round(min(score, 3.0), 3)


# ---- crawl4ai strategy pieces (imported lazily) -----------------------------
def build_scorer(weight: float = 1.0):
    from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer

    return KeywordRelevanceScorer(keywords=CFP_KEYWORDS + CONTEXT_KEYWORDS, weight=weight)


def build_filter_chain(start_url: str):
    """Stay on the conference site and only follow HTML pages."""
    from crawl4ai.deep_crawling.filters import (
        FilterChain,
        DomainFilter,
        ContentTypeFilter,
    )

    return FilterChain(
        [
            DomainFilter(allowed_domains=[registrable_domain(start_url)]),
            ContentTypeFilter(allowed_types=["text/html"]),
        ]
    )
