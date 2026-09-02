# cfp-monitor — Handoff & Single Source of Truth

**Body last fully revised 2026-08-01.** The running session log through 2026-08-28 lives in
[`docs/design/worklog.md`](docs/design/worklog.md) - read it for the latest state until these
sections are refreshed in a verified session.

> **Where the CFP work stands, end of 2026-09-01.**
>
> **Two check-3 rows and the manifest stub section from ACCEPTED.** Current files:
> `delivery_v23_check4_43col.csv` and `audit_cybersecurity_utility_43col_r10_20260901.csv`.
> Both remaining rows are upstream's: H2 MEET needs the rounds-table subpage (its date is
> **locked to 2026-09-30 under 2.4** - Nicolia verified it himself via cell history, so do not
> re-derive it), and Global Energy Show needs a person at a CAPTCHA. **We do not bypass
> CAPTCHAs.**
>
> **RUN `scripts/customer_context.py` BEFORE REMEDIATING ANY ROW.** On 2026-09-01, 22 rows were
> repaired that the customer had already verified or acted on, and two were about to ship as
> contradictions - ESF MENA queued as discontinued while they hold an acceptance and a $12,500
> sponsorship decision. The data has been in `client_conferences` since 08-30. The gate ranks by
> rule; the customer ranks by what they can still act on, and those orders are near-inverted.
>
> **Cross the id boundary with `identity.to_canonical`, never by comparing EVENT_IDs.** The
> delivery carries upstream's ids, the client layer carries ours (contract 5.4). The documented
> join scores **87 of 87**; a join to the `conferences` table scores 43 and looks like a finding.
> `identity.assert_mapped` refuses an empty map - a path fault otherwise returns zero findings
> that read as two records agreeing.
>
> **Export a customer sheet with `/export?format=csv`, NEVER `/gviz/tq?tqx=out:csv`.** gviz types
> each column and silently drops non-conforming text - it blanked eight sponsorship deadlines
> including ESF MENA's $12,500, and the diff reported them as customer edits.
>
> **Four defect classes in one day were one cause:** a row fixed downstream, regenerated broken
> by the next research pass. `preserve_repaired_citation` is now in the generator, ordered after
> the R22 filter so it cannot rescue an inadmissible citation.
>
> **Open, and worth doing next: seven rows marked `Verified` with nothing to verify** - blank
> deadline, sometimes no evidence URL at all. R2 only fires on a *date* and R11 reads
> `false` + `Verified` as agreeing, so the gate cannot see it. Past the threshold for a check.
>
> **Also open:** six scripts still parse the seed map themselves (debt that may shrink, never
> grow); 18 client rows unmatched; and the operator's next ask - surface the customer's own
> `status` / `speaker_abstracts_submitted` as filter chips on the HTML, the same way
> "Check against your sheet" was wired.

