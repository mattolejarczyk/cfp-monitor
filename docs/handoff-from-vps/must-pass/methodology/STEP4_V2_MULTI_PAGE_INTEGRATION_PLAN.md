# PR Monitor Step 4 v2 — Multi-Page Foundation + Multi-Model Passes

## Status
Implemented and smoke-tested outside production Step 4.

## New artifacts
- `multi_page_evidence.py`
  - Builds per-conference multi-page evidence packages.
  - Plans categories: `conference_event`, `contact_info`, `cfp_info`, `submission_url`.
  - Preserves `paths_planned`, `paths_tried`, `selected_source_urls`, evidence snippets, text chars, source status.
  - Writes a Windows local-browser job manifest for all category candidate URLs.

- `run_top5_multi_page_benchmark.py`
  - Runs top 5 free OpenRouter models as separate extraction passes over the same evidence package.
  - Preserves raw model response, parsed fields, `field_sources`, completeness, latency, usage/cost, and flags.

## Top 5 models carried forward
1. `openrouter/owl-alpha`
2. `poolside/laguna-xs.2:free`
3. `nvidia/nemotron-3-super-120b-a12b:free`
4. `nvidia/nemotron-3-ultra-550b-a55b:free`
5. `openai/gpt-oss-120b:free`

## Verification completed
- Python syntax check passed for both new scripts.
- Smoke evidence package generated for 1 conference.
- Smoke top-5 benchmark completed for 1 conference.

## Key finding from smoke
Direct VPS HTTP fetch was blocked on category subpages for Reuters (`403`), while the main page local-browser text was usable. Therefore Step 4 v2 must treat local-browser recovery as the preferred multi-page collection method for blocked/JS-heavy domains.

## Safest production integration point
Do not replace `/api/pr-monitor-1/extract` yet.

Add Step 4 v2 behind an explicit flag or separate endpoint first:
- Option A: `/api/pr-monitor-1/extract-v2-multipage`
- Option B: existing `/api/pr-monitor-1/extract` with `mode=multi_page_top5` only when explicitly selected

Recommended: Option A until gold-set review proves quality.

## Intended flow
1. Step 3 crawl gives base conference URLs.
2. Step 4 v2 expands each base URL into category candidate pages.
3. Generate/download local-browser multi-page job manifest.
4. Matt runs one-click Windows runner; upload returns category page text.
5. Build final evidence packages from recovered multi-page text.
6. Run top 5 free model passes over identical evidence.
7. Score structural completeness first, then human gold-set accuracy.
8. Only then choose default + fallback routing.

## Next gate
Run the generated local-browser multi-page job on Matt's Windows machine and upload results. Then rebuild evidence packages from those recovered subpages before judging model quality.
