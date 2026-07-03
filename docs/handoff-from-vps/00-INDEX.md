# PR Monitor — VPS→Local handoff manifest

**Purpose:** documents carried forward from the VPS "PR Monitor 1" build into the new local, native-crawl4ai `cfp-monitor` build. Tiers agreed 2026-07-02 (my analysis + VPS-build model, fully aligned).

**Read order for a fresh session:** this file → `local-build-analysis/` → `must-pass/` → `must-pass/methodology/` → `reference-only/` only when porting logic.

**Guiding principle carried over from the (excluded) recovery category:**
> "Blocked/partial pages must be classified and routed; no silent failures." — lives in the quality-gate docs now.

---

## Tier 1 — MUST-PASS (`must-pass/`)
Customer truth, product/quality contract, schema, roadmap. Copy all.

- REQUIREMENTS_COMPARISON.md — 62-requirement scorecard + gap analysis *(status: local copy is a fetched paraphrase — copy the real file)*
- DEVELOPMENT_MILESTONES.md — M0–M9 status
- HERMES_VOC_HANDOFF_NICOLIA.md — customer voice / pain / workflow
- VOICE_OF_CUSTOMER_REQUIREMENTS.md — detailed reqs, quotes, alert triggers, acceptance criteria
- PR_FIRM_TX_PROJECT_ARCHITECTURE_HANDOFF_2026-06-05.md — business/workflow context (mine the non-VPS-path parts)
- PROCESS_DOCUMENTATION.md — locked 54-column schema + extraction rules (output contract)
- PR_MONITOR_QUALITY_SYSTEM_PLAN.md — "no silent failures", gate targets, philosophy
- PR_MONITOR_CRAWL_QUALITY_GATE_SPEC.md — crawl quality taxonomy + pass/fail rules
- PR_OPPORTUNITY_INTELLIGENCE_ENGINEERING_ROADMAP.md — 19-card roadmap
- PR_OPPORTUNITY_INTELLIGENCE_TRIAGE_BRIEF.md — strategic framing (opportunity intelligence, not scraper)
- REPORTING_ALERTS_RECOMMENDATIONS.md — M6/M7 alerts+reporting guidance (forward-looking; closes bucket-C gaps)
- guidance_weekly_executive_report.md — weekly exec report structure (M7)

## Tier 2 — MUST-PASS / methodology (`must-pass/methodology/`)
Extraction & quality *methodology* (not results). Copy all.

- STEP4_V2_MULTI_PAGE_INTEGRATION_PLAN.md — Step 4 v2 multi-page extraction plan
- PHASE1_INTERNAL_LINK_DISCOVERY.md — internal link discovery work (CFP/contact often off-homepage)
- internal-link-discovery.md — link-discovery rules (register/signup ≠ junk)
- gold_set_template.md — human-approved gold-set template
- gold-set-scoring.md — deterministic scoring vs approved truth
- step4-v2-multipage-model-benchmark.md — benchmark *procedure* (frame as method, not results)
- extraction-model-benchmarking.md — broader benchmarking notes
- quality-system.md — condensed quality-system reference
- evidence-existence-check.md — evidence-gap vs data-truly-absent
- evidence-pipeline-discovery-gap.md — known discovery-wiring gap
- static-url-path-crawl-success-rate.md — which guessed paths work/fail (tune native scorer; disable low-yield)

## Tier 3 — REFERENCE-ONLY (`reference-only/`)
Do NOT treat as target architecture. Mine for schema/logic/field-names only.

- batch_processor.py — canonical extractor; mine field-mapping/prompt/report logic
- quality_monitor.py — crawl-status taxonomy + metric shape
- BATCH_PROCESSOR_QUICKREF.md — quick ref for the extractor
- PR_MONITOR_1_RUNBOOK.md — Step 1–5 workflow intent
- PR_MONITOR_1_ENDPOINT_CONTRACTS.md — endpoint behavior/field names (cautionary: raw-JSON-vs-form)
- PR_MONITOR_1_STEP_REFERENCE.md — plain-language app-flow walkthrough
- PR_MONITOR_REVIEW_API_SCHEMAS_AND_FIXTURES.md — review API schemas/fixtures
- PR_MONITOR_REVIEW_FORM_DRIVEN_SPEC.md — review form behavior/spec
- DOCUMENTATION_INDEX.md — map of the old VPS doc set
- TEST_REPORT.md — validation evidence (custom URL path, QA, guardrails)
- main.py — old FastAPI backend (workflow reveal only)
- pr_monitor_1.html — old UI (affordances Nicolia has seen)
- pr_monitor_settings.py — old path/env config
- architecture-component-map.md — condensed VPS component/path map (5.8 KB) ✅
- 20260702-PR-Monitor-Architecture-detailed.txt — fuller narrative "where things live" (11.3 KB; these are TWO different docs) ✅

## Tier 0 — LOCAL-BUILD ANALYSIS (`local-build-analysis/`)
Artifacts generated for the local build. ✅ already placed.

- 20260702-PR-Monitor-Gap-Analysis-Local-Crawl4ai.md — authoritative gap analysis + full 62 mapping ✅
- 20260702-PR-Monitor-Status.txt — point-in-time status snapshot ✅
- PR Monitor VPS-vs-Local-Gap-Analysis-20260702.docx — shareable (Word) version of the gap analysis ✅

---

## EXCLUDE — do NOT copy (VPS survival scaffolding)
Listed so the decision is explicit, not forgotten.

**Local-browser recovery loop (obsolete under residential egress):**
local-browser-fallback-architecture.md · local-browser-runner-one-click-and-benchmarking.md · local-browser-runner-one-click-v0-9.md · local-browser-one-click-recovery-ux.md · local-browser-runner-discovery-patch.md · upload-endpoint-health-check.md · crawl-results-data-source.md · local_browser_runner.py + windows_runner_v0_1/* · runner ZIP/static-publishing docs

**Ops / permissions (VPS/OpenClaw environment):**
dashboard-restart-procedure.md · OPENCLAW_PERMISSIONS_RUNBOOK.md · permission_fix.md · fetch_use_comparison/README.md

**Stale benchmark run outputs (point-in-time; env-dependent):**
runs/top5_local_browser_multi_page_20260623.../{report.md, DETAILED_RESULTS_AND_STRATEGY.md, field_population_matrix.md, contact_cfp_values.md}

**Optional / inspect-only:**
runs/.../GOLD_SET_REVIEW_HANDOFF.md — copy ONLY if it holds human-reviewed truth/reusable cases; skip if it's unapproved preliminary truth on old local-browser evidence.
