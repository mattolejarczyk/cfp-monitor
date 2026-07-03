# PR Monitor 1 Runbook (Production)

**Version:** 2026-06-02  
**Scope:** Step 1-5 operational flow used by `dashboard/main.py` + `dashboard/static/pr_monitor_1.html`

---

## Endpoint Contracts

Current request/response schemas and runtime path configuration are documented in `PR_MONITOR_1_ENDPOINT_CONTRACTS.md`.

---

## Smoke Gate

Run this gate from the dashboard root before starting or redeploying the PR Monitor 1 app:

```bash
cd /home/ubuntu/.openclaw/workspace/dashboard
./venv/bin/python scripts/pr_monitor_1_smoke.py
```

The smoke gate performs three checks:
1. Compiles `dashboard/main.py` with `py_compile` to catch syntax errors.
2. Imports `main:app` with schedulers disabled for a side-effect-light smoke run.
3. Verifies the active PR Monitor 1 page and critical API routes are registered:
   - `/pr-monitor-1`
   - `/api/pr-monitor-1/job/{job_id}`
   - `/api/pr-monitor-1/crawl`
   - `/api/pr-monitor-1/extract`
   - `/api/pr-monitor-1/latest`
   - `/api/pr-monitor-1/runs`
   - `/api/pr-monitor-1/run/{run_id}/rows`
   - `/api/pr-monitor-1/artifact/list`
   - `/api/pr-monitor-1/artifact/open`

Expected pass/fail interpretation:
- Pass: output starts with `PASS pr_monitor_1_smoke` and lists the compiled file, imported app route count, and each required route.
- Fail: any non-zero exit means the app is not safe to start/redeploy; read the traceback for the syntax, import/dependency, or missing-route blocker and fix it before proceeding.

---

## Readiness Health Check

Run this health check from the project root before demos, scheduled runs, or dependency/environment changes:

```bash
cd /home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas
/home/ubuntu/.openclaw/workspace/dashboard/venv/bin/python scripts/pr_monitor_healthcheck.py
```

Use the Python environment that will run the dashboard/crawl/extract flow. Use JSON output for automation/CI gates:

```bash
/home/ubuntu/.openclaw/workspace/dashboard/venv/bin/python scripts/pr_monitor_healthcheck.py --json
```

The health check bootstraps missing PR Monitor 1 runtime directories by default and verifies:
1. Python version and required imports for the active dashboard/crawl/extract runtime.
2. Project root, dashboard root, active UI (`dashboard/static/pr_monitor_1.html`), and canonical extractor (`batch_processor.py`).
3. Writable `pr_monitor_1` storage and expected crawl/extract/discovery/provider/master-list directories.
4. Artifact safe-path constraints: artifact access must stay inside `projects/PR_Firm_Texas/pr_monitor_1` and reject project files or `..` traversal outside that root.
5. Optional integration packages and credentials for Telegram alerts, LLM extraction, Google Sheets, billing, and Google APIs.

Expected pass/fail interpretation:
- `PASS blockers=0 warnings=0`: environment is ready and optional integrations are configured.
- `PASS_WITH_WARNINGS blockers=0 warnings=N`: core demo/crawl/extract readiness is OK; warnings are optional integrations such as missing Telegram/LLM/Google credentials or optional packages. These are not fatal.
- `FAIL blockers=N warnings=M`: do not run the demo/scheduled flow yet. Fix every `[BLOCKER]` item first. Missing crawl/extractor dependencies such as `crawl4ai`, `bs4`, `lxml`, or required dashboard imports are blockers with remediation commands in the output.

Use `--no-bootstrap` when you want a read-only-style check that reports missing runtime directories instead of creating them.

---

## Final Macro Flow

1. **Step 1 - Create Prompt**  
   Build prompt pack and persist artifact in:
   - `projects/PR_Firm_Texas/pr_monitor_1/prompt_pack_<timestamp>.json`

