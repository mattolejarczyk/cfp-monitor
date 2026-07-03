
# 54-Column Extraction Process Documentation

**Version:** 1.1  
**Date:** March 7, 2026  
**Purpose:** Universal conference extraction format (53 data columns + 1 metrics column)

## Update: PR Monitor 1 Runtime Architecture (May 31, 2026)

This document remains authoritative for 54-column extraction format and reporting rules.

For the **current dashboard process orchestration** (Step 1-5 flow, async jobs, crawl engine metrics, fallback alerting, artifact endpoints), use:

- `projects/PR_Firm_Texas/PR_MONITOR_1_RUNBOOK.md`

Summary of the current orchestration:
- Step 2 discovery is live-mode default (no dry-run lock by default).
- Step 3/4 run asynchronously with job polling:
  - `GET /api/pr-monitor-1/job/{job_id}`
- Crawl engine fallback is tracked and proactively alerted.

## Update: Custom URL Crawl Path + QA Contract (June 2, 2026)

PR Monitor Step 3 (`POST /api/pr-monitor-1/crawl`) now supports a direct custom URL path for fast end-to-end testing without running multi-model discovery.

- URL source precedence:
  1. `custom_urls`
  2. `urls` (alias)
  3. `urls_text`
  4. master list only when `use_master_list=true`
- Guardrail:
  - If all URL inputs are empty and `use_master_list=false`, API returns `HTTP 400` (no silent fallback).
- Parsing behavior:
  - Mixed input (blank lines, duplicates, invalid tokens) is normalized to valid unique `http/https` URLs.
- Runtime input contract:
  - This endpoint is currently `Form(...)` driven. Use form-encoded or multipart requests.
  - Raw JSON payloads can silently trigger default behavior and should not be used for validation unless endpoint parsing is changed.

Detailed runbook and validation examples:
- `projects/PR_Firm_Texas/PR_MONITOR_1_RUNBOOK.md`

---

## LOCKED PROCESS - USE BATCH PROCESSOR

**THE OFFICIAL PROCESS:** `batch_processor.py`

This documentation describes the 54-column format. **For execution, always use:**

```bash
python3 batch_processor.py --input <CSV_FILE> --output <PREFIX>
```

**Do NOT write custom scripts.** Do NOT use inline code. The batch processor is **locked** and handles:
- ✅ All 54 columns (including metrics)
- ✅ conf_page_url from source (Column A)
- ✅ 4-tier categorization
- ✅ Report generation
- ✅ Error handling

**Location:** `projects/PR_Firm_Texas/batch_processor.py`  
**Quick Reference:** `BATCH_PROCESSOR_QUICKREF.md`

---

## Critical Requirements

### Column A: conf_page_url - SOURCE MANDATORY

**The `conf_page_url` field MUST be populated from the source input file's "CONFERENCE URL" column (Column C in source CSV).**

This is the **seed URL** that initiated the extraction and must be preserved for:
- Reference back to source data
- Re-crawling if needed
- Audit trail

**Do NOT leave blank.** Extract from source file and populate directly.

---

## Column Definitions (All 54)

### Group 1: Conference Info (Main Page) - 11 columns

| Column | Description | Status Values |
|--------|-------------|---------------|
| conf_page_url | **FROM SOURCE** - Conference URL (Column C) | URL string - MUST populate from input |
| conf_name | Full conference name | VALUE_FOUND, PLACEHOLDER_FOUND, UNAVAILABLE |
| conf_name_found | Extraction status | VALUE_FOUND, PLACEHOLDER_FOUND, UNAVAILABLE |
| conf_dates | Event dates | string |
| conf_dates_found | Extraction status | VALUE_FOUND, PLACEHOLDER_FOUND, UNAVAILABLE |
| conf_location | City, State/Country | string |
| conf_location_found | Extraction status | VALUE_FOUND, PLACEHOLDER_FOUND, UNAVAILABLE |
| conf_description | Full description | string |
| conf_description_found | Extraction status | VALUE_FOUND, PLACEHOLDER_FOUND, UNAVAILABLE |
| conf_page_cost | API cost for this page | decimal (e.g., 0.001) |

