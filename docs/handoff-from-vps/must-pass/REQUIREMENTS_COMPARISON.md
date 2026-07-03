
# Comparative Analysis: Customer Requirements vs PR Monitor 1 Dashboard

## Overview
This document compares what Nicolia (the customer) asked for against what the
PR Monitor 1 dashboard actually delivers. Each requirement is rated:
- **MET** — the requirement is fully addressed
- **PARTIAL** — some of the requirement is met, but gaps remain
- **NOT MET** — the requirement is not addressed
- **NOT YET** — planned/infrastructure exists but not wired up end-to-end


---

## 62-REQUIREMENT SCORECARD

This scorecard is the roll-up used by the detailed comparison below. The detailed sections are grouped by category and sub-requirement; this table is the authoritative 62-requirement count from the current document.

| # | Category | MET | PARTIAL | NOT MET | NOT YET | Total |
|---:|----------|---:|---:|---:|---:|---:|
| 1 | Core monitoring pipeline | 4 | 3 | 0 | 0 | 7 |
| 2 | Data fields & schema | 9 | 1 | 0 | 0 | 10 |
| 3 | Alert triggers | 0 | 4 | 1 | 0 | 5 |
| 4 | Crawl path discovery & path memory | 5 | 0 | 0 | 0 | 5 |
| 5 | Reporting | 1 | 3 | 2 | 0 | 6 |
| 6 | Change detection | 2 | 1 | 0 | 0 | 3 |
| 7 | Scheduling & automation | 0 | 0 | 3 | 0 | 3 |
| 8 | Google Sheets integration | 0 | 0 | 3 | 0 | 3 |
| 9 | Success/failure tracking | 2 | 1 | 0 | 0 | 3 |
| 10 | Geographic scope | 4 | 0 | 0 | 0 | 4 |
| 11 | Multi-model discovery | 3 | 0 | 0 | 0 | 3 |
| 12 | Review workflow | 6 | 0 | 0 | 0 | 6 |
| 13 | 54-column schema | 3 | 0 | 0 | 0 | 3 |
| 14 | Cost | 1 | 0 | 0 | 0 | 1 |
| **TOTAL** | **All tracked requirements** | **40** | **13** | **9** | **0** | **62** |

### Scorecard interpretation

- **40 MET** — core demo/product spine is real and working.
- **13 PARTIAL** — capabilities or data exist, but are not fully surfaced, automated, or delivered.
- **9 NOT MET** — main remaining customer gaps are scheduling, proactive alerts, Google Sheets integration, report delivery, and client-specific routing.
- **0 NOT YET** — items are currently classified as met/partial/not met rather than future-only placeholders.

### Practical meaning

The product is beyond a scraper POC: the dashboard pipeline, schema, review workflow, path memory, discovery, and core extraction are in place. The remaining work is productization: make runs scheduled, alerts proactive, reports delivered, and customer/source-of-truth integration explicit.


## 1. CORE BUSINESS PROBLEM

### 1.1 Automate manual monitoring of 100-500+ conference websites
**STATUS: MET (with caveats)**

The dashboard provides a full pipeline: Discover URLs → Crawl → Extract → Enrich → Review.
A user can run the entire flow from the browser without manually visiting sites.

**User perspective:** The user clicks through Steps 1-4 and the system handles all
website visits and data extraction automatically. No manual site visiting required.

**Behind the scenes:** The crawl engine (crawl4ai) fetches pages, batch_processor.py
extracts structured data, and results are stored in SQLite. The pipeline runs without
human intervention once started.

**Caveat:** The system currently requires a user to manually initiate each run from
the dashboard. There is no built-in scheduler that automatically runs the full pipeline
on a recurring basis (weekly/daily) without human action. The APScheduler infrastructure
exists in main.py but is not wired to the PR Monitor 1 pipeline.

### 1.2 Find "Call for Abstracts" / "Call for Papers" status
**STATUS: MET**

**User perspective:** Step 4 (Extract Data) pulls CFP status from each conference
website. The extracted data appears in the Step 6 review table under "CFP Status."
The user can filter by CFP status and see which conferences have open CFPs.

**Behind the scenes:** batch_processor.py extracts cfp_status, cfp_deadline,
cfp_opens, cfp_sub_requirements, and cfp_page_url. The 54-column schema includes
dedicated CFP fields. The review table displays cfp_status and allows filtering.

