
# PR Opportunity Intelligence System — Durable Engineering Roadmap

Task: `t_7dddae94`
Date: 2026-06-05
Durable artifact: `/home/hermes/PR_OPPORTUNITY_INTELLIGENCE_ENGINEERING_ROADMAP.md`

## Executive prioritization

PR Monitor 1 already has a useful demo spine: prompt-pack creation, URL discovery, async crawl, async extraction through the canonical `batch_processor.py`, artifact-backed review, 54-column CSV output, and review/portfolio endpoints. The next product step is to turn extracted rows into an operating workflow for Nicolia's team: what changed, what is urgent, which opportunity fits which client, who should review it, and what action should happen next.

MVP must-haves are Cards 1-10. These restore runnable confidence, protect the active PR Monitor 1 contracts, add durable state/change detection, expose an Opportunity Review Queue, add deadline urgency, produce an executive weekly action report, and make successes/failures trustworthy. Later enhancements are Cards 11-19. These add client-fit scoring, awards/media expansion, stronger integrations, evaluation, and production hardening after the workflow is dependable.

## Evidence base used

- Triage brief: `/home/hermes/PR_OPPORTUNITY_INTELLIGENCE_TRIAGE_BRIEF.md` frames the product as broader than a conference scraper: conferences, awards, speaking slots, CFP/deadline alerts, client-fit scoring, PR/media ranking, review workflow, and future Brandable PR SQL/dashboard integration.
- VOC handoff: `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/HERMES_VOC_HANDOFF_NICOLIA.md` says Nicolia's team manually checks hundreds of conference/award sites weekly, needs to know whether calls are open, needs deadlines updated, needs new opportunities found, and wants future SQL/source-of-truth updates.
- Current architecture/runbook: `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/PR_FIRM_TX_PROJECT_ARCHITECTURE_HANDOFF_2026-06-05.md` and `PR_MONITOR_1_RUNBOOK.md` identify the active surface as `dashboard/static/pr_monitor_1.html` + `dashboard/main.py`, Step 1-5 flow, async crawl/extract jobs, artifact safety, and canonical extraction via `batch_processor.py` into a locked 54-column output.
- MVP requirements: `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/MVP1_CONFERENCE_MONITORING.md` requires weekly monitoring, CFP status/deadline/URL extraction, change detection, spreadsheet/source-of-truth updates, alert reports, >90% fetch success, >80% CFP status identification, and graceful failures.
- Prior audit metadata: task `t_bf55ce71` found a blocking `dashboard/main.py` syntax error, missing dependencies (`crawl4ai`, `gspread`, `bs4`, `lxml`), unauthenticated local write endpoints, hard-coded paths, prototype in-process jobs, DuckDuckGo-like discovery lanes rather than true provider APIs, and placeholder fields despite 54-column shape.

## Phase 0 — Foundation and demo recovery (MVP must-have)

### Card 1 — Fix active PR Monitor 1 app import and add a smoke-test gate

Title:
Fix active PR Monitor 1 app import and add a smoke-test gate

Problem/opportunity:
The active FastAPI app cannot be trusted if `dashboard/main.py` fails to compile/import. This blocks demos, endpoint tests, and confidence in all downstream PR Monitor work.

Evidence:
Prior POC audit reproduced `dashboard/main.py` line 4935 `SyntaxError: f-string: unmatched '['`; architecture docs identify `dashboard/main.py` as the active backend for `/pr-monitor-1` and `/api/pr-monitor-1/*`.

Proposed implementation scope:
- Fix the f-string quoting issue without changing unrelated dashboard behavior.
- Add a smoke-test script that runs `python3 -m py_compile dashboard/main.py` and imports the FastAPI app in the intended environment.
- Assert route registration for `/pr-monitor-1` and critical `/api/pr-monitor-1/*` endpoints.
- Document this smoke gate in the runbook as the first demo-readiness check.

Dependencies:
None.

Estimated complexity:
S.

Priority rationale:
MVP P0. The app must import before any workflow or intelligence feature can be verified.

Acceptance criteria:
- `python3 -m py_compile dashboard/main.py` exits successfully.
- Smoke test imports the app without syntax/import errors.
- `/pr-monitor-1`, job-status, crawl, extract, latest, runs, rows, and artifact routes are discoverable.
- Runbook includes the command and expected pass/fail interpretation.

