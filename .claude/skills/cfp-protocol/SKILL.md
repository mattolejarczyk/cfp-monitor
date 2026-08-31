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
4. **`docs/operations/DECISION-TREE.md`** - the *what follows*. Where a conference sits in its
   life decides what the customer sees, what we do next, and what it costs. Read it before
   deciding a row needs research: on 2026-08-11 eleven of ninety-three grounded requests were
   spent hunting calls for conferences that had already taken place. It is executable
   (`src/cfp_monitor/lifecycle.py`) - if the two disagree, the document wins.

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

## The second failure: a rule whose premise expired

On 2026-08-08 four defects were found in code that had been correct when written:

- `clean_city` corrupted 23 of the 26 rows it "repaired" (Seattle -> Washington, Tokyo ->
  Tokyo Big Sight), and since the canonical key derives from the city, 24 EVENT_IDs with it.
  It was RIGHT in July, when grounding really did put venues in `CITY`. Upstream fixed their
  side; nobody re-examined ours; a repair became a corruption. **Every test passed** - they
  all asserted the function FIXES broken input, none that it LEAVES GOOD INPUT ALONE.
- `make_handback.py` had its counts hard-coded in a header string, so every hand-back after
  the first reported cycle one's numbers to upstream as current.
- `recheck_dead_links.py --csv` checked `CFP_SUBMISSION_URL` but not `SUBMISSION URL`, so the
  mode meant to catch dead links skipped the link the customer actually clicks.
- A clear-before-import scoped by market membership deleted 4 rows silently, because
  `conference_markets` still held the previous cycle's memberships.

None was carelessness. **The shape to watch for is logic whose assumption stopped being true
and nothing re-checked it.** Before trusting a transformation, ask what it assumes about its
input and whether that is still so.

## Non-negotiables

- **One gate.** `scripts/accept_delivery.py` decides whether a delivery is acceptable.
  Never build a second opinion. New contract checks go *into* it.
- **Hold ourselves to the standard we set for upstream.** We require them to cite the exact
  page and quote the sentence. On 2026-08-08 we disputed 24 of their deadlines using our own
  cached crawls - 15 were decided by L0/L0s, which fetch nothing - and a customer found the
  first two wrong by hand. Before ANY finding goes to another party it must clear
  `scripts/audit_evidence.py`: fetched from the cited page, through the ladder, real content,
  quotable, internally consistent, and naming which call the date belongs to (R10).
- **No quote, no dispute.** A rival value we cannot quote is a regex hit, not evidence.
- **A mutation needs a reconciliation.** After any import or migration, run
  `scripts/check_invariants.py`. It is not a second gate: the gate judges a DELIVERY against
  the contract, this judges the DATABASE against the delivery. A file can be perfectly
  acceptable and still land in a database that lost four rows.
- **Never clear rows before importing.** Import upserts. Import, then reconcile, then delete
  only what you can positively identify as superseded. Anything with no counterpart and no
  declared reason is KEPT and declared in `market_sheets/held_rows.txt` (contract 2.1).
- **Never bless a golden-master diff without reading every line.** Changing anything that
  derives a value (`clean_city`, `event_id`, `gated_status`, `confidence`) rewrites stored
  data across every row. `tests/test_golden_derivation.py` and `scripts/snapshot_delivery.py`
  turn that into a diff you approve or reject. Blessing a corruption makes it permanent.
- **A reported number is derived, never written down.** If a count appears in a report, it is
  computed at render time from the data it describes.
- **Test that GOOD input survives, not only that bad input is fixed.** That inversion is the
  cheap general defence, and its absence is why 26 corrupted cities passed a full suite.
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

**If two rounds of prompt tightening have not moved a number, the prompt is not the problem.**
Five citation pilots landed on this: a model asked to REPORT what a page said produced fluent,
correctly dated sentences that were never on the page, and no instruction fixed it. A model
asked to POINT AT a sentence in text we fetched ourselves can be checked, because the answer
must be a literal substring of what we supplied.

Ask whether the answer is checkable without trusting the answerer. If it is not, move the
question until it is - do not write a third prompt rule. Full pattern, its three rules, and
where it should go next: **"Where an LLM is safe, and where it is not"** in the runbook.

## Where things live

| | |
|---|---|
| Downstream app, contract, gate, runbook | this repo |
| Upstream working area: audit script, market CSVs | a folder outside this repo |
| Cross-party documents, manifests, agendas | `handoff-files`, beside the upstream area |
| Long-term memory | the Obsidian vault - see its `MEMORY.md` |

## What runs without anyone starting it

| Job | When | Cost |
|---|---|---|
| CFP Weekly Verification | Sunday 01:00 | none - no LLM calls |
| CFP Monthly Re-Research | 1st, 02:00 | ~400 grounded requests |

Weekly re-checks what is loaded; only the monthly run DISCOVERS anything new. Before running
an audit by hand, check whether the scheduled job already covers it - quota was exhausted
once already.

**Paths are machine-specific and deliberately not recorded here.** Read the local
`CLAUDE.md` for the actual locations on this machine.

The physical split between the two working areas is itself a hazard: work done in the Markets
folder is still governed by the contract that lives in the repo.