### Group 2: Contact Info - 11 columns

| Column | Description | Status Values |
|--------|-------------|---------------|
| contact_page_url | Where contact found | URL string |
| contact_name | Person's name | string or N/A |
| contact_name_found | Extraction status | VALUE_FOUND, PLACEHOLDER_FOUND, UNAVAILABLE |
| contact_email | Email address | string or N/A |
| contact_email_found | Extraction status | VALUE_FOUND, PLACEHOLDER_FOUND, UNAVAILABLE |
| contact_phone | Phone number | string or N/A |
| contact_phone_found | Extraction status | VALUE_FOUND, PLACEHOLDER_FOUND, UNAVAILABLE |
| contact_org | Organization name | string or N/A |
| contact_org_found | Extraction status | VALUE_FOUND, PLACEHOLDER_FOUND, UNAVAILABLE |
| contact_page_cost | API cost | decimal |
| contact_paths_tried | URLs checked | semicolon-separated list |

### Group 3: CFP Info - 10 columns

| Column | Description | Status Values |
|--------|-------------|---------------|
| cfp_page_url | Where CFP info found | URL or UNAVAILABLE |
| cfp_status | Open/Closed/Unknown | string |
| cfp_status_found | Extraction status | VALUE_FOUND, PLACEHOLDER_FOUND, UNAVAILABLE |
| cfp_deadline | Submission deadline | date string or N/A |
| cfp_deadline_found | Extraction status | VALUE_FOUND, PLACEHOLDER_FOUND, UNAVAILABLE |
| cfp_opens | When CFP opens | date string or N/A |
| cfp_opens_found | Extraction status | VALUE_FOUND, PLACEHOLDER_FOUND, UNAVAILABLE |
| cfp_sub_requirements | Submission requirements | string or N/A |
| cfp_sub_requirements_found | Extraction status | VALUE_FOUND, PLACEHOLDER_FOUND, UNAVAILABLE |
| cfp_page_cost | API cost | decimal |
| cfp_paths_tried | URLs checked | semicolon-separated list |

### Group 4: Submission Portal - 9 columns

| Column | Description | Status Values |
|--------|-------------|---------------|
| sub_page_url | Submission page URL | URL or UNAVAILABLE |
| sub_link | Direct submission link | URL or N/A |
| sub_link_found | Extraction status | VALUE_FOUND, PLACEHOLDER_FOUND, UNAVAILABLE |
| sub_portal_name | Name of portal (EasyChair, etc.) | string or N/A |
| sub_portal_name_found | Extraction status | VALUE_FOUND, PLACEHOLDER_FOUND, UNAVAILABLE |
| sub_instructions | How to submit | string or N/A |
| sub_instructions_found | Extraction status | VALUE_FOUND, PLACEHOLDER_FOUND, UNAVAILABLE |
| sub_page_cost | API cost | decimal |
| sub_paths_tried | URLs checked | semicolon-separated list |

### Group 5: Summary - 11 columns

| Column | Description | Example |
|--------|-------------|---------|
| conference_name | Short display name | "ABLC 2026" |
| base_url | Root URL | "https://ablcevents.com/ablc/" |
| domain | Domain only | "ablcevents.com" |
| crawl_date | ISO timestamp | "2026-03-06T21:47:26Z" |
| total_cost | Sum of all page costs | 0.005 |
| fields_with_value | Count of VALUE_FOUND fields | 21 |
| fields_with_placeholder | Count of PLACEHOLDER_FOUND fields | 3 |
| fields_unavailable | Count of UNAVAILABLE fields | 27 |
| completeness_pct | Overall percentage | 43.1 |
| budget_exceeded | Boolean flag | False |
| fields_with_value | Count VALUE_FOUND | 21 |
| fields_with_placeholder | Count PLACEHOLDER_FOUND | 3 |
| fields_unavailable | Count UNAVAILABLE | 27 |
| completeness_pct | Percentage | 43.1 |
| budget_exceeded | Boolean | False |

