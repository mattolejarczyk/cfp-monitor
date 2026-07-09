# cfp-monitor — Worklog (running memory)

Append-only log of what changed each work session. Newest first. Keep entries short and factual
(what + why); the current-state snapshot lives in `roadmap-status.md`, deep design notes elsewhere.

---

## 2026-07-09
- **License proxy DEPLOYED LIVE** at https://channeled.org/cfp-proxy (Oracle VPS, nginx→uvicorn:8800,
  PM2). Verified: unknown 401 / active 200 / revoked 403.
- **Reconciliation annotator** shipped (`reconcile.py` + `reconcile_xlsx.py`): annotated .xlsx copy
  of the customer master sheet.
- **Licensing go-live extras:** friendly client license banner; OpenAI+OpenRouter support.
- **Ops:** `scripts/backup_licenses.sh` (weekly cron), `admin billing` (per-customer token/$ readout),
  `installer/install.ps1` (Windows one-shot customer installer — needs a clean-machine test).
- **Handoff:** `HANDOFF.md` (single source of truth for Matt + both Hermes), `scripts/vps_setup.sh`.

## 2026-07-07
- **M5 closed.** Coverage report (`coverage.py`, `scripts/coverage_run.py`): worked/failed % +
  failed links with concise reasons + **resolution-path breakdown** (Core crawl / Browser control /
  Signed-in browser / Unresolved) + which bypass was deployed. Plain-terms labels (no tool names leak).
- **Full editable 15-column customer sheet in the UI** (`app.py` Review tab): edits to crawl-produced
  fields use correction-precedence; human-owned columns save directly; added `NOTES` column (+ migration)
  and `set_fields/correct/set_verified`. Run tab now shows a customer-format table (URL included) + CSV.
- **IP protection.** Stopped an orphaned coverage run that was hammering Reuters' CAPTCHA and flagged the
  home IP. `fetch.py` no longer auto-hits a hard anti-bot domain without CDP (flags "Manual/signed-in").
- **CDP on by default** for live/scheduled runs (`cdp.py` `ensure_cdp()` auto-detects/starts a
  dedicated-profile Chrome on :9222); coverage runner refuses the unsafe path.
- **HubSpot no-name fix.** URL dedupe (drop hsLang/utm_/hs_ params) + `is_crawlable()` skips CTA/asset
  URLs + explore stops at `CFP_EXPLORE_FRACTION`=0.6 + extraction time-boxed to 90% (homepage first).
  industrialnetzero + connectinghydrogen now PASS with names.
- **Source-of-truth guard.** A failed/thin re-crawl can no longer wipe good stored data (skip tracked
  fields on ERROR/BLOCKED; never overwrite non-null with null).
- **Licensing Option D** (`licenseproxy/`): vendor-hosted licensed LLM proxy = kill switch +
  token metering + version-floor/feature gating. Customer build routes extraction through the
  proxy with a license key (no provider key locally); `admin revoke <key>` stops their crawling.
  Pure-stdlib `policy.py` enforcement core; `server.py` (FastAPI) shell; `admin.py` CLI.
- **Reconciliation annotator** (`reconcile.py` + `reconcile_xlsx.py`, openpyxl): writes an
  annotated copy of the customer's master .xlsx — changed cells highlighted + commented (our
  value + source + last-checked) + a summary tab. Taxonomy: Confirmed / Changed / Gap-filled /
  Unverified / Not-crawled. Date columns compared by (year, month); STATUS not diffed.
- **Licensing go-live:** friendly client license check (`licensing.py` → `/v1/license`) wired
  into the app (banner + Run disabled when inactive); proxy + client now support **both OpenAI and
  OpenRouter** (`provider_key()` / `PROXY_MODEL` by prefix); `.env.example` for client + proxy;
  `scripts/run_proxy.bat`. Proved live over real HTTP: active key → 200, `revoke` → 403 (kill
  switch), plus a TestClient proof of allow→forward→meter with the provider mocked.
- 97 offline tests green; all pushed to `main`.

## 2026-07-06
- **JS-shell recovery**: fast consent presence-check + bounded fallback render (cybertech PARTIAL→PASS).
- **Aggregator/org navigation** (`aggregator.py`): use spreadsheet row context (name/location/dates) to
  hop from a directory/org page to the specific event once, before spending LLM budget.
- **LOCATION + START DATE captured from the customer xlsx** (`GoldRecord.context()`, `load_inputs()`),
  threaded via `run_urls(contexts=)` so navigation runs on the real lists.
