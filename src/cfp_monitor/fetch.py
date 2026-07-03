"""Resilient page fetch: crawl4ai first, our own Playwright as fallback.

crawl4ai's browser sometimes captures a slow JS site's early loading shell, and its
anti-bot detector then false-flags "no <body>" (verified on Complianz/WordPress
conference sites, e.g. ushydrogenforum.com — raw Playwright loads the full page fine).
For those we render with our OWN Playwright, dismiss the cookie-consent banner (the real
blocker), wait for content, then hand the rendered HTML to crawl4ai (`raw://`, which skips
the anti-bot check) for markdown. Links are classified in Python (unit-testable).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

# One-click "accept" selectors across common consent platforms (try in order).
_CONSENT_SELECTORS = (
    ".cmplz-accept",                       # Complianz (WordPress)
    "#onetrust-accept-btn-handler",        # OneTrust
    ".cc-allow", ".cc-dismiss",            # Cookie Consent / Osano
    "#cookie-accept", ".cookie-accept",
    "[aria-label='Accept all']", "[aria-label='Accept']",
)
# Generic fallback: click any accept-ish control + close obvious overlay X's.
_ACCEPT_JS = r"""
() => {
  const wants = t => /^\s*(accept|accept all|accept cookies|allow all|i accept|agree|got it|ok)\s*$/i.test(t||'');
  for (const e of document.querySelectorAll('button,a,[role=button],input[type=button],input[type=submit]')) {
    if (wants(e.textContent) || wants(e.value)) { try { e.click(); } catch(_){} }
  }
  for (const x of document.querySelectorAll('[aria-label="Close"],.pum-close,.modal-close,.close,button.close')) {
    try { x.click(); } catch(_){}
  }
}
"""


def _host(u: str) -> str:
    try:
        h = (urlparse(u).hostname or "").lower()
    except Exception:
        return ""
    return h[4:] if h.startswith("www.") else h


def classify_links(anchors, page_url: str) -> dict:
    """Split [{href,text}] into internal/external by host vs page_url. Pure + testable.
    Ignores non-http(s) hrefs and dedupes."""
    base = _host(page_url)
    out = {"internal": [], "external": []}
    seen = set()
    for a in anchors or []:
        href = (a.get("href") or "").strip()
        if not href.lower().startswith(("http://", "https://")) or href in seen:
            continue
        seen.add(href)
        bucket = "internal" if _host(href) == base else "external"
        out[bucket].append({"href": href, "text": (a.get("text") or "").strip()[:80]})
    return out


@dataclass
class PageFetch:
    url: str
    success: bool
    status_code: Optional[int]
    html: str = ""
    markdown: str = ""
    links: dict = field(default_factory=lambda: {"internal": [], "external": []})
    via: str = "crawl4ai"   # or "playwright-fallback"


# Below this much markdown, treat crawl4ai's result as an empty shell / false success.
_MIN_MARKDOWN = 200


def _looks_blocked(r) -> bool:
    if r is None or not getattr(r, "success", False):
        return True
    return len(str(getattr(r, "markdown", "") or "").strip()) < _MIN_MARKDOWN


async def _render_with_consent(url: str, settings, tracer):
    """Render `url` in our own Playwright, dismiss consent, return (html, anchors, status)."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=settings.playwright_headless)
        try:
            page = await (await browser.new_context()).new_page()
            resp = await page.goto(url, wait_until="domcontentloaded",
                                   timeout=int(settings.per_site_timeout_s * 1000))
            status = resp.status if resp else None
            # Dismiss cookie-consent: known selectors first, then a generic text click.
            for sel in _CONSENT_SELECTORS:
                try:
                    await page.wait_for_selector(sel, state="visible", timeout=2500)
                    await page.click(sel, timeout=3000)
                    tracer.log("consent", url, f"clicked {sel}")
                    break
                except Exception:
                    continue
            try:
                await page.evaluate(_ACCEPT_JS)
            except Exception:
                pass
            # Let content settle after consent (the render lag that fools crawl4ai).
            await page.wait_for_timeout(int(settings.fallback_wait_s * 1000))
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            html = await page.content()
            anchors = await page.evaluate(
                "() => [...document.querySelectorAll('a[href]')]"
                ".map(a => ({href: a.href, text: (a.textContent||'').trim()}))")
            return html, anchors, status
        finally:
            await browser.close()


async def fetch_page(crawler, url: str, cfg, settings, tracer) -> PageFetch:
    """crawl4ai first; Playwright fallback when it looks blocked/false-positived."""
    r = None
    try:
        r = await crawler.arun(url, config=cfg)
    except Exception as e:
        tracer.log("skipped", url, f"crawl4ai raised: {e}")

    if not _looks_blocked(r):
        links = getattr(r, "links", None) or {"internal": [], "external": []}
        return PageFetch(url, True, getattr(r, "status_code", None),
                         str(getattr(r, "html", "") or ""), str(getattr(r, "markdown", "") or ""),
                         links, via="crawl4ai")

    if not settings.playwright_fallback:
        return PageFetch(url, False, getattr(r, "status_code", None))

    tracer.log("fallback", url, f"crawl4ai weak (status={getattr(r,'status_code','?')}) -> playwright render")
    try:
        html, anchors, status = await _render_with_consent(url, settings, tracer)
    except Exception as e:
        tracer.log("skipped", url, f"playwright fallback failed: {e}")
        return PageFetch(url, False, None, via="playwright-fallback")

    # Rendered HTML -> markdown via crawl4ai raw:// (local content, anti-bot check skipped).
    md = ""
    try:
        from crawl4ai import CrawlerRunConfig, CacheMode
        r2 = await crawler.arun("raw://" + html,
                                config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS, verbose=settings.verbose))
        md = str(getattr(r2, "markdown", "") or "")
    except Exception as e:
        tracer.log("skipped", url, f"raw markdown gen failed: {e}")

    links = classify_links(anchors, url)
    ok = len(md.strip()) >= _MIN_MARKDOWN or bool(links["internal"])
    tracer.log("crawled", url, f"via playwright-fallback chars={len(md)} internal_links={len(links['internal'])}")
    return PageFetch(url, ok, status, html, md, links, via="playwright-fallback")
