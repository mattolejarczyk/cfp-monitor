# The weekend process, in plain English

**What this is.** A step-by-step description of every scheduled CFP job, written for the operator,
not for programmers. The technical version is [`WEEKLY-CYCLE.md`](WEEKLY-CYCLE.md); the commands are
in [`market-runbook.md`](market-runbook.md). Each step below names the script that does it, in
brackets, so the two can always be lined up.

**How it stays current.** `scripts/check_process_doc.py` keeps a fingerprint of every script this
document describes. When any of them changes, the test suite fails until someone re-reads this
document, corrects it if needed, and re-confirms it with `python scripts/check_process_doc.py
--confirm`. A change to the weekend process therefore cannot ship with this document silently out
of date.

**Every run ends with an email** to the operator (`CFP_RECAP_TO`): did it work, the numbers, and
what it means for the next run.

| When | Job | Costs AI requests? |
|---|---|---|
| Saturday 2:00 AM | Weekly research + automatic load (Arnica, Utility Global) | Yes, about 120-290 |
| Sunday 1:00 AM | Weekly link and deadline check (all markets) | A few (about 9) |
| Monday 7:00 AM | Customer pages | No |
| Every 4th Wednesday 2:00 AM | Monthly research (the six markets without a customer) | Yes, about 280 |

---

## Saturday 2:00 AM - Weekly research (Arnica + Utility Global)

*Scheduled task "CFP Weekly Re-Research (live markets)" -> `Markets\run_monthly.ps1 -Markets Cybersecurity,Utility`*

