
# PR Monitor Quality System Plan

**Project:** PR Monitor / PR in a Box — Nicolia / Brandable PR / PRIME PR  
**Created:** 2026-06-22  
**Owner:** HAWKEYE for Matt Olejarczyk / AI Digital Agents  
**Purpose:** Bake ASQ-style quality discipline into the PR Monitor pipeline so conference/award monitoring becomes a reliable SaaS process, not a brittle scraper.

---

## 1. Intent

Nicolia's immediate need is a working SaaS/software/app that replaces Goby agents for conference and award monitoring.

The business requirement is not merely to crawl pages. The requirement is to produce trusted, fresh, reviewable, customer-ready conference/award intelligence with high accuracy and low manual burden.

The quality system must continually answer:

1. Did we access the page or correctly classify why we could not?
2. Did we extract the right facts, especially dates and CFP/submission details?
3. Did we normalize and enrich the facts into usable customer-facing records?
4. Did the review UX make verification fast, clear, and auditable?
5. Are failures visible, classified, and improving over time?

---

## 2. Scope

Current quality focus starts at Nicolia-provided source lists.

In scope now:

1. Crawl
2. Extract
3. Enrich
4. Review

Out of scope for current quality phase:

1. Prompt generation
2. Multi-model discovery
3. Net-new market URL discovery

Reason: Nicolia already has source lists. Stabilizing Crawl through Review first reduces variation and lets us build the core trust engine before expanding discovery.

---

## 3. Quality Philosophy

The target is not naive perfection. The target is controlled, measured, improving quality.

A failure is acceptable only when it is:

1. Detected
2. Classified
3. Preserved in the audit trail
4. Routed to the right next action
5. Used to improve the system

Silent failure is unacceptable.

For Crawl specifically, 95% quality should mean:

> At least 95% of submitted URLs produce either usable page content OR a correctly classified, actionable failure state.

This is more practical and more rigorous than requiring 95% successful access, because some sites will always block automated access. The quality issue is not merely that a site blocks us; the quality issue is failing silently, passing partial content downstream, or giving Nicolia false confidence.

---

## 4. Pipeline Quality Gates

### Gate 1 — Crawl Quality Gate

Input: Seed URL from Nicolia source list  
Output: Crawled content artifact OR classified actionable failure

Required statuses:

- PASS: usable content captured
- PARTIAL: page accessed but content is suspiciously thin or incomplete
- BLOCKED: bot protection, Cloudflare, captcha, 403, 429, or equivalent
- TIMEOUT: page did not complete within allowed time
- INVALID_URL: malformed or unreachable URL
- NON_CONFERENCE_PLATFORM: URL is a platform/tool page, not the event owner page (example: Sessionize)
- REDIRECTED: URL redirected to another domain/page and needs provenance review
- NEEDS_MANUAL: ambiguous result that should not proceed automatically

Target:

- 95%+ actionable classification rate
- 90%+ usable content rate initially, with continuous improvement
- 0 silent failures

### Gate 2 — Extract Quality Gate

Input: Crawl artifact  
Output: 54-column extracted record with field-level provenance and confidence

Critical fields:

- Conference/award name
- Event date/start date/end date
- Location
- CFP/submission deadline
- CFP/submission status
- Submission URL
- Source URL/provenance

Target:

- 95%+ correctness for critical date fields before customer-facing auto-trust
- Every critical field must have status: VALUE_FOUND, PLACEHOLDER_FOUND, UNAVAILABLE, EXTRACTION_FAILED, or NEEDS_REVIEW
- Every critical field must have source/provenance

### Gate 3 — Enrich Quality Gate

Input: Extracted record  
Output: normalized, deduplicated, filterable customer-ready record

Critical transformations:

- Normalize dates
- Normalize location/country/state
- Assign controlled market tags
- Detect duplicates
- Handle multi-location events
- Detect past events requiring next-year recrawl
- Preserve verified user corrections across recrawls

Target:

- 95%+ normalized critical fields
- 0 duplicate master records after dedup pass
- 100% preservation of manually verified values unless explicitly superseded

### Gate 4 — Review Quality Gate

Input: Enriched record  
Output: verified, deferred, or routed record with audit history

UX requirements:

- One-click verified/deferred/reopen actions
- Always show last crawled date
- Always show field confidence
- Always show source URL/provenance
- Always show what changed since previous crawl
- Never hide stale data

Target:

- Verification action can be completed in under 30 seconds per record
- No record reaches customer view without freshness/provenance/status
- Review decisions persist across recrawls

---

## 5. Quality Metrics

### Crawl Metrics

- urls_attempted
- urls_passed
- urls_partial
- urls_blocked
- urls_timeout
- urls_invalid
- urls_non_conference_platform
- urls_redirected
- urls_needs_manual
- actionable_classification_rate
- usable_content_rate
- avg_crawl_seconds
- p95_crawl_seconds
- fallback_protocol_used_count
- content_size_bytes
- content_hash_present_rate

### Extract Metrics

- records_extracted
- critical_field_value_found_rate
- date_field_confidence_rate
- date_field_manual_correction_rate
- cfp_deadline_found_rate
- cfp_status_found_rate
- hallucination_count
- non_conference_false_positive_count
- field_source_url_present_rate
- schema_validation_pass_rate

