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
Grouped by area; file pointers in parentheses. **97+ offline tests green.**

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

---

## 3. Canonical docs (detail lives here)
- [`docs/design/roadmap-status.md`](docs/design/roadmap-status.md) — status by milestone + capability.
- [`docs/design/worklog.md`](docs/design/worklog.md) — append-only session history.
- [`licenseproxy/README.md`](licenseproxy/README.md) — proxy architecture + deploy.
- [`licenseproxy/OPERATIONS.md`](licenseproxy/OPERATIONS.md) — day-to-day operator commands.
- `.env.example` (customer/dev) and `licenseproxy/.env.example` (vendor) — every setting explained.

---

## 4. How each party stays aligned
- **VPS Hermes:** clone is at `/home/ubuntu/.openclaw/workspace/cfp-proxy`. `git pull` → read this
  file + `OPERATIONS.md`. For any multi-step task, run scripts from the repo, don’t paste blocks.
- **Local Hermes:** clone is at `C:\Users\matts\cfp-monitor`. `git pull` → read this file.
- **Matt:** this file’s public URL (section top) is the shareable read-only web page.

---

## 5. Open / next
- ✅ **License DB backups** — `scripts/backup_licenses.sh` + weekly cron (install line in OPERATIONS.md).
- ✅ **Monthly billing readout** — `admin billing --period YYYY-MM --rate <$/M tokens> [--csv]`.
- 🟡 **Customer installer** — `installer/install.ps1` (+ README) built; **needs one validation run on
  a clean Windows machine** before mass distribution. v2: wrap in an Inno Setup `.exe`.
- Optional later: reconciliation **accept/reject per diff**; **Google Sheets** reconciliation (v2).