> **Where the CFP work stood, end of 2026-08-31.**
>
> **OPEN, HIGH: eight SecureWorld rows hold a conference date in `SUBMISSION DEADLINE`** - one
> reads as due tomorrow. They cite an events LISTING; the stored quote is two consecutive rows of
> it, and the first date became the deadline while the second (correctly) became `START DATE`.
> SecureWorld publishes no deadline at all - its real speaker page is a redirect stub. Sent as
> `handoff-files/Defect_SecureWorld_Listing_Dates_20260831.md`. **Upstream's field: do not blank
> it here** - R1 deliberately never touches a deadline value.
>
> **A date is not a deadline unless something says so.** Proposed as a gate check: a quote with
> no deadline vocabulary is inadmissible for `SUBMISSION DEADLINE` unless the cited URL is itself
> a call page. On the current delivery this flags exactly those eight rows and nothing else.
>
> **Ask a site for its own index before trusting a URL.** Five guessed call-for-speakers URLs
> across three SecureWorld hosts all return HTTP 200 with "page not found" bodies - invisible to
> a status-code check. `scripts/check_urls_against_site.py` (read-only) checks a cited URL
> against robots.txt, the sitemap and the homepage nav. **No sitemap step exists anywhere in the
> joint process**; discovery is upstream's side, verification ours.
>
> **`extract_citations` can return a quote that is not on the page.** Three of five came back
> composed from our own fields (`'Threat Defense 2026 2026-09-01'`). Fetch and test every
> extracted quote before applying it. Two recut cleanly and are the only pending changes:
> Climate Change and Hydrogen Technology Expo NA.
>
> **Read `docs/operations/DECISION-TREE.md` before deciding a row needs research.** It is the
> executable specification of what follows from a conference's timing - what the customer sees,
> what we do, what it costs. `src/cfp_monitor/lifecycle.py` is the same thing in code; if they
> disagree, the doc wins.
>
> **`STATUS` is DERIVED at display time, never read from the file.** 126 rows disagreed with the
> stored value; only 8 were corrections. Deriving beats storing **only where a date on the row
> proves the stored value wrong** - never from a blank field, never between two true words.
>
> **Cadence changed:** re-research is now **weekly, Saturday 02:00** (was monthly), so Sunday's
> free verification sweep sees fresh research. `scripts/run_end_to_end.ps1` chains the whole
> loop and **stops at the gate** - a delivery that is not ACCEPTED is never imported.
>
> **The sponsorship fields cannot fill yet, and it is not a research gap.** Upstream's audit
> script emits **36 columns against the agreed 43** - it never picked up v1.3 (lifecycle) or v1.5
> (organizer, sponsorship). A fresh 113-row run on 2026-08-31 was rejected by the gate at check 1.
> They agreed the same day and are updating the export. **Do not tell anyone these fields will
> populate on the next run** - that claim was made twice and was wrong both times.
>
> **Amendment v1.7** (`docs/operations/Contract_v1.7_Amendment_Additive_Sponsorship.md`), agreed
> in principle 2026-08-31: downstream may fill `SPONSOR_*` **only where upstream left it Unknown
> or blank**, marked as ours, never overwriting. The blank is the boundary, so an upstream row can
> only gain. `ORGANIZER` stays theirs alone. **Implementation is deliberately blocked on the
> 43-column export** - building against a schema that is not emitted is how the last gap formed.
>
> **Amendment v1.6** (`docs/operations/Contract_v1.6_Amendment_Deadline_Rounds_And_Sources.md`):
> **R23** - the deadline shown is the NEXT round a person can act on, because conferences run
> tiered rounds and one date cannot hold three. **R22** - a social post or link shortener can
> never evidence a deadline, and may be withdrawn even on a passed deadline.
>
> **67 editions corrected** with every `event_id` byte-identical. That warning had printed every
> Sunday since 2026-08-12 into a log nobody reads; **integrity warnings now reach the digest**
> with an owner and a deadline.
>
> Still blocking, and both upstream's: **27 check-3 citations** (the gate returns REJECTED and
> nothing downstream runs) and **31 dead links** handed back 2026-08-27, unactioned.
>
> ---
>
> **Where the CFP work stood, end of 2026-08-30.**
>
> **The customer's own sheet is now in the system.** Two clients loaded - Utility Global (58 rows,
> Utility) and Arnica (53, Cybersecurity) - into three additive tables: `clients`,
> `client_conferences`, `industry_candidates`. **Per-client values never go on `conferences`**:
> its columns are shared and single-valued, and `status_details` is 349/373 filled with OUR crawl
> text that looks exactly like the customer's column of the same name.
>
> Matcher applied: **80 of 111 rows joined at 100%**, 21 need a human decision (region and edition
> variants), 10 are genuinely absent and are pending promotion candidates. Only certainty sets an
> `event_id`.
>
> **41 rows are marked "Needs Verification" by the customer** - 18 Utility Global, 23 Arnica. A
> work queue aimed at us that nothing had ever read. Ownership and plan are the open question.
>
> **The weekly digest now reads as a report** - definitions, actions, owners, timeframes - after
> its "Recovered since last week (19)" turned out to be 4 real recoveries and 13 of our own
> cleared citations. Three canaries now cover reports that claim unearned success.
>
> **The 31 standing dead links were already sent to upstream on 2026-08-27 and are unactioned.**
> The digest cannot yet tell "needs sending" from "sent, awaiting upstream" and will repeat the
> instruction every Sunday.
>
> Customer deliverables for the 2026-09-02 meeting live in `handoff-files`:
> `Conference Review 2026-08-30.html` and `Customer_Facing_Schema_20260830.md`. The v1.5 sponsor
> fields are **empty by design** until the 2026-09-01 re-research.
>
> ---
>
> **Where the CFP work stood, end of 2026-08-29.**
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
> **`scripts/trace_quote_to_page.py`** is the tool for those 28: it walks the event's own site for
> the cited sentence and either retargets the citation or withdraws it under R1. It refuses to
> withdraw when no page could be read or the deadline has already passed. **Use `--dry-run` first.**
>
> **Upstream is aligned on data and contract as of this evening** - all eight falsifiable claims in
> their summary were checked against the files and hold. They are a day behind on architecture
> (they do not yet know about `sitewalk.py`, `canaries.py`, the enforcement test, the INCOMPLETE
> verdict or the tracer), and their test count of 619 is now 634.
>
> **108 and 184 are different populations.** 108 is the blank-deadline slice of the 186 check-3
> failures; 184 is the total blank-deadline citations cleared across the whole file. Do not
> reconcile them and conclude rows went missing.
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
- [`docs/design/roadmap-status.md`](docs/design/roadmap-status.md) — status by milestone + capability (is the product built). Its July summaries are stale; the milestone table is current to 2026-08-17.
- `handoff-files/CFP_Pipeline_Status.html` — **the operational one-pager: six macro steps, what is wired under each, and where the loop is open.** Lives in the PRIVATE repo because it names clients. This is the live roadmap for weekly work; regenerate it whenever a step changes state.
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
