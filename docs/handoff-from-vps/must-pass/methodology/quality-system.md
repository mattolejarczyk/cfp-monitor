# PR Monitor Quality System Reference

Session source: 2026-06-22 PR Monitor / Nicolia quality-planning and baseline crawl work.

## Trigger

Use this reference when Matt asks to improve, audit, baseline, monitor, or operationalize PR Monitor quality — especially for Crawl → Extract → Enrich → Review.

## Durable workflow learning

Matt wants PR Monitor quality treated as a rigorous ASQ-like operating system, not a one-time audit. The goal is a continuous improvement loop baked into the project.

Core principle:

> No silent failures. A URL/data point may fail, but it must be detected, classified, logged, routed, and used to improve the system.

## Customer Google Sheets rule

Nicolia's Google Sheets are customer source documents. Treat them as READ-ONLY unless Matt explicitly authorizes writes.

Do not:
- Update cells
- Add comments
- Change formatting
- Write statuses back to the sheet
- Use the sheet as the operational state store

Do:
- Export/read local snapshots
- Track derived state externally in the PR Monitor project
- Store crawl inputs, quality reports, verification state, and baselines under `pr_monitor_1/`

Recommended paths:
- `pr_monitor_1/source_snapshots/` — read-only CSV snapshots from customer sheets
- `pr_monitor_1/quality_inputs/` — baseline manifests derived from snapshots
- `pr_monitor_1/quality_reports/` — crawl/extract/enrich/review quality outputs
- `pr_monitor_1/quality_state/` — future local DB/JSON for verification decisions

## Quality system project artifacts created

Primary docs:
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/PR_MONITOR_QUALITY_SYSTEM_PLAN.md`
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/PR_MONITOR_CRAWL_QUALITY_GATE_SPEC.md`

Runtime script:
- `/home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas/quality_monitor.py`

Current inputs/reports:
- `pr_monitor_1/quality_inputs/latest_crawl_baseline_urls.json`
- `pr_monitor_1/quality_reports/latest_quality_report.json`
- `pr_monitor_1/quality_reports/latest_quality_report.txt`

## Initial source snapshots

Google Sheets were accessible by CSV export. Local snapshots:
- `pr_monitor_1/source_snapshots/nicolia_energy_2026-06-22.csv`
- `pr_monitor_1/source_snapshots/nicolia_appsec_cybersecurity_2026-06-22.csv`

Observed counts:
- ENERGY: 52 rows, 51 conference URLs found
- APPSEC/CYBERSECURITY: 998 rows, 56 conference URLs found in populated URL fields

## Crawl quality gate status taxonomy

Each URL should classify into exactly one status:
- `PASS` — usable content captured; proceed to extract
- `PARTIAL` — accessed but content suspiciously thin/incomplete; retry rendered/browser path or manual review
- `BLOCKED` — 403/429/CAPTCHA/Cloudflare/bot protection; fallback or manual path
- `TIMEOUT` — timed out; retry once with extended timeout, then manual check
- `INVALID_URL` — malformed/dead/HTTP hard failure; correct URL/manual check
- `NON_CONFERENCE_PLATFORM` — platform/tool/listing page, not owner event page (e.g. Sessionize); find actual owner URL
- `REDIRECTED` — redirected materially; provenance review
- `NEEDS_MANUAL` — ambiguous, do not proceed automatically

Targets:
- 95%+ actionable classification rate
- 90%+ usable content rate initially, with path to 95%
- 0 silent failures

## Initial baseline result

Baseline run: `crawl_quality_baseline_20260622`

Results:
- URLs attempted: 25
- PASS: 18
- BLOCKED: 6
- PARTIAL: 1
- Silent failures: 0
- Actionable classification rate: 100%
- Usable content rate: 72%

Interpretation:
- Classification quality met the target.
- Usable crawl quality did not meet target.
- Main blockers were Gartner URLs, Black Hat Asia, and Reuters/Gartner-style 403/Cloudflare blocks.
- OffensiveCon returned partial/low-content result.

Next recommended quality improvement:
- Add a rendered-browser fallback path for `BLOCKED` and `PARTIAL` URLs.
- Rerun the same 25-URL manifest before expanding the sample.
- Compare before/after on usable content rate and silent failure rate.

## Important approval/safety note

A non-destructive Chromium headless fallback test was proposed but blocked by approval handling. If continuing this work, ask for approval to run one browser-rendered fetch against a blocked URL. Clarify that it will not write to Google Sheets or modify customer documents.

## Recommended sequence for future sessions

1. Load `pr-monitor-dashboard` skill.
2. Read `PR_MONITOR_QUALITY_SYSTEM_PLAN.md` and `PR_MONITOR_CRAWL_QUALITY_GATE_SPEC.md` if quality work is involved.
3. Confirm customer sheets remain read-only.
4. Use local snapshots/manifests only.
5. Run `quality_monitor.py` smoke test before full run:
   - `python3 quality_monitor.py crawl-baseline --input pr_monitor_1/quality_inputs/latest_crawl_baseline_urls.json --limit 3`
6. Run full baseline only after smoke passes.
7. Save reports under `pr_monitor_1/quality_reports/`.
8. Interpret quality against targets and recommend the next fallback/improvement.

## Matt communication preference from this session

When explaining quality work, reflect intent first, then give concrete project artifacts and exact paths. Matt wants rigorous, practical quality engineering with clear failure modes, risk/impact, and improvement actions — not vague reassurance that the system is “high quality.”
