# ACT-51 follow-up design: add the missing customer rows automatically (NOT BUILT; written 2026-10-06)

Phase 1 (built, report only): `scripts/customer_coverage.py` states each Saturday which customer rows ahead of today are not on the research list. Phase 2 below makes the process ADD them. It is
a design, not code; nothing here runs.

## What phase 2 does

Each Saturday, right after the coverage check and before the 5-row test:

1. `customer_coverage.py --propose <runs_out/qa/<date>/proposed.csv>` lists the rows NOT in the queue (class-C layout).
2. A new gate, `scripts/auto_add_gate.py` (to be written with tests), sorts each proposed row into ADD or HOLD FOR A PERSON. Only ADD rows reach the next step.
3. `scripts/add_customer_rows.py --classified <gated csv> --apply` appends the ADD rows to `<Market>_input.csv` with a BLANK EVENT_ID_CANON (identity is upstream's; contract 5.4). Its existing proof
   (backup, `.tmp`, read-back equals old rows plus exactly the new ones) stays the only writer.
4. The same Saturday research then covers the new rows (research cost: one row, about 2 to 3 grounded requests each).
5. A dated request file for upstream (`experiments/purpose_audit/NOTE-TO-UPSTREAM-<n>.md`, a DRAFT: the operator sends it) lists the events that now need an id, with URL and start date. When ids
   come back, `scripts/stamp_given_ids.py` stamps them and writes the ledger. Until then the row is researched but held back from the load (stamp_input_ids.py, existing behaviour).
6. The recap says how many rows were added this week and how many are waiting for an id, next to the COVERAGE line (target for NOT in queue stays 0 after the add).

## Safeguards (why it can be trusted unattended)

* **Edition guard.** A row is ADDED only when the customer's URL, or a URL the page confirms, belongs to an edition that is still ahead AND no input row has the same domain with a different year
  (that is a held other edition: HOLD, a person decides). This is the Gartner IAM 2026 / 2027 and OWASP case in `docs/qa/ACT-51-coverage-reproduction-20261006.md`.
* **Linked but missing.** A row linked to an event we hold (event_id set) that is not on the list goes to HOLD, not ADD: adding a second row for a held event is how duplicates start. A person decides
  between "put the held event on the list" (stamp its canonical id) and "ruled out" (ledger).
* **Cap.** At most 10 rows per week and per market; more than that means the sheet changed shape or the matcher broke, so the step adds nothing and the recap says so.
* **Already-over and no-date rules** are those of `add_customer_rows.py` (`--min-start`): events starting before the next Saturday are skipped; a row with no date is added (research finds the date).
* **Never deletes.** Append only, with the backup and the read-back proof. A wrong add is undone by the operator putting the event in `customer_not_researched.csv` (the coverage check then stops
  counting it) and marking the input row DUP_OF or leaving it to age out; nothing is removed by code.
* **Nothing leaves the building.** The request to upstream is a draft file; the operator sends it.
* **Fails open.** The step is wrapped like the intake: any fault is a line in the log and in the recap, the research goes ahead, and the coverage check keeps reporting what is still missing.
* **Verifiable.** `customer_coverage.py` runs again after the add and its second line goes in the recap: `<k> NOT in queue after the add` must be 0 or every remaining row must be in the HOLD list.

## What the operator approves once

1. The rule itself: "any row the gate calls ADD is added without asking me" (versus today's by-hand step).
2. The cap (10 per week and market) and the edition guard wording.
3. That a blank-id row may be researched before upstream has given an id (already true since 2026-10-05; the cost is one research pass per row).
4. That `docs/operations/customer_not_researched.csv` is the only place a customer event is excluded on purpose, and that only the operator edits it.

After that approval the operator's weekly job is: read the recap, send the draft note to upstream when it says ids are wanted, and decide the HOLD rows.

## Build order for whoever takes it

(a) `auto_add_gate.py` with tests for the edition guard, the linked-but-missing HOLD and the cap; (b) a `run_monthly.ps1` patch (reviewer applies) running steps 1 to 3 wrapped and fail-open;
(c) the recap lines; (d) QA-REGISTER A39 status, WEEKEND-PROCESS step 3a, `check_process_doc.py --confirm`; (e) a sandbox rehearsal on copies of both input lists, never the live ones.
