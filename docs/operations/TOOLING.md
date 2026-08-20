# Tooling index - what already exists, and when to use it

**Read this before writing any new tooling for the CFP pipeline.**

This file exists because on 2026-08-05/06 a parallel delivery validator and a parallel
citation checker were built from scratch while `accept_delivery.py` and
`recheck_dead_links.py` already did the job - better. The information needed to prevent that
was available, but answering *"does a tool already exist for this?"* meant reading twenty
filenames and guessing. One page fixes that.

If you are about to write something that validates, fetches, verifies, repairs or reports,
check this list first. If it is not here, add it here when you build it.

---

## The three-stage shape

Work on a market moves through three stages. Use the tool that belongs to the stage.

| Stage | Question it answers | Tool |
|---|---|---|
| **Before** research | Is this input worth spending requests on? | `preflight_market.py` * |
| **During** research | Is this market finished, and did anything get lost? | `validate_market_output.py` * |
| **Before** shipping or loading | Does this delivery meet the contract? | **`scripts/accept_delivery.py`** |
| **After** any import or migration | Does the DATABASE still hold what was delivered? | **`scripts/check_invariants.py`** |
| **Before** anything leaves the building | Can we PROVE this to someone who disagrees? | **`scripts/audit_evidence.py`** |

`accept_delivery.py` and `check_invariants.py` are not duplicates: the first judges a
DELIVERY against the contract, the second judges the DATABASE against the delivery. A file
can be perfectly acceptable and still be imported into a database that quietly lost four
rows - which is exactly what happened on 2026-08-08.

`*` lives in the **upstream working area**, a folder outside this repo. Its path is
machine-specific - see the local `CLAUDE.md` rather than hard-coding it here.

**`accept_delivery.py` is the only authoritative gate.** Nothing else decides whether a
delivery is acceptable. If a check belongs to the contract, it belongs in that script - do
not add a second opinion elsewhere.

---

## Verification and citations

