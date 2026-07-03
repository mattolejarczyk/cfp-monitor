
# PR Monitor 1 — Development Milestones & Roadmap

## Approach

This plan uses **traditional milestone names** (Discovery, Design, POV, MVP, etc.) for
customer-facing clarity, but each milestone is executed in **short Agile cycles** with
fast feedback loops. The goal is to show working software early and often, get
customer input, and adjust — not to disappear for weeks and come back with a finished
product.

**Key principles:**
- Every milestone ends with something the customer can see and touch
- Feedback loops are built into every phase, not bolted on at the end
- Each cycle is 1-2 weeks max — short enough to course-correct quickly
- "Done" means "customer has seen it and confirmed it works" — not just "code works"

---

## MILESTONE 0: Discovery & Requirements
**Status: COMPLETE**
**Duration:** Feb 9 – Mar 5, 2026 (~3 weeks)

### What happened:
- Discovery call with Nicolia (Feb 9) — understood the manual process, pain points, and vision
- Documented current spreadsheet structure and data fields
- Defined alert triggers, crawl strategy, and reporting requirements
- Established acceptance criteria and success metrics
- Created detailed requirements document and MVP1 spec

### Deliverables:
- Discovery call transcript
- Detailed customer requirements document
- MVP1 conference monitoring spec
- Data schema (54-column format)

### Customer feedback loop:
- Requirements doc shared with Nicolia for confirmation
- MVP scope agreed upon before build started

---

## MILESTONE 1: Design & Architecture
**Status: COMPLETE**
**Duration:** Mar 5 – Mar 2026 (~2 weeks)

### What happened:
- Designed the extraction pipeline architecture
- Defined the 54-column locked schema
- Designed crawl path discovery and memory system
- Planned multi-model discovery approach
- Created process documentation and batch processor design

### Deliverables:
- Process documentation (54-column schema)
- Batch processor design
- Architecture handoff document
- Source registry design

### Customer feedback loop:
- Schema reviewed against customer's spreadsheet fields
- 54-column format confirmed to cover all tracked data

---

## MILESTONE 2: Proof of Concept (POC) — Core Extraction
**Status: COMPLETE**
**Duration:** Mar 2026 (~2 weeks)

### What happened:
- Built batch_processor.py — the core extraction engine
- Implemented web fetching and page crawling
- Built structured data extraction (conference info, CFP, contacts, submission portal)
- Generated 54-column CSV output
- Created executive report generator
- Tested on sample conference websites

### What the customer could see:
- Input: a list of conference URLs
- Output: a structured CSV with 54 columns of extracted data
- Output: a text-based intelligence report showing what was found

### Customer feedback loop:
- Sample output shared with Nicolia
- Confirmed the data fields matched what she tracks
- Identified gaps (geo data, deadline urgency) for next iteration

---

## MILESTONE 3: MVP1 — Dashboard & Review Workflow
**Status: COMPLETE**
**Duration:** Apr – May 2026 (~6 weeks)

### What happened:
- Built the PR Monitor 1 dashboard (HTML + FastAPI backend)
- Implemented Step 1 (Create Prompt) and Step 2 (Discover URLs)
- Implemented Step 3 (Crawl URLs) with async job processing
- Implemented Step 4 (Extract Data) with async job processing
- Implemented Step 5 (Enrich Data) for geo enrichment
- Built Step 6 (Review) with filtering, status management, overrides
- Added source registry for crawl path memory
- Added change detection between scans
- Added deadline urgency and action classification
- Built queue API with grouping and filtering
- Implemented six-state review status model with persistence

### What the customer could see:
- A working web dashboard at https://channeled.org/pr-monitor-1
- Full pipeline: create prompt → discover URLs → crawl → extract → review
- Review table with filtering, status buttons, CSV export
- Executive report generation

### Customer feedback loop:
- Dashboard demo'd to Nicolia
- UI refinements based on feedback (denser tables, column widths, button labels)
- Review workflow adjusted based on how she actually works

---

## MILESTONE 4: POC Hardening & Validation
**Status: COMPLETE**
**Duration:** Jun 1 – Jun 16, 2026 (~2 weeks)

### What happened:
- Added custom URL path for controlled demos (bypass discovery)
- Validated end-to-end crawl + extract with custom URLs
- Added input sanitization (dirty URL handling, deduplication)
- Added guardrails (use_master_list=false returns 400 instead of silent fallback)
- Fixed geo enrichment fallback in both run rows and queue endpoints
- Added Re-open button conditional hiding
- Ran smoke gates and health checks
- Created step-by-step reference documentation

### What the customer could see:
- Reliable demo flow: paste 2-3 URLs → crawl → extract → review
- Clean error handling when things go wrong
- Verified geo data appearing in the UI

### Customer feedback loop:
- Demo flow validated with real conference URLs
- Confirmed the system handles edge cases (bad URLs, unreachable sites)

---

## MILESTONE 5: Customer Presentation & Feedback
**Status: NOW**
**Duration:** This week

### What happens:
- Present the POC to Nicolia
- Walk through the full Step 1-6 workflow live
- Show: prompt creation → URL discovery → crawl → extract → review → export
- Demonstrate: filtering, status management, overrides, CSV export
- Share: Voice of Customer requirements doc and comparison analysis
- Discuss: what's built, what's next, and get her input on priorities

