# cfp-monitor — Worklog (running memory)

Append-only log of what changed each work session. Newest first. Keep entries short and factual
(what + why); the current-state snapshot lives in `roadmap-status.md`, deep design notes elsewhere.

---

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
- 78 offline tests green; all pushed to `main`.

## 2026-07-06
- **JS-shell recovery**: fast consent presence-check + bounded fallback render (cybertech PARTIAL→PASS).
- **Aggregator/org navigation** (`aggregator.py`): use spreadsheet row context (name/location/dates) to
  hop from a directory/org page to the specific event once, before spending LLM budget.
- **LOCATION + START DATE captured from the customer xlsx** (`GoldRecord.context()`, `load_inputs()`),
  threaded via `run_urls(contexts=)` so navigation runs on the real lists.