| Script | What it does | Notes |
|---|---|---|
| `scripts/accept_delivery.py` | The full acceptance gate. Structure, citation resolution, quote-verbatim, prose-vs-projection, past deadlines, R2/R8/R11/R12, placeholders, series rows, deadline sanity, defunct events, stub declaration. | Exits non-zero on failure. `--no-network` skips the citation fetches. `--db`/`--market` add criteria 7-8. **Read check 1 first** - if rows do not parse, every later check is measuring shifted columns. |
| `scripts/recheck_dead_links.py` | **Second opinion on links the fast pass called dead**, using a real browser. Distinguishes TRULY DEAD from BLOCKED-TO-SCRIPTS. | `--db` for loaded rows, `--csv <path>` for a delivery not yet imported. **A plain-HTTP 404 is never sufficient evidence to withdraw a citation.** Run this before believing any "dead link" finding. |
| `scripts/verify_grounding.py` | Layers 0/1/2 verification: own-crawl cross-check, link check, live page fetch including PDFs. | One market at a time. `--market` takes UPSTREAM's spelling, via the seed CSV. |
| `scripts/unconfirmed_citations.py` | **The ask for upstream**: every row whose deadline we could not confirm against its own cited page, grouped by what would fix it. | Not an accusation - for most we have no opinion on the date, only that nothing can confirm it. Flags rows already raised as disputes so nobody answers twice. |
| `scripts/citation_fixes.py` | **Proposes a better citation** where the one on record cannot support its own claim - using deep pages our own crawls already verified. | Offers a correction only when the CALL matches: the quote must name a call, it must suit the row's opportunity type, and it must agree with the call the cited URL names. R3 applies both ways - never propose a shallower page. Everything else goes to a human, not upstream. |
| `scripts/build_evidence.py` | **Promotes evidence to a queryable table.** One row per claim: field, value, source URL, quote, origin (grounding vs ours). Recovers what the crawl pipeline produced and buried in `result_json`. | 4,021 claims across 9 fields on first run, 2,616 of them our own readings nothing could query. `origin` keeps upstream's claims and ours distinct - contract 5.1. |
| `scripts/audit_evidence.py` | **Verifies claims against their own cited pages**, grouped by page so each is fetched once. Soft-404 detection. Writes a per-claim verdict, the quote actually found, and whether it is EXPORTABLE. | Measured 1.3s/page. A verdict says what the page said; `exportable` says whether it may go to another party. See "The outbound standard" in the runbook. |
| `scripts/find_replacement_links.py` | **Chases the CURRENT submission page for links that died.** Runs the full pipeline over each conference's own site, verifies the candidate resolves, then classifies it CONFIDENT / REVIEW / REJECT against the contract. | Reads dead links from `link_checks`. Writes NOTHING back - `SUBMISSION URL` is upstream's field (section 3), so output is a correction attached to the hand-back. Uses the OpenRouter key, never Gemini. **Do not try a cheaper keyword-only pass** - it was tried 2026-08-09 and returned speaker profiles and an about-us page; the docstring explains why. |
| `scripts/snapshot_delivery.py` | **Golden master over a REAL delivery.** Derives every row and diffs against a blessed snapshot; exits non-zero if derivation moved. Run before and after any change to `grounding.py`. | Snapshot must live in the PRIVATE upstream repo - the delivery is the customer's asset and this repo is public. `--exclude` has no default so scratch files in the working area are an explicit decision. |
| `scripts/cdp_ctl.py` | `check` / `wait` / `stop` for the CDP Chrome the weekly sweep drives. | `stop` matches on the dedicated `cfp-cdp-profile` directory, NEVER on `chrome.exe` - it must never close a window a human is using. Verified: 11 of 41 Chrome processes matched, 30 untouched. |
| `scripts/check_invariants.py` | **Database integrity after a mutation.** Every delivered row still present; no undeclared extra rows; no venue or postcode in a canonical key; nothing left unverified; event_id unique; link results populated. Exits non-zero on any violation. | Rows deliberately kept but absent from the delivery are declared in `market_sheets/held_rows.txt` - an undeclared extra is a violation, which is the point. Run by `weekly_verify.py`, and by hand after any import or migration. |
| `scripts/weekly_verify.py` | **The weekly sweep.** Runs `verify_grounding.py` across every market, then the browser recheck, then diffs against the previous state and emails a digest of what CHANGED - dead submission links and newly contradicted deadlines. Markets are auto-discovered from `market_sheets/*_seed.csv`. | **No LLM calls, no API quota.** Discovery is the separate MONTHLY grounded audit. Entry point `scripts/run_weekly.bat`. |
| `scripts/extract_citations.py` | **We extract the citation; upstream only supplies candidate pages.** Fetches each candidate through the full ladder, then picks the sentence stating the deadline. A quote it emits is on the page by construction. Output feeds `apply_resolutions.py --citations` unchanged. | Selection is an LLM judgement checked against the page: the answer must be a literal substring of text WE fetched, and the stored quote is re-cut from the page, so a paraphrase or a composed sentence cannot survive. The CALL label gets its own weaker check. `--no-llm` drops to string matching, which cannot tell a submission deadline from a withdrawal deadline on the same date. **See "Where an LLM is safe" in the runbook before copying this pattern.** |
| `scripts/check_dns.py` | **Does every host we cite still exist?** DNS only, no fetch, sweeps a delivery and the database in seconds. Exits non-zero on any that fail, so it can gate a send. | Distinct from `link_checks`, which asks what a page RETURNS. A lapsed domain never reaches a server, so it surfaces as a timeout - which the ladder deliberately treats as "blocked, not disproven" (5.2). Right for a site defending itself, exactly wrong for a domain that is gone, so nothing ever noticed. Found 6 of 403 hosts dead across 15 customer-facing fields on 2026-08-11. **Resolving is not being the right site**: `ablc.co` resolves and reads fine - it is a medspa. Feed its output to `build_review_page.py --dead-hosts` so the page withholds links to them. |
| `scripts/weekly_discovery.py` | **The only weekly job that spends API quota.** Builds the queue of rows that are unconfirmed AND still have a future deadline, optionally runs upstream's discovery over it, then puts the result through our extraction and merge guard. | Scoped deliberately: 9 rows today, so ~9 requests a week against the ~400 a full re-research costs - that scoping is what makes weekly affordable. **Refuses rather than truncates** when more rows qualify than `--max-rows`, because a spike means a data problem. Excludes rows already verified, retired, withdrawn, or past their deadline (JUDGEMENT rule 1). Reports only without `--run-discovery`; nothing it finds can land without clearing the merge guard. **The scheduled job runs it WITHOUT `--apply`** - the guard is strong but has never run unattended, and a Sunday digest merged on Monday still keeps the customer promise that a new call is caught within a week. Upstream's script needs an interpreter ours is not: `google-genai` and `pandas`. It auto-detects one and proves it by import before spending anything. Wired into `run_weekly.bat`, skipped silently if the key or upstream's script is missing so a discovery failure cannot lose the verification that already ran. |
| `scripts/fix_edition.py` | **Separates identity from edition.** Freezes `key_year` from the current edition so no canonical key can move, then derives `EDITION` from the conference's own `START DATE`. Never touches `event_id`. | 67 of 392 rows carried an edition disagreeing with their start date, and because `event_id()` builds the key from edition, two duplicate records were created by it. **A key is a name, not a fact** - the fix is to stop reading meaning out of the key, not to rewrite 67 keys. Report-only by default; backs up the DB on `--apply`. Where no date exists (33 rows) it changes nothing rather than guessing from the name. See contract amendment v1.4. |
| `scripts/match_customer_sheet.py` | **Matches a customer sheet to our canonical rows** and reports how sure it is and why. Their sheets carry no key of ours, so every ingest of their validation feedback starts here. Per market. | Three CERTAIN tests return 100% on their own: exact URL, a domain that resolves to exactly ONE row in our whole database (the exclusion is the proof), and name+city+date agreeing. Six supporting tests vote, weighted by precision MEASURED against anchors rather than assumed. **Editions are not ambiguity** - two of our rows for the same conference in different years collapse to one answer. Sequence position is a signal where their list is an export of ours, but aligned on DOMAIN: aligning on names produced confidently wrong pairs, because their names are abbreviations of ours. Utility, 2026-08-13: 50 of 57 at 100%. **Method and the six iterations behind it: `MATCHING-METHODOLOGY.md`. Operational steps: `customer-sheet-matching.md`.** |
| `scripts/refresh_delivery.py` | **Brings the delivery spreadsheet up to date from the database. A MERGE, never a regeneration.** Writes only the columns we own; the customer's and upstream's are protected and never touched. | `OWNED` vs `PROTECTED` encodes contract section 3. Writing the CSV out of the database would destroy `NOTES`, `STATUS DETAILS` and `SUBMISSION URL`, which are not ours. Excel-lock preflight, per-row `--overrides`, and a row/column reconciliation on write. |
| `scripts/run_full_cycle.py` | **The whole pipeline end to end, in the one order that is correct.** Preflight, DB backup, invariants, evidence, audit, DNS, export-checks, refresh, page, invariants again. | Every stage existed as a documented command and running them by hand still went wrong, because the ORDER is the part that matters. Use this rather than the individual commands unless you are debugging one stage. |
| `scripts/export_checks.py` | **Writes the deadline-verification CSV the customer page reads** - the input behind "Deadline confirmed", "Need to Verify" and its three sub-buckets. | Two filters, worked out by reproducing a hand-made file: `origin='grounding'` and a non-blank deadline. Precedence is current-citation-wins, then worst-first, then newest. Without this step the page reports 0 for everything, which reads as a result. |
| `scripts/weekly_review.py` | **Turns the weekly run into a REVIEW rather than a log.** Decision-shaped: what must be decided this week at the top, everything needing no decision counted rather than listed. | Deterministic - every number is a SQL query, no LLM. A summary read at a glance and trusted is the worst place for something that can hallucinate, and being deterministic means it can be sent without anyone reading it first. **Prototype: three known defects, see the task list before wiring it into the weekly job.** |
| `scripts/reconcile.py` | **Annotates a customer master `.xlsx` against our database.** Row-level comparison of what they hold against what we hold. | Predates `match_customer_sheet.py` and solves the neighbouring problem - that one establishes WHICH of our rows a customer row denotes, this one compares the values once identity is settled. Use the matcher first, this second. |
| `scripts/diagnose_unread.py` | **Why did a candidate page yield nothing?** Classifies the wall rather than guessing at it. | A blank has at least five causes and they need opposite responses - a 403 is retryable through the ladder, a 404 is not, an empty render is a JavaScript problem, an anti-bot page is neither. Lumping them together is how a live page gets recorded as dead. |
| `scripts/probe_menu_links.py` | **Measures how much is behind menu links we currently discard.** Changes nothing. | Built to answer whether link-following is worth implementing BEFORE implementing it. The pattern is worth copying: measure the opportunity, then decide. |
| `scripts/md2pdf.py` | **Renders a markdown document to a print-ready PDF.** Used for the customer and upstream documents that need to be handed over rather than read in a repo. | Tables, block quotes, headings and a page footer. Kept in the repo because the PDFs in `handoff-files` are otherwise NOT reproducible - the converter previously lived in a scratch directory that gets deleted. |
| `scripts/extract_sponsor_quotes.py` | **Produces `SPONSOR_QUOTE` from the page upstream supplied** - our half of amendment v1.5 (R20a). Reads rows where `SPONSOR_REQUIRED=Yes` with a URL and no quote yet, fetches through the ladder, and selects the sentence. | Same division as a deadline: they supply the claim and the page, we prove the sentence is on it. **Reuses `locate_verbatim` from `extract_citations.py` rather than reimplementing it** - a second copy is a second thing that can drift from the guarantee. A booth or delegate price is rejected even when verbatim, because floor space is not a speaking slot. An outage reports `unavailable`, never `blank`: a considered blank stands as a finding and an outage must not be written as one. Report-only without `--apply`. |
| `scripts/investigate_event.py` | **Is this one event's call open?** Walks the event's own site through the fetch ladder and reports verbatim evidence either way. Ours, not upstream's - once we hold a domain, re-reading it is verification. | **Two passes, run BLIND to each other, then compared.** Regex triages which pages deserve a model call and offers a candidate; the model answers the open question independently and its answer must be a literal substring of the page. Showing the model the regex answer would buy agreement bias, not confirmation. A scorecard records which pass answered - first measurement on Decarb Connect was regex-only 3, all navigation, so on that site it earned its place as triage and not as an opinion. `--no-llm` for the free-but-noisy pass alone. It gathers evidence and does not decide: 2.1 holds, an absent call-for-speakers page is not proof the call is shut. |
| `scripts/verify_report.py` | Human-readable verification summary. | |
| `src/cfp_monitor/verify.py` | `link_status()`, `fetch_text()` - the cheap pass-1 primitives. | 403 = real-but-blocked, NOT dead. Only 404/410 disprove. |