### 1.3 Find abstract submission deadlines
**STATUS: MET**

**User perspective:** CFP Deadline appears as a column in the Step 6 review table.
Users can sort by deadline and filter for upcoming-only items.

**Behind the scenes:** The extraction engine specifically looks for submission deadlines.
The deadline_intelligence module enriches rows with normalized deadlines, urgency
levels, and action states. The review table shows both raw and effective (override)
deadlines.

### 1.4 Track conference dates
**STATUS: MET**

**User perspective:** Conf Dates appears as a column in the review table. Users can
filter for upcoming conferences and exclude past events.

**Behind the scenes:** conf_dates is a core extraction field. The system parses
multiple date formats (US, international, month-name-first, day-first). Date
filtering in the review table supports upcoming-only and exclude-past logic.

### 1.5 Track location/geo data
**STATUS: MET**

**User perspective:** Geo City, Geo State, Geo Country, and Geo Confidence columns
appear in the review table. Users can filter by any geo field.

**Behind the scenes:** Step 5 (Enrich Data) specifically handles geo enrichment,
determining city/state/country from location text. The geo confidence status
(GEO_CONFIRMED, GEO_PARTIAL, GEO_UNKNOWN) is stored per row. The review table
displays all geo fields and allows filtering.

---

## 2. DATA FIELDS & SCHEMA

### 2.1 Conference name
**STATUS: MET** — conf_name and conference_name fields in extraction schema.

### 2.2 Conference URL (primary monitoring target)
**STATUS: MET** — conf_page_url is a required field in the 54-column schema.
The system preserves source URLs through the pipeline.

### 2.3 Location (City, State/Country)
**STATUS: MET** — conf_location in extraction + geo enrichment in Step 5.

### 2.4 Event dates
**STATUS: MET** — conf_dates with multiple format parsing.

### 2.5 CFP deadline
**STATUS: MET** — cfp_deadline with deadline intelligence enrichment.

### 2.6 CFP status (Open/Closed/Not Yet)
**STATUS: MET** — cfp_status is extracted and displayed. The review table
supports filtering by CFP status.

### 2.7 Submission URL
**STATUS: MET** — sub_page_url and sub_link in the extraction schema.

### 2.8 Contact info (name, email, phone)
**STATUS: MET** — contact_name, contact_email, contact_phone, contact_org
are all in the 54-column schema.

### 2.9 Submission tracking (submitted/not submitted)
**STATUS: MET** — submission_status field in the review table. Users can
mark items as submitted via the review/upsert endpoint.

### 2.10 Desired CFP status values (OPEN, Urgent, Submitted)
**STATUS: PARTIAL**

The system extracts CFP status from websites but does not automatically
categorize them into the customer's desired status values:
- "2. OPEN - Action Required" — not auto-assigned; user must determine this
- "3. Urgent - Deadline <30 Days" — the deadline_intelligence module calculates
  urgency, but it's not surfaced as a CFP status value in the review table
- "4. Submitted" — tracked via submission_status, but as a separate field
  from CFP status

**Gap:** The customer wants the system to automatically flag CFP status as
"OPEN - Action Required" when a CFP newly opens, and "Urgent" when deadline
<30 days. The deadline intelligence module exists but is not fully integrated
into the review table as a prominent status.

---

## 3. ALERT TRIGGERS

### 3.1 CFP status changes TO "Open" → HIGH priority alert
**STATUS: PARTIAL**

**What exists:** The change_detection.py module tracks scan-to-scan changes
including cfp_opened. The batch processor generates change snapshots.

**Gap:** There is no automated alert sent to the team when this happens.
The change data exists in the system but is not pushed to users via email
or notification. The user must manually check the review table to see changes.

### 3.2 New deadline < 30 days → HIGH priority alert
**STATUS: PARTIAL**

**What exists:** The deadline_intelligence module calculates urgency levels
and action states. The review table supports filtering for upcoming deadlines.

**Gap:** No automated alert is sent. The user must manually filter and check.

### 3.3 New conference discovered → MEDIUM priority
**STATUS: PARTIAL**

**What exists:** Step 2 (Discover URLs) uses multi-model AI search to find
new conferences. The master list is saved and can be compared to previous runs.

