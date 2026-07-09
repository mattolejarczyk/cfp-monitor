# cfp-monitor — Handoff & Single Source of Truth

**Updated 2026-07-09.** This file is the shared reference for **Matt + both Hermes instances**
(local dev box and the VPS). It lives in the public repo, so:

- **Read the latest:** `git pull` in your clone, then open this file — never paste long command
  blocks into a terminal; pull the repo and run from files instead.
- **Public web view:** <https://github.com/mattolejarczyk/cfp-monitor/blob/main/HANDOFF.md>
- **Alignment rule:** if something changes, edit this file (and the docs it points to) and
  `git commit && git push`. This doc + the linked docs are canonical; chat threads are not.

---

## 0. TL;DR
Two halves that work together:
1. **Customer app** (runs on each customer's own machine, residential IP): discover → resilient
   crawl → quality gate → source-of-truth DB → human-editable 15-column customer sheet → CSV/feed
   + reconciliation against their master spreadsheet.
2. **Vendor licensing proxy** (runs on Matt's VPS, **LIVE**): all LLM extraction is routed through
   it, keyed by a per-customer license. Revoke a key → that customer's crawling stops. Meters
   tokens for billing. **The only place the real LLM key lives.**

Crawling stays local (keeps the residential-IP anti-bot advantage); the VPS only brokers
LLM + license, so there is **no anti-bot regression** from using the VPS.

---

## 1. LIVE deployment — the licensing proxy (operational)
- **Public endpoint:** `https://channeled.org/cfp-proxy`
- **Host:** Oracle VPS (`ubuntu@129.80.155.255`).
- **App dir:** `/home/ubuntu/.openclaw/workspace/cfp-proxy` (a git clone of this repo).
- **Runs as:** uvicorn on `127.0.0.1:8800`, behind nginx (`location /cfp-proxy/`, TLS by Certbot),
  kept alive by **PM2** (app name `cfp-proxy`, user `ubuntu`); survives reboot via the existing
  `pm2-ubuntu.service`.
- **Secrets/data on the box:** `.env` (chmod 600 — vendor LLM key + `PROXY_MODEL` + `LICENSE_DB`);
  `licenses.db` (every key + usage — **back this up**).
- **Verified end-to-end:** unknown key → `401`, active key → `200`, `revoke` → `403`.
- **Operator commands:** see [`licenseproxy/OPERATIONS.md`](licenseproxy/OPERATIONS.md) (issue /
  revoke / usage / floor / quota / restart / logs).
- **Update the running proxy:** `cd` to the app dir → `git pull` → `PM2_HOME=$HOME/.pm2 pm2 restart cfp-proxy`.
- **First-time / rebuild setup (no pasting):** `bash scripts/vps_setup.sh` (installs venv+deps,
  writes `start.sh`; it does NOT touch `.env` or nginx).

**Customer build** — in the customer's `.env` (and **no** LLM key on their machine):
```
CFP_LLM_PROXY_URL=https://channeled.org/cfp-proxy
CFP_LICENSE_KEY=cfp_theirkey
```

---

## 2. What we built (2026-07-06 → 07-09)
Grouped by area; file pointers in parentheses. **98 offline tests green.**

**Crawl reliability**
- JS-shell recovery — fast consent check + bounded render (`fetch.py`).
- Aggregator/org navigation — directory page → the specific event via spreadsheet row context
  (`aggregator.py`, wired in `pipeline.py`).
- HubSpot slow-site name recovery — URL dedupe + junk-URL skip + explore time budget +
  extraction time-box (`scoring.py`, `crawler.py`, `pipeline.py`, `config.py`).
- IP protection — never auto-hit a hard anti-bot site (e.g. Reuters) without a signed-in CDP
  browser; CDP is on by default for live/scheduled runs (`fetch.py`, `cdp.py`).

**Data + review**
- Source-of-truth guard — a failed/thin re-crawl can’t wipe good data (`storage.py`).
- Full editable 15-column customer sheet in the app — verify + human-owned columns, persisted;
  URL on every row; CSV export (`app.py`, `customer_format.py`, `storage.py`).

**Reporting**
- Coverage report — worked/failed % + failed links with reasons + resolution-path breakdown
  (`coverage.py`, `scripts/coverage_run.py`).
- Reconciliation annotator — annotate the customer’s master .xlsx with our diffs (highlight +
  comment + summary tab); taxonomy Confirmed/Changed/Gap-filled/Unverified/Not-crawled
  (`reconcile.py`, `reconcile_xlsx.py`, `scripts/reconcile.py`).

**Licensing (Option D) — built AND deployed**
- Vendor-hosted licensed LLM proxy = kill switch + token metering + version/feature gating
  (`licenseproxy/`), client wiring + friendly launch banner (`config.py`, `extraction.py`,
  `licensing.py`, `app.py`). Both OpenAI and OpenRouter supported.

**Distribution & go-live (2026-07-09, after the backup/installer/billing milestone)**
- **Proxy DEPLOYED LIVE** at `https://channeled.org/cfp-proxy` (see §1). Verified end-to-end
  including a **real crawl through the proxy** from the packaged build (Carbon Capture Europe → PASS).
- **Windows customer installer** (`installer/install.ps1`, `installer/README.md`): one script —
  finds/installs **Python 3.12** (winget), downloads the app, builds venv + deps + the Playwright
  Chromium, writes the customer `.env`, drops a **"CFP Monitor" desktop shortcut**. No provider key
  on the customer's machine. **Validated on the dev machine** (`-SkipDeps` for fast checks, then a
  full run). Remaining: one smoke test on a genuinely clean/fresh Windows profile before mass send.
- **Windows hardening — two real bugs found during install validation, both fixed:**
  1. `.env` was written with a UTF-8 **BOM** (PowerShell's `Set-Content -Encoding UTF8` adds one),
     which corrupted the first line so `CFP_LLM_PROXY_URL` wasn't read → app fell back to
     "direct" mode / no license banner. Fixed: installer writes **no-BOM**; `config.py` loads
     `.env` with `utf-8-sig` so a BOM is tolerated regardless.
  2. A freshly winget-installed Windows Python's default trust store lacks the modern
     Let's Encrypt roots → the license banner's TLS check failed. Fixed: the check verifies via
     **certifi** (`licensing.py`). Crawling was never affected (litellm/httpx already use certifi).
- **Ops:** license-DB backup script + weekly cron (`scripts/backup_licenses.sh`), monthly billing
  readout (`admin billing --period YYYY-MM --rate <$/M tokens> [--csv]`).

---

## 3. Canonical docs (detail lives here)
- [`docs/design/roadmap-status.md`](docs/design/roadmap-status.md) — status by milestone + capability.
- [`docs/design/worklog.md`](docs/design/worklog.md) — append-only session history.
- [`docs/design/model-costs.md`](docs/design/model-costs.md) — LLM model + cost reference (DeepSeek vs GPT-5 vs Claude), per-conference economics, the `PROXY_MODEL` switch note.
- [`licenseproxy/README.md`](licenseproxy/README.md) — proxy architecture + deploy.
- [`licenseproxy/OPERATIONS.md`](licenseproxy/OPERATIONS.md) — day-to-day operator commands (issue/revoke/billing/backup).
- `.env.example` (customer/dev) and `licenseproxy/.env.example` (vendor) — every setting explained.

---

## 4. How each party stays aligned
- **VPS Hermes:** clone is at `/home/ubuntu/.openclaw/workspace/cfp-proxy`. `git pull` → read this
  file + `OPERATIONS.md`. For any multi-step task, run scripts from the repo, don’t paste blocks.
- **Local Hermes:** clone is at `C:\Users\matts\cfp-monitor`. `git pull` → read this file.
- **Matt:** this file’s public URL (section top) is the shareable read-only web page.

---

## 5. Cost & models (quick reference — full detail in `docs/design/model-costs.md`)
- **Extraction model:** DeepSeek-V3 (`deepseek-chat`) via OpenRouter — deliberately cheap; the task
  is clean-markdown → structured JSON, where a frontier model buys little.
- **Per-1M tokens:** DeepSeek ~$0.14–0.27 in / ~$0.28–1.10 out · GPT-5 $1.25 / $10 · Claude Sonnet 5
  $3 / $15 · Claude Opus 4.8 $5 / $25.
- **Per ~100-conference run:** DeepSeek **~$0.50–1** vs GPT-5 ~$5 vs Sonnet ~$7–10 vs Opus ~$16
  (frontier = ~10–30× the cost for marginal gain on this task; our misses are *crawl* problems, not
  extractor intelligence).
- **⚠️ Action:** DeepSeek deprecates the `deepseek-chat` name **2026-07-24** (becomes a V4 alias).
  When ready, update `PROXY_MODEL` in the VPS `licenseproxy/.env` + `pm2 restart cfp-proxy` — one
  edit changes the model for **all** customers, no client touch.

---

## 6. Open / next
- ✅ **License DB backups** — `scripts/backup_licenses.sh` + weekly cron (exact `crontab` line in OPERATIONS.md → Backups).
- ✅ **Monthly billing readout** — `admin billing --period YYYY-MM --rate <$/M tokens> [--csv]`.
- 🟢 **Proxy live** at `channeled.org/cfp-proxy`; **customer installer built + validated on the dev
  machine** (Python/BOM/TLS fixes done). Remaining before mass send: one smoke test on a clean/fresh
  Windows profile; v2 wrap in an Inno Setup `.exe`.
- Optional later: reconciliation **accept/reject per diff**; **Google Sheets** reconciliation (v2);
  `PROXY_MODEL` bump after the DeepSeek name deprecation.
