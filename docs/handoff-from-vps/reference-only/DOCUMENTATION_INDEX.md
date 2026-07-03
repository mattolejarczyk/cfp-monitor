# PROJECT DOCUMENTATION INDEX
## PR Firm Texas - Complete File Reference

**Project:** Conference Monitoring & Intelligence for PR Firm  
**Location:** `projects/PR_Firm_Texas/`  
**Last Updated:** June 2, 2026

---

## RECENT UPDATE (June 2, 2026)

Custom-URL crawl feature and validation work is complete and documented.

- Process runbook updates: `PR_MONITOR_1_RUNBOOK.md`
- Endpoint request/response contracts and env-backed path settings: `PR_MONITOR_1_ENDPOINT_CONTRACTS.md`
- 54-column process/contract updates: `PROCESS_DOCUMENTATION.md`
- Validation evidence and test outcomes: `TEST_REPORT.md`

Validation completed:
- `custom_urls` end-to-end crawl + extract
- Negative URL parsing inputs (blank/duplicate/invalid)
- Guardrail (`use_master_list=false` + no URLs => HTTP 400)
- Master-list regression (`use_master_list=true` unchanged)

---

## CORE DOCUMENTATION FILES

### 0. PR_FIRM_TX_PROJECT_ARCHITECTURE_HANDOFF_2026-06-05.md ⭐ CONSOLIDATED HANDOFF
**Purpose:** Single-page-plus technical handoff covering the business context, current PR Monitor 1 workflow, dashboard architecture, key code areas, runtime contracts, artifacts, QA status, and known risks.

**When to Use:**
- Answering "what is this project and how does it work?"
- Handing the project to another agent/developer
- Quickly locating the current architecture/code entry points
- Preparing for a client demo or technical review

### 0. HERMES_VOC_HANDOFF_NICOLIA.md ⭐ VOICE OF CUSTOMER
**Purpose:** Direct voice-of-customer handoff for Hermes, including Nicolia call source files, direct quotes, pain points, manual workflow, and VOC-driven product requirements.

**When to Use:**
- Giving Hermes direct customer context
- Preserving Nicolia's language in product/UX/architecture decisions
- Checking whether a proposed feature solves the actual customer workflow

### 0. PR_MONITOR_1_RUNBOOK.md ⭐ CURRENT PRODUCTION FLOW
**Purpose:** Definitive runbook for the Step 1-5 PR Monitor workflow now running in dashboard.  
**Contents:**
- Final macro process (Create Prompt -> Discover -> Crawl -> Extract -> Review)
- Live discovery mode behavior (Step 2 no longer dry-run default)
- Async job architecture for Step 3/4
- Crawl engine reliability controls and metrics
- Proactive fallback alerting and alert-log paths
- Artifact link endpoints and path-safety constraints
- Best-practice ops rules for reliability + repeatability

**When to Use:**
- Operating the current dashboard flow end-to-end
- Troubleshooting job status/progress issues
- Reliability/incident response for crawl engine fallback
- Onboarding future contributors to current architecture

### 0. PROJECT_OVERVIEW.md ⭐ START HERE
**Purpose:** Meta-level project explanation, high-level process, invocation guide  
**Contents:**
- What this project is (elevator pitch)
- High-level 5-phase process
- Key concepts (CFP, 4 Tiers, 53 Columns)
- How to invoke the project
- Expected inputs/outputs
- Example invocation scenarios

**When to Use:**
- First time engaging with project
- Need to understand "what is this thing?"
- Want to know how to invoke extraction
- Need context before providing conference URLs

---

### 1. MASTER_TRACKING.md
**Purpose:** Master tracker for all conference extraction batches  
**Contents:**
- Batch 1-3+ status tracking (11 / 100 / 500+ conferences)
- Row-by-row completion status
- URLs and extraction results
- Scale clarification (sample vs. full list)
- Quick resume instructions

**When to Use:**
- Check which rows are complete/pending
- Find reference to source data
- Understand scale (11 sample vs 500+ total)

---

### 2. PROCESS_DOCUMENTATION.md
**Purpose:** Complete extraction and reporting process specification  
**Contents:**
- **54 column definitions** (53 data + 1 metrics column)
- **CRITICAL: conf_page_url MUST be populated from source file** (Column C)
- **Column 54 (metrics) calculation rules** - CONF/CONTACT/CFP/SUB percentages
- Column 52 (notable_info) guidelines
- Column 53 (crawl_notes) guidelines
- 6-Phase process flow (Discover → Extract → Aggregate → Validate → Deliver → Report)
- Status definitions (VALUE_FOUND, PLACEHOLDER_FOUND, UNAVAILABLE)
- Cost tracking guidelines
- Quality thresholds
- **Phase 6: Report Generation** - Date validation, 4-tier categorization, template usage, email delivery

**When to Use:**
- Column reference during extraction
- Process flow guidance
- Report generation instructions
- Understanding status values

**Note:** For the new PR Monitor 1 dashboard runtime architecture and job orchestration, use `PR_MONITOR_1_RUNBOOK.md`.

---

### 3. REPORT_TEMPLATE.md
**Purpose:** Standardized template for executive intelligence reports  
**Contents:**
- Complete report structure with ASCII formatting
- Section-by-section template
- 4-Tier criteria definitions
- Formatting rules (no markdown, row numbers in parentheses)
- Example entry reference
- Delivery instructions

**When to Use:**
- Generating new executive reports
- Ensuring consistent formatting
- Training on report structure

---

### 4. QUICK_RESUME.md
**Purpose:** One-page session continuity reference  
**Contents:**
- Last session date and context
- What was accomplished (Batch 1 complete)
- Current status (awaiting Batch 2)
- Key findings summary
- File locations
- How to resume Batch 2