Risks/open questions:
Fixing syntax may expose dependency or import failures previously masked by the syntax error.

### Card 2 — Create PR Monitor dependency bootstrap and readiness health check

Title:
Create PR Monitor dependency bootstrap and readiness health check

Problem/opportunity:
The runtime needs a deterministic answer to “is this environment ready for a demo or scheduled run?” Missing packages and credentials should not appear halfway through a crawl/extract flow.

Evidence:
Prior audit found missing `crawl4ai`, `gspread`, `bs4`, and `lxml`; runbook requires crawl engine, Google Sheets integration potential, artifact directories, async jobs, and `batch_processor.py`.

Proposed implementation scope:
- Add `scripts/pr_monitor_healthcheck.py` or equivalent endpoint/CLI.
- Check imports, Python version, project paths, writable `pr_monitor_1` storage, artifact safe-path constraints, optional integration credentials, and canonical extractor availability.
- Classify checks as blocker, warning, or optional integration.
- Add dependency declarations to the project requirements/lockfile.

Dependencies:
Card 1.

Estimated complexity:
S.

Priority rationale:
MVP P0. Readiness checks turn fragile demos into repeatable operations.

Acceptance criteria:
- Health check reports all required imports and runtime directories.
- Missing optional credentials are warnings, not fatal errors.
- Missing extractor/crawl dependencies are blockers with actionable messages.
- Runbook documents how to run and interpret the health check.

Risks/open questions:
Dependency installation may be environment-specific; decide whether production uses venv, container, or system packages.

### Card 3 — Normalize PR Monitor endpoint contracts and path configuration

Title:
Normalize PR Monitor endpoint contracts and path configuration

Problem/opportunity:
Hard-coded `/home/ubuntu/.openclaw` paths and ambiguous form-vs-JSON endpoint behavior can make tests pass while the app uses unintended inputs.

Evidence:
Runbook warns Step 3 currently expects form fields and raw JSON can silently fall back to master-list defaults; audit found hard-coded absolute paths throughout scripts/backend.

Proposed implementation scope:
- Centralize project/runtime paths in one settings module or environment-backed config.
- Preserve current form contract where needed but reject misleading raw JSON with explicit errors or add JSON parsing intentionally.
- Add request/response schema docs for prompt-pack, discovery, crawl, extract, job status, latest, runs, rows, artifact, review, and portfolio endpoints.
- Add tests for `custom_urls`, `urls`, `urls_text`, and `use_master_list=false` guardrails.

Dependencies:
Cards 1-2.

Estimated complexity:
M.

Priority rationale:
MVP P0. The product cannot become a reliable operating system if callers do not know which inputs were actually used.

Acceptance criteria:
- Path config can run outside `/home/ubuntu/.openclaw` without code edits.
- Step 3 URL source priority is tested and matches the runbook.
- Raw JSON behavior is explicit: supported with tests or rejected with clear HTTP error.
- Endpoint contract docs are current and linked from the runbook.

Risks/open questions:
Changing endpoint behavior may break existing dashboard JavaScript or manual curl recipes.

### Card 4 — Replace prototype in-process jobs with durable job state

Title:
Replace prototype in-process jobs with durable job state

Problem/opportunity:
Async crawl/extract jobs currently depend on in-process daemon threads and local ephemeral state, which is fragile for scheduled runs, restarts, and production handoffs.

Evidence:
Runbook says Step 3/4 run async and are polled by job ID; audit flags in-process daemon-thread jobs/local files as prototype-only.

Proposed implementation scope:
- Introduce a durable job store for submitted crawl/extract/discovery runs: SQLite, Postgres, or a small queue-backed store.
- Persist job status, input manifest, artifact paths, timestamps, error messages, retry count, and operator-visible progress.
- On app restart, mark interrupted jobs as failed/recoverable instead of losing them.
- Keep existing `GET /api/pr-monitor-1/job/{job_id}` response shape or add a versioned compatible shape.

Dependencies:
Cards 1-3.

Estimated complexity:
M.

Priority rationale:
MVP P1. Weekly monitoring cannot rely on app-process memory.

