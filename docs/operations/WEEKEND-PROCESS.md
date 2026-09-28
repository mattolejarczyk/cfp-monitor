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
| Friday 2:00 AM | Weekly awards research + automatic load (Arnica, Utility Global) | Yes, about 130-300 |
| Saturday 2:00 AM | Weekly research + automatic load (Arnica, Utility Global) | Yes, about 120-290 |
| Sunday 1:00 AM | Weekly link and deadline check (all markets) | A few (about 10-20) |
| Monday 7:00 AM | Customer pages | No |
| Every 4th Wednesday 2:00 AM | Monthly research (the six markets without a customer) | Yes, about 280 |

**What the labels on each step mean**

| Label | Meaning |
|---|---|
| **[Setup]** | Gets ready - log file, browser, archive. |
| **[Take in]** | Reads what the customer has done. |
| **[Research]** | Finds facts with the AI and Google search. The only paid work. |
| **[Update]** | Refreshes or tidies information, without the AI - these change what the customer will see. |
| **[Safety check]** | Can STOP the run or block publishing if something is wrong. |
| **[Load]** | Writes into the database, always behind a backup. |
| **[Review]** | Flags things for us to look at. Never stops anything. |
| **[Build]** / **[Publish]** | Makes the pages / approves or releases them. |
| **[Report]** | A summary or the recap email. |

Most **[Safety check]** steps sit straight after a **[Load]** or **[Update]**, or at the handoff between two
jobs: each job checks what the previous one left instead of trusting it.

---

## Friday 2:00 AM - Weekly awards research (Arnica + Utility Global)

*Scheduled task "CFP Weekly Awards Research" -> `Markets\run_monthly.ps1 -Markets Awards` - the Saturday
job pointed at the awards list (`Markets\Awards_input.csv`), added 2026-09-28*

