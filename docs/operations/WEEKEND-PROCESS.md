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

**Status, 2026-09-30: two of these jobs are switched OFF by the operator.** The Friday awards job
(`CFP Weekly Awards Research`, its first run was due 2026-10-02) and the monthly job (`CFP Monthly
Re-Research (prospect markets)`; those six markets are speculative and have no customer) are
**Disabled** in Windows Task Scheduler. Nothing else changed: Saturday, Sunday and Monday still run.

*2026-10-03:* Saturday's research now asks a short question first (`CFP_PROMPT_MODE=narrow-first`, set in `run_monthly.ps1`): 130 of 130 rows grounded, against about a third before. Because that question does not ask every field, step 2 now also restores last week's value of the fields it leaves out, keeps last week's verified deadline evidence when this week's research returns no quote, and checks every row's years (step 3). The step that starts the load had a script bug that day (the load did not run by itself; fixed in `run_monthly.ps1`).

*2026-10-02:* sponsorship answers are no longer lost to an Unknown or a blank (step 2).

*2026-10-01:* the approved files that Saturday's load falls back to for rows that fail the approval check (`Markets/Utility_audited.final.csv`, `Markets/Cybersecurity_audited.final.csv`) were patched by hand so four corrected rows (India Energy Week 2027, Climate Change, SecureWorld, Global Energy Show) keep their corrected values; upstream acknowledged these local copies as the master for Saturday. Until upstream's re-research delivery is imported, a fallback to these files is safe for those rows. An operator edit to either file is logged in `experiments/purpose_audit/OPERATOR-EDITS-LOG.md`.
The sections below describe what each job does WHEN it is enabled. To turn one back on, run
`Enable-ScheduledTask -TaskName '<name>'` in an elevated (Administrator) PowerShell window.

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
3b. **[Setup]** **Marks the dormant awards so they are not researched this week (added 2026-10-04).** A Closed award whose next cycle is not near cannot have changed, so it is skipped
   (about a third of the list, about $2.60 a week) and its last accepted row is carried over untouched. Every award that is live, has a date ahead, is due to open within 60 days, is new or has
   not been researched for 56 days is researched; each other Closed award is looked at about once every four weeks, a quarter of them each week. If the plan ever wanted to skip over 70% it
   skips nothing. A fault in this step leaves every award to be researched. *(refresh_plan.py -> the REFRESH_SKIP column; the audit skips marked rows like duplicates)*
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
10b. **[Safety check]** **Checks what the awards load changed and whether it lost anything we had proven (added 2026-10-04)** - the same check Saturday has: for every award whose deadline is still ahead,
    a deadline, evidence page, quote or submission link that went missing is flagged; plus the per-step failure count (finding, proving, reading, identity) and how many awards were deliberately
    not researched. Filed as `runs_out\qa\<Monday>\load_awards.md`. *(post_load_qa.py --markets Awards)*
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
3a. **[Safety check]** **Checks that every customer row is in the research queue** *(added 2026-10-06; APPLIED to `run_monthly.ps1` on 2026-10-06, so it runs from the first Saturday after; patch kept at
   `docs/control/patches/ACT-51-run_monthly.ps1.patch`)*. The customers' sheets define the job: every event on them is researched. This step compares each customer row that is still ahead with our research list
   (`<Market>_input.csv`), by the event's permanent ID, or by its web address together with a start date within 30 days (the same website alone proves nothing: two events can share one), and prints a line `COVERAGE: <n> of <m> customer rows ahead of today are in the research queue; <k> are NOT`
   plus the first five names. Events that are over, rows the customer removed, rows marked as duplicates and rows the operator has ruled out (`docs/operations/customer_not_researched.csv`,
   only the operator adds to it) are left out and listed with the reason. A second list shows customer rows LINKED to an event whose date is more than 30 days off, or whose city differs, from what the customer wrote (a wrong link); it is reported, never changed. It runs before the research so a missing event can be added in time, but for now it only REPORTS and adds nothing.
   It can never stop the research. The Saturday recap repeats the line and puts FLAG in its subject when any row is missing (target: none). *(customer_coverage.py)*
