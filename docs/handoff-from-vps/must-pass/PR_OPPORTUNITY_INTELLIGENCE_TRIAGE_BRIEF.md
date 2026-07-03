
# PR Opportunity Intelligence Triage Brief

Review the PR Firm Texas / Nicolia POC and propose the next product-development roadmap for turning PR Monitor 1 into a “PR Opportunity Intelligence System.”

Current POC URL:
https://channeled.org/pr-monitor-1

Use these source-of-truth files:
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/HERMES_VOC_HANDOFF_NICOLIA.md`
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/DISCOVERY_TRANSCRIPT_ANALYSIS.md`
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/DETAILED_CUSTOMER_REQUIREMENTS.html`
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/MVP1_CONFERENCE_MONITORING.md`
- `/home/ubuntu/.openclaw/workspace/business/nicolia_deep_research_system.md`
- `/home/ubuntu/.openclaw/workspace/business/nicolia_prompt_improvement.md`
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/PR_FIRM_TX_PROJECT_ARCHITECTURE_HANDOFF_2026-06-05.md`
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/PR_MONITOR_1_RUNBOOK.md`
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/PROCESS_DOCUMENTATION.md`
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/TEST_REPORT.md`
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/PROJECT_OVERVIEW.md`
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/batch_processor.py`
- `/home/ubuntu/.openclaw/workspace/dashboard/main.py`
- `/home/ubuntu/.openclaw/workspace/dashboard/static/pr_monitor_1.html`

Important framing:
This is not merely a conference scraper. It should become a PR opportunity intelligence system for:
- conferences
- awards
- speaking slots
- CFP/deadline alerts
- client-fit scoring
- PR/media opportunity ranking
- team review workflow
- future Brandable PR SQL/dashboard integration

Voice-of-customer anchor:
Nicolia’s pain is weekly manual checking across hundreds of conference/award sites, risk of missing CFP windows, and needing the system to “find the new ones” and “go into our SQL database and check everything and constantly update.”

Deliverables:
1. Identify what the current POC already does well.
2. Identify the gap between current POC and Nicolia’s desired operating workflow.
3. Propose a phased roadmap:
   - Phase A: Demo-ready polish
   - Phase B: Nicolia workflow fit
   - Phase C: PR intelligence features
   - Phase D: Brandable PR SQL/dashboard integration
4. Break the roadmap into concrete engineering cards.
5. Prioritize the top 5 cards that would most increase client value before the next demo.
6. Do not recommend generic AI features. Every recommendation must tie back to VOC, source docs, or current UI/code.
7. Treat `batch_processor.py` as the canonical extraction engine.
8. Treat `dashboard/main.py` and `dashboard/static/pr_monitor_1.html` as the active POC surface.
9. Treat older March MVP scripts as historical unless current docs reference them.

## Recommended next direction

Top priority should be:

1. **Opportunity Review Queue**
   - “Open CFP”
   - “Deadline <30 days”
   - “New award/conference”
   - “Needs human review”
   - “Ready to pitch client”

2. **Client-fit scoring**
   - Which client is this opportunity for?
   - Why does it fit?
   - What angle should we pitch?

3. **Deadline alerting**
   - 30 / 14 / 7 day urgency
   - action-required status
   - missed-deadline risk

4. **Executive report for Nicolia**
   - “Here are the 8 opportunities your team should act on this week.”
   - Not just raw extracted rows.

5. **Path memory / site reliability**
   - Store where CFP info was found.
   - Retry/fallback when sites change.
   - Report failures clearly.

6. **Future SQL contract**
   - Define the Brandable PR database schema before trying to integrate.
   - Don’t wire SQL too early.