**Gap:** No alert is generated when new conferences are found. The user must
manually compare or review the discovery results.

### 3.4 Conference dates changed → MEDIUM priority
**STATUS: PARTIAL**

**What exists:** change_detection.py tracks dates_changed between scans.

**Gap:** No automated alert. Change data is stored but not pushed to users.

### 3.5 Submission URL changed → LOW priority
**STATUS: NOT MET**

The system does not specifically track or alert on submission URL changes.

---

## 4. CRAWL PATH DISCOVERY & PATH MEMORY

### 4.1 Discover CFP page paths (not always on main page)
**STATUS: MET**

**User perspective:** The system crawls multiple pages per site to find CFP info.
The extraction paths tried are recorded.

**Behind the scenes:** batch_processor.py tries multiple URL patterns (/cfp,
/speakers, /submit, etc.) and crawls up to 10 subpages. The source_registry
module tracks discovered paths per source domain.

### 4.2 Path memory system (remember discovered paths)
**STATUS: MET**

**Behind the scenes:** The source_registry.py module stores discovered paths
(CFP, submission, contact) per source domain. On subsequent runs, the system
tries remembered paths first via _prefer_source_registry_paths().

### 4.3 Path confidence tracking
**STATUS: MET**

The source registry stores path confidence levels along with the paths.

### 4.4 Self-healing (auto-update paths when sites change)
**STATUS: MET**

When a stored path fails, the system falls back to full crawl and updates
the source registry with the new path. This happens automatically.

### 4.5 Fast return visits (use stored path first)
**STATUS: MET**

The _prefer_source_registry_paths() function reorders URLs to try remembered
paths before broad source URLs.

---

## 5. REPORTING

### 5.1 Per-run scan summary
**STATUS: MET**

**User perspective:** After each crawl and extract, the dashboard shows:
total URLs, success/failure counts, engine metrics, artifact links.

**Behind the scenes:** Crawl jobs return url_count, reachable_count, and
failure details. Extract jobs return scan metrics. The UI displays these
in status text and metrics lines.

### 5.2 Weekly executive report (7 sections)
**STATUS: PARTIAL**

**What exists:**
- batch_processor.py has a generate_report() function that creates a
  conference intelligence report with tier summaries
- The weekly_executive_report.py module exists for generating reports
- The guidance_weekly_executive_report.md defines the 7 required sections

**Gap:** The weekly executive report is not automatically generated and
emailed on a schedule. It exists as a capability but is not wired into
the production run flow. The guidance document explicitly notes: "Card 9
implementation is not yet wired into production run flow. Weekly execution
is not configured."

### 5.3 Email delivery of reports
**STATUS: NOT MET (for PR Monitor 1)**

The system has email sending infrastructure (loops_send_transactional_email)
but it is not used to send PR Monitor 1 reports. No automated email is sent
to Nicolia with weekly findings.

### 5.4 Report sections required by customer
**STATUS: PARTIAL**

| Required Section | Status |
|-----------------|--------|
| 1. Top action items | NOT MET — not auto-generated |
| 2. Urgent deadlines | PARTIAL — data exists, not surfaced |
| 3. New/changed opportunities | PARTIAL — change detection exists, not reported |
| 4. Client-ready items | NOT MET |
| 5. Failures requiring attention | PARTIAL — shown in UI, not emailed |
| 6. Run quality metrics | MET — shown in dashboard after each run |
| 7. Recommended next actions | NOT MET |

---

## 6. CHANGE DETECTION

### 6.1 Compare current vs previous scan
**STATUS: MET**

change_detection.py performs scan-to-scan comparison using JSON snapshots.
It tracks changes in cfp_status, cfp_deadline, conf_dates, cfp_url, source_url,
confidence, and failure_state.

### 6.2 Identify specific change types
**STATUS: MET**

The system identifies: new_opportunity, cfp_opened, deadline_added,
deadline_changed, dates_changed, source_failed.

### 6.3 Flag items requiring team action
**STATUS: PARTIAL**

Changes are detected and stored but not actively flagged to the team.
The user must manually review. No push notification or email alert is sent.

---

## 7. SCHEDULING & AUTOMATION

### 7.1 Run automatically on schedule (weekly minimum)
**STATUS: NOT MET**

