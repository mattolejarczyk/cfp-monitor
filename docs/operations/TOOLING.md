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
| `scripts/weekly_verify.py` | **The weekly sweep.** Runs `verify_grounding.py` across every market, then the browser recheck, then diffs against the previous state and emails a digest of what CHANGED - dead submission links and newly contradicted deadlines. Markets are auto-discovered from `market_sheets/*_seed.csv`. | **No LLM calls, no API quota.** Discovery is the separate MONTHLY grounded audit. Entry point `scripts/run_weekly.bat`. |
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
| `scripts/apply_resolutions.py` | Apply upstream dispute resolutions. |
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
| `scripts/run_scheduled.bat` | Crawl-and-alert scheduled run over a URL list (`examples\urls.txt`). **Not the verification sweep** - see `run_weekly.bat` for that. |
| `scripts/run_weekly.bat` | Task Scheduler entry point for `weekly_verify.py`. Runs from the LIVE build with its own interpreter. |

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
