
# Reporting & Alerts System — Recommendations

## Context

Nicolia's core need (in her own words):
> "If we were able to take the ChatGPT level kind of stuff and get AI to not only
> find the new ones, but also go into our SQL database and check everything and
> constantly update for us. That's the key."

The system already detects changes and generates reports — but nothing is pushed
to Nicolia. She has to log in and check. The recommendations below close that gap
with a streamlined, layered approach that matches how she actually works.

---

## Design Principles

1. **Push, don't pull** — Nicolia shouldn't have to check the dashboard. The system
   tells her when something needs attention.
2. **Right channel for the right urgency** — Not everything is email. Critical
   alerts need immediate delivery; weekly summaries can be batched.
3. **Start simple, layer up** — Get the basics working first (email alerts,
   weekly report), then add sophistication (routing, digests, Slack).
4. **Leverage what exists** — The change detection, report generation, and email
   infrastructure are already built. We're wiring them together, not rebuilding.

---

## Recommended Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PIPELINE (Weekly Run)                     │
│  Discover → Crawl → Extract → Enrich → Change Detection    │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │   Change Detection     │
              │   (already built)      │
              │                        │
              │  Compares current vs   │
              │  previous snapshot     │
              │  Identifies:           │
              │  • cfp_opened          │
              │  • deadline_added      │
              │  • deadline_changed    │
              │  • dates_changed       │
              │  • new_opportunity     │
              │  • source_failed       │
              └───────────┬────────────┘
                          │
              ┌───────────┴───────────┐
              │                       │
              ▼                       ▼
    ┌─────────────────┐    ┌─────────────────────┐
    │  CRITICAL       │    │  WEEKLY DIGEST      │
    │  ALERTS         │    │  (Scheduled)        │
    │                 │    │                     │
    │  Immediate      │    │  Every Monday 9am   │
    │  email for:     │    │  CT (Chicago time)  │
    │  • CFP opened   │    │                     │
    │  • Deadline     │    │  Full 7-section     │
    │    < 30 days    │    │  executive report   │
    │  • New conf     │    │                     │
    │    discovered   │    │                     │
    └────────┬────────┘    └──────────┬──────────┘
             │                        │
             ▼                        ▼
    ┌─────────────────────────────────────────┐
    │         EMAIL DELIVERY                   │
    │                                          │
    │  Loops API (already configured)          │
    │  • Transactional emails                  │
    │  • HTML templates                        │
    │  • Attachment support                    │
    │                                          │
    │  Fallback: Gmail SMTP (already in code)  │
    └─────────────────────────────────────────┘
```

---

## Layer 1: Critical Alert Emails (Immediate)

**What:** Immediate email alerts when high-priority changes are detected during a pipeline run.

**Triggers (from Nicolia's requirements):**

| Trigger | Priority | Timing |
|---------|----------|--------|
| CFP status changes TO "Open" | HIGH | Immediate |
| New deadline discovered < 30 days | HIGH | Immediate |
| New conference discovered | MEDIUM | Immediate |
| Conference dates changed | MEDIUM | Batched (daily) |
| Submission URL changed | LOW | Batched (weekly) |

**Email format — Critical Alert:**

```
Subject: [PR MONITOR] CFP OPEN — World Hydrogen Summit 2026

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 CFP STATUS CHANGE — ACTION REQUIRED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Conference:  World Hydrogen Summit 2026
Market:      Hydrogen
Change:      CFP status changed from "Closed" → "OPEN"
Deadline:    September 15, 2026
Dates:       January 20-22, 2027
Location:    Amsterdam, NL
URL:         https://worldhydrogensummit.com

