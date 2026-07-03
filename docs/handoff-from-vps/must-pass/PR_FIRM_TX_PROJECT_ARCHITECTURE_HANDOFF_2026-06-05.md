
# PR Firm TX Project + Architecture Handoff

**Project:** PR Firm Texas / Bioveritas Conference Monitoring System  
**Client contact:** Nicolia  
**Current date:** 2026-06-05  
**Status:** PR Monitor 1 production flow is documented and validated for controlled demo use.

---

## What This Project Is

PR Firm TX is a conference intelligence and monitoring system for a PR firm that tracks speaking, award, and CFP opportunities across large conference lists. The business problem is that staff manually check conference websites, update Google Sheets, and risk missing submission windows.

The system automates:

1. Conference URL discovery and source-list management.
2. Website crawling and artifact capture.
3. Structured extraction into a locked 54-column schema.
4. Review of extracted conference rows.
5. Executive report generation for client decision-making.

The core value is time saved plus earlier detection of speaking opportunities, CFP deadlines, contact details, and conference changes.

---

## Current Production Flow

The active dashboard workflow is **PR Monitor 1**, available through:

- UI: `dashboard/static/pr_monitor_1.html`
- Backend/API: `dashboard/main.py`
- Operational runbook: `PR_MONITOR_1_RUNBOOK.md`

The macro flow is:

1. **Create Prompt**  
   Builds a prompt pack and stores it under `projects/PR_Firm_Texas/pr_monitor_1/prompt_pack_<timestamp>.json`.

2. **Discover URLs**  
   Calls `POST /api/pr-monitor-1/multi-model-discovery`. Discovery is live by default, not dry-run by default. Provider outputs and master lists are saved under `pr_monitor_1/discovery_jobs/`, `provider_lists/`, and `master_lists/`.

3. **Crawl URLs**  
   Calls `POST /api/pr-monitor-1/crawl`. Normal mode is async. Crawl results and artifacts are written under `pr_monitor_1/crawl_runs/`.

4. **Extract Data**  
   Calls `POST /api/pr-monitor-1/extract`. Normal mode is async. Extraction uses the canonical `batch_processor.py` and writes CSV, JSON, trace, and executive report artifacts under `pr_monitor_1/extract_runs/`.

5. **Review**  
   Uses latest/run/row endpoints to inspect and work extracted rows:
   - `GET /api/pr-monitor-1/latest`
   - `GET /api/pr-monitor-1/runs`
   - `GET /api/pr-monitor-1/run/{id}/rows`

---

## Architecture

```text
Dashboard UI
  dashboard/static/pr_monitor_1.html
        |
        v
FastAPI backend
  dashboard/main.py
        |
        +--> Preferences and prompt-pack endpoints
        +--> Multi-model discovery endpoint
        +--> Async crawl jobs
        +--> Async extract jobs
        +--> Artifact open/list endpoints
        +--> Review and portfolio endpoints
        |
        v
Project runtime storage
  projects/PR_Firm_Texas/pr_monitor_1/
        |
        +--> prompt packs
        +--> discovery jobs
        +--> provider lists
        +--> master lists
        +--> crawl runs and artifacts
        +--> extract runs
        +--> metrics and alert logs
        |
        v
Canonical extraction engine
  projects/PR_Firm_Texas/batch_processor.py
        |
        v
Outputs
  54-column CSV
  results JSON
  trace JSON
  executive report TXT
```

---

## Key Backend Code Areas

Primary file: `dashboard/main.py`

Important endpoint groups:

- Page route: `GET /pr-monitor-1`
- Source save/upload: `/api/pr-monitor-1/sources/save`, `/api/pr-monitor-1/sources/upload-csv`
- Geography helpers: `/api/pr-monitor-1/geo/*`
- Preferences: `/api/pr-monitor-1/preferences`
- Prompt pack creation: `POST /api/pr-monitor-1/prompt-pack`
- Legacy all-in-one run: `POST /api/pr-monitor-1/run`
- Multi-model discovery: `POST /api/pr-monitor-1/multi-model-discovery`
- Crawl job: `POST /api/pr-monitor-1/crawl`
- Extract job: `POST /api/pr-monitor-1/extract`
- Job status: `GET /api/pr-monitor-1/job/{job_id}`
- Crawl engine metrics: `GET /api/pr-monitor-1/crawl-engine-metrics`
- Artifacts: `GET /api/pr-monitor-1/artifact/list`, `GET /api/pr-monitor-1/artifact/open`
- Review data: `/api/pr-monitor-1/latest`, `/api/pr-monitor-1/runs`, `/api/pr-monitor-1/run/{run_id}/rows`
- Portfolio/review export: `/api/pr-monitor-1/portfolio/*`, `/api/pr-monitor-1-review/*`

Primary frontend file: `dashboard/static/pr_monitor_1.html`

The frontend calls the Step 1-5 endpoints directly, submits Step 3/4 as async jobs, polls job status, and renders artifact links when each job completes.

---

## Important Runtime Contracts