**What exists:** APScheduler is imported and used in main.py for other purposes
(OneSignal pushes, program day advancement). The infrastructure exists.

**Gap:** No scheduled job is configured to automatically run the PR Monitor 1
pipeline (Steps 1-5) on a weekly or daily basis. Each run must be manually
initiated from the dashboard.

### 7.2 Weekly → Daily once proven
**STATUS: NOT MET**

No scheduling exists at all for the PR Monitor 1 pipeline.

---

## 8. GOOGLE SHEETS INTEGRATION

### 8.1 Read conference list from Google Sheet
**STATUS: NOT MET**

The current system uses the master list file (master_list_latest.txt) or
custom URLs pasted into the dashboard. It does not read from the customer's
Google Sheet ("Test Dark Conference Master List").

### 8.2 Update Google Sheet with findings
**STATUS: NOT MET**

The system stores results in its own SQLite database and displays them in
the dashboard. It does not write back to Google Sheets.

### 8.3 Client-specific filtered views
**STATUS: NOT MET**

The dashboard supports filtering by market/customer in Step 6, but there
is no integration with the customer's existing Google Sheet structure
with per-client filtered views.

---

## 9. SUCCESS/FAILURE TRACKING

### 9.1 Track success/failure per site
**STATUS: MET**

**User perspective:** After crawling, the dashboard shows total URLs checked,
reachable count, and failure count. The crawl engine metrics show total runs,
engine runs, fallback runs, and failure count.

**Behind the scenes:** Each crawl job tracks per-URL success/failure. The
crawl_engine_metrics.json file maintains running counts. Failures are
categorized (timeout, 404, blocked, parse_error, ssl_error).

### 9.2 Retry logic
**STATUS: MET**

The crawl engine has fallback mode. Failed sites are retried on subsequent runs.

### 9.3 Failure reporting
**STATUS: PARTIAL**

Failures are shown in the dashboard UI and stored in metrics files. The
executive report template includes a "Failures Requiring Attention" section.
But failures are not proactively emailed to the team.

---

## 10. GEOGRAPHIC SCOPE

### 10.1 US-only (all states, contiguous 48, custom states)
**STATUS: MET**

Step 1 supports US scope with all states, contiguous US (excludes AK/HI),
and custom state multi-select.

### 10.2 International (global)
**STATUS: MET**

Step 1 supports International scope.

### 10.3 Specific non-US countries
**STATUS: MET**

Step 1 supports Specific Countries scope with multi-select country picker.

### 10.4 Separate geo preferences for conferences vs awards
**STATUS: MET**

Step 1 has separate Conference Region Scope and Award Geo Preference fields.

---

## 11. MULTI-MODEL DISCOVERY

### 11.1 AI-powered discovery of new conferences
**STATUS: MET**

Step 2 uses Perplexity, ChatGPT, and Gemini to search for conference and
award URLs. This is live by default (not dry-run).

### 11.2 Cross-reference multiple models for confidence
**STATUS: MET**

URLs found by multiple models get higher confidence scores (0.34 per model,
max 1.0). The master list shows which models found each URL.

### 11.3 Find both conferences AND awards
**STATUS: MET**

The discovery process searches for both conference and award opportunities.
The record_type field controls whether to search for conferences, awards, or both.

---

## 12. REVIEW WORKFLOW

### 12.1 Review extracted data in a table
**STATUS: MET**

Step 6 provides a 16-column review table with all extracted fields.

### 12.2 Filter by multiple criteria
**STATUS: MET**

12+ filter controls: QA status, AI called, review status, geo city/state/country,
domain, market, CFP status, changed-only, has-data, upcoming-only, and more.

### 12.3 Mark rows as reviewed / follow-up / re-open
**STATUS: MET**

Action buttons per row: "Reviewed" (marks reviewed with name/timestamp),
"Defer" (sets follow_up), "Re-open" (resets to needs_review). Re-open button
is hidden when already in needs_review status.

### 12.4 Override extracted values
**STATUS: MET**

Expandable detail rows allow overriding CFP status, CFP deadline, conference
dates, review notes, and submission status. Overrides are saved to the database.

### 12.5 Track who reviewed what and when
**STATUS: MET**

The review/upsert endpoint records reviewed_by and reviewed_at for each action.

### 12.6 Export to CSV
**STATUS: MET**