## Fetching - the escalation ladder

Defined in `src/cfp_monitor/coverage.py` as `PATH_ORDER`:

```
crawl4ai  ->  playwright-fallback  ->  cdp  ->  manual-antibot  ->  unresolved
```

| Rung | What it is |
|---|---|
| `crawl4ai` | Headless, cheapest. |
| `playwright-fallback` | Our own Playwright. **Runs HEADED by default** (`CFP_FALLBACK_HEADLESS=false`) because headless gets 403'd. A visible window means a CAPTCHA is solvable by hand. |
| `cdp` | Attaches to a REAL Chrome on port 9222, dedicated profile `~/cfp-cdp-profile`. `ensure_cdp()` auto-launches it. Disconnects rather than closes. For hard anti-bot domains. |
| `manual-antibot` | Formally recorded outcome: manual / signed-in needed. Not a failure. |
| `unresolved` | Nothing worked. |

Never re-implement a rung of this ladder. `src/cfp_monitor/cdp.py` and `fetch.py` own it.
Running only the first rung and declaring a link dead is the specific mistake this row exists
to prevent.

## Delivery handling

| Script | What it does |
|---|---|
| `scripts/import_grounding.py` | Import a delivery into `grounding_facts`. |
| `scripts/repair_delivery.py` | Rebuild a delivery broken by unquoted commas. Refuses to write unless every rebuilt row validates on six independently-shaped fields. **A repaired file still fails the gate** - upstream must fix its writer. |
| `scripts/join_parts.py` | Join a delivery pasted as numbered chat parts. |
| `scripts/apply_resolutions.py` | Apply upstream dispute resolutions. **`--citations <csv>` is the MERGE GUARD** for a citation-repair round: a blank never overwrites a populated field; a proposed citation must pass OUR fetch and have its quote on the page; a failed proposal leaves the old one standing; every accepted change is logged old -> new. Reports by default, writes with `--apply`. |
| `scripts/make_handback.py` | Generate the hand-back document for upstream. |
| `scripts/fix_records.py` | Targeted record corrections. |
| `scripts/rename_markets.py` | Market vocabulary changes. |