1. **Starts a log file.** Everything the job says goes into `Markets\logs\`, so if anything goes
   wrong at 2 AM the reason is written down. *(run_monthly.ps1)*
2. **Checks the AI key is present.** If it is missing, the job stops right away and spends nothing.
3. **Takes in the customer's week.** Reads both customers' Google Sheets (read-only), saves a
   copy, and records what each customer has done - submitted, declined, drafting. That way we do
   not spend research on events they have already acted on, and we never contradict their status.
   If this step fails, research still goes ahead. *(weekly_intake.py)*
4. **Adds permanent IDs to the research list.** Each event on the list is tagged with its
   permanent ID, so a renamed event cannot turn into a duplicate. An event that cannot be matched
   with certainty is left untagged and held back later - never guessed. *(stamp_input_ids.py)*
5. **Runs the 5-row test.** Researches 5 rows, checks that real Google searches happened, runs
   the approval check, and loads them into a **copy** of the database. If the test fails, the job
   stops before spending the full budget, and nothing is changed. *(run_canary.ps1)*
6. **Files away last week's research** into the archive, so the new run starts clean. Nothing is
   deleted.
7. **Researches every conference.** One at a time, spaced out, the AI searches Google for current
   deadlines, dates and links, and must cite the page it found. Answers with no Google search
   behind them are thrown out and retried. If search breaks down (10 failures in a row) or the
   quota runs out, it stops itself. This is the only expensive step. *(run_overnight.ps1 ->
   run_all.ps1 -> run_market_audit.py)*
8. **Checks the output's format** against the agreed structure before anything else uses it.
   *(validate_market_output.py)*

## Saturday, right after research - Automatic load into the database

*Same scheduled task; `run_monthly.ps1` calls `weekend_import.py` then `weekend_recap.py`*

1. **Stops if research failed.** Nothing is loaded and the database stays exactly as it was.
2. **Fixes wording-only problems** - for example a quote copied slightly wrong from the cited
   page. It never changes a date, a status or which page is cited. *(mechanical_repairs.py)*
3. **Runs the approval check with the row-by-row rule.** Rows that pass use this week's research.
   Rows that fail, were not researched, or cannot be matched to an event with certainty keep last
   week's approved version. Events not covered this week carry over, so nothing disappears from
   the page. *(accept_delivery.py - the one approval check)*
4. **Backs up the database** before touching it.
5. **Loads each row onto its permanent ID**, so a renamed event updates its name instead of
   becoming a duplicate. *(import_grounding.py --ids)*
6. **Re-verifies the new rows** against their cited pages. *(verify_grounding.py, fix_edition.py)*
7. **Runs the database health check.** If anything is wrong, **everything is undone from the
   backup** and nothing is approved. *(check_invariants.py)*
8. **Approves the files for Monday** and records the approval. *(promote_delivery.py)*
9. **Emails the Saturday recap** - worked or failed, the results table, and what it means for
   Sunday and Monday. Sent on failure too. *(weekend_recap.py saturday)*

## Sunday 1:00 AM - Weekly link and deadline check (all markets)

*Scheduled task "CFP Weekly Verification" -> `AppData\Local\CFP-Monitor\scripts\run_weekly.bat`*

1. **Opens a real browser** in the background, for websites that block automated checks. Closes
   it afterwards - only if it opened it. *(cdp_ctl.py)*
2. **Re-checks every deadline we hold** against its cited page - a quick read first, moving up to
   the real browser when a site resists. No AI requests. *(weekly_verify.py -> verify_grounding.py)*
3. **Re-checks every "submit here" link.** A link is only called dead after a real browser
   confirms it. *(recheck_dead_links.py)*
4. **Runs the database health check** against Saturday's approved files. *(check_invariants.py)*
5. **Writes a summary of what changed this week** - newly broken links, database items to watch,
   and older broken links still waiting.
6. **Looks for new calls for speakers** on the few rows whose deadline is unconfirmed and still in
   the future. A small number of AI requests (capped at 25 rows, about 9 typically); report only -
   nothing is changed automatically. *(weekly_discovery.py)*
7. **Emails the Sunday recap** - worked or failed, the counts, and whether Monday's pages will
   publish. *(weekend_recap.py sunday)*

## Monday 7:00 AM - Customer pages

*Scheduled task "CFP Weekly Customer Pages" -> `cfp-monitor\scripts\weekly_deliverable.py`*

1. **Records the starting point** - what Saturday's automatic load left in the database, so any
   change later in this run can be spotted. *(qa_import.py)*
2. **Re-reads every cited web page** and confirms each deadline is still written there. No AI
   requests. *(audit_evidence.py)*
3. **Updates the verdicts the pages show** ("verified" / "needs checking"), so the pages never
   show last week's labels. *(export_checks.py)*
4. **Does the same for awards** - award deadlines and their links. *(check_award_deadlines.py,
   link_check_awards.py)*
5. **Re-checks links** and flags any "submit here" link that has stopped working, so the customer
   sees a warning instead of a broken link.
6. **Runs the database health check again**, because steps 2-5 wrote to the database.
7. **Checks it is using this week's approved files** - approved, unchanged, and recent. If either
   fails, **nothing is published**. *(publish_guard.py)*
8. **Runs review checks** - possible duplicate events, citations to pages the AI never actually
   searched, what the customer is working on - and rebuilds the evidence matrix. Recorded for us;
   never blocks publishing. *(find_duplicate_events.py, grounding_review.py, customer_context.py,
   evidence_matrix.py)*
9. **Builds the two pages** - conferences and awards. *(build_review_page.py)*
10. **Publishes, only if everything above went well.** Both pages go into today's folder under
    `handoff-files\weekly\`, with a summary file listing what is in them. Otherwise the pages stay
    in a work folder, the summary says why, and nothing is published.

## Every 4th Wednesday 2:00 AM - Monthly research (markets without a customer)

*Scheduled task "CFP Monthly Re-Research (prospect markets)" -> `run_monthly.ps1` for Robotics,
Semiconductor, Consumer Electronics, Bioeconomy, BioMedTech and Additive Manufacturing*

1. **Same as Saturday's research steps 1-2 and 5-8** for these six markets.
2. **No customer check-in and no permanent-ID step** - there are no customer sheets to read.
3. **No automatic load.** These markets have no customer page, so their research stays in the
   Markets folder and is not loaded into the database - by design.
4. **Emails the monthly recap** - worked or failed, the numbers per market, and a reminder that
   nothing changes for the customers, Sunday's check or Monday's pages. *(weekend_recap.py monthly,
   added 2026-09-28)*

---

## Change history

- **2026-09-28** - document created. Monthly run gains its recap email.
- **2026-09-27** - Saturday gains the automatic load, permanent IDs and recap email; Sunday gains
  its recap email and checks against Saturday's approved files. Before this, a person loaded the
  research by hand and, when nobody did, Sunday and Monday worked from last week's data.
