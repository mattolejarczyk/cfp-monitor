# cfp-monitor — Worklog (running memory)

Append-only log of what changed each work session. Newest first. Keep entries short and factual
(what + why); the current-state snapshot lives in `roadmap-status.md`, deep design notes elsewhere.

---

## 2026-08-30 - the customer's own sheet enters the system

**The weekly digest was reporting our own cleanup as good news.** First scheduled run under the
NEW-vs-STANDING split fired clean, and its headline read "Recovered since last week (19)".
Measured: **4** rows actually verified. Of the other 16, **13 were citations we cleared on
08-29** - a row with no citation has nothing left to contradict, so it drops to not_found
mechanically. Same shape as the gate printing ACCEPTED for skipped checks; second occurrence in
three days. `build_digest` now splits the three cases and `still_cited` has no default.

"Standing backlog 80 -> 32" was likewise not 48 repairs: 49 URLs stopped being referenced when we
cleared their citations. **Zero were fixed.**

**The digest now reads like a report** - every category states what it MEANS, the ACTION, the
OWNER and the TIMEFRAME, with an At-a-glance table. The first draft printed "35 row(s) need
someone to act" above three rows reading "nothing to do now", because actionable was INFERRED
from having an owner. Owned and due-now differ; it is declared per category now. Real answer: 32.

**Canaries generalised to cover reports that lie.** Every entry before today was about data or
rules, implying our reports had never been the problem. 17 canaries now.

**The customer sheet layer.** Two client sheets (Utility Global, Arnica) snapshotted, hashed and
loaded. What they contain that changes the design: `STATUS DETAILS` is a dated field-research
log; **41 rows marked "Needs Verification"** aimed at us; call windows with timezones where we
hold one date; sponsorship hand-typed into the deadline column. **`LOGIN` and `PW` columns
exist** - empty today, but the snapshot rewrites rather than copies so they can never reach a
git repo.

**Layer 2 - the client dimension.** The database had no client concept at all. `conferences`
columns are single-valued and shared, so two cybersecurity clients tracking Black Hat would
overwrite each other. Three additive tables: `clients`, `client_conferences`,
`industry_candidates`. **`conferences.status_details` is 349/373 filled with OUR crawl text** and
looks exactly like the customer's column - importing theirs would have destroyed it.

**Same defect a third time:** first load reported 111 promotion candidates, every row, because
nothing had been matched yet. Candidates now require the matcher to have run and found nothing.

**Matcher applied** - 80 of 111 joined at 100%, 21 need a human, 10 are genuinely absent. Only
certainty sets an `event_id`. The middle band is region and edition variants. My earlier crude
"27 missing" was wrong; the real number is **10**.

**The 31 standing dead links were already sent** - 2026-08-27, unactioned. A regex that did not
exclude backticks first said "0 of 31 sent"; the truth is 31 of 31. The digest still cannot tell
"needs sending" from "sent, awaiting upstream".

**Customer deliverables:** `Conference Review 2026-08-30.html` (406 rows, 29 fields, sponsor and
organizer wired) and `Customer_Facing_Schema_20260830.md` for their UI/UX developer, superseding
the 38-column list in `Backend_Data_Design_20260807.md`. The v1.5 sponsor fields are **empty by
design** and populate on the 2026-09-01 re-research.

---

## 2026-08-29 (evening) - the tracer moved in, and upstream's alignment summary was checked

**The quote tracer is now `scripts/trace_quote_to_page.py`.** One of the six delivery-folder
scripts was a real capability - "find the page that actually carries this quote, or withdraw the
citation honestly". The other five apply a named list of rows to a named file on a particular
day; putting those in `scripts/` would say "run this again", which is false, and is how a tools
directory stops being trusted.