2. **Step 2 - Discover URLs (Live by default)**  
   `POST /api/pr-monitor-1/multi-model-discovery`
   - `dry_run` now defaults to `false` server-side.
   - UI submits live mode by default.
   - Persists:
     - `pr_monitor_1/discovery_jobs/`
     - `pr_monitor_1/provider_lists/`
     - `pr_monitor_1/master_lists/master_list_latest.txt`
     - `source_sets_pr_monitor_1/master_list_latest.txt`

3. **Step 3 - Crawl URLs (crawl engine + fallback)**  
   `POST /api/pr-monitor-1/crawl`
   - Async by default via `async_mode=true`.
   - Supports one-time **custom URL injection** to bypass discovery:
     - Priority: `custom_urls` -> `urls` -> `urls_text` -> master list fallback (`use_master_list=true` only)
     - `custom_urls` accepts JSON array-like text or newline/comma-delimited URL text.
   - Produces crawl artifacts in:
     - `pr_monitor_1/crawl_runs/`
     - `pr_monitor_1/crawl_runs/artifacts/<crawl_id>/`
   - Updates engine metrics:
     - `pr_monitor_1/crawl_engine_metrics.json`

4. **Step 4 - Extract Data**  
   `POST /api/pr-monitor-1/extract`
   - Async by default via `async_mode=true`.
   - Uses canonical extractor (`batch_processor.py`) against URL input.
   - Produces:
     - `pr_monitor_1/extract_runs/extract_<id>_CONFERENCES_54COLUMNS.csv`
     - `pr_monitor_1/extract_runs/extract_<id>_results.json`
     - `pr_monitor_1/extract_runs/extract_<id>_EXECUTIVE_REPORT.txt`
     - `pr_monitor_1/extract_runs/extract_<id>_trace.json`

5. **Step 5 - Review**  
   Read latest/runs/rows from review endpoints:
   - `GET /api/pr-monitor-1/latest`
   - `GET /api/pr-monitor-1/runs`
   - `GET /api/pr-monitor-1/run/{id}/rows`

---

## Async Job Architecture (Step 3/4)

### Job Submit
- Crawl: `POST /api/pr-monitor-1/crawl` with `async_mode=true`
- Extract: `POST /api/pr-monitor-1/extract` with `async_mode=true`
- Returns:
  - `{"ok": true, "async": true, "job_id": "...", "status": "queued"}`

### Job Status
- `GET /api/pr-monitor-1/job/{job_id}`
- Status values:
  - `queued`, `running`, `completed`, `failed`
- Response includes:
  - `progress`, `message`, `started_at`, `completed_at`, `result` or `error`

### UI Behavior
- Step 3/4 buttons submit async jobs and poll status until completion.
- Progress text updates continuously in UI.
- On completion, linkage + artifacts/outputs are rendered automatically.

---

## Step 3 Input Contract (Critical)

- Endpoint reads **form fields** (`Form(...)`), not raw JSON body.
- Use `application/x-www-form-urlencoded` or multipart payloads for reliable behavior.
- Raw JSON is explicitly rejected with `HTTP 415` and a detail containing `expects form data`; this prevents accidental fallback to the master list when callers intended direct URLs.

### Step 3 Effective URL Source Resolution

1. `custom_urls` (highest priority)
2. `urls` (compatibility alias)
3. `urls_text`
4. Master list only if `use_master_list=true`
5. If none found and `use_master_list=false` -> `HTTP 400`

### Step 3 Job Input Telemetry

Job status payload (`GET /api/pr-monitor-1/job/{job_id}`) includes:
- `url_count`
- `use_master_list`
- `custom_urls_used`
- `urls_alias_used`

Use these fields to verify the backend actually used the intended input path.

---

## Crawl Engine Reliability Controls

### Terminology
- UI label is **crawl engine** (not Crawl4AI branding).
- If crawl engine is unavailable, fallback mode runs to avoid hard outage.

### Metrics File
- `projects/PR_Firm_Texas/pr_monitor_1/crawl_engine_metrics.json`
- Key fields:
  - `total_runs`
  - `crawl_engine_runs`
  - `fallback_runs`
  - `crawl_engine_failure_count`
  - `last_crawl_engine_failure_at`
  - `last_crawl_engine_failure_reason`
  - `last_alert_sent_ok`
  - `last_alert_send_error`
  - `alert_log`

