
# Voice of the Customer — PR Monitor 1 Requirements Breakdown

## Source Documents
- Discovery call transcript: February 9, 2026 (Nicolia + Matt)
- Detailed customer requirements: March 5, 2026
- MVP1 conference monitoring spec: March 5, 2026
- Weekly executive report guidance: June 2026
- Project architecture handoff: June 5, 2026
- Process documentation (54-column schema): March 7, 2026

---

## 1. WHO THE CUSTOMER IS

**Nicolia** — President & Founder of PRIME|PR, a B2B tech PR firm in Austin, TX.
The firm serves dozens of clients across multiple industries (cybersecurity, hydrogen/clean energy, healthcare, legal tech, etc.). This is the primary customer contact and decision-maker.

---

## 2. THE CORE BUSINESS PROBLEM

The PR firm manually monitors **100-500+ conference websites on a weekly basis** to find speaking and award opportunities for their clients. With dozens of clients in different industries, this scales to hundreds of conferences.

**Current manual process (as described by Nicolia):**
1. Go to conference website (one of 100+ tracked conferences)
2. Check if "Call for Abstracts" / "Call for Papers" is open
3. Find the deadline for abstract submission
4. If new/updated: take URL, add to client-specific spreadsheet section
5. Submit speaking application for client
6. Mark as "submitted" in spreadsheet

**Pain points identified:**
- Time-consuming: 5+ seconds per site × 500+ sites = hours weekly
- Risk of missing deadlines (CFPs open/close without notice)
- Delayed client communication
- No systematic tracking of what was checked when
- Relies on a "very small list" of known conferences; new ones are discovered informally

**Scale:**
- 544+ conference entries in current Google Sheet
- 6+ clients with separate views
- Across industries: cybersecurity, hydrogen/clean energy, healthcare, legal tech, etc.

---

## 3. CUSTOMER QUOTES (Direct Voice)

> "We have to go every week to go look at their top conferences and then find when... they have updated the call for speakers yet."

> "When you've got dozens of clients all in different industries... now you're talking about hundreds of conferences."

> "The biggest issues there are one, finding the [conferences], making sure that the call for abstracts is open, updating the deadline for when those abstracts have to be delivered."

> "We just go to ChatGPT, put in a prompt for exactly what we're looking for, and let it search and it spits back 90% of what we're looking for."

> "If we were able to take the ChatGPT level kind of stuff and get AI to do this to not only find the new ones, but also go into our SQL database and check everything and constantly update for us. That's the key."

---

## 4. DATA THE CUSTOMER TRACKS

### Current Spreadsheet Columns (from Bioveritas test sheet):

| Field | Description | Critical? |
|-------|-------------|-----------|
| Conference Name | Full event name | Yes |
| Conference URL | Primary monitoring target | **PRIMARY** |
| Location | City, State/Country | Yes |
| Event Dates | When event occurs | Yes |
| Event Length | Duration description | No |
| Submission End | CFP deadline | **KEY FIELD** |
| Status Update | Current CFP status | **KEY FIELD** |
| Submission URL | Direct link to submit | Yes |
| Speaker/Abstracts Submitted | Tracking field | Yes |
| Notification Date | Acceptance notification | No |
| Contact Name | Event organizer contact | Yes |
| Email | Contact email | Yes |
| Phone | Contact phone | Yes |
| Overview | Long description | No |
| Notes | Internal notes | Yes |
| Login/PW | Credentials if needed | No |
| Source | Data source tag | No |
| Date Added | When entry created | No |

### Desired CFP Status Values (from requirements):

| Status | Meaning | Action |
|--------|---------|--------|
| 1. Closed | CFP not currently open | Continue monitoring |
| 1. Closed - Awaiting Details | CFP closed, waiting for next cycle | Continue monitoring |
| 1. Closed - Must be Exhibitor/Sponsor | Speaking requires sponsorship | Evaluate sponsorship |
| **2. OPEN - Action Required** | CFP newly opened | **Submit immediately** |
| **3. Urgent - Deadline <30 Days** | Deadline approaching fast | **Urgent submission** |
| **4. Submitted** | Application submitted | Track |

### Desired New Status Values (Phase 2):
- 2. OPEN - Action Required (CFP newly opened - submit immediately)
- 3. Urgent - Deadline <30 Days (deadline approaching fast)
- 4. Submitted (application submitted)

---

## 5. ALERT TRIGGERS (When Team Action Required)

These are the specific events that should trigger an alert:

| Trigger | Priority | Team Action |
|---------|----------|-------------|
| CFP status changes TO "Open" (was "Closed" or "Not Yet") | **HIGH** | Submit client speaking application immediately |
| New deadline discovered < 30 days away | **HIGH** | Urgent submission needed - rush application |
| New conference discovered (not in current list) | MEDIUM | Evaluate for client fit, add to tracking |
| Conference dates changed | MEDIUM | Update client calendar and planning |
| Submission URL changed | LOW | Update bookmark/submission link |