Acceptance criteria:
- Submitted job remains queryable after backend restart.
- Job record links to crawl/extract artifacts and input URL manifest.
- Interrupted jobs are visible as failed/recoverable with reason.
- UI polling still works with the durable job store.

Risks/open questions:
Choose smallest durable mechanism that fits deployment; avoid overbuilding a full queue before scheduling needs are clear.

## Phase 1 — Intelligence pipeline and operating state (MVP must-have)

### Card 5 — Add durable source registry and path memory

Title:
Add durable source registry and path memory

Problem/opportunity:
Nicolia needs the system to remember where CFP information was found and recover when sites change. Raw one-off crawls do not preserve enough knowledge to reduce weekly manual checking.

Evidence:
Triage brief names path memory/site reliability as a top priority; VOC asks for checking hundreds of sites and constantly updating; architecture requires `conf_page_url` to preserve source audit trail.

Proposed implementation scope:
- Create a source registry keyed by normalized URL/domain/opportunity identifier.
- Store last successful CFP URL, discovered submission/contact paths, crawl artifact references, status history, and failure history.
- During crawl/extract, prefer known high-signal paths before broad rediscovery.
- Expose source history in review rows and reports.

Dependencies:
Cards 3-4.

Estimated complexity:
M.

Priority rationale:
MVP P1. Path memory is the bridge from scraper demo to weekly intelligence workflow.

Acceptance criteria:
- Each monitored source has persistent last-known paths and source audit URL.
- New runs update path memory when CFP/submission/contact URLs move.
- Review UI/API can show when and where the current result was found.
- Failure reports distinguish “site unavailable” from “path changed / needs rediscovery.”

Risks/open questions:
Need entity-key strategy for conferences with multiple domains or annual event pages.

### Card 6 — Implement change detection between scan runs

Title:
Implement change detection between scan runs

Problem/opportunity:
The customer value is not just extracted rows; it is knowing what changed since the last check and what now requires action.

Evidence:
MVP requirements explicitly require comparing current vs previous scan for CFP open, new deadline, changed dates, and new conferences; triage brief asks for “what changed since last time?”

Proposed implementation scope:
- Persist normalized opportunity snapshots after each extract run.
- Diff CFP status, deadline, conference dates, CFP URL, source URL, confidence, failure state, and row identity.
- Add change-type labels such as `new_opportunity`, `cfp_opened`, `deadline_added`, `deadline_changed`, `dates_changed`, `source_failed`, `no_material_change`.
- Attach diffs to review rows, executive reports, and alert payloads.

Dependencies:
Cards 4-5.

Estimated complexity:
M.

Priority rationale:
MVP P1. Change detection is required by the original MVP and is core to reducing weekly manual checks.

Acceptance criteria:
- Running the same source twice produces stable `no_material_change` labels when nothing changes.
- Simulated fixture changes produce the correct change labels.
- Each changed row includes previous value, current value, and timestamp.
- Executive report can filter to action-worthy changes.

Risks/open questions:
Need normalization rules for dates/status text to avoid false positives.

### Card 7 — Add deadline urgency and action-status classification

Title:
Add deadline urgency and action-status classification

Problem/opportunity:
The team needs deadline windows translated into urgency and action labels, not just raw date strings.

Evidence:
Triage brief names 30/14/7 day deadline alerts and action-required status; MVP requirements define deadline <30 days as high priority and risk of missed deadlines.

Proposed implementation scope:
- Parse and normalize CFP/submission deadlines into canonical dates with timezone/unknown handling.
- Add urgency buckets: `overdue`, `<7_days`, `<14_days`, `<30_days`, `future`, `unknown`.
- Add action states: `needs_review`, `ready_to_pitch_client`, `submit_now`, `watch`, `closed`, `unknown`.
- Surface urgency in API rows, review filters, and reports.

Dependencies:
Cards 5-6.

Estimated complexity:
M.

Priority rationale:
MVP P1. Deadline risk is one of Nicolia's most explicit pains.

Acceptance criteria:
- Deadline parser handles common date formats from current artifacts and fixtures.
- Rows with deadlines inside 30/14/7 days are labeled correctly.
- Unknown/unparseable deadlines are routed to human review.
- UI/API can filter by urgency and action state.

