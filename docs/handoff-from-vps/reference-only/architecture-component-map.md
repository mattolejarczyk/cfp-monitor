# PR Monitor architecture component map

Use this when Matt asks "where does X live?", needs a handoff, or wants a VPS/local component inventory.

## Active runtime stack

Public URL:
- `https://channeled.org/pr-monitor-1`

VPS dashboard root:
- `/home/ubuntu/.openclaw/workspace/dashboard/`

Live server pattern:
- `uvicorn main:app --host 127.0.0.1 --port 8080`
- Usually launched with `/home/ubuntu/.openclaw/workspace/dashboard/venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8080`

Primary UI:
- `/home/ubuntu/.openclaw/workspace/dashboard/static/pr_monitor_1.html`

Backend/API:
- `/home/ubuntu/.openclaw/workspace/dashboard/main.py`

Path/settings module:
- `/home/ubuntu/.openclaw/workspace/dashboard/pr_monitor_settings.py`
- Defaults project root to `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas`
- Defaults DB path to `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/conference_pipeline.db`

## Project root

Main project:
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/`

Canonical extractor:
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/batch_processor.py`
- Treat as extractor of record; do not bypass with one-off production extractors.

Main DB:
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/conference_pipeline.db`

Important docs:
- `PR_FIRM_TX_PROJECT_ARCHITECTURE_HANDOFF_2026-06-05.md`
- `PR_MONITOR_1_RUNBOOK.md`
- `REQUIREMENTS_COMPARISON.md`
- `DEVELOPMENT_MILESTONES.md`
- `PR_MONITOR_QUALITY_SYSTEM_PLAN.md`
- `PR_MONITOR_CRAWL_QUALITY_GATE_SPEC.md`

## Runtime artifacts

Runtime root:
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/pr_monitor_1/`

Key subfolders/files:
- `prompt_pack_<timestamp>.json` — Step 1 prompt pack outputs
- `discovery_jobs/` — Step 2 multi-model discovery outputs
- `provider_lists/` — provider-specific URL lists
- `master_lists/` — merged/current master URL lists, including `master_list_latest.txt`
- `crawl_runs/` — Step 3 crawl manifests, URL lists, and outputs
- `crawl_runs/artifacts/<crawl_id>/` — captured crawl artifacts by run
- `extract_runs/` — Step 4 extraction CSV/JSON/report/trace outputs
- `preferences.json` — PR Monitor settings
- `crawl_engine_metrics.json` — crawl engine/fallback counters
- `crawl_engine_alerts.jsonl` — fallback incident/alert audit log
- `source_registry.json` — source/path memory unless env-overridden

Source-set mirror:
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/source_sets_pr_monitor_1/`

## Local browser fallback

VPS package/source area:
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/pr_monitor_1/local_browser_fallback/`

Current runner source:
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/pr_monitor_1/local_browser_fallback/windows_runner_v0_1/`

Key runner files:
- `local_browser_runner.py`
- `run_recovery_one_click.bat`
- `run_windows.bat`
- `jobs/`
- `uploads/`
- `upload_tokens/`

Packaged runner zips:
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/pr_monitor_1/dist/`

Public/static downloadable copies:
- `/home/ubuntu/.openclaw/workspace/dashboard/static/`

Uploaded local-browser recovery results:
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/pr_monitor_1/local_browser_fallback/uploads/`

## Extraction benchmarking and quality

Benchmark tools:
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/pr_monitor_1/extraction_benchmarks/`

Common files:
- `run_free_model_benchmark.py`
- `run_top5_multi_page_benchmark.py`
- `multi_page_evidence.py`
- `internal_link_discovery.py`
- `score_against_gold_set.py`
- `prefill_gold_set_from_evidence.py`

Benchmark outputs:
- `extraction_benchmarks/runs/`
- `extraction_benchmarks/evidence_packages/`

Quality monitor:
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/quality_monitor.py`

Quality folders:
- `pr_monitor_1/quality_inputs/`
- `pr_monitor_1/quality_reports/`
- `pr_monitor_1/source_snapshots/`

Hermes watchdog script:
- `/home/hermes/.hermes/scripts/pr_monitor_crawl_quality_watchdog.sh`

## Smoke and health checks

Dashboard smoke test:
- `/home/ubuntu/.openclaw/workspace/dashboard/scripts/pr_monitor_1_smoke.py`
- Run from dashboard root with `./venv/bin/python scripts/pr_monitor_1_smoke.py`

Project health check:
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/scripts/pr_monitor_healthcheck.py`
- Run from project root using dashboard venv: `/home/ubuntu/.openclaw/workspace/dashboard/venv/bin/python scripts/pr_monitor_healthcheck.py`

## Agent-facing knowledge, not app runtime

Hermes/user docs:
- `/home/hermes/PROJECT_PORTFOLIO.md`
- `/home/hermes/wiki/entities/pr-monitor-1.md`
- `/home/hermes/PR_OPPORTUNITY_INTELLIGENCE_ENGINEERING_ROADMAP.md`
- `/home/hermes/PR_OPPORTUNITY_INTELLIGENCE_TRIAGE_BRIEF.md`

Skill package:
- `/home/hermes/.hermes/skills/projects/pr-monitor-dashboard/`

## Simplified flow

Browser loads:
- `https://channeled.org/pr-monitor-1`

which serves:
- `dashboard/static/pr_monitor_1.html`

which calls:
- `dashboard/main.py`

which uses:
- `dashboard/pr_monitor_settings.py`
- `projects/PR_Firm_Texas/pr_monitor_1/`
- `projects/PR_Firm_Texas/batch_processor.py`
- `projects/PR_Firm_Texas/conference_pipeline.db`

Local recovery flow:
- VPS creates recovery job JSON → Matt runs Windows one-click runner → runner uploads light ZIP/summary → dashboard Step 3.5 reads recovery data from VPS uploads.

## Cautions

- Older March MVP docs still exist; use PR Monitor 1 docs/runbook for current runtime.
- Confirm `PR_MONITOR_DB_PATH` when debugging missing data. A wrong/fallback DB can make UI fields appear blank even when source DB has data.
- Files in `dashboard/static/` must be chmod `644` so the ubuntu-owned service can serve them.
