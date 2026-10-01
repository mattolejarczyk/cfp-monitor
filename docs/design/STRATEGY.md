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

## Agents (Hermes free capacity, Codex subscriptions)
Write every task as a brief (`docs/agents/README.md`: ten parts, success test fixed in advance). One question per brief. The agent proposes, we verify. Results are advisory files, never database writes. Briefs ready: 01 benchmark, 02 platform census, 03 whole-page reader (starts only after 01 passes its spot-check).

## Open decisions (keep this list to what is genuinely open)
1. Send the four-row correction package upstream (`C:/Users/matts/cfp-monitor/experiments/purpose_audit/CORRECTION-PACKAGE.md`).
2. India Energy Week: the customer learns of the 15 Oct date through Monday 10-05's customer page (the Monday send). Display gating shows a passed deadline as Closed, so the corrected date must reach our database before the 07:00 run, or the page will say Closed.
3. After benchmark and census results: build a platform parser, a whole-page model reader, or both; and whether Firecrawl is worth a fetch-layer test.