Risks/open questions:
Conference sites may list multiple deadlines; define primary deadline selection and preserve alternatives.

## Phase 2 — User workflow and executive action (MVP must-have)

### Card 8 — Build the Opportunity Review Queue

Title:
Build the Opportunity Review Queue

Problem/opportunity:
Step 5 review exists, but the product needs a queue organized around PR actions: open CFP, deadline soon, new opportunity, needs human review, and ready to pitch client.

Evidence:
Triage brief names Opportunity Review Queue as the top priority; architecture says review endpoints and portfolio/review export already exist; UI already supports review statuses per prior roadmap trace.

Proposed implementation scope:
- Add queue API that returns normalized rows grouped by action state and urgency.
- Extend review status model to include `needs_review`, `reviewed`, `follow_up`, `ready_to_pitch_client`, `submitted`, `dismissed`.
- Add filters for open CFP, deadline bucket, new/changed, failure/manual-review, client-fit status, and source.
- Preserve artifact links, source URL, evidence snippets, and row-level notes.

Dependencies:
Cards 5-7.

Estimated complexity:
M.

Priority rationale:
MVP P1. This is the main user-facing conversion from crawler output to PR operating workflow.

Acceptance criteria:
- Queue shows action groups with counts.
- Review status updates persist and survive page reload/backend restart.
- Queue rows include evidence, source path, deadline urgency, and change labels.
- Existing latest/runs/rows endpoints remain compatible or are versioned.

Risks/open questions:
Need stakeholder decision on exact review statuses and whether status is per opportunity, per client, or per source row.

### Card 9 — Generate Nicolia weekly executive action report

Title:
Generate Nicolia weekly executive action report

Problem/opportunity:
Nicolia should receive a concise weekly answer: which opportunities should the team act on now, which deadlines are at risk, what changed, and what failed.

Evidence:
Triage brief asks for “Here are the 8 opportunities your team should act on this week,” not raw rows; MVP reporting requirements define scan summary, new action items, failures requiring attention, and success/failure counts.

Proposed implementation scope:
- Create a report generator that consumes queue/change/deadline state.
- Sections: top opportunities, urgent deadlines, new/changed opportunities, client-ready items, failures requiring attention, run quality metrics, and recommended next actions.
- Produce Markdown/text artifact and optional JSON payload for downstream integrations.
- Link report from Step 5 and job completion output.

Dependencies:
Cards 6-8.

Estimated complexity:
M.

Priority rationale:
MVP P1. The report is the artifact that makes the system valuable even before full SQL integration.

Acceptance criteria:
- Report lists top action items with evidence, deadline, source URL, and review state.
- Report includes total sites checked, success/failure counts, and failure reasons.
- Report excludes unchanged low-priority rows unless configured otherwise.
- Report artifact is linked from run details and safe artifact endpoints.

Risks/open questions:
Need ranking defaults for “top opportunities” before client-fit scoring is mature.

### Card 10 — Add scheduled weekly run and alert delivery controls

Title:
Add scheduled weekly run and alert delivery controls

Problem/opportunity:
The original workflow requires weekly monitoring that can move toward daily checks. Manual button-driven demos are not enough for operations.

Evidence:
VOC and MVP requirements describe weekly checks, action reports, and future daily cadence; runbook Step 2-5 flow is ready to orchestrate once durable state exists.

Proposed implementation scope:
- Add a scheduler entrypoint that runs discovery/crawl/extract/change/report in controlled sequence.
- Support weekly default and configurable daily cadence.
- Send alert/report delivery via configured channel: email, Telegram, or dashboard notification.
- Include dry-run and small sample modes for QA.

Dependencies:
Cards 2, 4, 6, 9.

Estimated complexity:
M.

Priority rationale:
MVP P2. Scheduling turns the dashboard workflow into an ongoing service.

Acceptance criteria:
- Scheduler can run a known source set end-to-end and produce report artifact.
- Failures are logged and surfaced without stopping report generation for successful rows.
- Delivery channel can be disabled/enabled by config.
- Run history shows scheduled vs manual runs.

Risks/open questions:
Need production host/cron/worker ownership and delivery-channel credentials.

## Phase 3 — Client-fit intelligence and PR opportunity ranking (later enhancement)

### Card 11 — Define client/opportunity domain model and source-of-truth schema