1. **[Setup]** **Starts a log file** in `Markets\logs\`. *(run_monthly.ps1)*
2. **[Safety check]** **Checks the AI key is present.**
3. **[Update]** **Adds permanent IDs to the awards list**, from last week's awards page, exact names only.
   *(stamp_input_ids.py)*
4. **[Safety check]** **Runs a 5-row test** - researches 5 awards and checks real Google searches
   happened. If not, the job stops before spending the full budget. *(run_canary.ps1 -ResearchOnly)*
5. **[Setup]** **Files away last week's awards research** into the archive.
6. **[Research]** **Researches every award** - dates, entry windows and links, each with its cited page.
   Awards listed twice on the customer sheets are researched once. *(run_market_audit.py)*
7. **[Safety check]** **Checks the output's format.** *(validate_market_output.py)*
8. **[Safety check]** **Runs the approval check with the row-by-row rule** - the same rule as Saturday.
   *(weekend_import.py -> accept_delivery.py)*
9. **[Load]** **Backs up the database, then loads each award onto its permanent ID.** *(import_awards.py --ids)*
10. **[Safety check]** **Runs the database health check** (its awards half); anything wrong and
    everything is undone from the backup. *(check_invariants.py)*
11. **[Publish]** **Approves the awards file for Monday.** *(promote_delivery.py)*
12. **[Report]** **Emails the Friday recap.** A failed Friday never stops Monday's conferences page;
    Monday's summary says loudly if the awards page is not this week's. *(weekend_recap.py friday)*

## Saturday 2:00 AM - Weekly research (Arnica + Utility Global)

*Scheduled task "CFP Weekly Re-Research (live markets)" -> `Markets\run_monthly.ps1 -Markets Cybersecurity,Utility`*

1. **[Setup]** **Starts a log file.** Everything the job says goes into `Markets\logs\`, so if anything goes
   wrong at 2 AM the reason is written down. *(run_monthly.ps1)*
2. **[Safety check]** **Checks the AI key is present.** If it is missing, the job stops right away and spends nothing.
3. **[Take in]** **Takes in the customer's week.** Reads both customers' Google Sheets (read-only), saves a
   copy, and records what each customer has done - submitted, declined, drafting. That way we do
   not spend research on events they have already acted on, and we never contradict their status.
   If this step fails, research still goes ahead. *(weekly_intake.py)*
4. **[Update]** **Adds permanent IDs to the research list.** Each event on the list is tagged with its
   permanent ID, so a renamed event cannot turn into a duplicate. An event that cannot be matched
   with certainty is left untagged and held back later - never guessed. *(stamp_input_ids.py)*
5. **[Safety check]** **Runs the 5-row test.** Researches 5 rows, checks that real Google searches happened, runs
   the approval check, and loads them into a **copy** of the database. If the test fails, the job
   stops before spending the full budget, and nothing is changed. *(run_canary.ps1)*
6. **[Setup]** **Files away last week's research** into the archive, so the new run starts clean. Nothing is
   deleted.
7. **[Research]** **Researches every conference.** One at a time, spaced out, the AI searches Google for current
   deadlines, dates and links, and must cite the page it found. Answers with no Google search
   behind them are thrown out and retried. If search breaks down (10 failures in a row) or the
   quota runs out, it stops itself. This is the only expensive step. *(run_overnight.ps1 ->
   run_all.ps1 -> run_market_audit.py)*
8. **[Safety check]** **Checks the output's format** against the agreed structure before anything else uses it.
   *(validate_market_output.py)*

## Saturday, right after research - Automatic load into the database

*Same scheduled task; `run_monthly.ps1` calls `weekend_import.py` then `weekend_recap.py`*

1. **[Safety check]** **Stops if research failed.** Nothing is loaded and the database stays exactly as it was.
2. **[Update]** **Fixes wording-only problems** - for example a quote copied slightly wrong from the cited
   page. It never changes a date, a status or which page is cited. *(mechanical_repairs.py)*
3. **[Safety check]** **Runs the approval check with the row-by-row rule.** Rows that pass use this week's research.
   Rows that fail, were not researched, or cannot be matched to an event with certainty keep last
   week's approved version. Events not covered this week carry over, so nothing disappears from
   the page. *(accept_delivery.py - the one approval check)*
4. **[Load]** **Backs up the database** before touching it.
5. **[Load]** **Loads each row onto its permanent ID**, so a renamed event updates its name instead of
   becoming a duplicate. *(import_grounding.py --ids)*
6. **[Load]** **Re-verifies the new rows** against their cited pages. *(verify_grounding.py, fix_edition.py)*
7. **[Safety check]** **Runs the database health check.** If anything is wrong, **everything is undone from the
   backup** and nothing is approved. *(check_invariants.py)*
8. **[Publish]** **Approves the files for Monday** and records the approval. *(promote_delivery.py)*
9. **[Report]** **Emails the Saturday recap** - worked or failed, the results table, and what it means for
   Sunday and Monday. Sent on failure too. *(weekend_recap.py saturday)*

## Sunday 1:00 AM - Weekly link and deadline check (all markets)

*Scheduled task "CFP Weekly Verification" -> `AppData\Local\CFP-Monitor\scripts\run_weekly.bat`*

1. **[Setup]** **Opens a real browser** in the background, for websites that block automated checks. Closes
   it afterwards - only if it opened it. *(cdp_ctl.py)*
2. **[Update]** **Re-checks every deadline we hold** against its cited page - a quick read first, moving up to
   the real browser when a site resists. No AI requests. *(weekly_verify.py -> verify_grounding.py)*
3. **[Update]** **Re-checks every "submit here" link.** A link is only called dead after a real browser
   confirms it. *(recheck_dead_links.py)*
4. **[Safety check]** **Runs the database health check** against Saturday's approved files. *(check_invariants.py)*
5. **[Report]** **Writes a summary of what changed this week** - newly broken links, database items to watch,
   and older broken links still waiting.
6. **[Update]** **Looks for new calls for speakers - and applies what it can prove.** Covers rows whose
   deadline is unconfirmed and still in the future - in practice almost all in the six monthly
   markets (Saturday keeps Arnica's and Utility Global's rows confirmed). A finding is applied
   ONLY when the re-read page carries the whole quote with the deadline written inside it, word
   for word. Never applied: a quote that mentions an extension, a date without a year, or an
   ambiguous date like 12/4/2026. Rows on a customer's approved page are left for Saturday. The
   database is backed up first and restored automatically if the health check then fails.
   About 10-20 AI requests (hard cap 25 rows). *(weekly_discovery.py, apply_resolutions.py)*
7. **[Report]** **Emails the Sunday recap** - worked or failed, the counts, every new call applied (before
   and after), and whether Monday's pages will publish. *(weekend_recap.py sunday)*

## Monday 7:00 AM - Customer pages

*Scheduled task "CFP Weekly Customer Pages" -> `cfp-monitor\scripts\weekly_deliverable.py`*

1. **[Safety check]** **Records the starting point** - what Saturday's automatic load left in the database, so any
   change later in this run can be spotted. *(qa_import.py)*
2. **[Update]** **Re-reads every cited web page** and confirms each deadline is still written there. No AI
   requests. *(audit_evidence.py)*
3. **[Update]** **Updates the verdicts the pages show** ("verified" / "needs checking"), so the pages never
   show last week's labels. *(export_checks.py)*
4. **[Update]** **Does the same for awards** - award deadlines and their links. *(check_award_deadlines.py,
   link_check_awards.py)*
5. **[Update]** **Re-checks links** and flags any "submit here" link that has stopped working, so the customer
   sees a warning instead of a broken link.
6. **[Safety check]** **Runs the database health check again**, because steps 2-5 wrote to the database.
7. **[Safety check]** **Checks it is using this week's approved files** - approved, unchanged, and recent. If either
   fails, **nothing is published**. *(publish_guard.py)*
8. **[Review]** **Runs review checks** - possible duplicate events, citations to pages the AI never actually
   searched, what the customer is working on - and rebuilds the evidence matrix. Recorded for us;
   never blocks publishing. *(find_duplicate_events.py, grounding_review.py, customer_context.py,
   evidence_matrix.py)*
9. **[Build]** **Builds the two pages** - conferences and awards. *(build_review_page.py)*
10. **[Publish]** **Publishes, only if everything above went well.** Both pages go into today's folder under
    `handoff-files\weekly\`, with a summary file listing what is in them. Otherwise the pages stay
    in a work folder, the summary says why, and nothing is published.
11. **[Report]** **Writes the "before you send" review list** - what changed on the pages since last time.
    "Look at" holds only what needs a person; deadline changes where the old date had already
    passed are listed separately under "no action needed". A copy named
    `INTERNAL - Build QA <date> (do not send).md` goes in the same folder as the pages; the
    original is in `AppData\Local\CFP-Monitor\runs_out\qa\<date>\build.md`. *(qa_build.py)*

## Every 4th Wednesday 2:00 AM - Monthly research (markets without a customer)

*Scheduled task "CFP Monthly Re-Research (prospect markets)" -> `run_monthly.ps1` for Robotics,
Semiconductor, Consumer Electronics, Bioeconomy, BioMedTech and Additive Manufacturing*

1. **[Research]** **Same as Saturday's research steps 1-2 and 5-8** for these six markets.
2. **[Setup]** **No customer check-in and no permanent-ID step** - there are no customer sheets to read.
3. **[Load - skipped]** **No automatic load.** These markets have no customer page, so their research stays in the
   Markets folder and is not loaded into the database - by design.
4. **[Report]** **Emails the monthly recap** - worked or failed, the numbers per market, and a reminder that
   nothing changes for the customers, Sunday's check or Monday's pages. *(weekend_recap.py monthly,
   added 2026-09-28)*

---

## Change history

- **2026-09-28** - Friday weekly awards research added, same machinery as Saturday. Monday uses the approved awards file. Customer pages hide Closed rows by default in the four work-queue views.
- **2026-09-28** - Monday's review list separates changes to already-past dates from what needs a look, and a copy is saved beside the published pages.
- **2026-09-28** - Sunday's search for new calls applies what it proves word for word, with Saturday's safety net; its findings are in the Sunday recap. The last manual step in the weekly chain is gone.
- **2026-09-28** - category label added to every step, with a key at the top.
- **2026-09-28** - document created. Monthly run gains its recap email.
- **2026-09-27** - Saturday gains the automatic load, permanent IDs and recap email; Sunday gains
  its recap email and checks against Saturday's approved files. Before this, a person loaded the
  research by hand and, when nobody did, Sunday and Monday worked from last week's data.
