
# Hermes VOC Handoff - Nicolia / PR Firm TX

**Purpose:** Give Hermes direct voice-of-customer context for the PR Firm TX project.  
**Primary source:** `DISCOVERY_TRANSCRIPT_ANALYSIS.md`  
**Call date:** 2026-02-09 at 10:48 AM  
**Participants:** Matt and Nicolia

---

## Source Files Hermes Should Read

Primary VOC source:

- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/DISCOVERY_TRANSCRIPT_ANALYSIS.md`

Customer requirements derived from the call:

- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/DETAILED_CUSTOMER_REQUIREMENTS.html`
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/MVP1_CONFERENCE_MONITORING.md`

Related Nicolia strategy/prompt files:

- `/home/ubuntu/.openclaw/workspace/business/nicolia_deep_research_system.md`
- `/home/ubuntu/.openclaw/workspace/business/nicolia_prompt_improvement.md`

Note: I found a processed transcript analysis with direct quotes, but I did not find a separate raw transcript/audio file in the active project folder.

---

## Direct Customer Quotes

These are the clearest VOC statements currently captured:

> "We have to go every week to go look at their top conferences and then find when... they have updated the call for speakers yet."

> "When you've got dozens of clients all in different industries... now you're talking about hundreds of conferences."

> "The biggest issues there are one, finding the [conferences], making sure that the call for abstracts is open, updating the deadline for when those abstracts have to be delivered."

> "We're gonna ChatGPT, put in a prompt for exactly what we're looking for, and let it search and it spits back 90% of what we're looking for."

> "If we were able to take the ChatGPT level kind of stuff and get AI to do this to not only find the new ones, but also go into our SQL database and check everything and constantly update for us. That's the key."

---

## Customer Pain In Plain English

Nicolia's team manually checks conference sites every week to find speaking opportunities and deadlines for clients. The work is repetitive and scales badly because each client has different industries and relevant conferences.

The key customer pain is not just "data extraction." It is:

- not missing CFP/call-for-speaker windows,
- reducing weekly staff checking work,
- keeping Google Sheets or a future SQL database updated,
- finding new relevant conferences,
- turning conference intelligence into client action.

---

## Current Manual Workflow

1. Visit each conference website.
2. Check whether "Call for Abstracts" or call-for-speakers is open.
3. Find the submission deadline.
4. Add/update URL and deadline in client-specific spreadsheet sections.
5. Submit the speaking application for the client.
6. Mark the item as submitted or in progress.

This same workflow also applies to industry awards and product awards.

---

## VOC-Driven Product Requirements

Hermes should treat these as customer-led requirements:

- Monitor a list of conference websites provided by Nicolia.
- Detect whether CFP/call-for-speakers is open, closed, not yet open, or unknown.
- Extract conference dates, deadlines, URLs, and contact/submission info when available.
- Flag changes that require team action.
- Report success/failure per site so the team knows what can and cannot be read.
- Support weekly scheduled checks initially, with potential for more frequent checks later.
- Prepare for future integration with Nicolia's SQL/brandable PR platform.

---

## Customer Success Definition

From the VOC, success means:

- Nicolia's team spends less time checking sites manually.
- Deadlines and open calls are surfaced early.
- New relevant conferences are discovered.
- The system updates their tracking source of truth.
- The team can trust which sites were checked and which failed.

---

## Instruction For Hermes

Use `DISCOVERY_TRANSCRIPT_ANALYSIS.md` as the primary VOC artifact. Preserve Nicolia's language when making product, UX, workflow, or architecture decisions. Do not optimize only for technical extraction accuracy; optimize for the operational job Nicolia described: finding and maintaining speaking/award opportunities across many clients before deadlines are missed.