4. **[Update]** **Adds permanent IDs to the research list.** Each event on the list is tagged with its
   permanent ID, so a renamed event cannot turn into a duplicate. An event that cannot be matched
   with certainty is left untagged and held back later - never guessed. An id that UPSTREAM GAVE US for a brand-new event (recorded in `docs/operations/given_ids.csv` when we stamped it,
   `stamp_given_ids.py`) is kept even though the event is not in the database yet; without that record the stamp on a new event was cleared here. *(stamp_input_ids.py)*
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

*Same scheduled task; `run_monthly.ps1` calls `weekend_import.py`, then `post_load_qa.py` (conference markets), then `weekend_recap.py`. The steps are built by one function, and `run_monthly.ps1 -ListPostSteps` (added 2026-10-05) prints every post-research step it would run, with its whole arguments and whether its script exists, without researching, loading or emailing anything; a test runs it. Each step is skipped with a logged line if its script is missing, and runs with empty input, so a stray interactive prompt exits instead of waiting for a person (the 2026-10-03 hang).*

1. **[Safety check]** **Stops if research failed.** Nothing is loaded and the database stays exactly as it was.
2. **[Update]** **Fixes wording-only problems** - for example a quote copied slightly wrong from the cited
   page. It never changes a date, a status or which page is cited. *(mechanical_repairs.py)*
   Then, for sponsorship only: if this week's research comes back "Unknown" or blank for an event whose sponsorship
   answer we already hold for the same year's edition, last week's answer is kept together with its page; blank cells
   are filled, a fresh answer is never replaced, and a Yes-versus-No difference is left for a person. Every value
   kept is listed in the report. *(sponsor_carry.py)*
   Also, since 2026-10-03, for rows researched with the short question: fields it does not ask (organizer, city, overview,
   categories, coordinator email, and the like) take last week's accepted value for the SAME edition, never a different
   year's; last week's conference-dates text is restored only when it names the same full date as this week's start date;
   and if this week's research returned no quote for a deadline that is unchanged (or blank) while last week's was verified
   and has not passed, last week's page, quote and verified flag are kept together. A fresh answer is never overridden and
   the approval check in step 3 still reads the kept quote on its page. Every value kept is listed in the report.
   Since 2026-10-05 the load also records, for each value it kept, the date it was last confirmed (see step 8). Since 2026-10-05 this also covers an event that was loaded into the database by hand and is not yet in the approved file: its "last week" is the database row, so it keeps its evidence the first time too; the approved file itself is not edited, and the log says how many rows used the database.
   *(narrow_overlay.py)*
   Then, since 2026-10-03, **pinned rows**: anything a person verified on an event's own page (`docs/operations/pinned_rows.json`: a deadline, a start date, dates text, a city, a link, or "the page states
   nothing") is applied over this week's research until the pin's date passes or it is deleted. A blank pin also clears the database, because the load never erases a date on a blank. A pin is
   applied before the approval check, so a pinned quote is still read on its page, and every pin that changed something is listed in the report. Since 2026-10-05 the same applies to the Friday awards load (an award's pin is keyed on our award id; it may also pin the call-opens and winners-announced dates). *(pinned_rows.py)*
3. **[Safety check]** **Runs the approval check with the row-by-row rule.** Rows that pass use this week's research.
   Each row's years are checked first (start date inside its edition, conference-dates year equals start year, no
   past start still Open or Upcoming, deadline not after the start or more than 18 months before it); a row that fails
   is treated like any failing row. *(start_date_arbiter.py year checks)*
   Rows that fail, were not researched, or cannot be matched to an event with certainty keep last
   week's approved version. Events not covered this week carry over, so nothing disappears from
   the page. A cited page that an anti-bot wall will not let a plain read open (it answers with a
   short notice instead of the page) is not counted as a missing quote; it is listed in the
   approval report as "not checked" so that a person can confirm it. *(accept_delivery.py - the one approval check)*
4. **[Load]** **Backs up the database** before touching it.
5. **[Load]** **Loads each row onto its permanent ID**, so a renamed event updates its name instead of
   becoming a duplicate. *(import_grounding.py --ids)*
6. **[Load]** **Re-verifies the new rows** against their cited pages. *(verify_grounding.py, fix_edition.py)*
7. **[Safety check]** **Runs the database health check.** If anything is wrong, **everything is undone from the
   backup** and nothing is approved. *(check_invariants.py)*
