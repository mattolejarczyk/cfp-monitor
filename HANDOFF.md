# cfp-monitor — Handoff & Single Source of Truth

**Body last fully revised 2026-08-01.** The running session log through 2026-08-28 lives in
[`docs/design/worklog.md`](docs/design/worklog.md) - read it for the latest state until these
sections are refreshed in a verified session.

> **Where the CFP work stands, end of 2026-08-29.**
>
> **CURRENT FILE: `delivery_v14_final_43col.csv`.** Earlier files in that folder are superseded;
> `delivery_r3b_traced_43col.csv` was deleted (it carried 14 wrong withdrawals).
>
> **The delivery is NOT accepted.** An earlier ACCEPTED verdict this morning came from gate runs
> using `--no-network`, which SKIPS criteria 2 and 3 - and the gate printed ACCEPTED anyway.
> Always gate with the network before declaring anything.
>
> The gate now reports **INCOMPLETE** rather than ACCEPTED whenever a check was skipped,
> and exits non-zero - so that specific mistake cannot recur.
>
> On a full networked gate it passes everything except **check 3, at 28 rows** - live calls whose
> cited page does not carry its quote. That is upstream's active research queue, several with
> deadlines in early September.
>
> **Amendment v1.4 is written and implemented** (`docs/operations/Contract_v1.4_Amendment_Citation_Scope.md`).
> Criterion 3 now evaluates ACTIVE deadline claims only - blank and passed deadlines exempt -
> which took the failure from 186 to 28. **R3b is retired**: it tested URL shape as a proxy, and
> of 34 rows it flagged, 14 had their quote present on the cited homepage.
>
> **Three modules now enforce what used to be remembered:** `src/cfp_monitor/rules.py` (business
> rules as pure functions, each returning a reason), `src/cfp_monitor/sitewalk.py` (one
> site-walking implementation, was four), and `tests/canaries.py` (one record per real incident).
> `tests/test_no_reimplemented_crawling.py` fails the build if a fifth crawler appears.
>
> **Never "fix" R8c in the data** - multi-market events legitimately share one `EVENT_ID`
> (section 10); the gate check is per-market and correct.
>
> Open: upstream's 28 live calls and six organisation-domain searches. `ACCEPTED_COLS` is `{43}`.
>
> **Two joins that matter.** Our canonical `EVENT_ID` does NOT match upstream's (contract 5.4) -
> any script keyed on it silently matches nothing. Join on the URL being replaced. And a
> decision must be applied to every customer-facing URL field, not one: the review page renders
> four.
This file is the shared reference for **Matt + both Hermes instances**
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

3. **Grounding pipeline** (added late July 2026): an upstream Google-Search-grounded research
   process supplies one 35-column CSV per market; we import it as *unverified discovery*, check
   its claims against live pages, and label the customer view by how well-evidenced each row is.
   Upstream claims never overwrite crawled facts — they live in their own table.
   **Start here:** [`docs/operations/pipeline-contract.md`](docs/operations/pipeline-contract.md).

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
  full run). **Hardened for clean-machine unknowns:** graceful message if `winget` is absent (points
  to python.org) + re-verifies Python landed; launcher prints a friendly note when Chrome isn't
  installed (normal sites still crawl); script normalized to ASCII (stray em-dashes were tripping the
  PS 5.1 parser). Remaining: one smoke test on a genuinely clean/fresh Windows profile before mass send.
- **Windows hardening — two real bugs found during install validation, both fixed:**
  1. `.env` was written with a UTF-8 **BOM** (PowerShell's `Set-Content -Encoding UTF8` adds one),
     which corrupted the first line so `CFP_LLM_PROXY_URL` wasn't read → app fell back to
     "direct" mode / no license banner. Fixed: installer writes **no-BOM**; `config.py` loads
     `.env` with `utf-8-sig` so a BOM is tolerated regardless.
  2. A freshly winget-installed Windows Python's default trust store lacks the modern
     Let's Encrypt roots → the license banner's TLS check failed. Fixed: the check verifies via
     **certifi** (`licensing.py`). Crawling was never affected (litellm/httpx already use certifi).
- **Windows validation follow-up (2026-07-16):** actual licensed desktop install completed the
  first-launch license/CDP smoke test and passed a one-conference crawl. Customer output now has two
  cheap guardrails: the extraction prompt requests ASCII punctuation and the final 15-column
  customer table/CSV normalizes fields to Excel-safe ASCII. `.xlsx` intake is intentionally strict:
  only literal URL values in visible Column B become crawl targets; the matching row's A/C/D values
  (name/location/event date) feed the existing one-hop directory/organization resolver. Package XML,
  hyperlinks, notes, and other columns are ignored. A bad source URL is surfaced as an input-quality
  issue, never silently replaced.

- **Ops:** license-DB backup script + weekly cron (`scripts/backup_licenses.sh`), monthly billing
  readout (`admin billing --period YYYY-MM --rate <$/M tokens> [--csv]`).

---

## 3. Canonical docs (detail lives here)

**The grounding pipeline (read in this order):**
- [`docs/operations/pipeline-contract.md`](docs/operations/pipeline-contract.md) — **authoritative.** The upstream/downstream interface: principles, ownership boundary, verification model, the 9-point acceptance gate, the review loop, and rulings on cases that have caused real defects. Cold starts begin here.
- [`docs/operations/market-runbook.md`](docs/operations/market-runbook.md) — the operating procedure: exact commands in order, what to check at each step, and failure modes with their fixes.
- Upstream holds *Specification v4.3* (their mechanics). Where it and the contract disagree, **the contract wins** and v4.3 is amended.

**Everything else:**
- [`docs/design/roadmap-status.md`](docs/design/roadmap-status.md) — status by milestone + capability.
- [`docs/design/worklog.md`](docs/design/worklog.md) — append-only session history.
- [`docs/design/model-costs.md`](docs/design/model-costs.md) — LLM model + cost reference (DeepSeek vs GPT-5 vs Claude), per-conference economics, the `PROXY_MODEL` switch note.
- [`docs/operations/windows-desktop-install.md`](docs/operations/windows-desktop-install.md) — canonical licensed Windows install, Desktop shortcut, CDP, update, validation, and recovery runbook.
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
  machine** (Python/BOM/TLS fixes done) and **hardened for clean-machine unknowns** (winget-absent
  and Chrome-absent both handled gracefully; script is ASCII-clean). Remaining before mass send: one
  smoke test on a clean/fresh Windows profile; v2 wrap in an Inno Setup `.exe`.
- Optional later: reconciliation **accept/reject per diff**; **Google Sheets** reconciliation (v2);
  `PROXY_MODEL` bump after the DeepSeek name deprecation.
