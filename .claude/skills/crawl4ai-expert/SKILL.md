---
name: crawl4ai-expert
description: >-
  Expert guidance for building web crawling and extraction solutions with
  crawl4ai (unclecode/crawl4ai). Use this whenever writing code that crawls,
  explores, or extracts data from websites — especially agentic multi-page
  exploration, relevance-scored deep crawling, budget/boundary control, and
  LLM-based structured extraction. Read this BEFORE writing crawl4ai code so you
  use its native machinery instead of hand-rolling (and hallucinating) a crawler.
---

# crawl4ai expert

crawl4ai is a batteries-included async crawler built for LLM pipelines. The #1
mistake agents make is **hand-rolling** link-following, scoring, and budget logic.
Don't. crawl4ai already ships: relevance-prioritized deep crawling, keyword
scorers, filter chains, fast prefetch discovery, and provider-agnostic LLM
extraction. Configure those; don't reinvent them.

## Mental model (read first)
- One object does the work: `AsyncWebCrawler`. You call `arun(url, config=...)`.
- **All behavior lives in `CrawlerRunConfig`** — extraction, deep-crawl strategy,
  scraping strategy, caching. Do NOT pass strategies directly to `arun()`.
- Deep crawling is a *strategy* you attach to the config. Pick one:
  - `BestFirstCrawlingStrategy` — **default choice.** Visits highest-scoring URLs
    first (needs a scorer; use `stream=True`).
  - `BFSDeepCrawlStrategy` / `DFSDeepCrawlStrategy` — breadth/depth first; support
    `score_threshold` to prune.
- Result objects carry everything: `result.url`, `result.success`, `result.status_code`,
  `result.markdown`, `result.links` (`{"internal":[...], "external":[...]}`),
  `result.html`/`result.cleaned_html`, `result.metadata` (`depth`, `score`),
  `result.extracted_content` (JSON string when an extraction strategy ran).

## Install (Python 3.10+)
```bash
uv add crawl4ai            # or: pip install crawl4ai
crawl4ai-setup            # installs the Playwright/Chromium browser it drives
```

## Verified API cheat-sheet

### Simple crawl → clean markdown
```python
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
async with AsyncWebCrawler() as crawler:
    r = await crawler.arun("https://example.com",
                           config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS))
    if r.success:
        print(r.markdown)              # LLM-ready markdown
        print(r.links["internal"])     # [{"href","text",...}, ...]
```

### Fast URL/link discovery (prefetch) — 5–10x faster, no markdown/extraction
```python
cfg = CrawlerRunConfig(prefetch=True)
r = await crawler.arun(start_url, config=cfg)
internal = [l["href"] for l in r.links.get("internal", [])]
```
Use this for a **two-phase crawl**: prefetch to map the site, filter to the URLs
you care about, then full-crawl only those.

### Relevance-scored deep crawl (the workhorse)
```python
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
from crawl4ai.deep_crawling.filters import FilterChain, DomainFilter, URLPatternFilter, ContentTypeFilter

scorer = KeywordRelevanceScorer(keywords=["submit","call for papers","speaker"], weight=1.0)
filters = FilterChain([
    DomainFilter(allowed_domains=["conf.example.com"]),  # stay on-site
    ContentTypeFilter(allowed_types=["text/html"]),
])
cfg = CrawlerRunConfig(
    deep_crawl_strategy=BestFirstCrawlingStrategy(
        max_depth=2, include_external=False, max_pages=25,
        url_scorer=scorer, filter_chain=filters),
    stream=True,                       # recommended with BestFirst
    cache_mode=CacheMode.BYPASS,
)
async for r in await crawler.arun(start_url, config=cfg):   # note: `async for` in stream mode
    print(r.metadata.get("depth"), r.metadata.get("score"), r.url)
```
Budget/boundary knobs: `max_pages` (hard cap), `max_depth`, `score_threshold`
(BFS/DFS only), `include_external=False`, `DomainFilter`.

### LLM structured extraction (provider-agnostic via LiteLLM)
```python
from pydantic import BaseModel
from crawl4ai import LLMConfig, LLMExtractionStrategy

class Fields(BaseModel):
    name: str | None
    dates: str | None

strategy = LLMExtractionStrategy(
    llm_config=LLMConfig(provider="openrouter/deepseek/deepseek-chat",
                         api_token=OPENROUTER_KEY),
    schema=Fields.model_json_schema(),
    extraction_type="schema",
    instruction="Extract the fields as JSON. Use null when not present; never guess.",
    input_format="markdown",           # or "html" / "fit_markdown"
    apply_chunking=True, chunk_token_threshold=1200,
    extra_args={"temperature": 0.0, "max_tokens": 1200},
)
cfg = CrawlerRunConfig(extraction_strategy=strategy, cache_mode=CacheMode.BYPASS)
r = await crawler.arun(url, config=cfg)
import json; data = json.loads(r.extracted_content) if r.success else None
```
- Provider strings are LiteLLM: `openai/gpt-4o-mini`, `openrouter/<model>`,
  `ollama/<model>`, `anthropic/claude-...`. For OpenRouter set `api_token` to the
  `sk-or-...` key. `strategy.show_usage()` prints token cost.
- LLM extraction is **slower + costs tokens** — run it only on high-value pages,
  after you've narrowed the set with prefetch + scoring.

## Gotchas (these are why agents fail)
1. Strategies go in `CrawlerRunConfig`, never as `arun()` kwargs.
2. In **stream mode** `arun()` returns an async iterator → use `async for r in await crawler.arun(...)`. Non-stream returns a list.
3. `BestFirstCrawlingStrategy` needs a `url_scorer`; don't set `score_threshold` on it (it orders by score already).
4. Always check `result.success` / `result.status_code` before using content.
5. `max_depth > 3` explodes the frontier — always pair with `max_pages`.
6. robots.txt is disabled by default; enable respect explicitly if required.
7. Reuse ONE `AsyncWebCrawler` (browser) across many URLs; don't spin one per page.
8. `arun_many([...])` crawls a list concurrently; deep-crawl a single entry URL instead when you want exploration.
9. For "buttons"/CTAs that aren't `<a>` tags, parse `result.cleaned_html` for `button`, `[role=button]`, and nav text — `result.links` only has anchors.

See `reference/patterns.md` for longer, copy-ready recipes and the full result schema.