8. **[Safety check]** **Checks what the load changed and whether it lost anything we had proven.** For every event whose deadline is still ahead it
   flags evidence, quote, deadline or submission link lost, and verified turned projected; it counts blanks in the fields the short research question does
   not ask and venue words in CITY; it checks the shipped files' dates and years again; it lists any start date the load set on a projected row with no
   evidence page; it lists carried values (verified-deadline evidence, sponsorship, organizer) that have been kept for more than six weeks without being re-confirmed, from a small ledger the load keeps (added 2026-10-05); it lists any row whose deadline evidence is a third-party listing (such as cfptime.org) instead of the organizer's own page (added 2026-10-05); it confirms the approved files are signed and fresh so Monday's pages will publish; and it runs the named-row watch-list. It reports and never
   blocks: a flag is for a person. It also counts, per market, the rows that did not ship this week's research by the step that failed (finding the page, proving the quote, reading the claim,
   identity), appends the counts to `runs_out\qa\step_failures.jsonl` and shows the last loads side by side, so it is visible over weeks which step to improve; a step that rises by five or
   more rows since the previous load is flagged. The result is filed as `runs_out\qa\<Monday>\load.md`. *(post_load_qa.py, failure_steps.py)*
9. **[Publish]** **Approves the files for Monday** and records the approval. *(promote_delivery.py)*
10. **[Report]** **Emails the Saturday recap** - worked or failed, the results table, "Did the load lose anything?" with every flag, and what it means for
   Sunday and Monday. Sent on failure too; the subject reads "WORKED - n to check" when there are flags, and carries "FLAG: n customer row(s) not in the research queue" when step 3a found any. It also states how many of upstream's written promises (docs/operations/upstream_commitments.csv) were kept, and the subject carries "FLAG: n upstream promise(s) NOT kept" when one is broken (ACT-58). When any promise is NOT KEPT, the promise check also files a DRAFT note to upstream naming each one (event, field, what was found, what was promised) as `runs_out\qa\<date>\NOTE-TO-UPSTREAM-DRAFT-commitments.md`; it is a file for the operator to send and no code sends it. A malformed ledger line counts as a problem, so it cannot be skipped silently. The check runs as its own step just before the recap (from the Saturday after the run_monthly.ps1 patch ACT-58 is applied) and can never fail the run. *(weekend_recap.py saturday, check_commitments.py)*