Moving it forced the refactor. It carried its own crawler, so `test_no_reimplemented_crawling.py`
would have rejected it. It now uses `sitewalk.plan` and `rank_links` - **the first entry
`PENDING_MIGRATION` has lost rather than gained** (11 remain). It is the most destructive tool in
the repo, so the safety is not the script being careful: every decision routes through
`rules.may_withdraw_citation`, which refuses when no page could be read and when the deadline has
already passed. Seven tests, two of which read the source: it must call sitewalk rather than
`urljoin`, and must not contain the 35-character prefix match that could attach a citation to
whichever page shared an opening phrase. Smoke-tested on ProMat 2027 from the live queue: 10
pages walked, withdrawn under R1, stamp advanced, dry run wrote nothing. **634 tests green.**

`auto_trace_r3b_high.py` was DELETED from the Markets folder rather than left beside it. A
superseded file in a working folder gets picked up eventually - that is exactly how
`delivery_r3b_traced_43col.csv` nearly shipped with 14 wrong withdrawals. It stays in git history.

**Upstream sent an alignment summary and every falsifiable claim in it was checked against the
files, not agreed to.** All eight hold: 406 x 43; `SOURCE_AS_OF` = 2026-08-29 on exactly 5 rows
with 401 historical (08-03 x20, 08-05 x54, 08-06 x162, 08-07 x165); `delivery_r3b_traced_43col.csv`
absent from disk; check-3 categories 108 / 50 / 28; zero blank-deadline rows still carrying a
citation (230 blanks, 0 cited); `ACCEPTED_COLS = {43}`; v1.4 recorded; R3b retired. Their
inspection-stamp protocol matches `rules.withdrawal_changes(fetched=...)` exactly.

**Two things to correct back.** Their test count (619) predates the evening work (634), and their
summary does not mention `sitewalk.py`, `tests/canaries.py`, the enforcement test, the INCOMPLETE
verdict or the tracer - so they are aligned on data and contract but a day behind on
architecture. Also **108 and 184 are different populations**: 108 is the blank-deadline slice of
the 186 check-3 failures, 184 is the total blank-deadline citations cleared across the whole
file. Nobody should later "reconcile" those and conclude rows went missing.

---

## 2026-08-29 (afternoon) - the acceptance was wrong, and v1.4 came out of finding out why

**Supersedes the entry below, which says the cycle closed accepted.** It did not.

**The acceptance came from a partial gate.** Every run had used `--no-network`, which SKIPS
criteria 2 and 3 - the two that fetch pages - and the gate printed `RESULT: ACCEPTED` anyway. On
a full networked run, check 3 failed on **183** rows. FIXED the same day: the gate now reports
INCOMPLETE, never ACCEPTED, when any check was skipped, and exits non-zero.

**The 183 were then nearly mishandled twice.** First we assumed they were our own blindness,
since `fetch_text` deliberately skips the browser - sampled 10, and 9 were genuine. Then an
automated tracer proposed withdrawing 18 citations; **14 had deadlines that had already passed**,
one by 317 days. A CFP page comes down after its deadline. That output was discarded.

**Measuring instead of estimating changed the whole picture.** All 314 cited rows re-fetched and
classified:

    no deadline claimed at all   108  (58%)   a citation for a claim the row never makes
    deadline already passed       50  (26%)   expected decay
    genuinely live call           28  (15%)   the real work

We had predicted "most of it is staleness". It is 26%. The dominant category was one neither
side had considered - rows carrying a `DEADLINE_QUOTE` that is an event date, a calendar strip
or a site disclaimer, with no deadline to evidence.

**Amendment v1.4** (`docs/operations/Contract_v1.4_Amendment_Citation_Scope.md`) exempts both,
taking check 3 from 186 to 28, and **retires R3b** - of 34 rows it flagged, 14 had their quote
present on the cited homepage, so a hardened shape rule would have rejected working citations.

**Three defects recurred in scripts written hours apart**, which produced the day's real output:
- `src/cfp_monitor/rules.py` - the business rules as pure functions, each returning a reason.
  `withdrawal_changes` takes `fetched` with NO DEFAULT, so a withdrawal cannot skip the
  `SOURCE_AS_OF` decision the way ours did.
- `src/cfp_monitor/sitewalk.py` - one site-walking implementation. There were four, and the same
  three bugs had been fixed in some copies and not others.
