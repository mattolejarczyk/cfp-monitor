# STRATEGY: the standing brief for any session or agent on the CFP customer-market project

Read this first, before HANDOFF.md. It is short on purpose. Last revised 2026-10-01.

## Why this project exists
Customers act on one date per conference, so each row must show the date they can submit by, backed by a page we can point to. Today some dates are wrong or unprovable, the weekend research failed about 73% of its Gemini calls, and September cost 134 USD. Scope until further notice: Cybersecurity and Utility only.

## The five-line opener (every session starts with these, in this order)
1. **Where we are:** headline numbers from `docs/design/status.json` (provable submission date; customer agreement) and stage progress.
2. **What is running:** agent tasks out, loops active, with budget used.
3. **What is blocked:** and on whom.
4. **The one decision** waiting for the operator (never more than one in the opener).
5. **Spend:** Gemini and OpenRouter this month against budget.
Then stop and let the operator steer. Do not start with the history of the last session.

## How the operator wants to be worked with
- Stay zoomed out. The operator decides direction and approves actions; the strategist (Claude) handles the weeds and does not hand back micro-questions. Ask at most 3 or 4 high-level questions at a time, each with a recommended answer.
- Present the checklist (what / why / done / not done) after each ITEM is accomplished, not after every reply: `docs/design/PROGRESS-CHECKLIST.md`, board in `docs/design/status.json`.
- Every claim of quality has a number, a source file and a date. "Proved" means measured against an answer key we did not fit to.
- An honest blank beats a confident guess. Report the as-designed result first; label any post-hoc change and score it on fresh items.

## The plan in one view
Stage 0 diagnose (done) - 1 narrow Gemini prompt (grounding proven, quality and the other ~24 fields not) - 2 prove the date ourselves by reading pages - 3 clean existing data - 4 spend less - 5 wire it in behind a shadow run. Nothing is wired into a scheduled job before stage 5.

## Definitions (do not drift)
- **Provable submission date:** the stored deadline is on the cited page and code labels it a submission date. A correct answer is enough; a verbatim quote is preferred, not required.
- **Customer agreement:** among rows the customer's team marked Verified and that have a date, the share where our date equals theirs. Always shown beside the provable number.
- **Benchmark:** 40 events (20 per market), true current submission deadline per event, built by brief 01 and spot-checked, then locked with a checksum. Methods are scored on it, never fitted to it.

## Hard rules (from this project's own mistakes)
- Contract v2.4: downstream never changes what a claim says. Value corrections go upstream as defend-or-correct findings. Customer-sheet fields are the customer's.
- Run `scripts/customer_context.py` before touching any row.
- Public repo: no customer data, credentials or private paths. A patch or heredoc that contains a backslash-b turns into a backspace character on this machine: use the Edit tool.
- Before any new script: check `docs/operations/TOOLING.md` and say `USING EXISTING:` or `NEW CODE: searched ... found nothing`.

## The wisdom pattern (added 2026-10-01, operator's principle)
When a code solution grows complex or keeps failing, **try a cheap or free model first** (DeepSeek, Hermes free capacity), with code verifying its output and an answer key scoring it, before spending more weeks on rules. Evidence so far: a rules reader took days and failed a fresh test (0.33); one DeepSeek call read the same table correctly for $0.0009. Result so far (10-01): promising, not proven. As run precision 0.85 / recall 9 of 12 on 27 fresh pages; 0 wrong-purpose in 69 accepted dates; post-hoc 0.875 / 11 of 12. Needs a larger fresh test before wiring: `experiments/whole_page_reader/RESULT.md`.

## Rule for presenting rounds (operator, 2026-10-01)
Show both dates when a call has rounds. The DEADLINE is the first round that has not passed. Later rounds go in `STATUS DETAILS` (upstream's field; `NOTES` is the customer's, contract v2.0.1), in the order the conference states them. When the first round passes, the next becomes the deadline.