[View in Dashboard]  [Mark as Submitted]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This is an automated alert from PR Monitor.
To adjust alert settings: [Settings]
```

**Implementation approach:**
1. After each extraction run, `change_detection.py` already produces a changeset.
2. Add an `AlertEvaluator` that scores each change against the trigger table above.
3. For HIGH priority changes, call `loops_send_transactional_email()` immediately
   with a dedicated alert template.
4. For MEDIUM/LOW, accumulate into a daily digest queue (stored in SQLite).
5. Use the existing Loops API integration (already in `main.py` lines 1338-1374).

**Estimated effort:** 1-2 days. The detection and email infrastructure exist.
We're adding the evaluation + routing layer between them.

---

## Layer 2: Weekly Executive Report (Scheduled)

**What:** A comprehensive weekly email every Monday morning summarizing all activity.

**Schedule:** Monday 9:00 AM Central Time (Nicolia's timezone — she's in Austin, TX).

**Report sections (from Nicolia's requirements):**

```
Subject: [PR MONITOR] Weekly Report — June 16, 2026

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PR MONITOR — WEEKLY EXECUTIVE REPORT
Week of June 9-15, 2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 RUN SUMMARY
   Total sites checked: 186
   Successful: 179 (96.3%)
   Failed: 7 (3.7%)
   New conferences discovered: 4

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 TOP ACTION ITEMS (3)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. [HIGH] World Hydrogen Summit — CFP NOW OPEN
   Deadline: Sep 15, 2026 | Client: Bioveritas
   → Submit speaking application

2. [HIGH] CyberSec Europe — Deadline in 14 days
   Deadline: Mar 19, 2026 | Client: SecurIT
   → URGENT: Submit today

3. [MED] CleanTech Forum 2026 — Newly discovered
   Dates: May 5-7, 2026 | Market: Hydrogen
   → Evaluate for client fit

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ URGENT DEADLINES (< 30 DAYS) (2)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. CyberSec Europe — Mar 19, 2026 (14 days)
2. AI Infra Summit — Apr 30, 2026 (28 days)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✨ NEW / CHANGED OPPORTUNITIES (5)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. World Hydrogen Summit 2026 — CFP opened
2. CleanTech Forum 2026 — Newly discovered
3. Energy Transition Europe — Dates changed
   (was Mar 2026 → now May 12-14, 2026)