### Column 54: metrics (Per-Category Completeness) - REQUIRED

**Purpose:** Quick visual summary of extraction completeness by category

**Format:**
```
CONF {found}/{total} ({pct}%), CONTACT {found}/{total} ({pct}%), CFP {found}/{total} ({pct}%), SUB {found}/{total} ({pct}%)
```

**Example:**
```
CONF 4/4 (100%), CONTACT 3/4 (75%), CFP 0/4 (0%), SUB 0/3 (0%)
```

**Calculation Rules:**
| Category | Fields Counted | Total |
|----------|---------------|-------|
| CONF | conference_name, conference_dates, conference_location, conference_description | 4 |
| CONTACT | contact_name, contact_email, contact_phone, contact_org | 4 |
| CFP | cfp_status, cfp_deadline, cfp_link, cfp_sub_requirements | 4 |
| SUB | sub_link, sub_portal_name, sub_instructions | 3 |

**Note:** CFP total = 4 if cfp_status is not "Unknown", otherwise 0 (no CFP found)

---

### Column 52: notable_info (End User Intelligence)

**Purpose:** Business insights for PR firm decision-making

**Include:**
- `[URGENT]` Time-sensitive info (deadlines ending soon)
- `[VERIFY]` Data conflicts or needs confirmation
- `[OPPORTUNITY]` Sponsor slots available, good timing
- `[DATA-GAP]` Missing critical info
- `[INTEL]` Competitive intelligence
- `[NOTE]` General observations

**Example:**
```
[URGENT] Early bird ends Jan 15 | [VERIFY] Sponsor email bounced | [INTEL] Shell, BP are platinum sponsors
```

### Column 53: crawl_notes (Technical Metadata)

**Purpose:** Debugging and optimization tracking

**Include:**
- Pages crawled vs attempted
- Time per page
- Errors encountered
- Retry attempts
- Version of crawler used

**Example:**
```
Pages: 7 crawled/8 attempted, Time: 4.2 min, Errors: delegates page timeout, Version: crawler_v2.1
```

---

## Process Flow (5-Phase)

### Phase 1: Discovery (Adaptive)
```
START with seed URL
  ↓
DISCOVER all linked pages (BFS crawl)
  ↓
CLASSIFY pages by type (main, agenda, speakers, fees, sponsors, venue, contact)
  ↓
PRIORITIZE by data density
```

**Page Size Handling:**
- `< 50K chars`: Standard 45s timeout
- `50K-100K chars`: Extended 90s timeout
- `> 100K chars`: Chunked extraction OR mark for manual review

### Phase 2: Extraction (Scalable)
```
FOR EACH page:
  ↓
EXTRACT with category-specific schema
  ↓
IF timeout/error → RETRY once with extended timeout
  ↓
IF still failing → LOG as EXTRACTION_FAILED, continue
  ↓
TAG fields: VALUE_FOUND / PLACEHOLDER_FOUND / UNAVAILABLE
```

### Phase 3: Aggregation
```
COMBINE all page results
  ↓
RESOLVE conflicts (prefer most detailed)
  ↓
NORMALIZE to 53-column schema
  ↓
CALCULATE completeness metrics
```

### Phase 4: Validation
```
CHECK minimum data threshold (name + dates + location)
  ↓
FLAG if < 30% completeness or critical fields missing
  ↓
VERIFY budget not exceeded
```

### Phase 5: Delivery
```
FORMAT: CSV with 53 columns
  ↓
DELIVER: Email with CSV + summary
```

---

## Status Definitions

