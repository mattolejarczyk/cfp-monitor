# crawl4ai — copy-ready patterns & result schema

Longer recipes referenced by `SKILL.md`. All assume:
```python
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig, CacheMode
```

## Result object schema (what you get back)
| attribute | meaning |
| --- | --- |
| `result.url` | final URL (after redirects) |
| `result.success` | bool — check this first |
| `result.status_code` | HTTP status |
| `result.error_message` | populated on failure |
| `result.markdown` | LLM-ready markdown (str-like; also `.raw_markdown`, `.fit_markdown`) |
| `result.links` | `{"internal": [{"href","text",...}], "external": [...]}` |
| `result.html` / `result.cleaned_html` | raw / sanitized HTML |
| `result.media` | images/videos/audio dicts |
| `result.metadata` | includes `depth` and `score` during deep crawl |
| `result.extracted_content` | JSON string when an extraction strategy ran |

## Two-phase crawl (fast discover → selective extract)
```python
async with AsyncWebCrawler(config=BrowserConfig(headless=True)) as crawler:
    disc = await crawler.arun(start_url, config=CrawlerRunConfig(prefetch=True))
    urls = [l["href"] for l in disc.links.get("internal", [])]
    keep = [u for u in urls if any(k in u.lower() for k in ("cfp","call-for","speak","submit"))]
    for u in keep:
        r = await crawler.arun(u, config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS))
        if r.success:
            ...  # process r.markdown
```

## Deep crawl, collect with depth+score, cap the budget
```python
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer

cfg = CrawlerRunConfig(
    deep_crawl_strategy=BestFirstCrawlingStrategy(
        max_depth=2, max_pages=20, include_external=False,
        url_scorer=KeywordRelevanceScorer(keywords=[...], weight=1.0)),
    stream=True, cache_mode=CacheMode.BYPASS)

pages = []
async for r in await crawler.arun(start_url, config=cfg):
    if r.success:
        pages.append({"url": r.url, "depth": r.metadata.get("depth"),
                      "score": r.metadata.get("score"), "markdown": str(r.markdown)})
```

## Filters you'll actually use
```python
from crawl4ai.deep_crawling.filters import (
    FilterChain, DomainFilter, URLPatternFilter, ContentTypeFilter, ContentRelevanceFilter)

FilterChain([
    DomainFilter(allowed_domains=["conf.example.com"]),      # never leave the site
    URLPatternFilter(patterns=["*cfp*","*speak*","*submit*","*call-for*","*program*"]),
    ContentTypeFilter(allowed_types=["text/html"]),
])
```
`ContentRelevanceFilter(query="call for papers speaker submission", threshold=0.5)` is
a BM25 content filter (checks the page, not just the URL) — heavier but precise.

## LLM extraction against OpenRouter (cheap model)
```python
from crawl4ai import LLMConfig, LLMExtractionStrategy
LLMExtractionStrategy(
    llm_config=LLMConfig(provider="openrouter/deepseek/deepseek-chat", api_token=OR_KEY),
    schema=MyModel.model_json_schema(), extraction_type="schema",
    instruction="Extract fields as strict JSON. null when absent. Never invent dates.",
    input_format="markdown", apply_chunking=True, chunk_token_threshold=1400,
    extra_args={"temperature": 0.0, "max_tokens": 1400})
```

## Reliability checklist
- Wrap crawls in try/except; a single bad page shouldn't kill the run.
- Dedupe URLs (normalize trailing slash, strip `#fragment`, drop query noise).
- Cap everything: `max_pages`, `max_depth`, a wall-clock timeout per site.
- Log every decision (found / scored / crawled / skipped + why) for debuggability.
- Treat missing data as **unknown**, not false. Don't let the LLM guess.

## Popups, consent walls & anti-bot (crawl4ai 0.9.0 — verified 2026-07-03)
Conference sites routinely block crawls with a GDPR "Manage Consent" (IAB TCF/CMP)
modal + promo overlays; some serve hard anti-bot challenges. Native levers, in
increasing order of reach — try in this order:

1. `CrawlerRunConfig(remove_consent_popups=True, remove_overlay_elements=True)` —
   removes CMP consent modals + generic overlays BEFORE extraction. Cheap, safe,
   enable by default. (There is a dedicated `remove_consent_popups(page)` routine.)
2. `CrawlerRunConfig(magic=True)` — broader auto-overlay handling; heavier / less predictable.
3. `BrowserConfig(enable_stealth=True)` — playwright-stealth patches (navigator.webdriver
   etc.). Beats *basic* bot detection. Needs the `playwright_stealth` package.
4. `UndetectedAdapter` (exported from `crawl4ai`) — stronger undetected-browser mode.
   NOTE: cannot be combined with `enable_stealth`.
5. `BrowserConfig(browser_mode="cdp", cdp_url="ws://localhost:9222/...")` — drive a REAL,
   already-running Chrome via CDP. Most reliable for hard anti-bot because it IS a real
   browser; matches the "local desktop app / you'll see the browser" model.

**Verified gotcha:** some sites (e.g. ALJ Group / `ushydrogenforum.com`) return HTTP 200
with a **bodyless ~24KB anti-bot shell**; crawl4ai reports `success=False,
error="Blocked by anti-bot protection: Structural: no <body> tag"`. `remove_*_popups` +
`magic` + `enable_stealth` (headless AND headed) ALL still fail on it. For that hard
class, escalate to `UndetectedAdapter` or CDP-to-real-Chrome — do not burn time on
stealth flags.
