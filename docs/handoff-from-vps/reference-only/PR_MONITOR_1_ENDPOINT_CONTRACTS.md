# PR Monitor 1 Endpoint Contracts

Version: 2026-06-05
Scope: active `dashboard/main.py` PR Monitor 1 POC surface used by `dashboard/static/pr_monitor_1.html`.

Runtime path configuration:
- `PR_MONITOR_PROJECT_ROOT` defaults to `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas`.
- `PR_MONITOR_DASHBOARD_ROOT` defaults to `/home/ubuntu/.openclaw/workspace/dashboard`.
- `PR_MONITOR_RUNTIME_ROOT` defaults to `${PR_MONITOR_PROJECT_ROOT}/pr_monitor_1`.
- Optional overrides: `PR_MONITOR_SOURCE_SETS_DIR`, `PR_MONITOR_DB_PATH`, `PR_MONITOR_LEGACY_RUNNER`, `PR_MONITOR_BATCH_PROCESSOR`.
- The dashboard derives crawl, extract, discovery, provider-list, master-list, metrics, alert, preferences, and source-set paths from these settings. Deployments outside `/home/ubuntu/.openclaw` should set env vars rather than editing code.

Content-type policy:
- JSON endpoints below require `application/json` request bodies.
- Form endpoints below require `application/x-www-form-urlencoded` or `multipart/form-data`.
- Raw JSON submitted to form-only endpoints is explicitly rejected with HTTP 415 and a detail containing `expects form data`.

## Prompt pack

`POST /api/pr-monitor-1/prompt-pack`

Request: JSON object.

Common request fields:
- `market_focus` or `market`: string, required for useful prompts.
- `record_type`: `both`, `conference`, or `award`; default `both`.
- `conference_country_scope`, `conference_countries`, `conference_region_scope`, `conference_us_states`, `conference_geo_preference`: optional geographic controls.
- `award_geo_preference`: optional string.
- `date_window`: optional backward-compatible string; preserved but not used to constrain discovery prompts.
- `priority_mode`: optional string; default `balanced`.
- `include_unknown_geo`: optional boolean; default `true`.

Response 200 JSON:
- `ok`: true.
- `path`: prompt pack artifact path under runtime root.
- `prompt_pack`: persisted prompt pack object.
- `prompt_pack_id`: generated ID.
- `schema_version`: currently `step1_prompt_pack_v1`.
- `prompts`: prompt strings keyed by workflow stage.
- `defaults_applied`: list of defaults applied.

Errors:
- Unhandled validation/storage errors return FastAPI default errors.

## Discovery

`POST /api/pr-monitor-1/multi-model-discovery`

Request: JSON object.

Fields:
- `market_focus` or `market`: string, required.
- `providers`: optional list/string; allowed provider lanes are `perplexity`, `chatgpt`, `gemini`; default all three.
- `record_type`: `both`, `conference`, or `award`; default `both`.
- `dry_run`: boolean; default `false`. If true, fixture provider results are used.
- Prompt-pack fields are also accepted and forwarded to the prompt-pack builder.

Response 200 JSON:
- `ok`: true.
- `job_id`: discovery job ID (`mmd_<timestamp>`).
- `dry_run`, `providers`, `prompt_pack_id`.
- `provider_results`: per-provider candidate URL results and prompts used.
- `comparison`: pairwise overlap counts, unique master URL count, provider count.
- `master_list`: deduped URL rows with provenance/confidence metadata.
- `path`: discovery artifact path.
- `artifacts`: paths for master-list text artifacts, source-set copies, and provider-list artifacts.
- `generated_at`: ISO timestamp.

Errors:
- 400 if `market_focus`/`market` is blank.

## Crawl

`POST /api/pr-monitor-1/crawl`

Request: form data only.

Fields:
- `custom_urls`: optional string. Highest-priority one-time URL injection. Accepts JSON array text or newline-delimited URL text.
- `urls`: optional string. Compatibility alias, lower priority than `custom_urls` and higher priority than `urls_text`.
- `urls_text`: optional newline-delimited URL text.
- `use_master_list`: string boolean; default `true`. Latest master list fallback is used only when no direct URL fields produce URLs and this value is `true`.
- `async_mode`: string boolean; default `true`.

Step 3 URL source priority:
1. `custom_urls`
2. `urls`
3. `urls_text`
4. `pr_monitor_1/master_lists/master_list_latest.txt` only when `use_master_list=true`
5. HTTP 400 if no URLs are available.

Async response 200 JSON:
- `ok`: true.
- `async`: true.
- `job_id`: crawl job ID.
- `status`: `queued`.

Sync response 200 JSON:
- `ok`: true.
- `crawl_id`, `url_count`, `reachable_count`.
- `crawl4ai_enabled`, `crawl4ai_error`.
- `artifacts_dir`.
- `paths`: manifest, URL text, latest-manifest, latest-URL paths.
- `engine_metrics`: updated crawl-engine metrics.

Errors:
- 415 for raw JSON content type.
- 400 when no URLs are available.

## Extract

`POST /api/pr-monitor-1/extract`

Request: form data only.

