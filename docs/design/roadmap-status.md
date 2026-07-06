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
6. **Customer-deployable desktop package + revocable license** (see below) — a standalone install for Nicolia's customers, gated by a key you can revoke at any time.

## Distribution & licensing (roadmap — added 2026-07-04)
**Goal:** ship this to Nicolia's customers as a **standalone desktop package** they run on their own machine (residential IP + their own Chrome = keeps the anti-bot advantage), gated by a **license key Matt can revoke at any time.**

**Standalone package (no dev tools on the customer's machine):**
- Bundle app + Python runtime + deps into a one-click install (PyInstaller/Nuitka, or an embedded-Python folder + launcher; an Inno Setup installer for a clean desktop/Start-menu entry — reusing the `launch_ui.bat` pattern we already have).
- Run the crawl4ai/Playwright browser install as a post-install step; include the CDP-Chrome launcher for hard sites.
- Optional (v2): auto-update channel so customers pull new versions.

**Licensing + remote revocation:**
- A lightweight **license server** (Matt-controlled) that issues per-customer keys and can **revoke** them.
- The app validates the key on launch and re-checks periodically online; **works offline within a grace window**, then locks if it can't confirm an active key.
- Ties to the subscription model (Brandable tiers): revoke = access ends immediately.

**Open decisions (flag before building):**
- **LLM token-cost model:** embed Matt's key (Matt pays tokens, simplest) vs. each customer supplies their own OpenRouter key (customer pays). Directly affects margins.
- **Telemetry** back to Matt (runs, volumes) for billing/support/abuse detection.
- **Non-technical UX:** smooth over the CDP-Chrome + one-time sign-in step so customers don't need hand-holding for hard sites.

## Input-quality & aggregator handling (roadmap, added 2026-07-06)
Surfaced by the cyber-market hardiness test. Two input-side challenges:

**1. Aggregator / organization URLs (not a single event).** Some list entries point at an ORG or directory that lists MANY events, not one conference: e.g. `owasp.org` (the Foundation; the German event is `god.owasp.de/2026`), `isc2.org` (a cert body; Security Congress lives on a cvent page reached via `/professional-development/events`), `securitybsides.com` (a community hub; each city event is its own site, e.g. `bsides.org/event/bsideslv-3/`). The tool correctly says "no single conference here," but for the customer that is still a miss.
- **Approach:** detect an aggregator/org page (many event-like links, no single conference on it) and use the spreadsheet ROW CONTEXT (location, dates, conference name) to navigate the directory and pick the specific event, then crawl that. This mirrors exactly what a human does. Needs the row context passed into discovery (today we crawl a bare URL with no context).

**2. Dead / typo'd URLs (last-resort recovery).** Some entries are simply wrong (a missing letter, so DNS does not resolve). Today we correctly flag "unreachable" so a human fixes it.
- **Optional, human-confirmed:** on a hard DNS failure ONLY, search the conference NAME (plus "conference"/"summit") and propose the top candidate domain in the Review UI ("original URL dead, did you mean X?"). Accept only when obvious; never silently substitute. Keeps a human in the loop and avoids over-engineering.

## Known bounded limits (honest)
- **Deadlines** are only ~2/12 extractable because most expos don't publish one — surfaced as "needs verification" (feeds the human loop), not a bug.
- **Hard anti-bot** sites need the CDP Chrome running + signed in (one-time).
- **Pure SPA-router buttons** with no URL anywhere: click-through covers most; a rare few still escape.
