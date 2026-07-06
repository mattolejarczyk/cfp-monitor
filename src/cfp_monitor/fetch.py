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
_LAUNCHED = None  # (playwright, browser) — our own headed/headless Chromium
_CDP = None       # (playwright, browser) — attached real Chrome via CDP


def _resolve_cdp_ws(cdp_url: str) -> str:
    """Accept a ws:// endpoint directly, or resolve an http://host:port to Chrome's
    browser WebSocket URL via /json/version (avoids Playwright's trailing-slash 404)."""
    if cdp_url.startswith(("ws://", "wss://")):
        return cdp_url
    import json as _json, urllib.request
    data = _json.loads(urllib.request.urlopen(cdp_url.rstrip("/") + "/json/version", timeout=5).read())
    return data["webSocketDebuggerUrl"]


async def _get_launched_browser(headless: bool):
    global _LAUNCHED
    if _LAUNCHED is None:
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        _LAUNCHED = (pw, await pw.chromium.launch(headless=headless))
    return _LAUNCHED[1]


async def _get_cdp_browser(cdp_url: str):
    global _CDP
    if _CDP is None:
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        _CDP = (pw, await pw.chromium.connect_over_cdp(_resolve_cdp_ws(cdp_url)))
    return _CDP[1]


async def close_fallback_browser() -> None:
    """Disconnect/close fallback browsers at run end. For CDP we only DISCONNECT —
    never close the user's real Chrome."""
    global _LAUNCHED, _CDP
    if _LAUNCHED is not None:
        pw, browser = _LAUNCHED
        try:
            await browser.close()
        finally:
            await pw.stop()
        _LAUNCHED = None
    if _CDP is not None:
        pw, _ = _CDP
        await pw.stop()   # disconnect only; leave the real Chrome running
        _CDP = None


# CFP-relevant button text worth clicking through; skip anything transactional/destructive.
_CLICK_YES = "call for|speak|abstract|submit|proposal|present|nominat|award|entry|paper|poster|session|get involved|apply"
_CLICK_NO = "buy|register|pay|checkout|cart|login|log in|sign in|delete|logout|download|book now|ticket"


async def _click_through_buttons(page, base_url: str, tracer, limit: int = 3) -> list:
    """SPA / JS-only buttons reveal their target only on click. Click a few CFP-relevant
    buttons that have NO discoverable URL and capture where they go (new tab or same-page
    nav). Returns extra [{href,text}]. Bounded + guarded so it never runs away or submits."""
    from urllib.parse import urlparse
    try:
        cands = await page.evaluate(
            "() => {"
            f"  const yes=/({_CLICK_YES})/i, no=/({_CLICK_NO})/i;"
            "   const out=[]; let n=0;"
            "   for (const e of document.querySelectorAll('button,[role=button],input[type=button]')) {"
            "     const t=(e.textContent||e.value||'').trim();"
            "     const url=e.getAttribute('href')||e.getAttribute('data-href')||e.getAttribute('data-url')||e.getAttribute('formaction')||'';"
            "     const oc=e.getAttribute('onclick')||'';"
            "     if (yes.test(t) && !no.test(t) && !url && !/https?:|location|window\\.open/i.test(oc)) {"
            "       e.setAttribute('data-cfpx', n); out.push({i:n, t:t.slice(0,50)}); n++; }"
            "   } return out.slice(0,6); }")
    except Exception:
        return []
    found, base_host = [], (urlparse(base_url).hostname or "")
    for c in cands[:limit]:
        sel = f"[data-cfpx='{c['i']}']"
        try:
            popup = None
            try:
                async with page.context.expect_event("page", timeout=3500) as pinfo:
                    await page.click(sel, timeout=2500)
                popup = await pinfo.value
            except Exception:
                popup = None
            if popup:
                try:
                    await popup.wait_for_load_state("domcontentloaded", timeout=6000)
                    u = popup.url
                finally:
                    await popup.close()
                if u and u.startswith("http"):
                    found.append({"href": u, "text": c["t"]})
                continue
            await page.wait_for_timeout(1200)
            if page.url != base_url and (urlparse(page.url).hostname or "") == base_host:
                found.append({"href": page.url, "text": c["t"]})
                tracer.log("button", base_url, f"click-through -> {page.url[:60]}")
                try:
                    await page.go_back(timeout=6000)
                    await page.wait_for_timeout(600)
                except Exception:
                    break  # couldn't return; stop clicking on this page
        except Exception:
            continue
    return found