### What the customer will see:
- A working dashboard she can use today
- Her data (conference names, CFP status, deadlines, contacts) extracted automatically
- A review workflow that replaces her manual spreadsheet checking
- Export capability when she needs data in spreadsheet form

### Feedback loop:
- Record her reactions, questions, and requests
- Prioritize next milestones based on her input
- Agree on the next 2-week cycle's focus

---

## MILESTONE 6: Automated Scheduling & Alerts
**Status: NEXT (recommended priority)**
**Duration:** 1-2 weeks

### What we'll build:
- Wire APScheduler to run the pipeline on a weekly schedule (no manual initiation)
- Add email alerts for critical events:
  - CFP status changes to "Open" → immediate email to team
  - Deadline < 30 days → urgent email to team
  - New conference discovered → notification email
- Add configurable alert recipients per market/client

### What the customer will see:
- The system runs automatically every week without anyone clicking buttons
- She gets an email when something important changes
- No need to check the dashboard unless an alert brings her there

### Feedback loop:
- First automated run: confirm it works end-to-end
- First alert email: confirm it has the right info and goes to the right people
- Adjust alert thresholds and recipients based on her feedback

---

## MILESTONE 7: Automated Weekly Executive Report
**Duration:** 1 week

### What we'll build:
- Auto-generate the weekly executive report after each scheduled run
- Email the report to Nicolia and team
- Include all 7 required sections:
  1. Top action items (CFPs opened, urgent deadlines)
  2. Urgent deadlines (< 30 days)
  3. New/changed opportunities
  4. Client-ready items
  5. Failures requiring attention
  6. Run quality metrics
  7. Recommended next actions

### What the customer will see:
- A weekly email every Monday morning summarizing what needs attention
- One-page format: what to act on now, what's coming up, what failed
- No need to log into the dashboard for the weekly summary

### Feedback loop:
- First report: review format and content with Nicolia
- Adjust sections, wording, and level of detail based on her input
- Confirm delivery timing and recipients

---

## MILESTONE 8: Client Portal & Multi-User Support
**Duration:** 2 weeks

### What we'll build:
- User accounts and authentication
- Client-specific views (each client sees only their conferences)
- Team member roles (admin, reviewer, viewer)
- Activity log (who did what and when)

### What the customer will see:
- Her team can log in and see their assigned clients
- Each team member sees only what's relevant to them
- Audit trail of all review actions

### Feedback loop:
- Have Nicolia's team test with real accounts
- Adjust views and permissions based on how they actually work

---

## MILESTONE 9: Production Hardening
**Duration:** 2 weeks

### What we'll build:
- Automated backups of the database
- Monitoring and uptime alerts (if the system goes down, we know)
- Performance optimization for large conference lists (500+ sites)
- Error recovery and retry improvements
- Security review

### What the customer will see:
- A system that runs reliably without babysitting
- Faster processing for large conference lists
- Confidence that data is backed up and secure

### Feedback loop:
- Run the system for 2 weeks in production mode
- Track any issues or downtime
- Fix and improve based on real-world usage

---

## MILESTONE 10: Phase 2 Features (Future)
**Duration:** TBD based on customer priority

### Candidates (from Nicolia's original wishlist):
- AI-powered award monitoring (parallel to conference monitoring)
- SQL database integration (Brandable PR platform)
- Automated submission workflow (pre-fill and submit applications)
- Media/analyst CRM enrichment
- Share-of-voice dashboard
- Client-specific PR radar (reporter tracking, competitor mentions)

### Approach:
- Present options to Nicolia after Milestone 7 is stable
- Let her business needs drive priority
- Continue 2-week cycles with demos at the end of each

---

## Visual Roadmap

```
M0: Discovery          ████ COMPLETE (Feb 9 - Mar 5)
M1: Design             ████ COMPLETE (Mar 5 - Mar 20)
M2: POC Core          ████ COMPLETE (Mar 2026)
M3: MVP1 Dashboard    ████ COMPLETE (Apr - May 2026)
M4: POC Hardening     ████ COMPLETE (Jun 1 - Jun 16)
M5: Customer Pres     ███░ THIS WEEK
M6: Scheduling/Alerts ░░░░ NEXT (1-2 weeks)
M7: Weekly Report     ░░░░ (1 week)
M8: Client Portal     ░░░░ (2 weeks)
M9: Production Hard   ░░░░ (2 weeks)
M10: Phase 2         ░░░░ (TBD)
```

---

## How We Work (Agile Practices)

**Cycle length:** 1-2 weeks per milestone. No longer.

**At the start of each cycle:**
- We agree on what "done" looks like
- We identify the riskiest assumption to test first
- We set up a way to demo the result to the customer

**During the cycle:**
- Working software over comprehensive documentation
- If something is blocking progress, we cut scope — not quality
- We prefer "good enough to get feedback" over "perfect but not ready"

**At the end of each cycle:**
- Demo to the customer (even if it's rough)
- Get feedback: what's right, what's wrong, what's missing
- Adjust the next cycle's plan based on real input
- Update this roadmap so the customer always knows where we are

**Communication:**
- Short weekly update (even just "here's what we built this week")
- Demo at the end of every cycle — no exceptions
- If priorities change, we change the plan — not silently

---

## What "Done" Means

A milestone is NOT done when the code works. It's done when:
1. The customer has seen it work
2. The customer has confirmed it does what she needs
3. Any critical feedback has been addressed
4. The system is stable enough for real use

This prevents the classic trap of "we built everything but it's not what the customer wanted."