| Status | Meaning | When to Use |
|--------|---------|-------------|
| **VALUE_FOUND** | Real data extracted | Actual content found on page |
| **PLACEHOLDER_FOUND** | Placeholder text | "TBD", "Coming soon", "N/A" |
| **UNAVAILABLE** | Field not present | Page exists but field not found |
| **EXTRACTION_FAILED** | Technical failure | Timeout, error, inaccessible |

---

## Cost Tracking

**Per-page estimates (GPT-4o-mini):**
- Main page: ~$0.001
- Contact page: ~$0.001
- CFP page: ~$0.001
- Fees page: ~$0.001
- **Total per conference: ~$0.005**

**Budget threshold:** Flag if > $0.50 per conference

---

## Quality Thresholds

| Metric | Minimum | Target |
|--------|---------|--------|
| Completeness | 30% | 60%+ |
| Critical fields (name/dates/contact) | 2/3 | 3/3 |
| Cost per conference | <$0.50 | <$0.01 |
| Extraction time | <10 min | <5 min |

---

## Phase 6: Report Generation (Executive Delivery)

### Step 1: Date Validation & Categorization

**Current Date Reference:** Use today's date for all calculations

**Four-Tier System:**

| Tier | Criteria | Action |
|------|----------|--------|
| **TIER 1** | `conf_dates` contains "2026" | 2026 Confirmed - High alert |
| **TIER 2** | `conf_dates` contains "2025" AND month >= current month | Likely 2026 - Monitor |
| **TIER 3** | `conf_dates` contains "2025" AND month < current month | Likely Past - Archive |
| **TIER 4** | No year in dates OR no dates | Uncertain - Investigate |

**Month Extraction:**
- Extract month from `conf_dates` field
- Compare against current month (e.g., March = 3)
- Example: "July 2025" with current month March → Tier 2 (7 >= 3)
- Example: "February 2025" with current month March → Tier 3 (2 < 3)

### Step 2: Generate Report Using Template

**Template File:** `REPORT_TEMPLATE.md`

**Required Sections:**
1. Executive Summary (4-tier counts)
2. Tier 1: 2026 Confirmed (chronological order)
3. Tier 2: Likely 2026
4. Tier 3: Likely Past
5. Tier 4: Uncertain
6. Key Contacts and Dates (Tiers 1-2, numbered list)
7. Likely Past or Void (Tiers 3-4)

**Each Entry Must Include:**
- Conference name with (Row #) suffix
- Dates and location
- Website URL (conf_page_url)
- CFP URL (cfp_page_url or "Not found")
- Contact URL (contact_page_url or "Not found")
- Contact info (if available)
- CFP status

### Step 3: Formatting Rules

**CRITICAL - No Markdown:**
- ❌ DO NOT use `**`, `*`, `_`, or other markup
- ✅ Use plain text only
- ✅ Row numbers in parentheses: "Conference Name (Row 5)"

**Section Headers:**
```
═══════════════════════════════════════════════════════════════════
SECTION TITLE
═══════════════════════════════════════════════════════════════════
```

### Step 4: Email Delivery

**Recipient:** mattolejarczyk70@gmail.com

**Subject Format:**
```
Conference Intel: [X] Targets - [Descriptor]
```

**Body:** Plain text only (no HTML, no attachments)

**Example Subject:**
```
Conference Intel: 10 Targets - Date-Validated Triage
```

### Step 5: Archive Report

**Save Copy To:**
```
projects/PR_Firm_Texas/reports/
├── YYYY-MM-DD_intel_report.txt
└── latest_intel_report.txt (symlink to most recent)
```

---

## Quick Reference

**File naming:** `row{N}_{short_name}_53_columns.csv`

**Tracker location:** `MASTER_TRACKING.md`

**Template location:** `REPORT_TEMPLATE.md`

**Source list:** `media/inbound/file_81---37295934-c2c6-4712-8df1-1b6d9c16c4e2.csv`

**Consolidated output:** `all_conferences_53_columns.csv` (when complete)

---

*Document version: 1.1*  
*Updated: March 7, 2026 - Added Phase 6: Report Generation*