async def _render_with_consent(url: str, settings, tracer):
    """Render `url` in the shared fallback browser, dismiss consent, return
    (html, anchors, status, body_text). Under CDP, reuse the real signed-in context."""
    # CDP (real signed-in Chrome) ONLY for known hard-block domains (e.g. Reuters);
    # everything else uses our own launched browser (faster, proven).
    use_cdp = bool(getattr(settings, "cdp_url", None)) and _force_fallback_domain(url)
    if use_cdp:
        browser = await _get_cdp_browser(settings.cdp_url)
        if browser.contexts:
            ctx, own_ctx = browser.contexts[0], False   # reuse real signed-in context + cookies
        else:
            ctx, own_ctx = await browser.new_context(), True
    else:
        browser = await _get_launched_browser(settings.fallback_headless)
        ctx, own_ctx = await browser.new_context(), True
    page = await ctx.new_page()
    try:
        resp = await page.goto(url, wait_until="domcontentloaded",
                               timeout=int(settings.fallback_render_timeout_s * 1000))
        status = resp.status if resp else None
        # Dismiss cookie-consent FAST: one JS check for which known selectors are present,
        # then click only those. Avoids 8 x 2.5s sequential waits on sites with no popup
        # (that waste was ~20s/render and could blow the per-site budget on multi-page sites).
        try:
            present = await page.evaluate("(sels) => sels.filter(s => document.querySelector(s))",
                                          list(_CONSENT_SELECTORS))
            for sel in present:
                try:
                    await page.click(sel, timeout=2000)
                    tracer.log("consent", url, f"clicked {sel}")
                    break
                except Exception:
                    continue
        except Exception:
            pass
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
        # SPA / JS-only buttons: click a few CFP-relevant ones with no URL to reveal targets.
        try:
            anchors = anchors + await _click_through_buttons(page, url, tracer)
        except Exception:
            pass
        return html, anchors, status, body_text
    finally:
        await page.close()
        if own_ctx:
            await ctx.close()


# Few internal links means exploration will stall - a JS-shell signal that a high char count
# can MASK (a shell can carry boilerplate text but ~0 navigable links). "Rich" = enough links.
_RICH_LINKS = 5


def _richness(pf: "PageFetch") -> int:
    return len(pf.markdown.strip()) + 60 * len(pf.links.get("internal", []))


def _is_rich(pf: "PageFetch") -> bool:
    return len(pf.links.get("internal", [])) >= _RICH_LINKS


async def _fallback_fetch(crawler, url: str, settings, tracer, forced: bool = False) -> PageFetch:
    """Render with our own Playwright (or CDP for hard domains): consent dismissal +
    button click-through, then hand the HTML to crawl4ai raw:// for markdown."""
    tracer.log("fallback", url, "playwright render" + (" (forced)" if forced else ""))
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


async def fetch_page(crawler, url: str, cfg, settings, tracer, force_fallback: bool = False) -> PageFetch:
    """crawl4ai first; Playwright fallback when crawl4ai is blocked, a known hard-block
    domain, forced, OR returns a thin/link-poor page (a JS shell) - in which case we render
    and keep whichever of the two is richer. force_fallback=True skips crawl4ai entirely."""
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
            c4 = PageFetch(url, True, getattr(r, "status_code", None),
                           str(getattr(r, "html", "") or ""), str(getattr(r, "markdown", "") or ""),
                           links, via="crawl4ai")
            if not settings.playwright_fallback or _is_rich(c4):
                return c4
            # Thin / link-poor (JS shell): render it and keep whichever is richer. The render
            # is bounded by fallback_render_timeout_s so it can't blow the site budget.
            fb = await _fallback_fetch(crawler, url, settings, tracer)
            if fb.success and _richness(fb) > _richness(c4):
                tracer.log("fallback", url, f"thin crawl4ai -> richer render "
                           f"({len(fb.markdown)}c/{len(fb.links.get('internal', []))}L vs "
                           f"{len(c4.markdown)}c/{len(c4.links.get('internal', []))}L)")
                return fb
            return c4

    if not settings.playwright_fallback:
        return PageFetch(url, False, getattr(r, "status_code", None))
    return await _fallback_fetch(crawler, url, settings, tracer, forced=force_fallback)