Fields:
- `mode`: `smart_hybrid` or `full_ai`; default `smart_hybrid`.
- `min_confidence`: float; default `0.85`.
- `urls_text`: optional newline-delimited URL text.
- `allow_default_csv`: retained for legacy compatibility; default `false`.
- `skip_same_day`: string boolean; default `true`.
- `use_latest_crawl`: string boolean; default `true`.
- `async_mode`: string boolean; default `true`.

URL resolution:
1. `urls_text` when provided.
2. Latest crawl manifest rows when `use_latest_crawl=true` and no explicit URLs.
3. Latest master list if still no URLs.
4. Canonicalized/deduped URLs are passed to `batch_processor.py`.

Async response 200 JSON:
- `ok`: true.
- `async`: true.
- `job_id`: extract job ID.
- `status`: `queued`.

Sync/completed job result JSON:
- `ok`: true.
- `phase`: `extract`.
- `extract_id`, `source_crawl_id`, `used_latest_crawl`, `url_count`.
- `paths`: input CSV, output CSV, output JSON, output report, trace JSON, extract run dir.
- `output`: canonical extractor stdout.

Errors:
- 415 for raw JSON content type.
- 400 for invalid `mode`.
- 500 if canonical extractor fails.

## Job status

`GET /api/pr-monitor-1/job/{job_id}`

Request: path parameter `job_id`.

Response 200 JSON:
- `ok`: true.
- `job`: process-local job state. Common fields include `job_id`, `job_type`, `status`, `message`, `progress`, timestamps, `input`, `result`, `error`, and `traceback`.

Errors:
- 404 if the process-local job ID is unknown. Job state is not persisted across dashboard process restarts.

## Latest run

`GET /api/pr-monitor-1/latest`

Request: no parameters.

Response 200 JSON:
- `ok`: true.
- `run`: latest completed `pipeline_runs` row plus `rows_skipped_same_day`, or null when no completed run exists.

## Runs

`GET /api/pr-monitor-1/runs?limit=20`

Request query:
- `limit`: integer clamped to 1..200; default 20.

Response 200 JSON:
- `ok`: true.
- `runs`: recent completed runs. Each includes pipeline-run fields, `rows_skipped_same_day`, `rows_with_results`, and `rows_null_results`.

## Rows

`GET /api/pr-monitor-1/run/{run_id}/rows`

Request:
- Path `run_id`: string.
- Query filters: `qa_status`, `ai_called` (`0` or `1`), `changed_only` (`true`/`false`), `has_cfp_or_dates` (`true`/`false`), `domain_contains`, `limit` clamped to 1..2000.

Response 200 JSON:
- `ok`: true.
- `run_id`, `count`, `rows`.
- Rows combine `run_row_audit` fields with matching `conference_events` CFP/date fields.

## Artifacts

`GET /api/pr-monitor-1/artifact/list?path=<absolute-path>`

Response 200 JSON:
- `ok`: true.
- `path`: resolved directory path.
- `items`: child entries with `name`, `is_dir`, `path`, and file `size`.

`GET /api/pr-monitor-1/artifact/open?path=<absolute-path>`

Response 200:
- File response for an allowed artifact file.

Artifact path safety:
- Paths must resolve under configured `PR_MONITOR_RUNTIME_ROOT`.
- Project files outside runtime root and `..` traversal are rejected.

Errors:
- 400 when `path` is missing.
- 403 when path resolves outside runtime root.
- 404 when the allowed directory/file does not exist.

## Review

`POST /api/pr-monitor-1-review/review/upsert`

Request: JSON object.

Fields:
- `event_key`: string, required.
- `market`, `customer`: strings.
- `review_status`: string; default `needs_review`.
- `override_cfp_status`, `override_cfp_deadline`, `override_conf_dates`: optional strings.
- `review_notes`, `reviewed_by`, `reviewed_at`, `submission_status`: optional review metadata; `submission_status` defaults to `not_submitted`.

Response 200 JSON:
- `ok`: true.
- `event_key`: upserted key.

Errors:
- 400 if `event_key` is blank.

## Portfolio

`GET /api/pr-monitor-1/portfolio/latest`

Request query:
- `market`: default `hydrogen`.
- `customer`: default `default_customer`.
- `has_cfp_or_dates`: string boolean; default `true`.
- `limit`: integer clamped to 1..2000.

Response 200 JSON:
- `ok`: true.
- `count`, `rows`: latest event rows by event key.

`GET /api/pr-monitor-1/portfolio/export-csv`

Request query:
- `market`, `customer`, `has_cfp_or_dates` as above.
- `upcoming_only`: string boolean; default `false`.
- `limit`: integer clamped to 1..20000.

Response 200:
- UTF-8-BOM CSV file response.

`GET /api/pr-monitor-1-review/portfolio/latest`

Request query:
- `market`: default `hydrogen`.
- `customer`: default `default_customer`.
- `limit`: integer clamped to 1..2000.

Response 200 JSON:
- `ok`: true.
- `count`, `rows`: latest event rows joined with review state.

`GET /api/pr-monitor-1-review/portfolio/export-csv`

Request query:
- `market`, `customer`, `limit`.

Response 200:
- UTF-8-BOM CSV file response with event and effective review fields.