### Step 3 Crawl Input Priority

`POST /api/pr-monitor-1/crawl` resolves URLs in this order:

1. `custom_urls`
2. `urls`
3. `urls_text`
4. master list, only when `use_master_list=true`

If all URL inputs are empty and `use_master_list=false`, the endpoint should return `HTTP 400` instead of silently falling back.

### Form Encoding Requirement

The crawl endpoint currently reads `Form(...)` fields. Use form-encoded or multipart requests. Raw JSON can silently trigger defaults and make a test appear to use custom URLs when it actually uses the master list.

### Async Jobs

Step 3 and Step 4 run async by default. Submit endpoints return a job ID, then the UI polls:

```text
GET /api/pr-monitor-1/job/{job_id}
```

Job statuses are:

- `queued`
- `running`
- `completed`
- `failed`

---

## Data Model And Extraction Contract

The locked extraction output is a **54-column format**:

- 53 data columns
- 1 metrics column

The schema is documented in `PROCESS_DOCUMENTATION.md`.

Major field groups:

1. Conference info
2. Contact info
3. CFP info
4. Submission portal info
5. Summary and crawl metadata
6. Column 54 metrics string

Critical rule: `conf_page_url` must come from the source input URL and must not be left blank. It is the audit trail back to the seed URL.

Official execution command:

```bash
cd /home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas
python3 batch_processor.py --input <CSV_FILE> --output <PREFIX>
```

The process documentation says not to create one-off extractor scripts for production use. `batch_processor.py` is the canonical processor.

---

## Artifacts And Storage

Project root:

```text
/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas
```

Current PR Monitor runtime:

```text
projects/PR_Firm_Texas/pr_monitor_1/
```

Important subfolders/files:

- `crawl_runs/` - crawl manifests, URL lists, captured artifacts
- `extract_runs/` - extracted CSVs, reports, traces, JSON result files
- `discovery_jobs/` - multi-model discovery job outputs
- `provider_lists/` - provider-specific URL discovery lists
- `master_lists/` - merged/current master URL lists
- `preferences.json` - PR Monitor 1 settings
- `crawl_engine_metrics.json` - crawl engine and fallback counters
- `crawl_engine_alerts.jsonl` - alert audit log for fallback incidents

Artifact access is restricted to the PR Monitor 1 project folder through safe path handling in the backend.

---

## Reliability And QA Status

Current validation evidence is in `TEST_REPORT.md` and `PR_MONITOR_1_RUNBOOK.md`.

Validated on 2026-06-02:

- Custom URL crawl path works end to end.
- Extract from latest custom crawl works.
- Dirty custom URL inputs are normalized to valid unique `http/https` URLs.
- `use_master_list=false` with no URLs returns `HTTP 400`.
- Legacy master-list flow remains unchanged.

Representative artifacts:

- Crawl: `crawl_20260602T000318Z`
- Crawl URL list: `projects/PR_Firm_Texas/pr_monitor_1/crawl_runs/crawl_20260602T000318Z.txt`
- Extract examples under `projects/PR_Firm_Texas/pr_monitor_1/extract_runs/`

Recommended demo confidence: **high for controlled custom-URL demos**.

---

## Known Risks And Gotchas

1. **Raw JSON to Step 3 can mislead testing.**  
   Use form/multipart payloads because the endpoint reads form fields.

2. **Crawl engine fallback is a reliability incident.**  
   If fallback occurs, inspect `crawl_engine_metrics.json` and `crawl_engine_alerts.jsonl`.

3. **Do not bypass the locked extractor for production.**  
   Use `batch_processor.py`, not individual row scripts or new ad hoc extractors.

4. **Source URL integrity matters.**  
   `conf_page_url` must be preserved from source input for auditability and recrawling.

5. **Older project docs still exist.**  
   Some March docs describe the original MVP and 53-column process. Current runtime behavior is PR Monitor 1 plus 54-column output.

---

## Existing Documentation Map

Start here:

- `DOCUMENTATION_INDEX.md` - complete file reference and current doc map
- `PR_MONITOR_1_RUNBOOK.md` - current production workflow and architecture
- `PROCESS_DOCUMENTATION.md` - 54-column extraction contract and report rules
- `TEST_REPORT.md` - validation evidence and QA outcomes
- `README.md` - project usage and high-level feature notes
- `PROJECT_OVERVIEW.md` - business explanation and 5-phase process
- `MVP1_CONFERENCE_MONITORING.md` - original MVP requirements
- `DISCOVERY_TRANSCRIPT_ANALYSIS.md` - original client discovery analysis

---

## Current Bottom Line

The system is no longer just a scraper. It is now a dashboard-driven conference intelligence workflow with:

- live URL discovery,
- async crawl/extract jobs,
- artifact-backed review,
- safe custom URL test paths,
- a locked 54-column extraction contract,
- validated guardrails for demo use.

The main remaining work is product hardening: tighter endpoint contracts, clearer production/deprecated file separation, scheduled runs, and any client-specific Google Sheets integration needed for deployment.