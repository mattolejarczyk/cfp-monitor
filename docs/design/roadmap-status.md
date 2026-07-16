# cfp-monitor — Roadmap & Status

**Date:** 2026-07-09 · Customer: Nicolia / PRIME|PR. Local native-crawl4ai build.
**Branch:** all work merged + pushed to `main`. **98 offline tests green.**

**Latest (2026-07-09):** ✅ **Licensing proxy DEPLOYED LIVE** at `https://channeled.org/cfp-proxy`
(Oracle VPS, nginx→uvicorn:8800, PM2; verified unknown-401 / active-200 / revoked-403 and a real
crawl through the proxy); ✅ **reconciliation annotator** (annotate the customer's master .xlsx with
our diffs); ✅ **ops** — license-DB backup cron + `admin billing` readout; ✅ **Windows customer
installer** built + validated on dev (Python 3.12 via winget, no-BOM `.env`, certifi TLS); ✅
**model/cost reference** added (`docs/design/model-costs.md`). See [HANDOFF.md](../../HANDOFF.md).

**Latest (2026-07-16):** ✅ **Windows licensed customer workflow validated end-to-end** on the
real desktop install: proxy license banner, dedicated Chrome/CDP, one-URL crawl, and two-row XLSX
upload all work. Customer presentation fields are now **Excel-safe ASCII** (no em/en dashes or
mojibake); the extraction prompt requests ASCII punctuation and a deterministic final formatter
enforces it. `.xlsx` upload intake reads only literal conference URLs from visible **Column B**,
never workbook XML, hyperlinks, notes, or other columns. Input quality remains a human review gate:
a wrong/stale source URL is reported honestly and is never silently replaced. Targeted regression
coverage: customer format 10/10; XLSX intake 2/2.

