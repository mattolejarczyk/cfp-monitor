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


# Domains that HARD-BLOCK automated requests: crawl4ai's headless hit gets a 403 that
# also poisons a subsequent render from the same IP (verified: Reuters Events). For these,
# skip crawl4ai and render (headed) FIRST so OUR request is the first contact. Extend as found.
_FALLBACK_FIRST_DOMAINS = ("reutersevents.com",)


def _host(u: str) -> str:
    try:
        h = (urlparse(u).hostname or "").lower()
    except Exception:
        return ""
    return h[4:] if h.startswith("www.") else h


def _force_fallback_domain(url: str) -> bool:
    h = _host(url)
    return any(h == d or h.endswith("." + d) for d in _FALLBACK_FIRST_DOMAINS)


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


# --- Shared fallback browser: launched ONCE per run and reused across pages (perf).
# A fresh context per page keeps sites isolated. Headless browsers get 403'd by some
# platforms (Reuters Events), so the fallback runs headed by default (settings). ---
_FALLBACK = None  # tuple[playwright, browser, is_cdp] | None


def _resolve_cdp_ws(cdp_url: str) -> str:
    """Accept a ws:// endpoint directly, or resolve an http://host:port to Chrome's
    browser WebSocket URL via /json/version (avoids Playwright's trailing-slash 404)."""
    if cdp_url.startswith(("ws://", "wss://")):
        return cdp_url
    import json as _json, urllib.request
    data = _json.loads(urllib.request.urlopen(cdp_url.rstrip("/") + "/json/version", timeout=5).read())
    return data["webSocketDebuggerUrl"]


async def _get_fallback_browser(settings):
    """Shared fallback browser. If settings.cdp_url is set, ATTACH to a real running
    Chrome via CDP (no automation fingerprint — beats IP-reputation anti-bot); otherwise
    launch our own."""
    global _FALLBACK
    if _FALLBACK is None:
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        cdp = getattr(settings, "cdp_url", None)
        if cdp:
            browser = await pw.chromium.connect_over_cdp(_resolve_cdp_ws(cdp))
            _FALLBACK = (pw, browser, True)
        else:
            browser = await pw.chromium.launch(headless=settings.fallback_headless)
            _FALLBACK = (pw, browser, False)
    return _FALLBACK[1]


async def close_fallback_browser() -> None:
    """Disconnect/close the shared fallback browser at run end. For CDP we only
    disconnect — never close the user's real Chrome."""
    global _FALLBACK
    if _FALLBACK is not None:
        pw, browser, is_cdp = _FALLBACK
        try:
            if not is_cdp:
                await browser.close()
        finally:
            await pw.stop()
        _FALLBACK = None


async def _render_with_consent(url: str, settings, tracer):
    """Render `url` in the shared fallback browser, dismiss consent, return
    (html, anchors, status, body_text). Under CDP, reuse the real signed-in context."""
    browser = await _get_fallback_browser(settings)
    is_cdp = bool(_FALLBACK and _FALLBACK[2])
    if is_cdp and browser.contexts:
        ctx, own_ctx = browser.contexts[0], False   # reuse the real (signed-in) context + cookies
    else:
        ctx, own_ctx = await browser.new_context(), True
    page = await ctx.new_page()
    try:
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
        body_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        anchors = await page.evaluate(
            "() => [...document.querySelectorAll('a[href]')]"
            ".map(a => ({href: a.href, text: (a.textContent||'').trim()}))")
        return html, anchors, status, body_text
    finally:
        await page.close()
        if own_ctx:
            await ctx.close()


async def fetch_page(crawler, url: str, cfg, settings, tracer, force_fallback: bool = False) -> PageFetch:
    """crawl4ai first; Playwright fallback when it looks blocked/false-positived.

    `force_fallback=True` skips the crawl4ai attempt entirely — used for later pages of a
    site whose start page already needed the fallback, so we don't waste 20-60s per page
    letting crawl4ai fail again."""
    if _force_fallback_domain(url):
        force_fallback = True   # known hard-block platform: don't let crawl4ai poison the IP
    r = None
    if not force_fallback:
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

    tracer.log("fallback", url, "playwright render" + (" (forced)" if force_fallback else ""))
    try:
        html, anchors, status, body_text = await _render_with_consent(url, settings, tracer)
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
    # SPA safety net: if markdown came back thin, use the rendered visible text.
    if len(md.strip()) < _MIN_MARKDOWN and body_text and len(body_text.strip()) >= _MIN_MARKDOWN:
        md = body_text

    links = classify_links(anchors, url)
    ok = len(md.strip()) >= _MIN_MARKDOWN or bool(links["internal"])
    tracer.log("crawled", url, f"via playwright-fallback chars={len(md)} internal_links={len(links['internal'])}")
    return PageFetch(url, ok, status, html, md, links, via="playwright-fallback")