### Enrich Metrics

- normalized_date_rate
- normalized_location_rate
- market_tag_validation_rate
- duplicate_records_detected
- duplicate_records_resolved
- past_event_rollover_candidates
- verified_value_preservation_rate

### Review Metrics

- records_needing_review
- records_verified
- records_deferred
- avg_review_time_seconds
- stale_records_count
- high_confidence_auto_accept_count
- low_confidence_manual_review_count
- corrections_by_field

---

## 6. Continuous Improvement Loop

After every production crawl/extract/enrich run:

1. Generate quality report JSON
2. Score each gate
3. Flag failures by class
4. Recommend top corrective actions
5. Store report in `pr_monitor_1/quality_reports/`
6. Append trend metrics
7. Surface dashboard summary

Weekly:

1. Aggregate quality reports
2. Identify top 3 recurring failure modes
3. Select improvement actions
4. Implement fixes
5. Verify improvement against next run

Scheduled control loop:

- Cron job: `PR Monitor Crawl Quality Baseline`
- Job ID: `20edc3a68a00`
- Schedule: `30 8 * * 1` (Mondays 08:30 UTC)
- Script: `/home/hermes/.hermes/scripts/pr_monitor_crawl_quality_watchdog.sh`
- Policy: reads only local PR Monitor manifests/snapshots and writes external quality reports; never modifies customer Google Sheets.

This is the PDCA loop:

- Plan: identify failure mode and target improvement
- Do: implement improvement
- Check: compare quality metrics before/after
- Act: standardize fix or revise approach

---

## 7. Current Known High-Risk Areas

1. Crawl access gaps — some pages cannot be accessed due to bot blocking or dynamic rendering.
2. Partial content risk — page loads but important data is missing due to JavaScript/lazy load.
3. Date extraction accuracy — Nicolia reports Goby-style agents get dates wrong up to 80% of the time.
4. CFP page discovery — CFP data is often not on the main page.
5. Sessionize/platform false positives — platform pages can be mistaken for actual conferences.
6. Date rollover — past events must be checked for next-year dates.
7. Verified data preservation — human-corrected data must not be overwritten by new lower-confidence extraction.
8. Customer trust — every customer-facing field needs freshness, status, and provenance.

---

## 8. Initial Baseline Sources

Saved source snapshots:

- `pr_monitor_1/source_snapshots/nicolia_energy_2026-06-22.csv`
- `pr_monitor_1/source_snapshots/nicolia_appsec_cybersecurity_2026-06-22.csv`

Initial observed source counts:

- ENERGY: 52 rows, 51 conference URLs found
- APPSEC/CYBERSECURITY: 998 rows, 56 conference URLs found

Recommended first baseline batch:

- 25 URLs total
- Include both ENERGY and APPSEC/CYBERSECURITY
- Include known difficult cases:
  - SecureWorld multi-location case
  - Sessionize/platform edge case if present
  - Past events needing date rollover
  - International sites
  - Sites with known CFP/submission pages

---

## 9. Deliverables

### Required Docs

- `PR_MONITOR_QUALITY_SYSTEM_PLAN.md` — this document
- `PR_MONITOR_CRAWL_QUALITY_GATE_SPEC.md`
- `PR_MONITOR_QUALITY_FMEA.md`
- `PR_MONITOR_QUALITY_METRICS.md`
- `PR_MONITOR_QUALITY_DASHBOARD_SPEC.md`

### Required Runtime Artifacts

- `pr_monitor_1/quality_inputs/*.json`
- `pr_monitor_1/quality_reports/*.json`
- `pr_monitor_1/quality_reports/latest_quality_report.json`

### Required Script

- `quality_monitor.py`

Initial script function:

```bash
python3 quality_monitor.py crawl-baseline --input pr_monitor_1/quality_inputs/crawl_baseline_urls.json --output pr_monitor_1/quality_reports/crawl_baseline_YYYYMMDD.json
```

---

## 10. Launch Readiness Criteria

Before this is customer-facing:

1. Crawl gate achieves 95% actionable classification on Nicolia seed-list baseline.
2. Critical extraction fields have field-level provenance and confidence.
3. Dates/CFP fields either meet target accuracy or are forced into manual review.
4. Review UI preserves verified values across recrawls.
5. Dashboard shows freshness and confidence visibly.
6. Quality report is generated for every run.
7. Weekly quality review loop is active.

---

## 11. Near-Term Build Order

1. Create crawl baseline URL manifest from Nicolia sheets.
2. Implement Crawl Quality Gate classifier.
3. Run baseline on selected URLs.
4. Review failures and classify top risk drivers.
5. Improve crawler fallback paths until Crawl reaches target.
6. Move to Extract quality gate.

---

## 12. Key Principle

The PR Monitor product should sell trust.

Trust comes from:

- Accuracy
- Freshness
- Provenance
- Clear confidence
- Visible failures
- Fast review
- Continuous improvement

If we build quality into the process now, Nicolia can detach from Goby with confidence and use this as the backbone of a real SaaS business.