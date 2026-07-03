# Extraction Model Benchmarking and Multi-Page Protocol

Session learning from free OpenRouter extraction benchmark work.

## Why this exists

PR Monitor must minimize extraction cost while preserving accuracy. Benchmark free OpenRouter models first, then use paid models only as escalation/fallback. This supports the customer cost expectation and makes the system scalable.

## Benchmark model list pattern

Store benchmark model pools as JSON under:

`pr_monitor_1/extraction_benchmarks/<name>.json`

For the first free OpenRouter pool, tested models included:

- `openrouter/owl-alpha`
- `google/gemma-4-26b-a4b-it:free`
- `nvidia/nemotron-3-ultra-550b-a55b:free`
- `nvidia/nemotron-3-super-120b-a12b:free`
- `poolside/laguna-xs.2:free`
- `qwen/qwen3-next-80b-a3b-instruct:free`
- `qwen/qwen3-coder:free`
- `openai/gpt-oss-120b:free`
- `cognitivecomputations/dolphin-mistral-24b-venice-edition:free`
- `meta-llama/llama-3.3-70b-instruct:free`
- `meta-llama/llama-3.2-3b-instruct:free`
- `nousresearch/hermes-3-llama-3.1-405b:free`

## First benchmark caveat

A first structural benchmark against single-page local recovery text showed:

- Owl-Alpha, Poolside Laguna, and Nemotron Super produced valid JSON on all usable cases.
- Many free models timed out or failed JSON structure.
- Event basics were extracted reasonably.
- CFP/contact fields were weak or absent.

Do **not** conclude from this that models cannot extract CFP/contact. The benchmark used one page per conference, while the project requirements are explicitly multi-page.

## Required multi-page extraction protocol

The Voice of Customer and existing `conference_monitor_enhanced.py` require category-specific path discovery:

| Category | Intended paths |
|---|---|
| conference_event | `/` |
| contact_info | `/contact/`, `/about/`, `/team/`, `/organizers/` |
| cfp_info | `/speakers/`, `/cfp/`, `/call-for-papers/`, `/submit/`, `/abstracts/` |
| submission_url | `/speakers/`, `/submit/`, `/submission/` |

The system should crawl/extract category pages, record `paths_tried`, store the source URL per field/category, remember successful paths per domain, and try remembered paths first next time.

## Recommended benchmark v2

Benchmark models per category, not just per conference:

1. Build fixed cases with content from main + contact/about + CFP/speaker/submit pages.
2. Run category-specific prompts:
   - event basics
   - contact/org
   - CFP/deadline/requirements
   - submission URL/portal/instructions
3. Score structural quality first:
   - JSON validity
   - field completeness
   - latency
   - zero/actual cost
   - error/timeout rate
4. Create a human-reviewed gold set before judging accuracy:
   - exact/normalized match for CFP status/deadline
   - fuzzy/contains match for name/dates/location
   - URL-normalized match for submission/CFP links
   - hallucination penalty for unsupported emails/dates/deadlines
5. Choose routing rules:
   - free default model for each category
   - rules-first extraction for obvious emails/URLs when possible
   - paid model only for invalid/low-confidence/free-model failures

## Step 4 v2 implementation pattern

For multi-page Step 4 work, keep multi-page evidence as the foundation and make each model an extraction pass over the same evidence package. Do not judge model quality before the multi-page evidence package is complete.

Current scaffold scripts:

- `pr_monitor_1/extraction_benchmarks/multi_page_evidence.py`
  - Builds per-conference evidence packages with `paths_planned`, `paths_tried`, `selected_source_urls`, evidence snippets, text chars, and source status.
  - Also writes a Windows local-browser job manifest containing all main/contact/CFP/submission candidate URLs.
- `pr_monitor_1/extraction_benchmarks/run_top5_multi_page_benchmark.py`
  - Runs the top 5 free OpenRouter models as separate passes over identical multi-page evidence.
  - Preserves raw response, parsed fields, `field_sources`, completeness, latency, usage/cost, and flags.

Top 5 free models to carry into Step 4 v2 until replaced by new benchmark evidence:

1. `openrouter/owl-alpha`
2. `poolside/laguna-xs.2:free`
3. `nvidia/nemotron-3-super-120b-a12b:free`
4. `nvidia/nemotron-3-ultra-550b-a55b:free`
5. `openai/gpt-oss-120b:free`

### Local-browser evidence is part of Step 4 v2, not an afterthought

Direct VPS HTTP fetch can be blocked on subpages even when the local-browser main-page recovery succeeds. If category pages return 403/blocked/partial from the VPS, generate a local-browser multi-page job and have the Windows runner collect the category pages. The runner preserves unknown row metadata, so include `case_id`, `conference_name`, `base_url`, and `categories` in each URL item for later evidence reconstruction.

Generated multi-page job manifests should be published via the standard static-link pattern when Matt needs to run them: copy to `dashboard/static`, `chmod 644`, verify HTTP 200/content-length, then provide the URL.

### Production integration gate

Do not immediately replace `/api/pr-monitor-1/extract` with experimental multi-page/model benchmarking. Add Step 4 v2 behind an explicit endpoint or mode first:

- preferred: `/api/pr-monitor-1/extract-v2-multipage`
- acceptable: existing `/api/pr-monitor-1/extract` only when `mode=multi_page_top5` is explicitly selected

Only promote it to default after local-browser multi-page collection, structural benchmark, and human gold-set accuracy review pass.

## Dashboard/business rule

Expose model benchmark results as a matrix: models as rows, extraction fields as columns. Include actual field values for top models, not just aggregate scores, because field-level comparables reveal whether a model is finding data or just returning well-formed empty JSON. When asked for org/contact detail, show actual `contact_name`, `contact_email`, `contact_phone`, and `contact_org` values by case and model.

## Data source rule: local ZIP vs VPS evidence

When asked about crawl success rates or URL-level stats, **always** read from `local_browser_fallback/uploads/<run_id>/<zip>.zip` (the actual Playwright crawl), **never** from `evidence_packages/` (which uses `requests.get()` and 403s on session-dependent subpages). See `references/crawl-results-data-source.md` for the full analysis, code snippets, and known stats.