---

## 6. CRAWL PATH DISCOVERY REQUIREMENTS

Nicolia specifically identified that CFP information is often NOT on the main page:

> "Often the information will not be available on the main page and that a person will have to crawl all of the webpages to find the correct information... Each website is going to have a completely different structure than the next, but once the path is discovered to the information it should be easier to find using the path that was discovered."

**Required: Path Memory System**

| Component | Purpose | Storage |
|-----------|---------|---------|
| CFP_PAGE_PATH | Discovered URL path to CFP info (e.g., "/call-for-papers", "/speakers") | New column or JSON state file |
| PATH_CONFIDENCE | Reliability of path (High/Medium/Low) | Stored with path data |
| LAST_PATH_CHECK | When path was last verified | Timestamp |

**Required Crawl Strategy:**

*First Visit (Discovery):*
1. Check main page
2. Try common CFP patterns (/cfp, /speakers, /submit, etc.)
3. If not found: Crawl up to 10 most relevant subpages
4. Store discovered path for future visits

*Return Visits (Fast Path):*
1. Try stored path first
2. If path works: Extract data quickly (~2 seconds)
3. If path fails: Fall back to full crawl + update stored path

*Self-Healing:*
- System automatically updates paths when sites change
- Zero manual maintenance required

---

## 7. 54-COLUMN EXTRACTION SCHEMA (Locked Production Format)

The customer requires a standardized 54-column output (53 data columns + 1 metrics column). This is the production-grade schema:

### Group 1: Conference Info (11 columns)
- conf_page_url (FROM SOURCE - must not be blank)
- conf_name + conf_name_found
- conf_dates + conf_dates_found
- conf_location + conf_location_found
- conf_description + conf_description_found
- conf_page_cost

### Group 2: Contact Info (11 columns)
- contact_page_url, contact_name + found, contact_email + found
- contact_phone + found, contact_org + found, contact_page_cost
- contact_paths_tried

### Group 3: CFP Info (10 columns)
- cfp_page_url, cfp_status + found, cfp_deadline + found
- cfp_opens + found, cfp_sub_requirements + found
- cfp_page_cost, cfp_paths_tried

### Group 4: Submission Portal (9 columns)
- sub_page_url, sub_link + found, sub_portal_name + found
- sub_instructions + found, sub_page_cost, sub_paths_tried

### Group 5: Summary (11 columns)
- conference_name, base_url, domain, crawl_date, total_cost
- fields_with_value, fields_with_placeholder, fields_unavailable
- completeness_pct, budget_exceeded

### Column 54: Metrics String
- Format: `CONF {found}/{total} ({pct}%), CONTACT {found}/{total} ({pct}%), CFP {found}/{total} ({pct}%), SUB {found}/{total} ({pct}%)`

### Notable Info Field (Column 52):
- `[URGENT]` Time-sensitive info (deadlines ending soon)
- `[VERIFY]` Data conflicts or needs confirmation
- `[OPPORTUNITY]` Sponsor slots available, good timing
- `[DATA-GAP]` Missing critical info
- `[INTEL]` Competitive intelligence
- `[NOTE]` General observations

---

## 8. REPORTING REQUIREMENTS

### Per-Run Report (Weekly minimum, daily target):

```
Scan Summary - [Date/Time]
============================
Total Sites Checked: 247
Successful: 231 (93.5%)
Failed: 16 (6.5%)

NEW ACTION ITEMS (8):
--------------------
1. [HIGH] World Hydrogen Summit - CFP NOW OPEN
   Deadline: 2025-09-15 | Client: CleanTech Inc
   Action: Submit speaking application

2. [HIGH] CyberSec Europe - Deadline in 14 days
   Deadline: 2025-03-19 | Client: SecurIT
   Action: URGENT - Submit today

FAILURES REQUIRING ATTENTION (3):
---------------------------------
1. impacthub.vienna - SSL certificate expired
2. techconference2025.com - 404 error
3. globalenergyforum.org - Cloudflare blocking

SCAN COMPLETE - [Timestamp]
```

### Weekly Executive Report (for Nicolia / leadership):

**Intended consumer:** Nicolia and leadership team. One-page answer each week to:
- What should we act on now?
- Which deadlines are at risk?
- What changed?
- What failed and needs attention?
- Recommended next actions?

**Required sections:**
1. Top action items
2. Urgent deadlines
3. New/changed opportunities
4. Client-ready items
5. Failures requiring attention
6. Run quality metrics
7. Recommended next actions