4. Sustainable Investment Forum — Newly discovered
5. Data Center Cooling Forum — CFP opened

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ CLIENT-READY ITEMS (4)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Decarb Connect UK — CFP open, ready to submit
2. European Hydrogen Energy Conf — CFP open
3. CO2-based Fuels Conference — CFP open
4. Structures Congress 2026 — CFP open

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
❌ FAILURES REQUIRING ATTENTION (3)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. impacthub.vienna — SSL certificate expired
2. techconference2025.com — 404 error
3. globalenergyforum.org — Cloudflare blocking

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 RUN QUALITY METRICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Success rate: 96.3% (target: >90%) ✅
CFP accuracy: 87% (target: >80%) ✅
Avg extraction cost: $0.009/row
Total AI cost this week: $1.67

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 RECOMMENDED NEXT ACTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Submit Bioveritas application for World Hydrogen Summit
2. Rush SecurIT application for CyberSec Europe (14 days)
3. Review CleanTech Forum for hydrogen client fit
4. Update impacthub.vienna bookmark (SSL expired)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[View Full Dashboard]  [Download CSV]  [Settings]
```

**Implementation approach:**
1. Wire APScheduler (already imported in `main.py`) to run every Monday at 9am CT.
2. The scheduler triggers a `generate_weekly_report()` function that:
   - Queries the database for all changes since last run
   - Calls the existing `generate_report()` from `batch_processor.py`
   - Formats the 7 sections using the template above
   - Sends via Loops API with HTML formatting
3. Store report history in SQLite for reference.

**Estimated effort:** 2-3 days. Report generation logic exists in `batch_processor.py`.
We're adding the scheduler wrapper, HTML template, and email delivery.

---

## Layer 3: Daily Digest (Optional, Phase 2)

**What:** A lighter daily email for medium/low priority changes that don't warrant
an immediate alert but shouldn't wait a week.

**Schedule:** Daily at 8:00 AM Central Time (only sent if there's content).

**Content:**
- New conferences discovered (MEDIUM)
- Conference dates changed (MEDIUM)
- Submission URL changes (LOW)
- Crawl failures from the last 24 hours

**Implementation:** Same alert evaluator from Layer 1 accumulates MEDIUM/LOW
changes into a daily queue. A separate APScheduler job sends the digest at 8am.

**Estimated effort:** 1 day (builds on Layer 1).

---

## Layer 4: In-Dashboard Notifications (Phase 2)

**What:** Real-time notification badges and an activity feed within the dashboard itself.

**Components:**
- Notification bell icon in the sidebar with unread count
- Activity feed on the overview page (already partially designed)
- Toast notifications when alerts fire during an active session
- "Last updated" timestamp showing when data was refreshed

**Implementation:** Add a `notifications` table in SQLite. When alerts fire, write
a notification record. The dashboard queries this on load and polls every 60 seconds.

**Estimated effort:** 1-2 days.

---

## Technical Implementation Plan

### What Already Exists (No Build Needed)

| Component | Location | Status |
|-----------|----------|--------|
| Change detection engine | `change_detection.py` | ✅ Complete |
| Report generator | `batch_processor.py` `generate_report()` | ✅ Complete |
| Email API (Loops) | `main.py` `loops_send_transactional_email()` | ✅ Complete |
| SMTP fallback (Gmail) | `main.py` lines 4634-4667 | ✅ Complete |
| APScheduler | `main.py` line 22 (imported) | ✅ Imported, not wired |
| Deadline intelligence | `deadline_intelligence.py` | ✅ Complete |
| Change snapshots | `change_snapshots.json` | ✅ Complete |
| Crawl metrics | `crawl_engine_metrics.json` | ✅ Complete |

### What Needs to Be Built

| Component | Effort | Priority |
|-----------|--------|----------|
| Alert evaluator (score changes → alert level) | 0.5 day | HIGH |
| Critical alert email template (HTML) | 0.5 day | HIGH |
| Alert sender (calls Loops API with template) | 0.5 day | HIGH |
| Weekly report scheduler (APScheduler cron) | 0.5 day | HIGH |
| Weekly report HTML template (7 sections) | 1 day | HIGH |
| Weekly report sender | 0.5 day | HIGH |
| Daily digest accumulator + scheduler | 1 day | MEDIUM |
| Notification table + API | 1 day | MEDIUM |
| In-dashboard notification UI | 1 day | LOW |
| **TOTAL** | **6.5 days** | |

---

## Recommended Phasing

### Phase 1: Critical Alerts + Weekly Report (Week 1-2)
- Build alert evaluator
- Create critical alert email template
- Create weekly report template
- Wire APScheduler for weekly report
- Configure Loops API for both
- Test end-to-end with real data

**Outcome:** Nicolia gets immediate emails when CFPs open and a comprehensive
Monday morning report. This alone closes the biggest gaps.

### Phase 2: Daily Digest + Dashboard Notifications (Week 3)
- Build daily digest accumulator
- Add notification table to SQLite
- Add notification bell and activity feed to dashboard
- Add toast notifications for active sessions

**Outcome:** Complete notification coverage across all channels.

### Phase 3: Advanced Routing (Week 4+)
- Per-market alert routing (hydrogen alerts → one team member, cyber → another)
- Configurable alert thresholds per user
- Slack/Teams integration (if Nicolia uses those)
- Mobile push notifications

**Outcome:** Enterprise-grade alerting that scales with the team.

---

## Configuration

All alert settings should be configurable per user:

```json
{
  "alerts": {
    "email": "mattolejarczyk70@gmail.com",
    "critical_immediate": true,
    "daily_digest": true,
    "weekly_report": true,
    "markets": ["hydrogen", "cybersecurity"],
    "min_priority": "medium",
    "quiet_hours": {
      "enabled": true,
      "start": "22:00",
      "end": "07:00",
      "timezone": "America/Chicago"
    }
  }
}
```

---

## Cost Estimate

| Component | Cost |
|-----------|------|
| Loops API (transactional email) | Free tier: 2,000 emails/month |
| APScheduler (runs on existing VPS) | $0 |
| SQLite storage | $0 |
| **Total monthly cost** | **$0** |

At Nicolia's scale (weekly report + ~5-10 alerts/week), well within Loops' free tier.

---

## Summary

The system already has all the hard parts built — change detection, report generation,
and email delivery. The recommendations above are primarily about **connecting the
pieces** and **pushing information to Nicolia** instead of requiring her to pull it.

**Phase 1 (1-2 weeks) delivers:**
- Immediate email when a CFP opens
- Immediate email when a deadline is <30 days
- Comprehensive Monday morning executive report
- Zero additional monthly cost

This directly addresses Nicolia's #1 pain point: "making sure that the call for
abstracts is open, updating the deadline for when those abstracts have to be delivered."
She'll know about changes before she'd even think to check.