**Earlier (2026-07-09):** ✅ **M5 closed** — coverage report (worked/failed % + failed links with
reasons + resolution-path breakdown) and the **full 15-column customer sheet in the UI** (editable,
persisted, exportable, URL included); ✅ **IP protection** — hard anti-bot sites never auto-hit
without signed-in CDP (stopped an orphaned run hammering Reuters' CAPTCHA); ✅ **CDP-on-by-default**
for live/scheduled runs; ✅ **HubSpot no-name fix** (URL dedupe + junk-URL skip + explore budget +
extraction time-box → recovers the homepage name on slow sites); ✅ **source-of-truth guard** — a
failed/thin re-crawl can no longer wipe good stored data.
**2026-07-06:** JS-shell recovery (cybertech PARTIAL→PASS); aggregator/org navigation; LOCATION +
START DATE captured from the xlsx and wired end-to-end.

## Where we are — one line
The local build is a **coherent end-to-end system**: discover → resilient crawl (self-healing, IP-safe) → quality-gate → source-of-truth DB (degrade-proof) → human-editable customer sheet → customer feed → alerts + weekly report + scheduler. Energy gold set **43/44 PASS**; cross-market cyber **49/56 PASS** (100 sites, 0 blocked).

## Status by capability bucket
| Bucket | Area | Status |
|---|---|---|
| **A** | Crawl + extract core | ✅ **Done — hardened 07-07.** crawl4ai primary + Playwright fallback (consent, SPA-button click-through) + **CDP-to-real-Chrome** for hard anti-bot. Added JS-shell recovery, **aggregator/org navigation** (row context → specific event), **HubSpot budget/dedupe fixes** (homepage-name recovery on slow sites), and **IP-protection** (no auto-hit of anti-bot sites without CDP). Quality gate = 0 silent failures. |
| **B** | Persistence + review | ✅ **Done — hardened 07-07.** SQLite source-of-truth (**degrade-proof**: a failed/thin re-crawl can't wipe good data), run history, change detection, **verification lifecycle** (correction-precedence), rollover. **Full editable 15-column customer sheet in the UI** (per-row edits + NOTES persisted); CSV/JSON export. |
| **C** | Automation + delivery | 🟡 **Code done, needs activation.** Alerts + weekly report + run-once scheduler built; **CDP-on-by-default** makes unattended runs IP-safe. Needs: SMTP creds, Task Scheduler registration, real URL list. |
| **D** | Extraction quality / eval | 🟡 **Partial.** Coverage harness done; homepage-name recovery improved 07-07. **Deadline extraction data-bounded** (many expos publish none → honest "needs verification"). Model-per-field eval not yet formalized. |
| **Pre** | Discover *new* conferences | ⬜ **Deferred.** Ingests a fixed/uploaded list; multi-model discovery (Perplexity/GPT/Gemini) is later. |

## Milestone view (vs the VPS M0–M9)
- **M0–M4** (discovery/reqs → architecture → POC → MVP dashboard → hardening): ✅ met; local build **surpasses the VPS on crawl reliability** (0 datacenter-IP blocks).
- **M5 — Presentation / reporting:** ✅ **Done (07-07).** Coverage report (worked/failed + resolution-path breakdown) + the full editable 15-column customer sheet in the UI. This was the open gap.
- **M6 — Scheduling & alerts:** 🟡 code complete (`scheduler.py`, `alerts.py`, `scripts/run_scheduled.bat`); CDP-on-by-default made it IP-safe; needs activation (below).
- **M7 — Weekly executive report:** 🟡 `report.py` done; email delivery scaffolded (off until SMTP set).
- **M8 — Client portal / multi-user:** 🟡 **advanced 07-07** — the in-app editable customer sheet is the reviewer surface; **Brandable** live pull waits on their side.
- **M9 — Production hardening:** 🟡 stronger (IP protection, data-integrity guards, 78 tests); deploy/monitoring on the always-on machine still to do.

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

**Licensing + remote revocation — Option D SHIPPED 2026-07-07 (`licenseproxy/`):**
- Chosen approach = **server-side dependency**: the customer build never holds the LLM provider key; extraction is routed through a **vendor-hosted licensed proxy** (`CFP_LLM_PROXY_URL` + `CFP_LICENSE_KEY`). The proxy validates the license and forwards to the provider with the VENDOR key, metering tokens.
- **Kill switch**: `python -m licenseproxy.admin revoke <key>` → that customer's crawling stops on the next extraction call (enforcement is server-side, so it can't be patched out locally).
- Also: **version floor** (force-upgrade / kill old versions), **feature gating**, **token quota + metering** (resolves "who pays for tokens" — vendor meters & bills). Pure-stdlib `policy.py` enforcement core, 8 unit tests.
- Resolves the earlier open decision (embed vendor key vs customer key) in favor of the vendor proxy — it delivers the kill switch AND the cost model in one move.
- **DEPLOYED LIVE 2026-07-09** at `https://channeled.org/cfp-proxy` (Oracle VPS: nginx `location /cfp-proxy/` → uvicorn `127.0.0.1:8800`, PM2, survives reboot). Verified end-to-end incl. a real crawl through the proxy. Friendly launch-time `/v1/license` banner shipped. Operator commands: `licenseproxy/OPERATIONS.md`; deploy/update: `HANDOFF.md` §1.
- **Windows customer installer SHIPPED + validated on dev** (`installer/install.ps1`): finds/installs Python 3.12, downloads the app, venv+deps+Playwright, writes the customer `.env`, desktop shortcut. Two Windows bugs found during validation and fixed: `.env` BOM (dropped `CFP_LLM_PROXY_URL`) → no-BOM write + `utf-8-sig` load; fresh-Python TLS trust → certifi in the license check. Hardened for clean-machine unknowns (graceful winget-absent + Chrome-absent handling; script normalized to ASCII to avoid a PS 5.1 parser trip). Remaining: one smoke test on a clean Windows profile; v2 Inno Setup `.exe`.
- **Ops shipped:** license-DB weekly backup (`scripts/backup_licenses.sh` + cron), monthly billing readout (`admin billing --rate`).
- **Model/cost:** DeepSeek-V3 for extraction (~10–30× cheaper than frontier for this task); full reference + the `PROXY_MODEL` switch + the DeepSeek `deepseek-chat` name deprecation (2026-07-24) in `docs/design/model-costs.md`.

## Reconciliation vs. the customer master sheet
**Offline .xlsx annotator SHIPPED 2026-07-07** (`reconcile.py` + `reconcile_xlsx.py` + `scripts/reconcile.py`). Reconciles crawl results against the customer's original spreadsheet using a shared taxonomy — **Confirmed / Changed / Gap-filled / Unverified / Not-crawled** — and writes a copy of their sheet with changed cells highlighted, a comment carrying our value + source + last-checked, and a Reconciliation summary tab. Rows aligned by normalized URL; date columns compared by (year, month) to avoid Excel-serial-vs-verbatim false positives; STATUS deliberately not diffed (their workflow vocabulary ≠ our detection label). Verified on the real Utility sheet (5 confirmed / 12 changed / 1 gap-filled / 49 not-crawled against the 5-row DB).
- **Quality note:** "Changed" is a review prompt, not a verdict — a human decides update vs conflict. Per-field source is the conference URL + last-checked (verbatim evidence snippets are a later enhancement).
- **Deferred (roadmap):** accept/reject per diff (tracked-changes style) feeding the verification lifecycle; and a **Google Sheets** surface (v2 — live/collaborative, but needs OAuth; ~3–5 days vs ~1 for offline).

**Open decisions:**
- ✅ **LLM token-cost model — RESOLVED:** vendor proxy holds the key, meters tokens, Matt bills the customer (`admin billing`). See `docs/design/model-costs.md`.
- **Telemetry** back to Matt (runs, volumes) for billing/support/abuse detection — partially covered by proxy usage metering; richer run telemetry still optional.
- **Non-technical UX:** the installer + desktop icon + auto-CDP launcher now cover most of this; the one-time CDP sign-in is only needed for hard anti-bot rows.

## Input-quality & aggregator handling (roadmap, added 2026-07-06)
Surfaced by the cyber-market hardiness test. Two input-side challenges:

**1. Aggregator / organization URLs (not a single event). [SHIPPED 2026-07-06]** Some list entries point at an ORG or directory that lists MANY events, not one conference: e.g. `owasp.org` (the Foundation; the German event is `god.owasp.de/2026`), `isc2.org` (a cert body; Security Congress lives on a cvent page reached via `/professional-development/events`), `securitybsides.com` (a community hub; each city event is its own site, e.g. `bsides.org/event/bsideslv-3/`); `first.org/conference` (a page literally titled "Annual Conferences" listing many years, not one event). The tool correctly says "no single conference here," but for the customer that is still a miss.
- **Implemented (`aggregator.py` + `pipeline.py`):** discovery now collects every link on the crawled pages (`ExploreResult.all_links`); when the row supplies CONTEXT (name / location / dates), the pipeline scores each link against that context (city match, distinctive name tokens, target year; stale years and social/mirror hosts are penalized so the event's OWN current site wins). If a discovered link matches the row markedly better than the page we landed on (`target_score >= self_score + 1.0`), we recognize a directory/org page and hop to that specific event ONCE, before spending any LLM budget on the directory's own pages. Verified live: `bsides.org/events/` (a directory) -> resolves `bsidesaustin.com` ("BSides Austin") with row context Austin/April 2026.
- **Bounded limit:** this is a ONE-hop navigation from the crawled page's links. A bare org LANDING page that does not itself list cities (e.g. `securitybsides.com`, whose home only links to the generic `bsides.org` org pages) needs the directory URL as the list entry, or a better row context; those remain input-list-quality items. Also requires the row context to be passed in (the batch/gold path threads it via `run_urls(..., contexts=[...])`; the paste-URLs UI path has no per-row context, so navigation stays off there, safely).

**2. Dead / typo'd URLs (last-resort recovery).** Some entries are simply wrong (a missing letter, so DNS does not resolve). Today we correctly flag "unreachable" so a human fixes it.
- **Optional, human-confirmed:** on a hard DNS failure ONLY, search the conference NAME (plus "conference"/"summit") and propose the top candidate domain in the Review UI ("original URL dead, did you mean X?"). Accept only when obvious; never silently substitute. Keeps a human in the loop and avoids over-engineering.

## Known bounded limits (honest)
- **Deadlines** are only ~2/12 extractable because most expos don't publish one — surfaced as "needs verification" (feeds the human loop), not a bug.
- **Hard anti-bot** sites need the CDP Chrome running + signed in (one-time).
- **Pure SPA-router buttons** with no URL anywhere: click-through covers most; a rare few still escape.
- **JS-shell homepages** (content only after render, e.g. `cybertechisrael.com`): **fixed 2026-07-06** (commit `8d4b562`). The earlier hang came from the fallback's slow consent loop (8 selectors × 2.5s) plus an unbounded render; replacing it with a fast presence-check for consent banners + a hard `fallback_render_timeout_s` (45s) cap recovered cybertech PARTIAL→PASS ("Cybertech Global TLV 2027", 4 pages). Residual limit: a page that renders to genuinely zero recoverable content/links would still be PARTIAL — but that's now rare, not the common JS-shell case.