## Agents (Hermes free capacity, Codex subscriptions)
Write every task as a brief (`docs/agents/README.md`: ten parts, success test fixed in advance). One question per brief. The agent proposes, we verify. Results are advisory files, never database writes. Briefs ready: 01 benchmark, 02 platform census, 03 whole-page reader (starts only after 01 passes its spot-check).

## Open decisions (revised 2026-10-01 evening)
1. Send `C:/Users/matts/cfp-monitor/experiments/purpose_audit/NOTE-TO-UPSTREAM-3.md` (new leads + still-open round-2 items; the Saturday 02:00 safeguard is time-critical).
2. Hermes benchmark stage 2 (5 new events): needs a debug Chrome on port 9222 (restart with `scripts/launch_chrome_cdp.bat`), then your go. Rollout ladder in `docs/agents/README.md`.
3. After the benchmark and census: build a platform parser, widen the whole-page model reader, or both; whether Firecrawl is worth a fetch-layer test. The page library (`scripts/page_library.py`, 360 pages) and the refresh policy (`docs/design/page-refresh-policy.md`) are done / designed.
4. Climate Change `(26)` date check in `verify.find_date`: extend after Monday 10-05 (decided).
5. I diff the four corrected rows after Saturday's load and report before Monday 07:00.

## Working with upstream: standing principles (operator, 2026-10-02: "keep this top of mind")

Upstream is a chat session whose only web access is a Google search index (confirmed by upstream 2026-10-02; the first canary run, `docs/qa/UPSTREAM-QA-PROTOCOL.md`). It cannot open an arbitrary URL and its code environment has no network. Every shortcut it takes, intentional or not, comes from that gap plus requests that were not specific enough about WHAT and HOW. So:

1. **Question the mechanism, not just the answer.** Every request states WHAT is wanted, HOW it should be found (a page it opened or a search result that names the event), and what to say when it cannot (a plain "could not open", not "404").
2. **Ask for proof with every fact**: the exact URL, a verbatim sentence, the page title, and one line on how it was obtained (snippet, opened page, or our table). Then verify it ourselves: the gate for the mechanics, a real read for anything that matters.
3. **We read, they format.** Anything that needs a specific page read is read on our side (our reader and the page library, Hermes, or the built-in browser) and handed over as URL plus verbatim sentence for them to apply literally. This is what produced the 22-of-22 delivery; the unaided ones failed.
4. **Sparse patches only**, never regenerated rows; and compare the patch field by field with what we asked for. A difference we did not request is a finding.
5. **Watch for wrong-event attribution.** A search snippet can belong to a different event (the Fuel Ethanol Workshop deadline was replaced by another conference's date on 2026-10-02, turning a correct row wrong). Check the event name in the cited page before accepting a date.
6. **Log what each exchange taught us** (gap, cause, fix) in the worklog, so the requests get sharper each round.

Known gaps so far (2026-10-02): composed URL paths; "404" reported without observing it; full-row regeneration filling fields with filler; deadlines copied from the customer's sheet; snippet attributed to the wrong event; CSV commas left unquoted three times; GATED_STATUS filled twice; location facts wrong (CODASPY, Apres-Cyber).

## Board update checklist (operator, 2026-10-02: the "Working on" and "Waiting on you" sections were stale)

Every time the CFP Status Board is updated, in the same commit as the work, ALL of these, not just the numbers:
1. `python scripts/board_metrics.py --update-status` (headline numbers and both quality indexes).
2. Rewrite `working_on` in `docs/design/status.json` (3 to 5 short items, each with a state: In progress, Waiting on upstream, Queued) and set `now_updated` to today's `as_of`. Never append to `now`; it is one sentence.
3. Prune `decisions` to what is genuinely open and waiting on the operator. Each has an `added` date; anything done is deleted, not left. The board shows each item's age and flags anything older than 2 days.
4. `python scripts/status_dashboard.py` prints a WARNING for any stale item; fix it before publishing. Then republish.