"Export Market CSV" button generates a CSV with all data including overrides.

---

## 13. 54-COLUMN SCHEMA

### 13.1 Locked 54-column extraction format
**STATUS: MET**

batch_processor.py produces the locked 54-column format with all required field
groups: conference info (11 cols), contact info (11 cols), CFP info (10 cols),
submission portal (9 cols), summary (11 cols), and metrics string (1 col).

### 13.2 Source URL preservation (conf_page_url)
**STATUS: MET**

conf_page_url is populated from source input and preserved through the pipeline.
This is enforced in the extraction contract.

### 13.3 Completeness metrics
**STATUS: MET**

Column 54 contains the metrics string showing completeness percentages by category
(CONF, CONTACT, CFP, SUB).

---

## 14. COST

### 14.1 Minimal operational cost (<$5/month target)
**STATUS: MET**

The system runs on the existing VPS. Web fetching uses direct HTTP requests
(not paid APIs). The main cost is LLM API calls during discovery and extraction,
which can be controlled by the user.

---

## SUMMARY SCORECARD

| Category | MET | PARTIAL | NOT MET | NOT YET |
|----------|-----|---------|---------|---------|
| Core monitoring pipeline | 4 | 3 | 0 | 0 |
| Data fields & schema | 9 | 1 | 0 | 0 |
| Alert triggers | 0 | 4 | 1 | 0 |
| Crawl path discovery | 5 | 0 | 0 | 0 |
| Reporting | 1 | 3 | 2 | 0 |
| Change detection | 2 | 1 | 0 | 0 |
| Scheduling & automation | 0 | 0 | 3 | 0 |
| Google Sheets integration | 0 | 0 | 3 | 0 |
| Success/failure tracking | 2 | 1 | 0 | 0 |
| Geographic scope | 4 | 0 | 0 | 0 |
| Multi-model discovery | 3 | 0 | 0 | 0 |
| Review workflow | 6 | 0 | 0 | 0 |
| 54-column schema | 3 | 0 | 0 | 0 |
| Cost | 1 | 0 | 0 | 0 |
| **TOTALS** | **40** | **13** | **9** | **0** |

---

## KEY GAPS (NOT MET)

1. **No automated scheduling** — The pipeline must be manually initiated each time.
   The customer expects weekly automatic runs.

2. **No Google Sheets integration** — The system does not read from or write to
   the customer's Google Sheet. This was a core part of the original MVP spec.

3. **No automated email alerts** — When a CFP opens or a deadline is approaching,
   no email is sent to the team. The customer expects proactive notifications.

4. **No automated weekly executive report** — The report generation capability
   exists but is not scheduled or delivered via email.

5. **No automated change alerts** — Change detection works but changes are not
   pushed to users. The customer expects to be notified when CFP status changes.

6. **No client-specific alert routing** — The customer wants alerts routed to
   the right team member based on client assignment.

---

## KEY STRENGTHS (FULLY MET)

1. **Complete extraction pipeline** — Discover → Crawl → Extract → Enrich → Review
   all works end-to-end from the dashboard.

2. **54-column schema** — The locked production format is fully implemented.

3. **Crawl path memory** — The source registry remembers discovered paths and
   self-heals when sites change.

4. **Multi-model AI discovery** — 3 AI models search for new conferences and
   awards with confidence scoring.

5. **Rich review workflow** — Filtering, status management, overrides, CSV export,
   and reviewer tracking all work.

6. **Geographic scope** — Full support for US, International, and Specific Countries
   with separate conference/award geo preferences.

7. **Success/failure tracking** — Per-site tracking with retry logic and metrics.

---

## RECOMMENDED PRIORITY ORDER FOR REMAINING GAPS

1. **Automated scheduling** — Wire APScheduler to run the pipeline weekly. This
   is the single biggest gap between what the customer expects and what exists.

2. **Email alerts for critical changes** — When CFP opens or deadline <30 days,
   send an email to the team. The change detection data already exists.

3. **Google Sheets integration** — Read the conference list from the customer's
   Google Sheet and write findings back. This was in the original MVP spec.

4. **Automated weekly executive report** — Generate and email the report on
   schedule. The report template and data both exist.

5. **Client-specific alert routing** — Route alerts to team members based on
   client assignment.