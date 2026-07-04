# cfp-monitor — Roadmap & Status

**Date:** 2026-07-04 · Customer: Nicolia / PRIME|PR. Local native-crawl4ai build.
**Branch:** all work merged to `main`. **51 offline tests green.**

## Where we are — one line
The local build is a **coherent end-to-end system**: discover → resilient crawl → quality-gate → source-of-truth DB → human verify → customer feed → alerts + weekly report + scheduler. **98% usable coverage** on the 44-URL gold set, **0 errors**.

## Status by capability bucket
| Bucket | Area | Status |
|---|---|---|
| **A** | Crawl + extract core | ✅ **Done.** crawl4ai primary + Playwright fallback (consent dismissal, SPA-button click-through) + **CDP-to-real-Chrome** for hard anti-bot (Reuters). Quality gate (PASS/PARTIAL/BLOCKED, 0 silent failures). Gold set: 43/44 PASS. |
| **B** | Persistence + review | ✅ **Done.** SQLite source-of-truth, run history, change detection, **verification lifecycle** (correction-precedence), past-event rollover, path/quality memory, **Review & Verify UI**, **15-col customer export** (CSV/JSON, tag-filterable). |
| **C** | Automation + delivery | 🟡 **Code done, needs activation.** Alerts engine + weekly report + run-once scheduler built. Needs: SMTP creds (to email), Task Scheduler registration, real URL list. |
| **D** | Extraction quality / eval | 🟡 **Partial.** Gold-set harness done; deadline extraction is **data-bounded** (many expos don't publish one → honest "needs verification" output). Model-default selection not yet formalized. |
| **Pre** | Discover *new* conferences | ⬜ **Deferred.** Build ingests a fixed/uploaded list; multi-model discovery (Perplexity/GPT/Gemini) is later. |

## Milestone view (vs the VPS M0–M9)
- **M0–M5** (discovery/reqs → architecture → POC extraction → MVP dashboard → hardening → presentation): ✅ effectively met, and the local build **surpasses the VPS on crawl reliability** (0 blocked vs 6 blocked baseline).
- **M6 — Scheduling & alerts:** 🟡 code complete (`scheduler.py`, `alerts.py`, `scripts/run_scheduled.bat`); needs activation (below).
- **M7 — Weekly executive report:** 🟡 `report.py` done (opportunities + system health); email delivery scaffolded (off until SMTP set).
- **M8 — Client portal / multi-user:** 🟡 Review UI exists; **Brandable integration**: our feed is ready, their app pulls it when access/coordination exists.
- **M9 — Production hardening:** 🟡 tests + resilient crawl in place; deploy/monitoring on the always-on machine still to do.

## To activate what's built (needs YOU, not more code)
1. **Run it yourself:** double-click `scripts/launch_chrome_cdp.bat` (once, sign in) for hard sites, then `scripts/launch_ui.bat` → paste/upload URLs → Run. Review/verify in tab 2.
2. **Schedule it:** put your real URL list in `examples/urls.txt`; register `scripts/run_scheduled.bat` in Windows Task Scheduler (weekly).
3. **Email alerts:** set `CFP_SMTP_HOST/USER/PASS` + `CFP_ALERT_TO` env vars.
4. **Always-on:** decide the host for scheduled runs (home always-on box vs hybrid) — the one real tradeoff of the local decision.

## Roadmap — recommended order
1. **Activate M6/M7** (steps above) — turns it from tool into hands-off service. *Highest customer value.*
2. **Awards as a parallel entity** (deferred until conferences solid — now they are).
3. **Multi-model discovery** of new conferences (bucket Pre) — expand beyond a fixed list.
4. **Model/gold-set eval** (bucket D) — formalize which cheap model to trust per field.
5. **Client-fit scoring**, then **Brandable live integration** when their side is ready.

## Known bounded limits (honest)
- **Deadlines** are only ~2/12 extractable because most expos don't publish one — surfaced as "needs verification" (feeds the human loop), not a bug.
- **Hard anti-bot** sites need the CDP Chrome running + signed in (one-time).
- **Pure SPA-router buttons** with no URL anywhere: click-through covers most; a rare few still escape.