Title:
Define client/opportunity domain model and source-of-truth schema

Problem/opportunity:
Client-fit scoring and future Brandable PR SQL integration need a clear model for clients, industries, opportunities, submissions, sources, and review decisions.

Evidence:
Triage brief recommends defining the Brandable PR database schema before wiring SQL; MVP sheet schema includes client assignment, submission status, action required, notes; VOC emphasizes dozens of clients in different industries.

Proposed implementation scope:
- Draft schema for clients, client industries/topics, opportunities, source sites, opportunity events/deadlines, submissions, reviews, and run snapshots.
- Map locked 54-column CSV fields to the future domain model.
- Identify fields that remain computed vs human-owned.
- Produce migration/backfill strategy from existing sheets/CSV artifacts.

Dependencies:
Cards 5-8.

Estimated complexity:
M.

Priority rationale:
Later enhancement P2. Needed before scoring and SQL writes, but not before MVP queue/report.

Acceptance criteria:
- Schema document includes entities, keys, relationships, field ownership, and mapping from current outputs.
- Ambiguous fields are flagged for Nicolia/stakeholder review.
- No SQL write integration begins before schema review.
- Test fixtures represent at least one client with multiple opportunities and review states.

Risks/open questions:
Brandable PR existing database schema may constrain naming, IDs, and ownership rules.

### Card 12 — Implement transparent client-fit scoring v1

Title:
Implement transparent client-fit scoring v1

Problem/opportunity:
The system should help answer “which client is this opportunity for?” and “why does it fit?” without inventing generic AI features.

Evidence:
Triage brief names client-fit scoring, fit rationale, and pitch angle; VOC describes many clients across industries, making manual matching expensive.

Proposed implementation scope:
- Create a deterministic/rule-assisted scoring module using client industries, topics, geography, opportunity type, audience, deadline, and confidence.
- Generate explainable fit rationale and suggested pitch angle fields.
- Route low-confidence matches to human review instead of auto-approval.
- Add score/rationale to queue and executive report.

Dependencies:
Card 11 plus Cards 7-9.

Estimated complexity:
M.

Priority rationale:
Later enhancement P2. High customer value, but only after durable opportunity state exists.

Acceptance criteria:
- Each scored opportunity includes score, matched clients, rationale, and confidence.
- Rules can be adjusted without code changes where practical.
- Low-confidence or multi-client conflicts are marked `needs_review`.
- Reports include client-fit explanation, not only a numeric score.

Risks/open questions:
Need client profiles and acceptable criteria; avoid opaque AI ranking until stakeholders trust baseline rules.

### Card 13 — Add PR/media/award opportunity type expansion

Title:
Add PR/media/award opportunity type expansion

Problem/opportunity:
The desired system includes awards, speaking slots, and broader PR/media opportunities, not only conferences.

Evidence:
Triage brief explicitly lists conferences, awards, speaking slots, CFP/deadline alerts, and PR/media ranking; VOC says the workflow also applies to industry and product awards.

Proposed implementation scope:
- Extend opportunity type taxonomy: conference, award, speaking slot, media opportunity, analyst/report opportunity, unknown.
- Update extraction prompts/schema mapping to preserve type-specific fields while maintaining the 54-column contract or a versioned output.
- Add type filters to queue/report.
- Add fixtures for awards and speaking opportunities.

Dependencies:
Cards 6-8, Card 11.

Estimated complexity:
M.

Priority rationale:
Later enhancement P2. Expands value after the core monitoring workflow is proven.

Acceptance criteria:
- Opportunity type is assigned for current conference rows and test award rows.
- Award/speaking-specific deadlines and URLs can be represented.
- Type-specific queue filters work.
- Output contract changes are documented and backward-compatible or versioned.

Risks/open questions:
The locked 54-column schema may not fully represent non-conference opportunities without extension.

### Card 14 — Add opportunity ranking and deduplication across discovery providers

Title:
Add opportunity ranking and deduplication across discovery providers

Problem/opportunity:
Discovery can generate duplicate or low-quality sources. The product needs a ranked, deduped candidate list before sending work to review.

Evidence:
Architecture docs mention provider lists and master lists; audit found discovery labeled multi-model but implemented via search lanes/fixtures; triage asks for new relevant opportunities, not noisy lists.