**When to Use:**
- Picking up after session break
- Quick context refresh
- Finding key files quickly

---

## REFERENCE DATA FILES

### 5. REFERENCE_BATCH1_10_CONFERENCES_53COLUMNS.csv
**Purpose:** Fresh reference copy of completed Batch 1 extraction  
**Contents:**
- 10 conferences, 54 columns (53 + metrics)
- 15KB file size
- All extractions complete
- Per-row metrics (CONF/CONTACT/CFP/SUB breakdown)
- Date-validated categorization

**When to Use:**
- Batch 2 template matching
- Column format validation
- Metrics calculation reference
- CFP categorization examples

---

### 6. batch1_all_10_conferences_with_metrics.csv
**Purpose:** Working copy of Batch 1 with metrics  
**Contents:**
- Same as REFERENCE file
- Active working version
- Used for report generation

**When to Use:**
- Generating reports
- Analysis and metrics

---

## SOURCE & INPUT FILES

### 7. Source: media/inbound/file_81---37295934-c2c6-4712-8df1-1b6d9c16c4e2.csv
**Purpose:** Original master list from Matt (11 conference sample)  
**Contents:**
- 11 rows (Type, Conference, URL, Location, Dates, etc.)
- 18 columns of source data
- Used as input for Batch 1 extraction

**When to Use:**
- Reference for Batch 1 URLs
- Understanding source data structure

---

## IMPLEMENTATION / CODE FILES

### 8. batch_processor.py ⭐ THE LOCKED PROCESS
**Purpose:** Universal batch processor - THE ONLY SCRIPT TO USE  
**Status:** LOCKED - Production-ready, handles all batches  
**Contents:**
- Reads any CSV with CONFERENCE URL column
- Extracts all conferences with LLM
- Generates 54-column output with metrics
- Creates executive report
- Error handling for failed extractions

**Usage:**
```bash
python3 batch_processor.py --input <CSV> --output <PREFIX>
```

**When to Use:**
- **ALWAYS** - This is THE process for all batches
- Replaces all individual row scripts
- Handles 3 to 500+ conferences

**Generates:**
- {PREFIX}_CONFERENCES_54COLUMNS.csv
- {PREFIX}_EXECUTIVE_REPORT.txt
- {PREFIX}_results.json

---

### 9. BATCH_PROCESSOR_QUICKREF.md
**Purpose:** Quick reference guide for batch processor  
**Contents:**
- One-line usage examples
- Input/output specifications
- Troubleshooting guide
- Example sessions

**When to Use:**
- Quick command reference
- Troubleshooting issues
- Onboarding to the process

---

### 10. rows_4_11_batch.py (LEGACY)
**Purpose:** Batch processing script for rows 4-10 (Batch 1 only)  
**Status:** DEPRECATED - Use batch_processor.py instead  

---

### 11. Individual Row Scripts (LEGACY)
- `row2_ssg_dubai.py`
- `row3_decarb_uk.py`
- `ablc_52_column_extractor.py`
- `ablc_52_col_skip_delegates.py`

**Purpose:** Single-conference extraction scripts  
**When to Use:**
- Reference for one-off extractions
- Understanding crawler implementation

---

## ANALYSIS & REPORTS

### 10. rows_4_11_eight_conferences.csv
**Purpose:** Raw output from batch processing script  
**Contents:**
- Rows 4-10 extraction results
- 53 columns per conference

---

### 11. batch1_rows_1_2_3_combined.csv
**Purpose:** Intermediate consolidation (rows 1-3)  
**Contents:**
- Rows 1-3 combined
- Used before full 10-row consolidation

---

## LEGACY / ARCHIVE

### 12. Other Files in Directory
- `conference_crawler_mvp1.py` - Early crawler version
- `conference_monitor_enhanced.py` - Enhanced version with fixes
- `all_conferences.json` - JSON output format
- Various test files and logs

---

## DOCUMENTATION HIERARCHY

```
START HERE (New Session):
├── QUICK_RESUME.md → Context refresh
├── MASTER_TRACKING.md → Check status
└── PROCESS_DOCUMENTATION.md → Process reference

DURING EXTRACTION:
├── BATCH_PROCESSOR_QUICKREF.md → Command reference
├── batch_processor.py → Run extraction
└── REFERENCE_BATCH1_10_CONFERENCES_53COLUMNS.csv → Format template

REPORT GENERATION:
├── REPORT_TEMPLATE.md → Format template
├── PROCESS_DOCUMENTATION.md → Phase 6 instructions
└── batch1_all_10_conferences_with_metrics.csv → Data source

QUALITY ASSURANCE:
├── PROCESS_DOCUMENTATION.md → Status definitions, thresholds
├── REFERENCE_BATCH1_10_CONFERENCES_53COLUMNS.csv → Reference data
└── MASTER_TRACKING.md → Completion verification
```

---

## FILE STATISTICS

| File Type | Count | Total Size |
|-----------|-------|------------|
| Documentation (.md) | 6 | ~32KB |
| Documentation (.html) | 6 | ~60KB |
| Reference CSV | 3 | ~45KB |
| Python Scripts (1 LOCKED) | 1 primary + legacy | ~70KB |
| Source/Input | 1 | ~5KB |
| **Total** | **17+** | **~210KB** |

---

## CONFIRMATION CHECKLIST

✅ REPORT_TEMPLATE.md created - Standardized executive report format  
✅ PROCESS_DOCUMENTATION.md updated - Phase 6: Report Generation added  
✅ All files documented with purpose and usage guidelines  
✅ Documentation hierarchy established  
✅ File statistics compiled  

---

*Index Version: 1.0*  
*Created: March 7, 2026*
