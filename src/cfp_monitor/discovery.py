"""Main-page fetch + link/button/CTA discovery (feat 3, 4, 9).

Fetches the starting page once (full crawl → we get markdown for main-page
extraction AND the links), then harvests every clickable target — anchors, nav
items, and button/CTA elements — scores them for CFP relevance, and flags links to
known external submission platforms.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin

from .scoring import normalize_url, same_site, score_link, detect_submission_platform
from .trace import Tracer


@dataclass
class Candidate:
    url: str
    text: str
    score: float


@dataclass
class Discovery:
    start_url: str
    start_markdown: str = ""
    start_html: str = ""
    ok: bool = False
    candidates: list[Candidate] = field(default_factory=list)      # ranked, on-site
    submission_links: list[dict] = field(default_factory=list)     # [{url, platform, text}]


def _extract_clickables(html: str, base_url: str) -> list[dict]:
    """Anchors + nav items + role=button / <button> elements, as {href, text}."""
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return []
    try:
        soup = BeautifulSoup(html or "", "html.parser")
    except Exception:
        return []
    out: list[dict] = []
    for el in soup.select("a[href], [role=button], button"):
        text = el.get_text(" ", strip=True)
        href = el.get("href") or el.get("data-href") or el.get("data-url")
        if href:
            out.append({"href": urljoin(base_url, href), "text": text})
    return out


async def discover(crawler, start_url: str, settings, tracer: Tracer) -> Discovery:
    from crawl4ai import CrawlerRunConfig, CacheMode

    cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, verbose=settings.verbose)
    try:
        r = await crawler.arun(start_url, config=cfg)
    except Exception as e:
        tracer.log("error", start_url, f"start fetch raised: {e}")
        return Discovery(start_url)

    if not r or not getattr(r, "success", False):
        tracer.log("error", start_url, f"start page failed: {getattr(r, 'error_message', '')}")
        return Discovery(start_url)

    md = str(getattr(r, "markdown", "") or "")
    html = getattr(r, "html", "") or ""
    links = getattr(r, "links", {}) or {}
    internal = links.get("internal", []) or []
    external = links.get("external", []) or []
    clickables = _extract_clickables(html, start_url)

    seen = {normalize_url(start_url)}
    candidates: list[Candidate] = []
    for l in internal + clickables:
        href = (l.get("href") or "").strip()
        text = (l.get("text") or "").strip()
        if not href or not href.lower().startswith("http"):
            continue
        nu = normalize_url(href)
        if nu in seen or not same_site(nu, start_url):
            continue
        seen.add(nu)
        sc = score_link(nu, text)
        candidates.append(Candidate(nu, text[:120], sc))
        tracer.log("found", nu, f"score={sc}", text=text[:60])

    candidates.sort(key=lambda c: c.score, reverse=True)

    submission_links: list[dict] = []
    seen_sub = set()
    for l in internal + external:
        href = (l.get("href") or "").strip()
        plat = detect_submission_platform(href)
        if plat and href not in seen_sub:
            seen_sub.add(href)
            submission_links.append({"url": href, "platform": plat, "text": (l.get("text") or "")[:80]})
            tracer.log("found", href, f"submission platform: {plat}")

    tracer.log("crawled", start_url, "start page", chars=len(md), links=len(internal))
    return Discovery(start_url, md, html, True, candidates, submission_links)