10b. **[Experiment, changes nothing]** **Shadow reader of the other facts (added 2026-10-05).** Just before the finder, after the load and the recap. For every live row it reads the event's own pages (at most 3) with a cheap model and accepts a start date, city, country, venue, organizer or format only when a verbatim sentence on the page states it, then counts, per field, where that agrees with what we ship, differs, or is something we do not have. It writes nothing to the database or the approved files, stops at 45 minutes or 0.60 USD, skips itself if the job has already run 4.6 hours, and never fails the run. A difference is a list for a person, not yet an accuracy figure. Files: `runs_out\shadow\shadow_reader_<stamp>.md/.csv/.json`, one short email. *(shadow_reader.py --markets ...)*
10c. **[Experiment, changes nothing]** **Second shadow reader: GPT-6 Luna (added 2026-10-06, ACT-61).** After step 10b and the deadline finder, so it can never squeeze either; it uses 10b's newest report. For the same live rows (customer-linked events first, then those starting in the next 60 days, then the rest) it asks GPT-6 Luna at maximum effort, through the Codex program on the operator's ChatGPT subscription and never through any other provider, to read the same facts from the same pages, one fresh blind question per event (it sees only the event, the year and the page text, never another reader's answer or our data). A fact counts only when its quote is literally on the page, exactly as in step 10b. It then compares, in code, Luna with the existing reader and with the database and writes a plain list of the disagreements. It stops at 45 minutes or 1.5 million subscription tokens, stops at once and quotes the exact message if Codex reports any limit or error (no retry), skips itself if Codex is not signed in or the job has already run 4.6 hours, changes nothing in the database, approved files, pins or pages, and never fails the run. The recap line to look for in the log: `LUNA SHADOW: n facts read, agree a, disagree d, Luna-only found f, reader-only found r, tokens t (budget b)`. Files: `runs_out\qa\<date>\luna_shadow.md` and rows added to `experiments\model_bakeoff
egistry.jsonl`. After four Saturdays the registry gives a written recommendation (adopt, keep as second reader, drop). *(luna_shadow.py --markets ...)*
11. **[Experiment, changes nothing]** **Shadow run of the real-URL deadline finder (added 2026-10-04).** Last, after the load and the recap, so it can delay neither. For every live row (Open or Upcoming, about 40) it reads the event's own home page, sitemap and menu, picks the pages that look like the call, reads each with a cheap model and accepts a deadline only if a verbatim sentence on the page states it. It sets that next to what we ship and emails a short note: how many agree, and every place the pages state a different date (look at these) or a date where we ship none. It writes nothing to the database or the approved files, takes about 2 to 3 minutes per event (about 40 events, so roughly 100 minutes), stops at 120 minutes or 0.60 USD, skips itself if the job has already run 4.25 hours, and never fails the run. Files: `runs_out\shadow\shadow_<stamp>.md/.csv/.json`. Purpose: collect Saturday-by-Saturday evidence on whether it should become a second opinion or a fallback. *(shadow_finder.py)*

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
   for word. If the quick read of a page returns only an anti-bot wall, the real browser reads it
   instead (added 2026-10-01, after a correct quote was rejected against a wall). Never applied: a quote that mentions an extension, a date without a year, or an
   ambiguous date like 12/4/2026. Rows on a customer's approved page are left for Saturday. The
   database is backed up first and restored automatically if the health check then fails.
   About 10-20 AI requests (hard cap 25 rows). *(weekly_discovery.py, apply_resolutions.py)*
7. **[Report]** **Emails the Sunday recap** - worked or failed, the counts, every new call applied (before
   and after), and whether Monday's pages will publish. *(weekend_recap.py sunday)*

## Monday 7:00 AM - Customer pages

*Scheduled task "CFP Weekly Customer Pages" -> `cfp-monitor\scripts\weekly_deliverable.py`*

1. **[Safety check]** **Records the starting point** - what Saturday's automatic load left in the database, so any
   change later in this run can be spotted. *(qa_import.py)*
2. **[Update]** **Registers this week's links, then re-reads every cited web page** and confirms each
   deadline is still written there. Registering first matters: until 2026-09-28 the links Saturday's
   load wrote were registered after the re-read, so they were never opened. No AI requests.
   *(build_evidence.py, audit_evidence.py)*
3. **[Update]** **Updates the verdicts the pages show** ("verified" / "needs checking"), so the pages never
   show last week's labels. Each result is filed under every research ID the event has had, so a
   renamed event still finds its result. *(export_checks.py)*
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
    original is in `AppData\Local\CFP-Monitor\runs_out\qa\<date>\build.md`. It also has an "Upstream's promises" section listing every promise that is NOT KEPT (and malformed ledger lines) as a "look at", and files the same draft note to upstream beside the report (ACT-58). *(qa_build.py)*

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

- **2026-10-06** - new Saturday step 3a: a check that every event on the two customer sheets is on the research list (`customer_coverage.py`), reported in the recap; report only for now (ACT-51).
- **2026-09-28** - Monday registers this week's links before re-reading them, and results are filed under every research ID (renamed events had lost their results).
- **2026-09-28** - Friday weekly awards research added, same machinery as Saturday. Monday uses the approved awards file. Customer pages hide Closed rows by default in the four work-queue views.
- **2026-09-28** - Monday's review list separates changes to already-past dates from what needs a look, and a copy is saved beside the published pages.
- **2026-09-28** - Sunday's search for new calls applies what it proves word for word, with Saturday's safety net; its findings are in the Sunday recap. The last manual step in the weekly chain is gone.
- **2026-09-28** - category label added to every step, with a key at the top.
- **2026-09-28** - document created. Monthly run gains its recap email.
- **2026-09-27** - Saturday gains the automatic load, permanent IDs and recap email; Sunday gains
  its recap email and checks against Saturday's approved files. Before this, a person loaded the
  research by hand and, when nobody did, Sunday and Monday worked from last week's data.