Proposed implementation scope:
- Normalize candidate URLs/domains/titles from all discovery lanes.
- Deduplicate by canonical URL, event name, domain, and fuzzy title/date matching.
- Rank by relevance to client/profile, freshness, source reliability, and opportunity type.
- Store rejected/duplicate rationale for auditability.

Dependencies:
Cards 5, 11-12.

Estimated complexity:
M.

Priority rationale:
Later enhancement P2. Prevents the review queue from becoming noisy as discovery expands.

Acceptance criteria:
- Duplicate candidates collapse into one opportunity with source evidence list.
- Ranking output includes score components and rationale.
- Reviewers can see why a candidate was included, merged, or suppressed.
- Existing master list generation remains compatible.

Risks/open questions:
Fuzzy matching may merge distinct events with similar annual names; require reviewer override.

## Phase 4 — Integrations and source of truth (later enhancement)

### Card 15 — Implement Google Sheets synchronization with conflict handling

Title:
Implement Google Sheets synchronization with conflict handling

Problem/opportunity:
Google Sheets is part of the current/manual workflow and likely remains a near-term source of truth or stakeholder-visible export.

Evidence:
MVP requirements require reading/updating Google Sheets, marking new information, logging check status, and appending scan timestamps; audit found `gspread` missing.

Proposed implementation scope:
- Add configurable Sheet reader/writer for source lists and result updates.
- Map sheet columns to opportunity/source state and action statuses.
- Implement conflict handling when humans edit sheet fields between runs.
- Add a sync report that lists updates, skipped rows, and conflicts.

Dependencies:
Cards 2, 5-8, Card 11.

Estimated complexity:
M.

Priority rationale:
Later enhancement P2/P3. Important for deployment, but should follow internal state and review workflow clarity.

Acceptance criteria:
- Can read a configured sheet source list into the source registry.
- Can write status/deadline/action updates back to a test sheet.
- Human-owned fields are not overwritten without explicit rule.
- Sync errors are visible in run reports.

Risks/open questions:
Need Sheet access/credentials and stakeholder decision on which columns are human-owned.

### Card 16 — Define and implement Brandable PR SQL integration contract

Title:
Define and implement Brandable PR SQL integration contract

Problem/opportunity:
Nicolia wants the system to check and update their SQL database, but wiring SQL too early risks corrupting a future source of truth.

Evidence:
VOC quote asks for AI to “go into our SQL database and check everything and constantly update”; triage brief says define SQL contract before integrating and don’t wire SQL too early.

Proposed implementation scope:
- After Card 11 schema review, define read/write API or direct SQL contract for clients, opportunities, submissions, and status updates.
- Build staging-mode integration first with dry-run diff output.
- Add idempotent upsert keys and audit log for every external write.
- Gate production writes behind config and integration tests.

Dependencies:
Card 11, Cards 5-10, optionally Card 15.

Estimated complexity:
L.

Priority rationale:
Later enhancement P3. High strategic value, but unsafe until internal model and workflow are stable.

Acceptance criteria:
- Contract document approved or at least ready for stakeholder review.
- Dry-run produces exact SQL/API changes without writing.
- Staging write tests pass with idempotent upserts.
- Production write mode is disabled by default and auditable.

Risks/open questions:
Need access to Brandable PR schema/API, security requirements, and rollback expectations.

## Phase 5 — Evaluation, quality, and production hardening (MVP plus later hardening)

### Card 17 — Build extraction/evaluation harness for CFP status, deadlines, and source reliability

Title:
Build extraction/evaluation harness for CFP status, deadlines, and source reliability

Problem/opportunity:
The MVP requires >90% fetch success and >80% CFP status identification, but the system needs repeatable evaluation rather than anecdotal demo success.

Evidence:
MVP acceptance criteria specify success-rate and CFP-identification targets; prior audit verified CSV shape but noted placeholder/fixed fields and missing dependencies.

Proposed implementation scope:
- Create labeled fixture set from known conference/award pages and existing artifacts.
- Measure fetch success, CFP status classification, deadline extraction, source URL integrity, and failure classification.
- Track metrics by run and expose trend summary in health/report output.
- Add regression tests for representative successes and failure types.

