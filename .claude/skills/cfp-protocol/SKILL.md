---
name: cfp-protocol
description: >-
  MANDATORY reading gate for any work on the CFP conference-monitoring pipeline.
  Use this BEFORE writing code, validating, verifying, fetching, auditing,
  de-duplicating, repairing or shipping anything that touches a market list, a
  delivery CSV, a citation, a submission deadline, or the grounded audit. Triggers
  include: CFP, call for papers, market audit, delivery, acceptance gate,
  grounding, citation, dead link, submission deadline, conference row, EVENT_ID,
  IS_PROJECTED, robotics/cybersecurity/semiconductor/bioeconomy/utility market,
  run_market_audit, accept_delivery, or any *_audited.csv / *_input.csv file. Also
  use when asked to "check", "confirm" or "look into" a market run - diagnosis turns
  into delivery work faster than it looks.
---

# CFP pipeline - read before you act

This pipeline has a written, two-sided contract with a customer, an agreed acceptance gate,
and a documented runbook. **Almost everything you are about to do already has a defined way
of being done.** Skipping the read has cost real rework.

## Do this first, every time

Read these three, in order, before writing any code or touching any data:

1. **`docs/operations/pipeline-contract.md`** - the *why*. Joint Pipeline Contract v1.1.
   Governs the interface between upstream (grounded research) and downstream (cfp-monitor).
2. **`docs/operations/market-runbook.md`** - the *how*. Exact commands, in order, and the
   failure modes already seen in the wild.
3. **`docs/operations/TOOLING.md`** - the *what with*. Every script that already exists and
   which stage it belongs to.

Then state, in one line, which stage you are working in and which existing tool covers it.
If none does, say so explicitly before writing anything new.

## The failure this skill exists to prevent

On 2026-08-05/06 a session rebuilt a delivery validator that duplicated eight checks already
in `scripts/accept_delivery.py`, and a citation checker that reached two rungs of the
five-rung fetch ladder. It withdrew six citations on plain-HTTP 404s - evidence the contract
explicitly calls insufficient - and left `EXPECTED_COLS` at 35 after adding a 36th column, so
the real gate would have rejected every delivery while the parallel tool reported PASS.

The instruction to read the runbook already existed. It did not fire because the work started
as a small diagnostic question and grew. **Re-check the stage you are in when the task
changes shape.**

## Non-negotiables

- **One gate.** `scripts/accept_delivery.py` decides whether a delivery is acceptable.
  Never build a second opinion. New contract checks go *into* it.
- **Only 404/410 disprove a link.** 403, 500, timeouts and empty bodies mean
  blocked-or-broken, never dead. Before acting on any "dead link", get the browser second
  opinion: `scripts/recheck_dead_links.py --db ...` or `--csv <delivery.csv>`.
- **Never re-implement a rung of the fetch ladder**
  (`crawl4ai -> playwright-fallback -> cdp -> manual-antibot`). `src/cfp_monitor/fetch.py`
  and `cdp.py` own it.
- **Citation withdrawal is a citation-only edit (R1).** Clear the URL and the quote. The
  submission deadline is never touched. Record which URL was withdrawn - dropping it silently
  makes the decision impossible to review.
- **Discovery is innocent until proven guilty (2.1).** "We could not verify it" is a label,
  never a deletion.
- **An honest blank beats a confident guess (2.6).** Decline rather than guess (2.5).
- **The verified count is reported, never targeted.** Pushing it up produces invented
  citations.
- **Changing the schema changes the gate.** If you add or remove a column, update
  `EXPECTED_COLS` in `accept_delivery.py` in the same change, and amend the contract.

## Before spending API requests

The grounded audit costs money and quota, and quota has been exhausted once already.

- Preview first: `run_market_audit.py --dry-run` reports rows, request count and time,
  and makes no API calls.
- Never diagnose against the production key. If investigating needs API calls, state a
  budget first and get agreement.
- Batch with `--limit` and inspect between batches on a market's first run.
- A quota error is terminal for the window - the run stops itself. Do not retry, and do not
  switch models to dodge it: the quota is account-level and shared.

## When something fails twice the same way

Two identical failures on the same row means stop and inspect the row. Retrying blind spends
requests and teaches nothing.

## Where things live

| | |
|---|---|
| Downstream app, contract, gate, runbook | this repo |
| Upstream working area: audit script, market CSVs | a folder outside this repo |
| Cross-party documents, manifests, agendas | `handoff-files`, beside the upstream area |
| Long-term memory | the Obsidian vault - see its `MEMORY.md` |

**Paths are machine-specific and deliberately not recorded here.** Read the local
`CLAUDE.md` for the actual locations on this machine.

The physical split between the two working areas is itself a hazard: work done in the Markets
folder is still governed by the contract that lives in the repo.