### Visible Failure Banner
- UI shows high-visibility red banner when `crawl_engine_failure_count > 0`.
- Auto-refreshes on page load and after each crawl run.

### Proactive Fallback Alerting
- On fallback, backend attempts immediate Telegram alert.
- Env vars used:
  - `PR_MONITOR_TELEGRAM_BOT_TOKEN` (fallback: `TELEGRAM_BOT_TOKEN`)
  - `PR_MONITOR_TELEGRAM_CHAT_ID` (fallback: `MATT_TELEGRAM_CHAT_ID` or `TELEGRAM_CHAT_ID`)
- Alert audit log:
  - `projects/PR_Firm_Texas/pr_monitor_1/crawl_engine_alerts.jsonl`

---

## Artifact Access Endpoints

- `GET /api/pr-monitor-1/artifact/list?path=...`
- `GET /api/pr-monitor-1/artifact/open?path=...`
- Safety: paths are restricted to `projects/PR_Firm_Texas/pr_monitor_1`.

UI surfaces minimized links for:
- Step 3 artifact folder + crawl manifest
- Step 4 trace JSON + output CSV + output report

---

## Best-Practice Operating Rules

1. Run Step 2 once, then iterate Step 3/4 as needed.
2. Treat any fallback event as a reliability incident; inspect:
   - `crawl_engine_metrics.json`
   - `crawl_engine_alerts.jsonl`
3. Keep extraction method-testing artifact-driven:
   - prefer latest crawl artifacts/URLs over ad-hoc recrawls.
4. Use async endpoints for normal operation (sync is fallback-only behavior).
5. For quick QA loops, skip Step 2 and run Step 3 with `custom_urls` + `use_master_list=false`.

---

## Validation Snapshot (2026-06-02)

### Completed
- Custom URL end-to-end path validated (crawl -> extract).
- Negative parser test validated (blank lines, duplicates, invalid tokens).
- Guardrail validated (`use_master_list=false` + no URL inputs returns `HTTP 400`).

### Representative Artifacts
- Crawl: `crawl_20260602T000318Z` (2 valid URLs retained from mixed input)
- Crawl URL list: `projects/PR_Firm_Texas/pr_monitor_1/crawl_runs/crawl_20260602T000318Z.txt`
- Guardrail check response: `HTTP 400` with `No URLs to crawl. Provide URLs or generate master list first.`

---

## Canonical Components

- API/UI orchestration:
  - `dashboard/main.py`
  - `dashboard/static/pr_monitor_1.html`
- Extraction engine of record:
  - `projects/PR_Firm_Texas/batch_processor.py`

---

## Section 5 Geo Field Display Issue (postmortem)

### Symptom
Section 5 on `channeled.org/static/pr_monitor_1.html` showed `geo_city`, `geo_state`, `geo_country`, and `geo_confidence_status` as empty/null even though geo data existed in the project database.

### Root Cause
The live dashboard process was not pointing to the correct source-of-truth database for Section 5's portfolio/review endpoint. As a result, the backend opened an empty/fallback DB path, so the `portfolio/latest` response returned null `geo_*` values.

### Verification
- The source-of-truth DB `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/conference_pipeline.db` contains populated `geo_*` records.
- Section 5 renders those columns from JSON (`r.geo_city`, `r.geo_state`, `r.geo_country`, `r.geo_confidence_status`); no UI change was required.

### Fixes Applied
- Updated `dashboard/start.sh` to export `PR_MONITOR_DB_PATH=/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/conference_pipeline.db` before launching uvicorn.
- Ensured the dashboard is restarted from `/home/ubuntu/.openclaw/workspace/dashboard` in the intended runtime context so `pr_monitor_settings.py` resolves to the Texas project DB.
- Added startup logging for the active `db_path` in `pr_monitor_settings.py`.
- Added optional `debug=1` response metadata in `/api/pr-monitor-1-review/portfolio/latest` so future DB-path issues can be diagnosed via API response.

### Result
After restart, Section 5 began returning populated geo values and the geo columns render correctly.\n
