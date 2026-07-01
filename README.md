# CFP Monitor

Agentic **Conference / Event Call-for-Papers monitor** built on
[crawl4ai](https://github.com/unclecode/crawl4ai). Give it a fixed list of
conference URLs; for each one it explores the site, finds speaking/submission
opportunities, extracts the key facts (what/when/where, CFP status, deadlines,
where to submit), and returns a single **evidence-backed, machine-readable**
result — clearly separating confirmed facts from unknowns.

It ships with a reusable **crawl4ai expert Skill** (`.claude/skills/crawl4ai-expert/`)
so coding agents build crawl4ai solutions correctly instead of hand-rolling a crawler.

## Why it's reliable
Half the work is *configuration of crawl4ai's native machinery*, not custom code:
- **Exploration + prioritization** → `BestFirstCrawlingStrategy` + `KeywordRelevanceScorer`
- **Boundaries + budget** → `DomainFilter`, `max_pages`, `max_depth`, per-site timeout
- **Structured extraction** → `LLMExtractionStrategy` / LiteLLM against a cheap model
- **Evidence + honesty** → every fact carries source URL + snippet; missing data is
  `unknown`, never guessed.

## Architecture (modular — feat 15)
```
src/cfp_monitor/
  config.py       settings + budget/boundary knobs
  keywords.py     CFP/speaking vocabulary + submission-platform registry
  models.py       pydantic schemas (per-page extraction + consolidated result)
  scoring.py      crawl4ai scorer/filters + link/button relevance + URL utils
  discovery.py    main-page fetch + link/button/CTA discovery (feat 3,4,9)
  crawler.py      BestFirst deep crawl within budget (feat 2,5,11)
  extraction.py   LLM structured extraction per page (feat 4,6,7,8,9,12)
  consolidate.py  merge → one evidence-backed result (feat 10,12,13)
  trace.py        debuggable crawl-decision log (feat 14)
  pipeline.py     the core crawl loop (orchestration)
app.py            Streamlit UI
run.py            CLI
```

## Setup
```bash
uv sync                     # or: pip install -e .
crawl4ai-setup              # installs the Chromium browser crawl4ai drives
cp .env.example .env        # then add your OPENROUTER_API_KEY
```

## Run

**UI:**
```bash
streamlit run app.py
```
Paste your conference URLs, tune the budget, Run. Each result shows the CFP
verdict, the facts + confidence, the evidence (source URL + snippet), and the full
crawl decision trace.

**CLI:**
```bash
python run.py examples/urls.txt -o results.json
python run.py https://conf.example.com --max-pages 15
```

**As a library:**
```python
import asyncio
from src.cfp_monitor import run_urls, Settings

results = asyncio.run(run_urls(["https://conf.example.com"], Settings()))
print(results[0].model_dump_json(indent=2))
```

## Output shape (per conference)
```jsonc
{
  "start_url": "...",
  "name":            {"value": "...", "confidence": "confirmed", "evidence": [...]},
  "conference_dates":{"value": "...", "confidence": "confirmed", "evidence": [...]},
  "location":        {"value": "...", "confidence": "unknown",   "evidence": []},
  "has_cfp": true,
  "cfp_status": "open",            // open | closed | upcoming | unclear | none
  "cfp_close_date":  {"value": "...", "confidence": "confirmed", "evidence": [...]},
  "submission_url":  {"value": "https://sessionize.com/...", "confidence": "confirmed", "evidence": [...]},
  "submission_platform": "Sessionize",
  "evidence": [ {"field": "...", "source_url": "...", "snippet": "..."} ],
  "pages_crawled": 9, "pages_skipped": 2,
  "trace": [ {"action": "found|scored|crawled|skipped|extracted|consolidated", "url": "...", "reason": "..."} ]
}
```
Designed so a downstream agent can score, monitor, or automate on it directly.

## Configuration
All knobs live in `.env` (see `.env.example`) or `Settings`. Key ones: `CFP_MAX_PAGES`,
`CFP_MAX_DEPTH`, `CFP_MAX_EXTRACT_PAGES`, `CFP_SITE_TIMEOUT_S`, `CFP_LLM_PROVIDER`
(any LiteLLM provider — OpenRouter, OpenAI, or a local `ollama/*` model for $0).

## The crawl4ai Skill
`.claude/skills/crawl4ai-expert/` is a self-contained Claude Agent Skill: the verified
current API, copy-ready recipes, and the gotchas that make agents fail. Open this repo
in Claude Code (or point any agent at `SKILL.md`) to build crawl4ai features correctly.