**Data grounding rule:** Do not invent conference details. Each line must carry:
- Conference name or unnamed with source URL
- Current action state
- Current CFP/deadline values as found
- Evidence text extracted from row/crawl notes
- Review state when present

**Delivery:** Email to Nicolia and relevant team members. Also update Google Spreadsheet in real-time with color-coded high-priority flags.

---

## 9. ACCEPTANCE CRITERIA

| Criteria | Target |
|----------|--------|
| Read all conference URLs from sheet | 100% |
| Website fetch success rate | >90% |
| CFP status identification accuracy | >80% |
| Detect and flag status changes | 100% of changes |
| Update Google Sheet within | 5 minutes of scan |
| Generate email report | Every scan |
| Run automatically on schedule | Weekly (to start) |
| Handle failures gracefully | Log, retry, report |

---

## 10. REQUIRED SYSTEM BEHAVIORS

### Success/Failure Tracking

**SUCCESS:** Website responded (HTTP 200), page content readable, required fields extracted, data saved.

**FAILURE Types:**
| Code | Reason | Retry? |
|------|--------|--------|
| TIMEOUT | Site didn't respond in 30s | Yes (3x) |
| 404 | Page not found | No |
| BLOCKED | Cloudflare/captcha | Yes (next run) |
| PARSE_FAIL | Can't find expected data | Manual review |
| SSL_ERROR | Certificate issue | No |

### Change Detection Requirements
- Compare current data vs previous scan
- Identify: CFP status → Open, new deadline, dates changed, new conference added
- Flag items requiring team action
- Update state storage for next comparison

### Source URL Integrity
The customer explicitly requires that the original source URL (`conf_page_url`) is preserved from the input through to the final output. This is the audit trail back to the seed URL and must not be left blank.

### Geographic Scope
The system must support:
- US-only (all states, contiguous 48, or custom state list)
- International (global scope)
- Specific non-US countries
- Separate geo preferences for conferences vs awards

### Multi-Model Discovery
The customer explicitly referenced ChatGPT-style search and wants AI-powered discovery. Requirements:
- Find NEW conferences not in the current list
- Use AI search queries (not just monitor known URLs)
- Cross-reference multiple AI models for confidence scoring
- Currently implements: Perplexity, ChatGPT, Gemini

---

## 11. CURRENT ASSETS PROVIDED BY CUSTOMER

| Asset | Details |
|-------|---------|
| Google Sheet | "Test Dark Conference Master List" (Hydrogen-Conferences-20260217) |
| Size | 544+ conference rows |
| Clients | 6+ different clients with filtered views |
| Test Client | Bioveritas (hydrogen/clean energy focus) — 11 conferences |
| Contact email | mattolejarczyk70@gmail.com |

---

## 12. PHASE 2 FUTURE ENHANCEMENTS (On Customer Radar)

These have been discussed but are not part of MVP1:

| Feature | Description |
|---------|-------------|
| AI-Powered Discovery | Automatically find NEW conferences not in current list |
| SQL Database Integration | Feed into Brandable PR platform (their web app with SQL backend) |
| Client Portal Dashboard | Replace Google Sheets with branded web dashboard |
| Automated Submission | Pre-fill and auto-submit applications |
| Schedule | Weekly → Daily once proven |

---

## 13. COST EXPECTATIONS

The customer expects minimal operational cost:
- Web fetch API calls: ~$0 (within free tiers)
- Google Sheets API: Free tier sufficient
- Email notifications: Negligible
- Compute (cron job): Minimal VPS usage
- **Total monthly: <$5** at 500 sites × 4 checks/month

---

## 14. SUMMARY OF WHAT THE CUSTOMER IS LOOKING FOR

**Core need:** Automate the tedious, error-prone manual process of checking hundreds of conference websites for speaking/CFP opportunities, tracking deadlines, and keeping spreadsheets updated.

**In Nicolia's own words, the "key" is:**
> "Take the ChatGPT level kind of stuff and get AI to not only find the new ones, but also go into our SQL database and check everything and constantly update for us."

**At minimum, the system must:**
1. Monitor a list of conference websites (provided by customer)
2. Auto-discover NEW conferences using AI search
3. Extract: CFP status, deadlines, conference dates, location, contact info, submission URLs
4. Detect changes vs previous scan (especially CFP opening, new deadlines)
5. Alert the team via email when action is needed (CFP opens, deadline <30 days)
6. Track success/failure of each site check
7. Generate weekly executive reports showing what needs action now
8. Update spreadsheets or database with findings
9. Run on a schedule without manual intervention
10. Handle failures gracefully (log, retry, report)

**The system should feel like:** A tireless assistant that checks every conference website, notices when something important changes, and puts the relevant opportunity in front of the right team member with clear context on what action to take and by when.