- `tests/canaries.py` + `test_no_reimplemented_crawling.py` - one record per real incident, and
  a test that fails the build if a fifth crawler appears.

**Corrections we sent after being wrong:** the "most of it is staleness" prediction; classifying
136 rows as live calls when blank deadlines were being read as "not yet passed"; and withdrawing
four rows without advancing `SOURCE_AS_OF` after rendering 11-14 pages of each site - upstream's
rule was right and ours was not.

Current file: **`delivery_v14_final_43col.csv`**. 622 tests pass.

## 2026-08-29 (morning)
**The v1.5 cycle closed.** `delivery_phase2_remediated_43col.csv` gates ACCEPTED with zero
failures, five days ahead of the 2 September backstop. The entry below was written before this
happened and says the delivery is still rejected - it was, at that moment. This supersedes it.

Getting from rejected to accepted took three things, and only one of them was upstream's:
- Upstream's remediation script fixed check 6 and R11 correctly, and applied the R2 safeguard we
  asked for - no `IS_PROJECTED=false` without a live citation.
- We made three edits rather than round-trip: narrowed the check 4 prose fix from **81 rows to
  7** (the sweep was replacing accurate text with something FALSE for concluded events - "Google
  Cloud Next '26 ... has concluded" became "awaiting official announcement"), added SCOPE Summit
  to the R11 list, and added GreenBiz 27 to the past-deadline list because it is `Fixed
  Deadline`, not rolling.
- **The last blocker was our own gate.** R8c compared `EVENT_ID` globally when section 10
  excludes market from the key precisely so one event stays one record across markets. Fixed to
  key on (EVENT_ID, Market), guarded both ways. That is the check that produced our "merge them
  under R9" advice - retracted the day before, cause fixed now.

Imported and reconciled: 392 rows, no loss, invariants hold, zero rows still citing a dead URL,
`sponsor_required` populated on 391. **`SOURCE_AS_OF` untouched** - every stamp still from the
original July/August passes, nothing stamped with the import date. The discipline held through
upstream's export, our propagation fixes, the remediation and the import.

`ACCEPTED_COLS` dropped to `{43}`; the two transition tests were INVERTED rather than deleted so
the record of why the window existed survives. 595 tests pass.

One correction sent after acceptance: upstream's manifest declared the wrong seven rows as
ungrounded stubs - they used our check 4 list, because our acceptance note asked them to
"declare the 7 ungrounded stub rows" without listing them and that was the only list of seven in
the document. Our ambiguity, their reasonable reading. Reissued with the real seven.

## 2026-08-28
Long CFP day: the weekly digest was root-caused, the dead-link backlog was drained into an
actual correction list, and the v1.5 delivery was pulled forward from 2 September to today.

**Weekly verification digest, root-caused.** The 2026-08-27 run emailed 119 dead submission
links. Every line was TRUE - ten probed independently, all genuine 404s - and the report was
still close to useless. Three defects, all fixed:
- 119 lines described only **80 distinct URLs**, because a URL living in several of the four
  customer-facing fields was emitted once per FIELD. Now keyed by (event, url). 119 -> 82.
- **Zero of the 80 were new**; all were in the 2026-08-16 digest. The digest now leads with
  NEW SINCE LAST RUN and follows with the standing backlog, and only new failures count toward
  the subject-line issue count.
- `link_checks` was `(url primary key, state, checked_at)`, overwritten every run, so it could
  not say whether a link broke this week or had never worked. Added `http_status`, `first_seen`,
  `last_alive`. Answer, once it could be asked: **of 80 dead links, 4 have ever worked. 76 have
  never resolved on any check we have run.**

**Backlog drained into corrections.** `find_replacement_links` over the dead set produced 15
CONFIDENT replacements with evidence and **21 calls confirmed OPEN** - moved pages, not ended
calls. New `find_event_pages.py` chases dead MAIN_INFO_URL / CONFERENCE URL, which the submission
chaser never touched (38 of 82 links).

**v1.5 expedited.** Live build was 12 files stale with the gate hard-coded to `EXPECTED_COLS =
38`, so upstream's 43-column file would have been rejected on arrival. Synced, rehearsed the full
chain on Utility against a DB copy, and added `R19b` - an advisory that fires when 20+ rows share
one `SOURCE_AS_OF`, because with `SPONSOR_REQUIRED` defaulting to Unknown that stamp is the only
thing separating "inspected, nothing found" from "never looked at".

Phase 1 (15 replacements + 2 event pages + 51 R1 withdrawals) and Phase 2 (7 REVIEW verdicts,
4 disputes, 1 org page) applied and gated. Delivery still REJECTED on check 4 (7), check 6 (11),
R11 (7); R8c (12) is our own false positive.

**Four claims went out unverified today and had to be corrected** - three of them ours:
- Told upstream the 12 duplicate `EVENT_ID`s were R9 name-drift and to **merge** them. All 11
  are one event in several markets - same name, distinct markets, zero duplicates inside any
  per-market file, and contract section 10 says market is excluded from the key precisely so
  this works. Merging would have deleted real market memberships. Retracted before they acted.
- Disputed Pittcon 2027's deadline. The page runs **eight** calls; we quoted the Invited Symposia
  one and upstream's `2026-09-28` matches a live call. **Our dispute was wrong.** Withdrawn.
- Claimed the rehearsal covered `SPONSOR_QUOTE` extraction before running that step.
- Reported `mem-save.ps1` missing. `agentos\tools` is HIDDEN; `Test-Path` on the exact path
  would have said so in one line.

**The characteristic failure of this codebase, named:** a value presented as verified when the
check either did not run or measured something else. Today it appeared as the "dead site" label
(wrong for 4 of 5), `link_checks` with no history, the digest that could not tell new from
standing, "no live page found" counting 38 pages nobody searched for, a relative URL that
`link_status` could not verify and therefore passed, and a hand-back naming an attachment
filename frozen three weeks earlier. Six instances, one shape.

## 2026-08-21
- **Multi-edition false positive fixed** (`consolidate.py`). The caution compared raw
  date strings with only `.strip()`, so `AUGUST 10-13, 2026` vs `August 10-13, 2026` -
  a pure case difference - counted as two values, tripped `len(date_vals) >= 2` and put
  a customer-facing "Caution: crawled pages disagree on dates" on rows that agreed. New
  `_date_key()` builds a canonical COMPARISON key (case, dash style, comma/period,
  spacing, month abbreviations - deterministic aliases only). It deliberately does NOT
  parse dates: an uninterpretable string keeps its own key rather than being guessed
  into one, so real disagreements still report. Raw strings are still what gets
  displayed. 4 tests added in both directions (cosmetic variants collapse; genuinely
  different dates and uninterpretable strings still flag). 569 green, golden-derivation
  diff clean.
- **Two stale brief items retired, measured not assumed.** The daily brief had recycled
  three "CFP polish" items since ~2026-07-26 from a v3-era TODO block in the (now frozen)
  cross-project Project Log. Verified against the code: the cosmetic `Submit via :` item
  was already fixed and regression-tested (`test_consolidate.py`); the date-normalize item
  was real and is the fix above. The stretch item ("capture explicit CFP open/close dates
  more aggressively - only Bioprocessing yielded a deadline in the v3 run") is obsolete:
  measured on the live DB, `conferences.cfp_close_date` is populated on 81/373 rows (21.7%)
  and `grounding_facts.deadline` on 168/392 (42.9%), so the v3-era premise no longer holds.
  There is also no `cfp_open_date` COLUMN in `conferences` and no open-date field anywhere
  in the pipeline contract - the customer deliverable does not include one. Not built. Note
  the standing rule: the verified count is reported, never targeted.
- **Why those items kept coming back (fixed upstream of CFP).** They were being mined from
  a v3-era TODO block in the cross-project Project Log, which was frozen 2026-08-20. Root
  cause found in the AgentOS brief engine: its exclusion rules are written with `/` but the
  note paths come from `path.relative()`, which on Windows uses `\` - so the Archive and
  dashboard exclusions had never fired on this machine. Fixed in agentos (`9389bbe`), and
  the three TODO boxes are now ticked with outcomes. Relevance to CFP: a stale doc that
  onboarding is FORCED to read is worse than no doc - the same reason this worklog and
  HANDOFF must stay current (see the 2026-08-21 EOD process change: daily wraps now update
  THIS repo, not a shared cross-project log).

## 2026-08-20
- **Investigator hardened + run across every unconfirmed row.** `investigate_event.py`
  now follows the site's own menu (reads homepage links, follows the promising ones)
  instead of guessing paths (`335b4d6`); `diagnose_silence()` separates domain-gone /
  404 / 403 / JS-shell / our-ladder-failing and retries live sites through a real browser
  (`a2ff286`). Ran over all 24 unconfirmed rows: 11 returned the call OPEN with a verbatim
  quote; 5 corroborate deadlines already held (Pittcon, SEMICON China, ISE, DIA, ALD/ALE).
  3 commits, 565 tests green.
- **Two of my own claims fell over (kept as lessons).** (1) "model-only = 0" does NOT
  prove the regex triage is sound - the model only sees pages the regex already flagged,
  so it measures the regex opinion, not the triage; measuring triage needs an ablation
  nobody has run. (2) The tool labeled 5 sites "DEAD"; direct probing showed 4 of 5 wrong
  (two 403 refusals, two answered a plain request while our ladder came back empty, one
  truly gone). A confident wrong negative is worse than a plain failure.
- **FEW host migration - fixed.** `fuelethanolworkshop.com` 404s at the root; its own
  redirect names the successor `2027-few.bbiconferences.com` (same pageId, host only), so
  every BBI URL can be rewritten mechanically. New citation names the 2027 call and the
  Feb 12 2027 deadline unaided. Per contract section 3 this is upstream's field - a
  correction for the hand-back, not a DB edit. `overrides_20260820_few.csv` is local-only.
- **v1.5 readiness: not ready.** Utility has 0 of 44 rows on all five v1.5 fields (columns
  exist, no wide delivery landed). Upstream's local `run_market_audit.py` is stale (7 Aug,
  36 columns, no v1.5) - a Utility run today would spend ~54 grounded requests to produce
  a file our own gate rejects. No confirmed 43-column delivery date exists on disk.

## 2026-08-17
- **CFP weekly digest email activated** (M6/M7): `CFP_SMTP_*` + `CFP_ALERT_TO` set as
  user-level env vars; a real send verified end to end. Traps: `weekly_verify.py` does NOT
  read a .env file, and user-level `setx` is sufficient (tasks run InteractiveToken).

> Catch-up note (2026-08-21): 2026-08-11 through 2026-08-14 were logged as Obsidian memory
> notes (Agent Inbox) during that stretch and not mirrored here - see those notes for the
> evidence-table / outbound-gate / weekly-discovery / customer-sheet-matching detail. This
> worklog resumes normal per-session updates via the one-step /eod.

## 2026-07-18
- **UI: live crawl progress + non-destructive downloads** (`app.py`, `pipeline.py`). `run_urls`
  gained an optional `on_progress(done,total,current)` callback (best-effort); the Run tab shows
  "Crawling 15 of 51: <site>… · ~ETA left" with the in-flight site name. Results/table/downloads
  now render from `st.session_state` OUTSIDE the Run-button block, so a download no longer reruns
  the page into a blank state. Run tab is explicitly read-only; editing stays in Review & Verify.
- **Competitive review → 3 borrowed, componentized improvements** (commit, 117 tests green):
  1. **TRACK column** (`tracks.py`) — coarse Speaking/Awards/Other, derived purely from the
     `opportunity_types` we already extract; appended LAST in `CUSTOMER_HEADERS` (client's 15-col
     order untouched); read-only in the Review editor. Blank when nothing detected — never guessed.
  2. **Edition stale-trap** (`consolidate.edition_consistency`) — downgrades a shaky Open to Needs
     Review when the deadline belongs to a different/past edition; only ever downgrades, never
     fabricates, fires only on unambiguous years (guards against false flags).
  3. **"Watching this page" status copy** — honest "located the CFP page, not open yet" wording.
  Each is isolated from conference identification. Rival was an independent prototype for the same
  client; its own honest recall was 1 find / 54 sites → **open frontier: measure our recall on the
  same list** (higher value than more features). Shareable write-up published as a Claude Artifact.
- **Industry dimension + run input-audit + Tier-1 review filters** (127 tests). Driven by the PR-firm
  workflow (speaking/awards across industries, worked to deadlines):
  - **Industry**: per-run label in the Run tab, overridden per-row by an optional "Industry" column in
    the upload (`ConferenceResult.industry`, `run_urls(industry=)`, `uploads` header scan). Persisted
    non-tracked in `storage` (migrated; never blanked by a run without one).
  - **Run input-audit** (explains the 54→51): `uploads.normalize_urls_and_contexts_audited` returns a
    manifest {raw/kept/dropped[{url,reason,duplicate_of}]}; stored per run (`runs.input_manifest`,
    `Store.recent_runs`); shown in the Run tab after upload and a Review "Run history + input audit" panel.
  - **Tier-1 filters** in Review & Verify: Industry / Status / Track / Deadline-window / text search,
    applied to the editable sheet (save + CSV download honor the filter). INDUSTRY is a read-only column,
    NOT added to the customer 15-col export. `filtering.parse_deadline` accepts only a full y-m-d (no
    guessing) so a PR user never sees a false "closing soon". `python-dateutil` declared explicitly.
  - Deferred (noted for the user): true per-run historical snapshots ("show the sheet as of run X");
    current model = living master record + change history, so "latest run" == current state.

## 2026-07-09
- **License proxy DEPLOYED LIVE** at https://channeled.org/cfp-proxy (Oracle VPS, nginx→uvicorn:8800,
  PM2). Verified: unknown 401 / active 200 / revoked 403.
- **Reconciliation annotator** shipped (`reconcile.py` + `reconcile_xlsx.py`): annotated .xlsx copy
  of the customer master sheet.
- **Licensing go-live extras:** friendly client license banner; OpenAI+OpenRouter support.
- **Ops:** `scripts/backup_licenses.sh` (weekly cron), `admin billing` (per-customer token/$ readout),
  `installer/install.ps1` (Windows one-shot customer installer, now hardened for clean-machine unknowns).
- **Handoff:** `HANDOFF.md` (single source of truth for Matt + both Hermes), `scripts/vps_setup.sh`.
- **Installer validated on dev + Windows hardening (two real bugs fixed):** (1) `.env` written with a
  UTF-8 BOM dropped `CFP_LLM_PROXY_URL` → installer now writes no-BOM; `config.py` loads via
  `utf-8-sig`. (2) fresh-Python TLS trust store lacked modern roots → the license banner check now
  verifies via certifi (`licensing.py`). Crawling was never affected (litellm/httpx use certifi).
  Installer pins Python 3.11/3.12; literal launcher here-string; `-SkipDeps`/`-ShortcutDir` for
  validation. Proved the packaged build crawls end-to-end through the live proxy (Carbon Capture → PASS).
- **Model/cost reference** added (`docs/design/model-costs.md`): DeepSeek-V3 extraction ~10–30× cheaper
  than GPT-5/Sonnet/Opus for this task; per-conference economics; `PROXY_MODEL` switch; DeepSeek
  `deepseek-chat` name deprecates 2026-07-24 (update `PROXY_MODEL` then). 98 offline tests green.
- **Installer hardened for clean-machine unknowns.** `install.ps1`: graceful message when `winget`
  is absent (points to python.org, "Add to PATH") + re-verifies Python landed after winget; launcher
  `.bat` now prints an explicit friendly note when Google Chrome isn't installed (normal sites still
  crawl; only hard anti-bot needs Chrome) instead of silently no-opping; non-fatal Chrome heads-up at
  install time. Also normalized the whole script to ASCII — stray UTF-8 em-dashes in a no-BOM `.ps1`
  were tripping the PowerShell 5.1 tokenizer. Validated: parses clean, `-SkipDeps` completes, `.env`
  written without a BOM.

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
