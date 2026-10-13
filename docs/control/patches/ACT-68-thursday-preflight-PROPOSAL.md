# ACT-68 proposal (NOT built, NOT registered): a Thursday 18:00 pre-flight for Friday and Saturday

Status: a proposal for the operator. Nothing here is created, scheduled or applied. It needs one decision: yes or no.

## Why

The Sunday pre-flight (built, ACT-68) tells the operator on Sunday what Monday's pages will lack. By then Friday's awards research and Saturday's conference research have already run. Three of the gaps that cost the last three weeks were decided BEFORE those runs and were
invisible until the pages came out:

- a patch to `Markets\run_monthly.ps1` that the reviewer had approved but nobody had applied (so a step did not run);
- awards the customer lists that were not yet on `Awards_input.csv`, or were on it with no permanent id upstream had given (so the award was researched but never loaded);
- a switch left off (`CFP_AWARDS_NEW_EVENTS` at user level) so a new award with an id still did not load.

A check on Thursday evening leaves Friday 02:00 (awards) and Saturday 02:00 (conferences) to be fixed in time.

## What it would report (read-only, one email to the operator only, same mailer as the release gate)

1. **Patches applied.** Read `Markets\run_monthly.ps1` (never edited) and list which of these markers it carries: `STEP 0` (intake), `STEP 0a0` (customer coverage), `STEP 0a1` (add missing customer rows), `STEP 0a1b` (customer awards), `STEP 0a` (permanent ids),
   `STEP 0a2` (awards refresh plan), `STEP 0b` (canary). Each marker is compared with the list in `docs/control/patches/` (one `ACT-nn-run_monthly.ps1.patch` per marker). A patch in the repo whose marker is absent from the live script is named: "approved, not applied".
   (`run_monthly.ps1 -ListPostSteps` already lists the post-research steps without running anything; the check can call it.)
2. **Awards waiting for ids.** Live rows of `Awards_input.csv` with a blank `EVENT_ID_CANON` and no `DUP_OF` (the same list the release gate calls "ids owed"), each with the date it was added; and the draft request to upstream (`request_to_upstream_awards_<date>.md`) if it exists, so the operator can send it before Friday.
3. **Switches** (user-level environment variables, read with `[Environment]::GetEnvironmentVariable(name, 'User')`): `CFP_AWARDS_NEW_EVENTS` (new awards with an id load on Friday), `CFP_AUTOADD_APPLY` and `CFP_AWARDS_AUTOADD_APPLY` (the Saturday and Friday steps ADD missing customer rows instead of only reporting them),
   `CFP_RECAP_TO` and the `CFP_SMTP_*` set (the recap and the gate can reach the operator). Each is printed as ON / OFF / not set with what that means for Friday. Values are never printed for the SMTP password.
4. **Customer sheets.** The four snapshots' ages (the release gate's check f), and the coverage numbers (`customer_awards.py` and `customer_coverage.py`, both read-only), so a customer row missing from the research queue is seen BEFORE the research runs, when adding it still helps.
5. **Verdict.** READY / READY WITH NOTES / FIX BEFORE 02:00, in the same words as the release gate.

## What it would take

- `scripts/release_gate.py --thursday` (about 120 lines reusing `check_snapshots`, `ids_owed`, `customer_awards.run` in dry-run mode and `customer_coverage.run`), a test with a stub mailer and a copy of `run_monthly.ps1`, and a row in TOOLING.md and QA-REGISTER.
- One new scheduled task registered by the operator, modelled on the existing ones: `CFP Thursday Pre-flight`, Thursday 18:00, running the dev repo's script with the dev interpreter, exactly as the Sunday recap does. A registration script like `experiments\act67_rehearsal\apply_act67_customer_awards.py` would be delivered, tested on a copy, and refusing a second run.
- No change to Friday's or Saturday's job.

## Decision needed

Build it? (It costs no API calls and sends one extra email a week to the operator.)