Dependencies:
Cards 1-3, Cards 6-7.

Estimated complexity:
M.

Priority rationale:
MVP-adjacent P2. Required to trust the system before broad rollout.

Acceptance criteria:
- Evaluation harness reports fetch success, status accuracy, deadline extraction accuracy, and failure taxonomy counts.
- Baseline metrics are recorded for current fixtures/artifacts.
- Regressions fail CI or health checks when below configured thresholds.
- Metrics appear in executive/internal QA reports.

Risks/open questions:
Need gold labels for enough real sites to make metrics meaningful.

### Card 18 — Add security/authentication and write-surface controls

Title:
Add security/authentication and write-surface controls

Problem/opportunity:
Endpoints that write local artifacts or external sources of truth should not remain unauthenticated once the system leaves controlled demo use.

Evidence:
Prior audit flagged unauthenticated local write endpoints; future integrations will write Google Sheets or SQL state.

Proposed implementation scope:
- Add authentication/authorization for PR Monitor write endpoints and artifact access as appropriate.
- Separate read-only demo routes from operator/admin write routes.
- Add CSRF or token requirements for browser-triggered writes depending on deployment model.
- Redact secrets and avoid exposing sensitive artifact paths in public responses.

Dependencies:
Cards 3-4, Cards 15-16 before external writes.

Estimated complexity:
M.

Priority rationale:
Later hardening P3, but should happen before any public or client-facing deployment.

Acceptance criteria:
- Write endpoints reject unauthenticated requests in non-demo mode.
- Read-only demo mode cannot mutate sources, jobs, review statuses, or external integrations.
- Secrets and credentials are not logged or returned in API responses.
- Security behavior is covered by tests.

Risks/open questions:
Need deployment identity model: single admin, team users, or shared internal link.

### Card 19 — Containerize/deploy PR Opportunity Intelligence with observability and rollback

Title:
Containerize/deploy PR Opportunity Intelligence with observability and rollback

Problem/opportunity:
A production operating system needs reproducible deployment, logs, metrics, backups, and rollback, not local workstation state.

Evidence:
Architecture docs currently describe local project runtime storage and controlled demo confidence; audit found hard-coded paths and prototype job state; MVP requires scheduled unattended operation and graceful failures.

Proposed implementation scope:
- Package backend, static UI, dependencies, scheduler, and runtime config in a container or equivalent reproducible environment.
- Add structured logging, run metrics, job metrics, crawl fallback alerts, report-delivery audit, and backup/restore for durable state.
- Provide deployment checklist and rollback procedure.
- Add smoke/e2e test command for production readiness.

Dependencies:
Cards 1-4, 10, 17-18.

Estimated complexity:
L.

Priority rationale:
Later hardening P3. Necessary for reliable production after MVP value is proven.

Acceptance criteria:
- Fresh deployment can run health check and a small sample crawl/extract/report flow.
- Logs and metrics expose job failures, crawl fallback, report delivery, and queue counts.
- Durable state is backed up or restorable.
- Rollback plan is documented and tested at least once in staging.

Risks/open questions:
Need final hosting target, persistence layer, and notification/credential management strategy.

## MVP vs later enhancement summary

MVP must-haves: Cards 1-10.
- 1 app import/smoke gate
- 2 dependency/readiness health check
- 3 endpoint/path contract normalization
- 4 durable job state
- 5 source registry/path memory
- 6 change detection
- 7 deadline urgency/action classification
- 8 Opportunity Review Queue
- 9 weekly executive action report
- 10 scheduled run and alert delivery controls

Later enhancements: Cards 11-19.
- 11 client/opportunity domain model and schema
- 12 client-fit scoring
- 13 awards/media/speaking expansion
- 14 provider dedupe/ranking
- 15 Google Sheets sync
- 16 Brandable PR SQL integration
- 17 extraction/evaluation harness
- 18 security/write controls
- 19 production deployment/observability

## Recommended next 5 cards before the next demo

1. Card 1 — Fix app import and smoke gate.
2. Card 2 — Dependency/readiness health check.
3. Card 3 — Endpoint/path contract normalization.
4. Card 8 — Opportunity Review Queue prototype using current rows and statuses.
5. Card 9 — Weekly executive action report from current artifacts.