## Running and reporting

| Script | What it does |
|---|---|
| `scripts/run_batch.py` | Batch crawl runner. |
| `scripts/coverage_run.py` | Coverage across the escalation ladder. |
| `scripts/exec_report.py` | Executive summary output. |
| `scripts/launch_ui.bat` | Desktop UI; starts CDP Chrome and sets `CFP_CDP_URL`. |
| `scripts/launch_chrome_cdp.bat` | CDP Chrome only, dedicated profile, port 9222. |
| `scripts/run_scheduled.bat` | **RETIRED 2026-08-17 - do not use, do not schedule.** Crawl-and-alert run over a fixed URL list (`examples\urls.txt`), from the original single-machine design. Superseded by `run_weekly.bat`. Its URL list never left the shipped placeholder (`pycon.org` / `djangocon.us`), and its line 7 calls `uv run python` - the pattern later banned for stranding a `.venv` in this directory. Left on disk, unscheduled. If you want a scheduled sweep, `run_weekly.bat` is the answer. |
| `scripts/run_weekly.bat` | Task Scheduler entry point for `weekly_verify.py`. Runs from the LIVE build with its own interpreter. **Starts CDP Chrome** if nothing is on 9222, and stops only a browser it started itself. |

## Upstream working area

Not in this repo, but part of the same pipeline. Path is machine-specific; see the local `CLAUDE.md`.

| Script | What it does |
|---|---|
| `run_market_audit.py` | The grounded audit. Rate limiter over every request, quota circuit breaker, per-request timeout, progress ledger keyed on INPUT names, `--limit`, `--dry-run`, `--redo-stubs`. Exit codes: 0 clean, 1 needs review, 3 out of quota, 130 interrupted. |
| `preflight_market.py` | Input-file report before spending requests: duplicates, series rows, missing fields, dead baseline URLs. **A report, not a gate.** |
| `validate_market_output.py` | Production checks only - coverage against input, renames, stubs. Delivery criteria belong to `accept_delivery.py`. |
| `run_all.ps1` | One market: preview, confirm, audit, validate. Key from environment only. |
| `run_overnight.ps1` | Several markets in sequence. Halts on quota/interrupt, pushes through stubs. |

---

## Rules that keep this from rotting

1. **Check this file before building.** If something close exists, extend it.
2. **Add your tool here the moment you build it**, with the stage it belongs to.
3. **One gate.** Contract criteria go in `accept_delivery.py`, nowhere else.
4. **Never widen a schema without checking `EXPECTED_COLS`.** Adding `FORMAT` as column 36
   silently made the gate reject every delivery on check 1 while a parallel validator
   reported PASS.
