# cfp-monitor — Handoff & Single Source of Truth

**Body last fully revised 2026-08-01.** The running session log through 2026-08-28 lives in
[`docs/design/worklog.md`](docs/design/worklog.md) - read it for the latest state until these
sections are refreshed in a verified session.

> **2026-10-09 - FIRST FRIDAY AWARDS RUN: TWO FIRST-RUN BUGS FIXED, AWARDS LOADED. RESUME WITH docs/control/RESUME.md.** The 02:00 run failed at its canary (4 of its 5 sample rows were REFRESH_SKIP dormant awards); fixed in Markets/run_canary.ps1 (backup run_canary.ps1.pre-skipfilter-20261009; QA A54). The by-hand rerun researched 80 awards (86 requests, all grounded) and was failed again by validate_market_output.py check_coverage counting the 9 DUP_OF + 43 REFRESH_SKIP rows as lost; fixed (backup validate_market_output.py.pre-skiprows-20261009; QA A55). Sandbox rehearsal then live `weekend_import.py --markets Awards --research-exit 0`: 127 awards shipped (58 new, 69 kept), 7 held back (5 need permanent ids from upstream: Computing Security Awards, Cyber Security Awards, World Hydrogen and Carbon Asia, Clinton Global Initiative, Fast Company World Changing Ideas; 2 Fast Company Most Innovative rows say Open with a passed deadline). Load QA PASS, live invariants hold; pre-load backup cfp_monitor.db.backup-pre-awardimport-20261009-141637.db. Monday 07:00 should publish the awards page from Awards_audited.final.csv. The email recap of 09:00 still says FAILED (not re-sent). The ACT-58 and ACT-51 phase-2 patches are still NOT applied to run_monthly.ps1: do that with the operator before Saturday 02:00 or leave them for next week. NEXT: Sat 10-10 readout (ACT-31).
>

> **2026-10-08 - PRE-FLIGHT FOR THE FIRST FRIDAY RUN; FOUR BUILDERS MERGED, NOTHING APPLIED LIVE. RESUME WITH docs/control/RESUME.md.** Control list: 28 verified, 14 in review, 5 waiting, 2 conditional. Live-path changes were frozen until Fri 10-09 02:00 (first awards run) is read. Merged to main (all unapplied): ACT-51 phase 2 `scripts/customer_auto_add.py` (gate ADD / HOLD, dry-run default, patch docs/control/patches/ACT-51-phase2-run_monthly.ps1.patch); ACT-54 link_agreement.py, customer_row_answers.py, schedule_only.py / check_schedule_status.py (R16c advisory); ACT-58 remainder (Monday QA promises, draft note to upstream, ledger lint; Saturday patch docs/control/patches/ACT-58-run_monthly.ps1.patch); ACT-59 `scripts/input_list_audit.py` (219 rows, 0.225 USD; 84 DIFFERS, corrections in experiments/input_audit/results-20261008/full-run/ NOT applied: read page by page after Saturday). Reviewer fix: the ledger lint "id not one we hold" check is opt-in (--strict-ids), else it flags 23 of 32 real promises and false-FLAGs the recap. The 5 stale hook tests and the ACT-22 patch were repaired for the Luna step order. Suite: 1797 passed (+15 hook tests separately). Checked: all CFP tasks Ready, sleep Never, commitments 7 kept / 0 NOT kept / 25 not yet. NEXT: read Friday (ACT-30), then apply the ACT-58 and ACT-51 patches before Saturday with the operator; Saturday (ACT-31) readout and ACT-46/47. Memory note: Agent Inbox/claude/2026-10-08 - CFP pre-flight for first Friday awards run four builders merged nothing live.md.
>

> **2026-10-06 - MODELS BAKE-OFF, GERMAN DATE RULE, UNCONFIRMED BADGE, LUNA SHADOW LIVE. RESUME WITH docs/control/RESUME.md (STOPPING POINT 2026-10-06).** Control list v16, 28 of 47 verified. ACT-56: experiments/model_bakeoff (blind calls, append-only registry, compare.py, models.json); on 21 person-confirmed facts DeepSeek V4.1 Flash, deepseek-chat and Nemotron about 16 found with 1 wrong-accepted (German OWASP Day start, a rule gap), Luna max 17/17/16 with 0 wrong after the fix, Sol 15, space-bunny-alpha untestable (404): keep DeepSeek as reader, drop Nemotron and Sol, second opinion adds nothing. ACT-62: German main-day label rule and the "Sponsor required (unconfirmed)" badge merged and verified (live with Monday's page). ACT-58: Saturday recap states upstream promises kept / NOT kept with a subject FLAG. ACT-61: Luna shadow is the LAST Saturday step in run_monthly.ps1 (backup run_monthly.ps1.pre-lunashadow-20261006), summary in the log only. Rulings R-002 (sponsorship gate stays link-only; published enquiry email counts as found; model routing via ChatGPT Plus/Codex first). Sponsor quote rerun with Chrome: 3 of 114 proved. Open: send note 45 and the VulnCon email; Fri 10-09 awards run and Sat 10-10 load readouts; PC on Thu-Sat (ACT-60).
>

> **2026-10-05 (night) - THE CUSTOMER SHEETS DEFINE THE JOB; CUSTOMER EVENTS NOW IN THE QUEUE. RESUME WITH docs/control/RESUME.md (STOPPING POINT block).** FOUND: the process never fed customer-sheet rows into the research queue (weekly_intake.py only reads their status; WEEKLY-CYCLE says verification never adds anything). The customer sheets grew Arnica 53 to 125 and Utility 58 to 84 rows (08-30 to 09-16); 84 customer rows had no confident match on 10-03, 57 still ahead. Operator rule: EVERY event on the two customer sheets is researched (ACT-51, TOP PRIORITY). DONE BY HAND: 56 events appended to the input lists with blank ids (`scripts/add_customer_rows.py`, backups `*_input.pre-customerrows-*`), upstream's 59 ids stamped by URL (`scripts/stamp_given_ids.py`), 3 more events added (Google Cloud Next 2027, CDAO Defense and Security 2027, World of Concrete 2028). BUG FIXED: `stamp_input_ids.py` cleared stamps on events not yet in the database; the ledger `docs/operations/given_ids.csv` keeps them. Lists now Cybersecurity 117 rows, Utility 74. STILL TO BUILD: the weekly route and the Saturday recap line 'customer rows not in the queue' (target 0). RULING R-001 (docs/operations/OPERATOR-RULINGS.md; upstream accepted): START DATE = first day of the MAIN conference. MY ERROR: note 29 gave upstream a 2028 call as the 2027 one (World of Concrete); corrected in note 29b, the 2028 row minted and loaded live (`cfp_monitor.pre-woc2028-*.db`; key_year set with the operator's approval after the permission classifier blocked a direct write; seed row appended; live invariants all ok). WAVES: Wave 2 reviewed (ACT-21, 26, 20, 23, 25 verified; ACT-20 patch applied to run_monthly.ps1: Saturday shadow reader, backup `run_monthly.ps1.pre-shadowreader-20261005`), Wave 3 reviewed (ACT-50, 49, 44 verified; ACT-40 and 42 partial at review); control list 24 verified, tests 1673 passed. NEXT: ACT-52 (triage upstream's reply to note 32: Industrial Net Zero survivor and duplicate pair, a new 2026 row, AFPM blank row); Fri 10-09 02:00 first scheduled awards run (ACT-30); Sat 10-10 02:00 first load of the 58 new customer events (never proved end to end: ids not yet in the database), shadow reader and finder (ACT-31); then ACT-46 and ACT-47. OPERATOR OWES: the sponsorship rule (ACT-53, parked) and a ruling on Hack In The Box Phuket 2026. Memory note: Agent Inbox/claude/2026-10-05 - CFP customer sheets define the job - queue gap found.md.
>
> **2026-10-05 - CONTROL LIST, BUILDER WAVES, IDENTITY FIXES. RESUME WITH docs/control/RESUME.md (read it first).** The failure-point register (docs/operations/FAILURE-POINTS.md, 60 root causes by macro step A to F) is worked through a control list (docs/control/ACTION-LIST.html, data action_list.json, 31+ actions in five waves) by a BUILDER sub-agent in an isolated worktree, with Claude as REVIEWER (verifies, applies live items, merges, marks verified; the builder never verifies). Wave 1 (ACT-10..19) was reviewed, merged and verified; 15 actions verified at the end of the day; register 25 overcome / 22 mitigated / 4 watch / 9 pending. Wave 2 builder is RUNNING (worktree C:/Users/matts/cfp-monitor-builder2, branch builder/wave2): review procedure is in RESUME.md. Live changes today (backups, logged): nine input rows stamped with upstream-confirmed ids, one stamped with a survivor id, one marked DUP_OF (unresolved input ids 11 -> 1); verify_basis column migrated live; board proof counts date basis (or an independent evidence-layer read) only; customer export label for status-only rows is now 'Call confirmed, date not confirmed on page' (operator decision). Upstream replied to notes 26, 27, 28: ids now ours, location claims withdrawn after our page checks (IEW stays Kolkata, WHEC stays Singapore); remaining items are ACT-46/47 and ACT-43. NEXT: Fri 10-09 02:00 first scheduled awards run (ACT-30), Sat 10-10 02:00 first automatic load, step-failure trend and first shadow run (ACT-31); review Wave 2 when its hand-back arrives. Operator picks outstanding: none blocking.
>
> **2026-10-04 - FINDER + READER, SHADOW RUN, AWARDS REFRESH PLAN.** EVIDENCE (n = 14 known live deadlines, gold favours the grounded call): real menu/sitemap URLs + cheap reader + code-proven quotes + main-call rule found the right deadline for 12 of 14, 0 wrong (grounded 8 of 14); when the two agreed the date was right 7 of 7 (experiments/finder_reader_test/RESULT.md). It is an EXPERIMENT: scripts/shadow_finder.py runs it as the LAST step of Saturday's run_monthly.ps1, read-only, capped (120 min, 0.60 USD, 4.25 h into the job), and emails disagreements; first real run Sat 10-10 (about 40 rows, about 100 minutes, about 15 cents). Answer-key candidates (docs/qa/answer-key-CANDIDATES.csv, 17 events): 29 facts proven and agree, 0 differences; nothing is confirmed without a person. AWARDS: scripts/refresh_plan.py marks dormant Closed awards REFRESH_SKIP (audit skips like DUP_OF, importer carries the row; about 35 percent skipped, about 2.60 USD a week); awards load QA (post_load_qa --markets Awards -> load_awards.md); awards grace in Complete % (68 to 77). ODSC East 2027 pinned. Markets files edited (outside git) have backups: run_monthly.pre-shadow-20261004.ps1, run_monthly.pre-refresh-20261004.ps1, run_market_audit.pre-refresh-20261004.py. Full suite 1,483 passed. OPEN: nothing running. NEXT ACTION: Fri 10-09 02:00 first scheduled awards run (narrow prompt on awards, refresh plan, load_awards; rehearsal covered skip-and-carry only): read the canary, the recap and load_awards.md; then Sat 10-10 research, load, step-failure trend and the first shadow email. Operator picks on the board: awards answer key + finder, pins for awards, conference answer-key decision, recall gaps.
>
> **2026-10-03 (night) - QUALITY METRICS REBUILT; RECALL LIMITERS AND PER-STEP FAILURE COUNT LIVE.** BOARD: Complete % and Accurate % sit under the header and REPLACE the weighted six-component index (retired; freshness and call health stay as unscored process health). COMPLETE = expected fields filled (a pinned honest blank counts) averaged with coverage; call fields (deadline, link, evidence) are excused while the event starts more than 90 days ahead and no call is open. ACCURATE = proven / (proven + contradicted) over stated facts; unproven shown, never wrong; a contradiction is never excused. Provable metric: a deadline you pinned counts as proven, far-future without a firm call is excused. Customer agreement: another edition or earlier round (>180 days apart, or their date passed while ours is ahead) and our far-future blank are shown beside the figure, not scored. Now: conferences Complete 92 / Accurate 94; awards 68 / 100 (12 facts, thin); provable 14 of 17; agreement 14 of 15. Rules: QA-REGISTER A14-A16, code scripts/board_metrics.py (split_scores, process_drivers). PER-STEP FAILURE COUNT: scripts/failure_steps.py, wired into post_load_qa and the recap; history runs_out/qa/step_failures.jsonl (first record 10-03: FIND 7, PROVE 6, READ 2, IDENTITY 11). RECALL LIMITERS (render fallback, multilingual dates, heading year) committed; Expo MENA 2027 pinned (June 8-9, 2027, ADNEC; 14 pins, answer key 46 facts). Full suite 1,455 passed. OPEN: nothing running. Your picks on the board: page-finding tests (docs/design/page-finding-options.md), the next recall gaps, or wait. NEXT ACTION: Friday 10-09 02:00 awards run, then Saturday 10-10 02:00 research and load (first with fixed load step, evidence carry, pins and the per-step trend); read runs_out/qa/<Monday>/load.md and the board.
>
> **2026-10-03 (late) - EXPERIMENTS AND A CORRECTION.** Experiment 4 (read-the-page pass, experiments/read_the_page_pass/RESULT.md): quote-checked extraction by a cheap model made 0 wrong claims in about 70 scored answers and kept every blank-expected case blank; recall 44-62% on readable pages, limited by script-built pages, date formats and heading-year; cost under 1 cent a pass. Trap cases (docs/qa/trap-cases.json, scripts/trap_cases.py): 6 pass, 3 known gaps, 3 need a person or model. 12 operator-verified events are PINNED (docs/operations/pinned_rows.json; scripts/apply_pins_live.py applies a new pin to the approved files and database the same day; scripts/answer_key_from_pins.py writes docs/qa/answer-key.csv; board panel 'Verified by you'). CORRECTION: on 10-03 I cleared ODSC East 2027's start date and pinned it blank as 'operator verified' on a page summary that missed the header; the page states May 10-12th, 2027 (real browser read). Restored in the database and approved file (re-gated 23/23, re-promoted), pin removed, trap T02 rewritten, notes to upstream corrected (note 24 item 5); OPERATOR-EDITS-LOG has the entry. Rule: a summary of a page is not a read of the page, and a pin is 'operator verified' only if the operator said so. OPEN: close the three recall limiters, then re-run experiment 4 x3 per model; experiments 3 and 5; send note 24 (upstream: new rows must be valid CSV, ids we hold, evidence for 'Discontinued').
>
> **2026-10-03 - SATURDAY'S LOAD DONE (by hand), NARROW PROMPT WORKS, THREE SAFEGUARDS ADDED.** Research: 130 of 130 rows grounded, 0 stubs (was ~1/3). The scheduled load did NOT run: `run_monthly.ps1` built the import and recap steps as one flattened array (comma binds tighter than +), python started with single characters and hung; FIXED (backup `run_monthly.pre-stepfix-20261003.ps1`), the Awards job (Fri 10-09) would have hit it too. Narrow answers leave fields blank or wrong (ORGANIZER blank on 130, venue as CITY on 28, input-list dates wrong on 66), so `scripts/narrow_overlay.py` (same-edition carry, conference-dates restore, verified-evidence carry) and the year checks in `scripts/start_date_arbiter.py` now run inside `weekend_import.py` before the gate. Live load at 07:49 (backup `cfp_monitor.pre-golive-20261003.db`): Cybersecurity 70 rows, Utility 55 rows; it blanked verified evidence on RSA 2027, Black Hat Asia call for summits, Nullcon (and moved CODASPY, Apres-Cyber, Global Energy Show link); RESTORED from backups by `experiments/purpose_audit/restore_rows_20261003.py` (16 DB cells, 19 approved-file cells; pre-restore snapshot `cfp_monitor.post-golive-before-restore-*.db`); gate on both approved files ACCEPTED, watch-list 25/26 (Nullcon entry updated to the renamed row). Five Utility date conflicts settled by the operator's manual page reads (`OPERATOR-EDITS-LOG.md`); upstream's replies (notes 21, 22): their ids differ from ours, rulings lack R16 evidence, so SAF Europe / Sustainable Fuels duplicate and Future Fuels MENA are OPEN (our dates blank). New row Carbon Capture Technology Expo MENA 2027 loaded (DB 427, organizer blank). OPEN: after Sat 10-10 and the Fri 10-09 awards run check the same blank-overwrite pattern (watchlist_check + the overlay report); CODASPY (11-16 abstract vs 11-23 paper) and Apres-Cyber (11-20 vs 11-21) are fresh-research answers the carry rule does not cover; STATUS corrections (H2 MEET, six awards, CGI) still owed; upstream's R16 evidence for SAF Europe duplicate and Future Fuels MENA; idea: countdown timers on event pages signal the upcoming edition.
>
> **2026-10-02 (night) - SIX ARNICA EVENTS LOADED; AWARDS JOB ENABLED.** Operator ran Enable-ScheduledTask on 'CFP Weekly Awards Research' (State Ready; first run Fri 10-09 02:00, narrow prompt). Upstream's earlier 'out of scope' ruling on AAIML, ICRAI, RAAI, AI Con USA, AppWorld, ODSC East was REVERSED (they are on the customer's own sheet; notes 18-21 in experiments/purpose_audit). First delivery REJECTED (no research, wrong cities; the gate passes an empty file), then two sparse patches gated ACCEPTED and loaded (import_grounding --ids, DB 420 -> 426, backups cfp_monitor.pre-arnica6-20261002.db and ...6b...): AAIML, ICRAI, RAAI verified (deadline 10-10), AI Con USA Open 10-18 (Seattle; walled to a plain fetch, read in a browser), AppWorld and ODSC East held as projected with blank deadlines. Our own slips: verify_grounding run without --market Cybersecurity + --seed-csv restricts to ALL rows and wrote 13 verify_state/detail changes (no deadline changes); the importer keeps an old start_date when the new one is blank (ODSC cleared by hand). Upstream claimed the rows were stamped into Cybersecurity_input.csv; they were not (we added them: 73 rows, seed 72). Two ids carry wrong city slugs (london, guangzhou), locked. BOARD: Agent-tasks card and pill layout fixed. STILL OWED: eight STATUS corrections (H2 MEET, six awards, CGI) were asked of upstream only as 'next regular delivery' (no date); plan is to check after Saturday (H2 MEET) and after Friday 10-09 (awards) and ask with a date only if still Open. Customer is informed by the next customer page, not by a message.
>
> **2026-10-02 (late) - NARROW RESEARCH PROMPT LIVE FOR SATURDAY.** `Markets/run_market_audit.py` has a narrow-first mode (CFP_PROMPT_MODE; narrow question on attempts 1-2, unchanged full prompt on 3-4; CONFERENCE never asked so no renames); `Markets/run_monthly.ps1` now defaults it to narrow-first (caller can set `full` to roll back). Real test (`experiments/purpose_audit/narrow_test_run.py`, 4 conference + 3 award rows): 7 of 7 grounded, 0 fallbacks, 0 stubs, one 504 retried. Caveat: narrow answers omit ~24 non-deadline fields (they carry from the input row; new events have little). OPEN: after Saturday 02:00 run `scripts/watchlist_check.py --previous-db %LOCALAPPDATA%/CFP-Monitor/cfp_monitor.pre-r6-20261001.db` and report before Monday 07:00; operator re-enables 'CFP Weekly Awards Research' (elevated PowerShell) after Saturday looks healthy; eight STATUS corrections owed by upstream; customer to be told 6 out-of-scope events (3 Urgent, close 10-10).
>
> **2026-10-02 - current state, open, next.** STATE: benchmark LOCKED (`docs/agents/results/01-benchmark-key.csv` + `.sha256`; 40 events, 9 hand labels; brief 01 now has rule 7a, the edition rule). Hermes runs are pinned by `-m/--provider/--reasoning` and confirmed from `%LOCALAPPDATA%/hermes/state.db` (sessions.model, model_config); the one-shot CLI reads config.yaml (space-bunny-alpha), an open Hermes window is separate. Upstream's 7 new rows: gate ACCEPTED 22/22 after a clean re-emit; 4 speaking rows (Black Hat Asia summits and briefings, SANS CTI/OSINT, TROOPERS27) loaded on upstream's permanent IDs (`import_grounding.py --ids`, then `verify_grounding`, `fix_edition`, declared in `held_rows.txt`), added to `Markets/Cybersecurity_input.csv` (EVENT_ID_CANON stamped by a guarded one-off, because `stamp_input_ids.py` only links events already on last week's page) and to `market_sheets/cyber_seed.csv`; a full weekend_import sandbox rehearsal ships all four. 2 award rows (Climate Change Emerging Scholar Awards, ACT Expo Fleet Awards) loaded into the awards tables with `import_awards.py --ids` (119 -> 121). Our own defect found and fixed: the 10-01 hand patches had left GROUNDING_CONFIDENCE out of step with IS_PROJECTED on 5 approved-file rows (rule R11); one word corrected on each, backups beside the files; the Cybersecurity approved file passes the full gate. Gate check 3 now reports a walled page (anti-bot notice) instead of failing it: shared `is_block_page` in `src/cfp_monitor/verify.py`, tests in `tests/test_gate_block_page.py`. OPEN: (1) DONE 10-02 later: upstream answered note 8 (Utility_Awards_master.csv is their staging queue = the Utility rows of Markets/Awards_input.csv; approved Utility awards baseline = Awards_20260905_out.csv + the 2 rows). Added both rows to Awards_input.csv (guarded script `experiments/purpose_audit/sandbox_20261002/add_awards_input_rows.py`, backup `Awards_input.pre-2awards-*.bak.csv`), placed `Markets/Awards_20261002_out.csv` (127 + 2 rows; becomes the newest awards file the page is built from; delete it to undo), and `stamp_input_ids.py --markets Awards --apply` stamped the two ids itself (it links only ids on the awards file the page was last built from, so the new file had to be placed first). Awards page preview renders both rows (Open). The new awards file is NOT gate-accepted: 6 older rows with passed deadlines still marked Open and one dead CGI link, none from the new rows; flag to upstream; (2) status cleanups (H2 MEET + 6 awards still STATUS Open after their deadlines; gate check 6): upstream's two full-row re-emits were REJECTED (R8a GATED_STATUS filled, dead invented submission links, NOTES overwritten with literal filler text, 10-16 populated fields changed per row; see worklog); their third reply was a clean SPARSE patch (`experiments/purpose_audit/upstream_sparse_patch_20261002.csv`). Applied only the CGI citation withdrawal to `Markets/Awards_20261002_out.csv` (2 cells, backup `Awards_20261002_out.pre-patch-20261002-160817.bak.csv`); `apply_row_patch.py` refuses STATUS/STATUS DETAILS (customer-owned), so the 8 status values must arrive through upstream's normal delivery; until then the file fails gate check 6 on 6 award rows (the page shows them Closed by display gating) and H2 MEET is re-researched Saturday; (3) Hermes platform census (brief 02) not started; (3d) BOARD: `python scripts/board_metrics.py --update-status` computes both headline numbers and two quality indexes (conferences 69%, awards 58% on 3 of 6 components); follow the 'Board update checklist' in `docs/design/STRATEGY.md` (rewrite `working_on`, set `now_updated`, prune dated `decisions`). OWASP BASC is now loaded too (gate reports script-built pages as 'quote not checked'). Closing note to upstream: `experiments/purpose_audit/NOTE-TO-UPSTREAM-17.md`. (3c) SIX MORE EVENTS LOADED 2026-10-02 (upstream's third sparse patch, gate ACCEPTED on the six rows; backups `cfp_monitor.pre-6more-20261002.db`, `cfp_monitor.pre-apres-city-20261002.db`): Triangle InfoSeCon, WSED, ACS GC&E (Minneapolis, 31st, symposia deadline 10-13, abstracts Jan 4-Feb 15 in STATUS DETAILS), ACM CODASPY (abstract Nov 16; paper Nov 23 in STATUS DETAILS), Apres-Cyber (Park City UT), Fuel Ethanol Workshop / Sustainable Fuels Summit (2027-02-12): `import_grounding --ids`, `verify_grounding` (6 of 6 verified), `fix_edition`, `held_rows.txt`, input lists and seed sheets (`experiments/purpose_audit/add_inputs_and_seeds.py`); grounding_facts 413 -> 419. NOT LOADED: OWASP BASC (its quote is verbatim in a real browser but the page is script-built and the gate's plain fetch sees 52 characters): waiting on the operator's decision to report such pages as 'quote not checked' like anti-bot walls. Our own bug found and fixed: `grounding.clean_city` read 'Park City' as a venue and stored 'UT' (tests added). (3a) SPONSORSHIP OPTION A BUILT (operator chose A now, B later, 2026-10-02): `scripts/sponsor_carry.py` called from `weekend_import.resolve_market` before the gate; every carry is in the report (`sponsor_carried`) and log; B (stop re-asking while fresh) not built; design `docs/design/sponsorship-carry-forward.md`. UPSTREAM QA: `docs/qa/UPSTREAM-QA-PROTOCOL.md` (canary pages are live in the repo; send the three questions and score them); Saturday research logs show only ~35% of calls were real grounded searches. (3b) DATE-READER FIX APPLIED 2026-10-02 (operator approved; `src/cfp_monitor/verify.py`, `tests/test_find_date_boundaries.py`): a claim of 2 October no longer matches 'October 12' and the '(26)' style is read; measured on 350 library pages; full suite 1,307 green before apply, re-run after (see experiments/purpose_audit/sandbox_20261002/suite3_out.txt). Undo: git revert the commit; (4) Black Hat Asia rows read as unconfirmed because blackhat.com answers a plain fetch with HTTP 403 ("the cited page could not be read"), NOT because of the date reader (find_date reads their dates; corrected 2026-10-02): the page library holds those pages, so the verifier could fall back to it; the two-digit-year `(26)` reader and sponsorship carry-forward after Monday; (5) full test suite was started in the background at 15:03: check `experiments/purpose_audit/sandbox_20261002/suite_out.txt`. NEXT ACTION: after Saturday 02:00's load, run `python scripts/watchlist_check.py --previous-db %LOCALAPPDATA%/CFP-Monitor/cfp_monitor.pre-r6-20261001.db` (watch-list in `docs/operations/watchlist.json`; also `scripts/qa_import.py --previous-db ...`) instead of diffing by hand: the four corrected rows, the six new rows and the approved files. Before the load it reports 16 of 20 holding, the 4 CHANGED being the known db gap. Original wording: diff the four corrected rows and the six new rows against today's backups (`cfp_monitor.pre-4newrows-20261002.db`, `...backup-pre-awardimport-20261002-144553.db`) and report before Monday 07:00 (India Energy Week must read open).
>
> **2026-10-01 END OF DAY - current state, open, next.** STATE: all four known-wrong customer-market rows are corrected in our database AND in the approved files Saturday 02:00 reads
> (`Markets/Utility_audited.final.csv`, `Cybersecurity_audited.final.csv`; backups beside them); upstream acknowledged our local copies as master. Offline page library built (`scripts/page_library.py`, 360 pages);
> whole-page DeepSeek reader run over it (347 pages, 0.45 USD): promising, not proven. Refresh policy designed, not built. Status board: `scripts/status_dashboard.py`. Nothing runs in the background.
> OPEN: (1) apply upstream's Nullcon Goa 2027 payload to the approved Cybersecurity file (report mode clean; operator approval pending); (2) upstream's re-research delivery (7 new rows, IS_PROJECTED flags,
> India Energy Week 2026 duplicate retirement) is NOT received: verify it on arrival, our DB still holds both IEW rows; (3) Hermes benchmark stage 2 needs the debug Chrome (`scripts/launch_chrome_cdp.bat`) restarted and the operator's go;
> (4) Climate `(26)` date check after Monday; sponsorship carry-forward; platform census. NEXT ACTION: after Saturday 02:00's load, diff the four corrected rows (India Energy Week, Climate Change, SecureWorld, Global Energy Show)
> against today's backups in `%LOCALAPPDATA%/CFP-Monitor` and report BEFORE Monday 07:00 (India Energy Week must read open on the customer page). Operator edits are logged in `experiments/purpose_audit/OPERATOR-EDITS-LOG.md`.
>
> **READ FIRST: `docs/design/STRATEGY.md` (standing brief and the 5-line session opener), `docs/design/PROGRESS-CHECKLIST.md`, and the status board (`scripts/status_dashboard.py`, data in `docs/design/status.json`). Agent briefs: `docs/agents/`.**
>
> **2026-10-01 (later) - purpose audit + heading reader Phase 1 (experiments only; nothing changed).** `experiments/purpose_audit/` (RESULT.md, LIVE-ROWS-REVIEW.md): of 39 stored
> customer-market deadlines, 9 confirmed as submission dates on their cited page, 1 mismatch (Climate Change, above), 16 absent, 12 with no readable page; 3 not-yet-passed rows need a
> person (SecureWorld Gov & CI, India Energy Week 2027, Global Energy Show Canada 2027: see LIVE-ROWS-REVIEW.md). `experiments/heading_reader/RESULT.md`: tuned on the 15 labelled pages 24/24,
> but the fresh 10-page holdout FAILED (precision 0.33; only 2 submission labels). Own-words judgments safe (19/19); heading-inherited ones not. Advisory use only; needs a revised rule and a fresh holdout.
>
> **2026-10-01 - OPEN DATA FINDING, review before the next customer send: Climate Change conference deadline (on-climate.com).** Stored
> `grounding_facts.deadline` = 2026-12-19, `verify_state` = `verified`, but the detail reads "[L0s] the page itself states the call is open": the CALL STATUS was
> confirmed, not the date. On the call page (`/2027-conference/call-for-papers`) 2026-12-19 is the end of the REGISTRATION regular period. The PROPOSAL periods end
> 2026-06-19 (early), 2026-10-19 (regular) and 2026-12-20 (late). The `evidence` table's own deadline claim is 2026-12-20 with verdict `no_quote` ("claim stands"), one
> day off the stored value. Under R23 the date a person can act on now is 2026-10-19. NOTHING WAS CHANGED. To do: check how the customer page shows this row (confirmed or
> not) and whether it reaches the next send. **Same class, measured:** of 48 stored deadlines in the two customer markets, 13 have a `verified` state that came from the L0s
> status layer (call open or closed), not from the date, and 5 more are `verified` with no evidence page at all. A deadline's own `verify_detail` and evidence verdict should be
> read before treating `verified` as "date confirmed". Found while pre-labelling pages for the sentence-picking test; the evidence is in
> `experiments/sentence_picking/labels.json` (`db_flags`) and `RESULT.md`. An earlier note in `experiments/sitemap_discovery/RESULT.md` (UPDATE 6) counted this event as a recall
> HIT; that was wrong (a registration date was matched) and is corrected there.
> **2026-09-30 / 10-01 experiments (all in `experiments/`, nothing wired into a scheduled job):** `grounding_reliability/` (narrow prompt: 24 of 24 grounded vs 9 of 24; the
> "504" is our own 120 s timeout enforced by Google); `sitemap_discovery/` (site page inventory, crawl-priority rules v3.1, menu-vs-map, date reader v2, bounded crawl and fair
> recall tests); `sentence_picking/` (model picks the sentence, code proves it; deepseek-chat matched deepseek-v4.1-flash at about one eighth of the cost; precision 1.00 for both,
> recall 16 of 24 post-hoc; the misses are tables and schedules, so the next step is a heading-aware reader). Designs in `docs/design/` (`grounding-reliability-test-plan.md`,
> `sitemap-discovery-design.md`, `sentence-picking-design.md`). **Scheduled tasks DISABLED by the operator 2026-09-30:** `CFP Monthly Re-Research (prospect markets)` (prospect markets are
> speculative; no customers) and `CFP Weekly Awards Research` (first run was due 2026-10-02; re-enable with `Enable-ScheduledTask` in an elevated shell). The Saturday, Sunday and Monday
> jobs are unchanged.
> **NEXT (each needs an operator decision):** (1) review the Climate Change row above and how the customer page shows it; (2) heading-aware reader: Phase 1 on the 15 labelled
> pages plus a 10-page holdout labelled and locked first, then the purpose audit of the 48 stored deadlines (`docs/design/heading-aware-reader-design.md`, section 8);
> (3) sponsorship carry-forward (agreed in principle: sponsorship passes are about 70% of a weekend's search spend and re-ask nearly every row because the research input has no
> `SPONSOR_*` columns); (4) a per-site preferred language for h2meet.com (its English twin read 3 of 5 useful pages against 0 of 5 in Korean) and six inventory sites to fix
> (four redirect aliases, two script-built menus). `docs/operations/WEEKEND-PROCESS.md` now notes the two disabled tasks.
> **Where the work stands, end of 2026-09-28.** Five scheduled jobs, every one ending in a recap email (see `docs/operations/WEEKEND-PROCESS.md`, test-guarded against drift). NEW TODAY: Friday 02:00 weekly awards research (limit 16h, first run Fri 2026-10-02); Sunday discovery auto-applies findings proven word for word (strict, backed up, rolled back on failure); monthly recap; Monday build QA splits already-past date changes out of "Look at" and saves a copy beside the pages; customer pages hide Closed rows by default in the four work-queue views; Monday verification coverage FIXED (register citations before the re-read; results written under every upstream id).
> **MOST URGENT - GAP 5, next year's editions are never picked up.** Contract R13-R15 (v1.3) agreed "research the successor, not the concluded edition" and it was never built. 5a (free) found 12 of 44 past events already publishing next year's dates on their own site; **CCUS 2027 (Utility) has its call for abstracts OPEN now and we do not show it**; Hydrogen Technology Expo MENA is labelled discontinued but 2027 is announced. See `experiments/gap5_next_edition/`. Trap: weekend_import holds back any row without a permanent id, so a genuine successor needs an id minted only after R14 + R15 pass.
> **The gaps (experiments/ - theory and isolated tests only; nothing wired until proven, operator rule; report all in every update):** 4a measured (skip 19 rows, save 45 requests, nothing lost) - ON HOLD, folds into gap 5. Gap 3 (answers from memory) - postponed, Google badly degraded 09-28. Gap 1 (made-up links) - no AI needed, can run anytime. Gap 2 after 1; 4b after 3.
> **OPEN:** (the one-time awards test task was deleted 2026-09-28.) Proposed, not built: a job cut off mid-run sends no recap - have the next job check the previous finished. Awards test run showed ~6.4 min/row and 52% failures on a bad Google day.
>
> **IDEA TO CONSIDER LATER - NOT SCHEDULED (operator, 2026-09-28):** a measured head-to-head of Firecrawl (search + fetch + "point at the sentence" extraction) against the current Gemini-grounded research, on ~20 rows with known answers, scored on correct deadline / real working link / verbatim quote. Do NOT set up without the operator asking.
>
> **THIS WEEK'S CONFERENCE PAGE OF RECORD (operator-confirmed 2026-09-28):** `Desktop\Nicolia-PR-Prime\handoff-files\weekly\2026-09-28\Conference Review 2026-09-28 - Live Markets.html`, rebuilt 13:47 (Closed rows hidden by default in the four work-queue views; verification coverage fixed - every row with a cited link and a deadline has a real result: 14 confirmed, 12 not on page, 9 could not check, 1 disputed). Default counts: Need to Verify 0, Deadline confirmed 4, Check against your sheet 3, Submit Link Missing 2, Everything 112. The 8:50 and 11:49 builds are superseded (kept as `work_2026-09-28\*.pre-closed-hidden.html`). Any `conf.html` in a scratchpad or a mis-named `Awards_Review_20260928.html` is a test copy, not a record.
>
> **Where the work stands, end of 2026-09-27 - THE WEEKEND RUNS NOW FINISH THE JOB THEMSELVES.** Saturday: intake -> `stamp_input_ids.py` (permanent ids onto the research input) -> canary -> research -> `weekend_import.py` (gate, row-by-row rule, backup, import on CARRIED ids, verify, reconcile, rollback on failure, promote) -> `weekend_recap.py` email. Sunday: verification (now of THIS weekend's research, against both promoted files) -> recap email. No manual step between Saturday and Monday. First live load 2026-09-27: both markets PROMOTED, invariants hold, 0 duplicates, 0 events lost; Monday 2026-09-28 publishes this weekend's research (it would otherwise NOT have published - last week's files had no promotion manifest).
> **Why it was manual, in one line:** identity was rebuilt from the NAME at both research and import, so every rename made a duplicate (24 in one weekend); a person matched them. Identity is now carried from the input through `<Market>_audited.identity.csv` and `import_grounding --ids`.
> **Saturday 2026-09-26 failed** on three canary bugs (stale ledger, no --seed-dir, sample judged by full-delivery rules) - all fixed; the Saturday job now writes `Markets\logs\run_monthly_<stamp>.log`.
> **NEXT:** (1) confirm the one-time Sunday copy (`CFP Weekly Verification - ONE-TIME 2026-09-27`, 23:50) ran and emailed; delete both ONE-TIME tasks. (2) Refresh the research input names from last week's approved file each week - only ~60% of rows used this week's research (stubs + 11 unlinkable stale names). (3) Build a deploy step for the live build - it was 59 files behind the repo (synced tonight with backup). (4) Record an R9 contract note: identity is now carried by us.
> **STANDING PREFERENCES (added):** no manual review steps in the weekly chain - auto-report and state the downstream impact; test a scheduled job by cloning the REGISTERED task with a one-time trigger, never by hand; keep the Sunday schedule fixed.
>
> **Where the work stood, end of 2026-09-22 - a quality-by-design build day. All on main in both repos, pushed as built; nothing uncommitted.**
> Built and shipped: the GROUNDING EVIDENCE TRAIL on every audit run + `grounding_review` (the composed-URL signal -> a review action); the Step-4a PROMOTE GUARD (`promote_delivery.py` + `publish_guard` - the Monday build goes DEGRADED rather than publish a stale/unaccepted `.final.csv`; the last silent-failure path, closed); an awards-aware `validate_market_output`; SELF-HEAL Phase 1 (`verify_methods` method ladder L1 upstream AI / L2 code / L3-5 self-heal / L6 grounded $, `self_heal.py` report-only + `--apply` proven confirmations only, grounded step spike-guarded/budgeted/off-by-default, `grounded_ask.py` upstream so cfp-monitor never imports google-genai); `verify_dates` (low yield, most dates stay `unv`); the EVIDENCE MATRIX (`evidence_matrix.py` - flat filterable heatmap by customer/market/cost/depth + click-to-expand per-field card) wired into the Monday build with `--refresh`; and BUCKET A review signals in the Monday build (duplicate detection now runs weekly - it found ~15 outstanding groups; 2 conflicts, ACT Expo and 19th ICCCIR Johannesburg, were merged).
> **NEXT (all optional):** browser+LLM date verification if date coverage matters (~3/374 today, mostly `unv`); apply the grounded self-heal confirms (only the 2 free browser ones were `--applied`); wire `weekly_review.py` (still a prototype).
> **STANDING PREFERENCES:** work on `main` directly - no feature branches/PRs unless asked (main had drifted 53 commits behind on 2026-09-22, fast-forwarded and merged branches deleted); add a plain description when sharing an error code.
>
> **Where the work stood, end of 2026-09-20. THIS WEEK'S RESEARCH IS IMPORTED AND ALL INVARIANTS HOLD.** Monday 07:00 publishes 58 Cybersecurity and 54 Utility rows. Both deliveries cleared the gate as ACCEPTED. Net change for the customer: 10 improvements, 4 genuine losses, and 12 already-expired deadlines cleared off the page.
>
> **NEXT: nothing is required before Monday.** After that, in order:
> 1. **SAF Europe Summit 2027** - held OPEN in `market_sheets/held_rows.txt` with no established reason. An UPCOMING event should not fall off a live-market input list; the other two holds (it-sa Exhibiting, Oil and Gas Decarbonisation 2026) are likelier to be harmless.
> 2. **Awards cadence** (operator agreed the split, not yet built): add awards to `weekly_verify.py` using the existing `check_award_deadlines.py` and `link_check_awards.py` - free, no LLM - then a monthly paid awards re-research task offset from the Wed prospect sweep. Awards intake already runs weekly; 153 rows live in the two sheets against 135 in the Sept 3 seed.
> 3. **Amend the contract for the R16 decision** below. Upstream assigns the number.
>
> **THE SATURDAY JOB IS ARMED** with the ungrounded guard, circuit breaker, corrected model default, canary (both its first-run bugs fixed), archive fix and tightened lifecycle prompt. The 2026-09-19 02:00 run wrote 114 answers no search stood behind; 0 have been written since.
>
> **R16 CHANGED, BY OPERATOR DECISION 2026-09-20.** An ASSERTED ending with no citation still fails the gate. A DECLARED DOUBT - "Needs Verification" plus IS_PROJECTED=true - now ships with a note saying someone should go cite it. Previously the generator deliberately produced rows the gate always rejected, and two of them, on conferences nobody at the customer tracks, blocked all 112 rows of a week's research. Nothing ships as "Closed" on prose alone; that protection is untouched. `tests/test_gate_r16_declared_doubt.py` pins both directions.
>
> **TWO TRAPS FOR THE NEXT SESSION, both cost hours today:**
> - `import_grounding --out` must write to the seed directory **beside the DATABASE** (`AppData\Local\CFP-Monitor\market_sheets`), using the SHORT names `cyber_seed.csv` / `utility_seed.csv`. Writing `cybersecurity_seed.csv` into the repo folder leaves the DB holding rows the index does not know about.
> - `verify_grounding` runs **between** import and `check_invariants`. Skipping it leaves every new row without a verify state.
>
> **Read `C:\Users\matts\CLAUDE.md` before writing any code.** It now requires announcing `USING EXISTING: <path>` or `NEW CODE: searched TOOLING.md ... found nothing` before each run. Roughly 20 throwaway scripts were written on 2026-09-20 and two produced wrong conclusions that were reported as fact - one of them joined on the delivery's EVENT_ID directly, the join contract 5.4 forbids, when `scripts/qa_import.py` already did the job correctly.
>
> **Where it stood end of 2026-09-16. The customer's sheets are read automatically, reconciled, linked to our conferences, and every step leaves a QA report.**
>
> **NEXT (operator asked for this first): turn the page check into a weekly step.** Measured today
> on 117 customer links, cached, results and script in
> `AppData\Local\CFP-Monitor\runs_out\qa\2026-09-21\page_check_measurement\` (a rerun from the
> cache takes about a minute). The question: open THEIR link and ask whether the page shows their
> name/date/city AND ours. Result: 58 of 96 existing links page-confirmed; Decarbonization Congress
> looks like a wrong link; 10 links where our date is not on their page (Carbon Capture USA, Future
> Fuels MENA, SAF NAM, Infosecurity Europe, CYBERUK, Gartner SRM, CES x2, European Biomass, H2 MEET);
> Decarb Connect Canada where their sheet looks stale. Of 21 review rows the page settles 8: link
> OWASP Global AppSec EU, OWASP LASCON, ACS Green Chemistry, FEW, Renewable Resources (+SXSW AI Track
> for a person); keep Nullcon Berlin and NA SAF apart. **Nothing written yet** - the operator
> approves the auto-link rule first. Rules already learned: tolerate spelling (s/z, joined words,
> typos), drop ordinals ("17th"), browser-read pages that show no dates, fold accents and alias
> cities, and "different event" needs THEIR date on the page and OURS absent.
>
> **WHAT CHANGED TODAY**
>
>     duplicates      tidy closed (Nullcon, ShmooCon merged); decided keeps declared in
>                     docs/operations/duplicate_decisions.txt, read by detector AND merge tool
>     lifecycle       grounding_facts gained lifecycle_evidence_url/quote (R16) - the claim "this
>                     event has ended" had no column. 0 -> 15. A blank import never erases one.
>     gate check 2    a 403 gets a browser second opinion (Black Hat USA was a 404 behind it);
>                     SUBMISSION URL now reported as note 2s, advisory until upstream agrees -
>                     request DRAFTED, NOT SENT: handoff-files/Handback_Criterion2_Submission_Links_20260916.md
>     intake          service account works (key on disk; google-auth installed). Retries stop on
>                     failures a retry cannot fix, and record the real reason.
>     sheet shape     reconciled first after every download; a removed column keeps last week's
>                     values instead of BLANKING every row; contact emails no longer read as
>                     "submitted"; one status vocabulary (clients.LIVE/DONE/UNDECIDED_STATES)
>     matching        now runs every intake. Three defects fixed: their date column was never read
>                     (EVENT START DATE); calibration needed their list in our order; "unique
>                     domain" linked sibling events (SANS, OWASP, Nullcon). Links we hold are never
>                     rewritten. Utility 39 -> 53 linked of 84, Arnica 39 -> 43 of 125.
>     QA reports      runs_out/qa/<cycle Monday>/{intake,import,build}.md+.json, one folder per
>                     cycle. Import and build run automatically inside Monday's weekly_deliverable.
>
> **OPEN, needing the operator:** what "Closed" and "Not Appropriate" mean (17 rows; Black Hat Asia
> and USENIX are Closed with deadlines ahead); send the criterion-2 hand-back or not; the 94
> customer conferences we do not research (pending industry candidates); two sheet-hygiene points
> for the customer, recorded in the private memory note, not here.
>
> **Watch:** Sat 2026-09-19 is the first live intake with shape check, matching and QA. Mon
> 2026-09-21 is the first automatic import and build QA - read build.md before sending. Utility
> currently fails gate check 6 (Climate Week NYC past its deadline); should clear with Saturday's
> delivery, as should six rows labelled Registration on the page sent 2026-09-14.
>
> **Other open items:** nothing checks a lifecycle quote against its page (ShmooCon's fails);
> 62 of their deadlines are free text and not compared on the review page; remaining QA reports
> for steps 1 (research), 2 (verify), 3 (review), 6 (send).

> **Where the work stands, end of 2026-09-15. Foundations day - three things were stored where they could drift, or not stored at all, and nothing reported it. Nothing reached the customer.**
>
> **THE DAY HAD ONE SHAPE.** Three separate investigations ended in the same finding: a fact
> about OUR OWN data was somewhere it could drift, and every check stayed green.
>
>     market membership   identified a conference by its WEBSITE ADDRESS. Addresses move; the
>                         row stays pointing at the old one. 115 of 401 (29%) were on NO market
>                         list, including all 13 SecureWorld rows, and ~98 entries pointed at
>                         addresses nothing uses. Everything that asks "show me the Cybersecurity
>                         conferences" reads that list. Now 1 (the declared AES hold).
>     our START DATE      had no column. Upstream always sent it; import read it for validation
>                         and dropped it. So the matcher sourced our side of name+city+date - one
>                         of three CERTAIN tests - from a delivery CSV passed on the command line,
>                         five weeks old and missing the row being matched. 0 -> 365 of 401.
>     awards              had NO reconciliation at all. v2.1 made them a second entity type and
>                         every invariant since looked only at conferences.
>
> **When a check is silent, ask whether it RAN, not only what it said.** A missing step, an
> absent column and a stale list all look identical to a green dashboard.
>
> **AWARDS INVARIANTS, checks 10-15 inside `check_invariants.py`** (one gate; new checks go into
> it). Identity; **the awards evidence pass has run at all** - the check that would have caught
> 119 rows sitting at `unverified`; market membership; **an award window opens before it closes**
> (the analogue of gate 6b, which awards are exempt from because an award has no event to attend,
> v2.3); and presence against `--awards-delivery`. Now `weekly_deliverable` step 2d - that run
> mutates twice and had never reconciled - **recorded, never blocking**: an invariant failure is
> about the DATABASE while the conference page is built from the delivery CSVs.
>
> **A CHECK THAT CANNOT TELL A REASONED DECISION FROM A FAULT TEACHES PEOPLE TO STOP RUNNING IT.**
> Check 14 called 8 delivered awards "missing" on its first run. All 8 are deliberate:
> `import_awards` excludes rows whose `OPPORTUNITY_TYPE` is not an award, and rows labelled
> `DUP_OF`. It now recomputes the importer's OWN exclusions rather than restating the rule, and
> prints each with its reason.
>
> **A SECOND DUPLICATE DETECTOR: same city, same dates, agreeing names.** Only possible because
> `start_date` now exists. The operator proposed city+date as a MATCHING rule; measured, it fails
> - 50 pairs share a city and start within a day, because big shows carry satellites (AppSec
> Village inside DEF CON, four IFA events in Berlin on one morning), industry weeks cluster, and
> sister expos co-locate. But it is an excellent DUPLICATE finder, since two of our own rows for
> one event always share both. Found 8 pairs the name-slug grouping is blind to - `&` against
> `and`, Summit against Expo, an ordinal prefix, a "Virtual" qualifier. **6 merged, 401 -> 395.**
>
> **TWO PAIRS REFUSED, both after checking their websites:** Carbon Capture Technology Expo NA
> against Hydrogen Technology Expo NA, and World Biogas Summit (`world-biogas-summit.com`)
> against World Biogas Expo (`biogastradeshow.com`). A conference and its co-located trade show
> share a city, a date and most of a name. `merge_duplicate_events --exclude` makes that a named
> decision.
>
> **CUSTOMER INTAKE IS NOW STEP 0 OF THE SATURDAY JOB** (`scripts/weekly_intake.py`, called from
> `run_monthly.ps1`). Contained so it can NEVER cost a research window: exit code ignored,
> exceptions swallowed, returns 0 even when degraded. Self-repairing where it honestly can be -
> it loads any snapshot the database has not seen, which immediately closed a two-week gap where
> 2026-09-01 snapshots sat on disk unloaded while the tables held 2026-08-30. **It always reports
> the AGE of the client layer**, because silence about staleness is the failure.
>
> **VOICE OF CUSTOMER, CORRECTED.** "Info Needed" is NOT the customer asking us for anything -
> their NOTES are intelligence written for themselves and the only STATUS DETAILS on those rows
> describe THEM emailing organisers. It is also not the untouched default (blank status is, 53
> rows): it carries a PRIORITY on 9 of 15, so it is deliberate triage they then pursue. **The
> field that asks something of us is `SUBMISSION DATE VERIFIED`** - 41 rows read "Needs
> Verification". `CUSTOMER-SIGNAL.md` already said this.
>
> **The contract in this repo is now the contract in force** - consolidated v2.0.1 plus the five
> amendment files beside it, behind a header listing them, with `tests/test_contract_current.py`
> failing the build if that header stops matching the files present. It had been v1.1 from
> 2026-08-01 while the `cfp-protocol` skill sent every session there to read it.
>
> **NEXT: the duplicate tidy** - 3 groups left (it-sa keep, ShmooCon possibly two real editions,
> 1 MIXED). Then the gate's blind spots on `SUBMISSION URL` and behind a 403, which two earlier
> sessions were handed and left no commits on.
> **Open:** the Google service-account key is still not on this machine - the config is complete
> (both sheet ids, both gids, the key path), only the downloaded JSON is missing, and its
> `client_email` is what the sheets must be shared with. Until then Saturday's intake reports
> DEGRADED and the browser export remains the path. Also: ~98 membership entries point at dead
> addresses (reported, never deleted); 36 rows still carry no start date; the 27 rows citing no
> page now read "not yet checked", which is true.
> **Rollback:** `known-good-2026-09-15b`, plus per-step DB backups beside the live database.

> **Where the work stands, end of 2026-09-14. Contract is at v2.5, the database is deduplicated, and awards rows are verified for the first time.**
>
> **CONTRACT AMENDMENT v2.5 ADOPTED** (accepted by upstream in full, numbered by them).
> `OPPORTUNITY_TYPE` is restricted to actionable submission opportunities - `Speaking` (default,
> unsuffixed), `Awards`, `Exhibiting`. **`Registration` is retired and will no longer be emitted.**
> The case was one measurement: 17 rows carried an OPPORTUNITY suffix and NOT ONE had a submission
> deadline, which is the entire justification for the component being in the key. Upstream will
> supply booth closing dates WITH CITATIONS where published, blank where the site is silent.
> Text: `handoff-files/Contract_v2.5_Amendment_Opportunity_Type_Narrowing_20260914.md`.
>
> **AWARDS ARE VERIFIED AT LAST.** All 119 rows read `unverified` because the pass did not exist:
> `audit_evidence.py` and `export_checks.py` join `grounding_facts`, the CONFERENCES table.
> `check_award_deadlines.py` was the sibling, written 2026-09-08 and never wired to anything. It
> now has `--apply` and runs as **step 1a of `weekly_deliverable.py`**. First run: 100 cited
> deadlines over 95 pages - **41 verified, 53 no_quote, 6 unreadable, 19 with no cited page**.
> Every one of the 53 has a deadline already past (award pages roll to the next cycle); of the 19
> rows whose deadline is still AHEAD, **16 are confirmed**.
> The worse half: the awards page had been built with the CONFERENCE checks CSV, whose 162 rows
> contain zero awards, so it shipped reading "0 Deadline confirmed - we read it on their page".
> An omission rendered as a result. Run health saw nothing wrong because every step it knew about
> succeeded - **health counts steps that ran, not steps that should have existed.**
>
> **DUPLICATES: 21 GROUPS, NOT 9. 18 ROWS MERGED OUT, 419 -> 401.** `event_id` is minted once from
> `<year>-<name>-<city>[-<opportunity>]`, so a change to any of the three makes the next import
> INSERT instead of update. `find_duplicate_events.py` reports and classifies; `merge_duplicate_events.py`
> drafts and (with `--apply`) performs. **Neither customer page was ever affected** - both are one
> row per event. Merged: 7 SAME_TODAY, 5 PLACE, 6 NON_OPPORTUNITY. **Still open: 1 OPPORTUNITY
> (it-sa exhibiting, keep), 1 YEAR (ShmooCon, may be two real editions), 1 MIXED.**
>
> **FIVE MERGE RULES, each found by drafting and READING the output, not by reasoning:**
>
>     survivor = the customer's row   6 of 7 SAME_TODAY links pointed at the OLDER row; keep-newest
>                                     would have orphaned ACT Expo (Drafting Abstract, Urgent) and
>                                     WFES (Submitted). A key is a name, not a fact.
>     citation moves as a UNIT        deadline+quote+URL+verify_state+detail+is_projected, from ONE
>                                     row or none. Assembled from two rows it is a claim neither made.
>     R1 outranks that atomicity      a citation edit clears URL and quote; THE DEADLINE IS NEVER
>                                     BLANKED (SecureWorld St. Louis nearly lost 2026-07-08).
>     the name breaks a city tie      St. Louis vs Clayton (the venue's town). Invariant 3 cannot
>                                     catch it - Clayton is a real place, not a venue string.
>     a retired row never survives    v2.5. The Gartner IAM draft kept the REGISTRATION row and
>                                     deleted the speaking row, taking its speakers URL with it.
>
> **THE MERGE IS NOT DONE WITHOUT REPOINTING THE SEEDS.** `check_invariants.py` failed within a
> minute of the first merge ("no delivered row is missing", 7 keys): `identity.seed_map` reads
> `EVENT_ID_CANON` straight out of `market_sheets/*_seed.csv`, which still named the deleted rows.
> The next import would have recreated every duplicate, every Saturday, for ever. `--apply` now
> repoints them (27 rows over 6 files, each backed up). **This is what a reconciliation after a
> mutation is for.**
>
> **NOT RETIRED, deliberately:** `2026-rng-conference-dana-point-registration` and
> `2026-international-pulp-week-vancouver-registration` are Registration rows with NO speaking
> counterpart - the only record we hold of those events, so 2.1 keeps them. They need no
> `held_rows.txt` entry: they are still named by the seeds, and that file is for rows ABSENT from
> the delivery. Expect them to re-key as Speaking next cycle; the duplicate is flagged in v2.5 so
> neither side reads it as drift.
>
> **NEXT:** `weekly_deliverable.py` has **never run** (`CFP Weekly Customer Pages`, LastRunTime
> never, first fire **Mon 2026-09-21 07:00**) and its script changed twice on 2026-09-14. **No
> customer page has ever been built from a 401-row database.** Dry-run it into a scratch out-dir
> before the 21st - no API cost.
> **Open:** `docs/operations/pipeline-contract.md` is STILL VERSION 1.1 (2026-08-01) while the
> contract in force is v2.0.1 + amendments through v2.5 - and the `cfp-protocol` skill sends every
> new session to read it as "the why"; gate check 2 still reads neither SUBMISSION URL nor behind a
> 403; awards have no invariants equivalent; LIFECYCLE evidence never requested; STATUS ownership
> unresolved; OpenRouter credits about $18; replacement links still go to a person.
> **Rollback:** checkpoint `known-good-2026-09-14-v25` (all three repos tagged and pushed, 177-file
> live snapshot). Plus 3 `cfp_monitor.before-merge-*.db` and 8 seed `.before-merge-*.csv` - keep
> until the merges survive one real import cycle.

> **Where the work stands, end of 2026-09-13. Runs now report their own health; automatic replacement links do not work yet.**
>
> **Live data:** SecureWorld Twin Cities 2026 (Open, deadline 2026-09-19) and St. Louis carried a
> dead submission link that answers HTTP 403 to scripts and 404 in a browser. Replaced with
> upstream's round-5 portal `info.secureworld.io/speaker-submission-form` (browser-verified to list
> both), gate ACCEPTED, imported, invariants hold. Logged for upstream in the Markets record file.
>
> **NEW DEFAULTS - read before running anything:**
>
>     runs report health     src/cfp_monitor/run_health.py; SUMMARY.md opens with HEALTHY|DEGRADED;
>                            delivery_loop exits 0 accepted / 1 not accepted / 2 DEGRADED
>     Saturday + sponsorship end with "RUN HEALTH: ..." and log [GROUND] N search(es) per call
>     403s get a browser    rules.NEEDS_BROWSER_STATUS - recheck_dead_links --csv, mechanical_repairs
>     LLM page reads retry  429/transient after 5s, 15s, 30s (extraction.py)
>     loop link questions   --links-via crawl (default); Gemini step parked behind --links-via gemini
>
> **THE FAIL POINTS, so nobody re-learns them** (full list in docs/design/worklog.md, 2026-09-13):
> 17 grounded Gemini calls returned no usable link - mostly 504 DEADLINE_EXCEEDED on both models, and
> the answers that came back were composed, dead URLs. A diagnostic call proved grounding RUNS, but
> its sources are per domain and support only the facts: **Gemini is good for dates, bad for exact
> URLs and verbatim quotes.** The crawl alternative first ran blind (OpenRouter deepseek-chat 429
> "rate-limited upstream" on nearly every page, swallowed); rerun HEALTHY it still found HubSpot
> plumbing, not SecureWorld's real form. **Replacement links go to a person, crawl candidates are hints.**
>
> **NEXT:** read the RUN HEALTH line of the 2026-09-19 Saturday run, then run `delivery_loop.py` on
> its delivery. **Open:** 9 real duplicate event pairs from key drift (CITY changed/blank or EDITION
> year changed - St. Louis/Clayton, HITB, Nullcon, Decarb TechInvest, ACT Expo, Carbon Capture Expo,
> Decarb Connect, Climate Change conf, Industrial Net Zero); gate check 2 still reads neither
> SUBMISSION URL nor behind a 403 (the 2026-09-12 side sessions left no commits); OpenRouter credits
> about $18; LIFECYCLE evidence never requested; STATUS ownership unresolved.

> **Where the work stands, end of 2026-09-12. Both live markets are ACCEPTED and IMPORTED, and the hand-back loop can close itself.**
>
> **Cybersecurity (58) and Utility (54) passed the full networked gate, are imported, and every
> invariant holds.** The 2026-08-31 import gap from yesterday is closed. H2 MEET 2026 is corrected
> (call open to 2026-09-30, event Nov 4-6, CITY Goyang) and its same-day duplicate key deleted, with
> the full row kept in `Markets/Utility_h2meet_dedupe_record.txt`. **Nothing is awaiting upstream.**
>
> **KNOWN-GOOD FALLBACK:** `C:\Users\matts\CFP-KnownGood\2026-09-12` (live build, DB, seeds,
> deliveries, scheduled-task XML, SHA256 manifest, `ROLLBACK.md`) and git tag
> `known-good-2026-09-12` on this repo, Markets and handoff-files - taken before the changes below.
>
> **THE OPERATOR IS BEING TAKEN OUT OF THE MIDDLE.** Three steps, all built and tested today:
>
>     1. Markets/standing_rules.md     agreed rules read by the Saturday run (it refuses to start without them)
>     2. scripts/mechanical_repairs.py contract v2.4 (adopted): fix how a claim is WRITTEN, never what it claims
>     3. scripts/delivery_loop.py      gate -> repairs -> questions -> Markets/answer_findings.py (Gemini) -> verified -> gate
>
> **NEXT: the 4-request live pilot of `delivery_loop.py`** on a copy of
> `Markets/Cybersecurity_audited.patched.csv` (the morning file), to judge Gemini's answers before
> the 2026-09-19 weekly run. It has only been dry-run. The loop applies citations and links only;
> proposed date/status changes wait for a person. It never imports.
>
> **Not the same tool:** `scripts/repair_delivery.py` is the older unquoted-comma repair.
>
> **Gotchas proven today.** The live DB and seeds live under `AppData\Local\CFP-Monitor`; the
> repo-root `cfp_monitor.db` is a fixture, and the runbook's relative `--db cfp_monitor.db` misleads.
> Write seeds to the live `market_sheets` with the existing name (`cyber_seed.csv`). Run
> `fix_edition.py` after importing new rows - `import_grounding.py` leaves `key_year` blank.
> Gate check 2 has never read `SUBMISSION URL`, and verifier L0s let a July crawl contradict CES 2027
> (both in separate sessions). `LIFECYCLE_EVIDENCE_URL/QUOTE` are never requested by the prompt.

> **Where the work stands, end of 2026-09-11. The weekly research job had been a no-op for two weeks.**
>
> **Both scheduled research tasks reported success while auditing zero rows** on 2026-09-02
> and 2026-09-05. `powershell.exe -File script.ps1 -Markets A,B` binds one literal string,
> not an array, so each run looked for a market input file named after both markets joined
> and exited clean. Both tasks now use `-Command "& 'script.ps1' -Markets A,B"`, verified
> against the real script. Changing a registered task needs a genuinely elevated shell.
>
> **The last productive research run was 2026-08-31, by hand, and its output was never
> imported.** The database's newest import is 2026-08-29; the delivery holds 8 rows the
> database does not. **Importing that output is the open item** - and run
> `check_invariants.py` after, per the mutation rule.
>
> **Saturday 2026-09-12 is deliberately skipped** in favour of a manual run; the weekly
> trigger resumes 2026-09-19 with nothing to re-enable.
>
> **N5 is closed in code, blocked on credentials.** `scripts/fetch_customer_sheet.py` on
> branch `feat/fetch-customer-sheet` fetches each customer sheet with a read-only service
> account and hands the bytes to `snapshot_customer_sheet.py`, which keeps owning the
> snapshot store. It refuses an HTML sign-in redirect, a wrong gid, or an empty export,
> because a bad file stored today is diffed next week as a customer deletion. Needs the
> operator to create the service account and share both sheets as Viewer; a script cannot
> create credentials. Sheet ids live in
> `%LOCALAPPDATA%\CFP-Monitor\customer_sheets.json`, never in this public repo.
>
> **Sponsorship:** the dedicated pass built 2026-09-08 has still not run at scale.

> **Where the work stands, end of 2026-09-08. The awards delivery is ACCEPTED and IMPORTED.**
>
> **`Markets/Awards_20260905_out.csv` passes 23 of 23 gate checks.** Two NOTEs remain and both
> are the contract working rather than debt: 11 dead cited pages on passed-deadline rows
> (v2.2 decay) and 10 declared stubs (2.1).
>
>     database  119 awards rows in `award_grounding_facts` + 119 memberships
>               conferences UNTOUCHED at 392 / 391, asserted by a test
>     links     171 awards URLs in `link_checks`, 16 dead, 0 false 404s out of 16
>     page      127 rows, 43 deadlines confirmed, 10 dead links, 57 need verification
>
> **THE NEXT THING IS THE AWARDS VERIFY PASS.** All 119 rows are still
> `verify_state='unverified'`. The link check is done and the deadline check exists
> (`check_award_deadlines.py`), but nothing sets `verify_state` on the award table -
> `verify_grounding.py` is hard-wired to `grounding_facts` in two SQL statements. Its layer 0
> cross-checks our own crawl history, which for awards is empty, so **layer 0 will be inert**;
> layers 1 and 2 transfer unchanged.
>
> **`handoff-files/Reply_Batch1_ACCEPTED_20260908.md` is drafted and NOT SENT.**
>
> **There is no `check_invariants` equivalent for the award tables.** On the conference side
> that is the tool that catches a bad mutation after the fact.
>
> **Contract v2.2 and v2.3 were both adopted 2026-09-08** and both are implemented. v2.2 gives
> criterion 2 the passed-deadline exemption - **a blank deadline is deliberately NOT exempt**,
> which is why criterion 2 went 14 failures to 3 rather than to zero, closed by three agreed
> withdrawals. v2.3 is the awards `EDITION` anchor ladder; **rung 1 is upstream's and is not
> implemented here**, so a derived edition never overwrites an evidenced one, and awards
> disagreements are REPORTED. Do not auto-withdraw passed-deadline 404s: tried 2026-08-29,
> 14 of 18 would have been wrong.
>
> **UPSTREAM MUST SEND CANDIDATE URLS, NOT QUOTES.** Their first patch had 0 of 9 keys matching
> ours and 5 of 6 citations that did not survive a fetch - three cited pages 404'd and two live
> pages did not contain their sentence. Same signature as the pilot in `extract_citations`'s own
> header: the model knows the fact and guesses where it lives. The candidate-URL split fixed it.
> **A successful fetch is not a successful citation** - those 404 error pages returned 2712,
> 3430 and 2752 characters.
>
> **`NOTES` IS THE CUSTOMER'S AND WE WERE OVERWRITING IT.** Zero of 96 joined conference rows
> preserved their text. Fixed at source; the awards file is repaired; upstream has agreed to
> stop emitting it. **`ORGANIZER` was empty on every row since v1.5 created it** because no
> prompt asked - the organiser was going into `NOTES` instead. Fills on future runs only.
>
> **Two of our own gate checks were wrong, not the data.** Criterion 4 matched a bare "active"
> and failed rows saying "no active cycle"; 6b assumed a deadline precedes its event, which is
> false for an award closing entries during its own ceremony week. Both fixed, both guarded.
>
> **Stage 6 is built.** `build_review_page.py --kind awards` - own vocabulary, own chips
> ("Opening soon" is the one that matters), shared renderer. **The page cannot be sent yet**:
> the rows are not imported, so there is no evidence pass and those views read "not yet
> checked". Import is gated on acceptance, which is blocked on the above.
>
> **Next action: send the two documents.** Everything left needs upstream's answer.

> **Where the work stood, end of 2026-09-05. ONE CONTRACT, and the awards run is in flight.**
>
> **The contract is `Joint_Pipeline_Contract_v2.0.1_CONSOLIDATED_20260905.md` plus
> `Contract_v2.1_Amendment_Renumbering_And_Awards_Window.md`, both in `handoff-files`, both
> adopted by upstream 2026-09-05.** Nothing else in that folder is in force - see its new
> `README.md`, which names the two current documents out of 106 and stamps the rest. A
> parallel session's v1.9 consolidation was rejected before sending: it dropped **34 numbered
> sub-rules**, including R23.3, the only new obligation R23 places on upstream.
>
> **SCHEMA IS NOW 45 COLUMNS (R26).** `SUBMISSION_OPENS` and `ANNOUNCEMENT_DATE` appended.
> The gate accepts `{43, 45}` as a transition - drop 43 once a 45-column delivery is accepted.
> **The v1.5 sponsorship block is no longer last**, so anything checking "the last five
> columns" is wrong; check positions 39-43. That bug was live in the gate this morning.
> `Markets/test_schema_agrees_with_gate.py` now compares the two repos, which nothing did.
>
> **AWARDS RUN IN FLIGHT.** 127 rows started 19:13 on 2026-09-05, roughly 1.3 min/row,
> expected around 21:58. Output `Markets/Awards_20260905_out.csv`. **The 09-03 pilot output is
> schema-stale at 43 columns - do not merge the two files.**
>
> **Rule numbers moved.** The v1.4 identity rules are now **R24/R25**; v1.5 sponsorship keeps
> R18/R19. Which set moved was decided by grep - every code reference is to sponsorship.
>
> **`NOTES` is the customer's.** Tiered rounds and a contested `ORGANIZER` both go in
> `STATUS DETAILS`. v2.0 got this wrong and upstream was about to act on it.
>
> **Next action: stage 6, the awards customer page.** A preview from the seed proves the
> renderer accepts awards data but is not sendable - every label says conference, and the
> awards columns render blank because they are absent from `build_review_page.FIELDS`, the
> documented trap in that file's own comment. Needs its own field list and vocabulary, and one
> genuinely new filter chip - **"opening soon"** - which has no conference equivalent and is
> the reason the module exists.
>
> **Upstream owes:** Bioeconomy Batch 1, and two AES Europe rows in the next Consumer
> Electronics delivery. Nothing owed to them.
>
> **Worth one line next time:** upstream said "upcoming awards research will build against the
> 45-column schema", but awards research is ours. Possible duplicate spend.
>
> **Deferred:** a secret gist for the contract (upstream cannot fetch `handoff-files` - it is
> private; `cfp-monitor` is public, verified by anonymous fetch); and a JUDGEMENT rule that
> **an absence or a total requires a count, never a truncated list** - I asserted "no code
> references the identity rules" from a `head -30` that happened to show all 30.

> **Where the work stood, end of 2026-09-03. AWARDS is now a second module.**
>
> **DECIDE FIRST TOMORROW - this repo is public and already carries client detail.** Not a new
> exposure and not fixable per-file: `Nicolia` appears in 10 tracked markdown files, `Arnica` and
> `Utility Global` in 7 each, `ESF MENA` and the $12,500 sponsorship figure in 6 - including
> `HANDOFF.md`, `worklog.md`, `JUDGEMENT.md`, `customer-sheet-matching.md` and the protocol
> skill. Nothing was pushed to `cfp-monitor` on 09-03 pending one coherent decision. `Markets`
> and `handoff-files` were pushed as usual.
>
> **Awards, stages 1-3 of 7 done.** Plan and full reasoning: [`docs/design/awards-plan.md`](docs/design/awards-plan.md).
> Seed: `Markets/Awards_seed_20260903.csv`, 135 rows, **127 to research** after 8 `DUP_OF`.
>
> **The premise: 135 award rows, TWO live deadlines.** Awards is a discovery job, not a
> verification job. The existing rows are a known-name set.
>
> **Operator decisions taken 09-03:**
> 1. The awards file still targets **this week** for the customer.
> 2. **Confirm the Cyber Defense date conflict FIRST tomorrow, before warning anyone.** Three
>    seed rows, one operator, two dates: a fresh quote says **2026-09-04**, two other rows say
>    2026-09-18. If the earlier date is right it has already passed by the time this is read.
> 3. Public-repo redaction - superseded by the finding above; one decision, not per-file.
> 4. **Stage 4 (127 rows, 3.0-4.4h) HOLDS until Gemini answers on v1.8.** Do not spend it early.
>
> **Upstream is Gemini** - designer and contract signer, cannot execute on this machine, so the
> operator runs things and couriers both ways. `handoff-files/Upstream_Request_v1.8_20260903.md`
> is drafted and **not sent**: it asks for a machine-readable keyed reply, lists every factual
> claim with how to check it, and deliberately puts one untested finding up to be contradicted.
>
> **Awards and conferences ask SEPARATE questions and share ONE engine.** Two rule constants in
> `run_market_audit.py`, dispatched on `OPPORTUNITY_TYPE`; a row without that column takes the
> conference path unchanged (proved byte-identical). The engine is shared on purpose - a second
> copy of the retry and citation machinery is the parallel-validator failure. Rule 0, the
> anti-echo guard, is asserted byte-identical in both prompts by `Markets/test_prompt_separation.py`.
>
> **`run_market_audit.py` imports NOTHING from this repo.** Retrieval is one Gemini call per row
> with the `google_search` tool; the crawl4ai/playwright/cdp ladder is downstream's only. An
> earlier claim that the crawl layer was "already awards-aware" was wrong - it came from greps,
> not from reading `audit_conference()`.
>
> **Awards need their own tables.** `conferences` has **no `opportunity_type` column**, so an
> award imported today is indistinguishable from a conference. Proposed: `awards` and
> `client_awards`; `clients` / `industries` / `link_checks` are already generic. Undecided:
> `evidence` and `grounding_facts` key on `event_id`, `changes` on `conference_id`.
>
> **Untested hypothesis, sent to Gemini rather than acted on:** in `audit_conference` the record
> is seeded from the input row and most fields fall back to it when the model omits a key, while
> `SUBMISSION DATE VERIFIED` and `SOURCE_AS_OF` are stamped with the run date unconditionally.
> That may be the mechanism behind the seven rows marked `Verified` with nothing to verify.
>
> **Also open:** the 10-row pilot left 2 stub rows from server-side 504s - needs `--redo-stubs`.
> The model renamed 4 of 10 rows and `EVENT_ID` derives from the name; the awards prompt now
> forbids it, but the risk is general. Awards `AWARD`/`CONFERENCE` column rename deferred as debt.

> **Where the CFP work stands, end of 2026-09-01.**
>
> **Two check-3 rows and the manifest stub section from ACCEPTED.** Current files:
> `delivery_v23_check4_43col.csv` and `audit_cybersecurity_utility_43col_r10_20260901.csv`.
> Both remaining rows are upstream's: H2 MEET needs the rounds-table subpage (its date is
> **locked to 2026-09-30 under 2.4** - Nicolia verified it himself via cell history, so do not
> re-derive it), and Global Energy Show needs a person at a CAPTCHA. **We do not bypass
> CAPTCHAs.**
>
> **RUN `scripts/customer_context.py` BEFORE REMEDIATING ANY ROW.** On 2026-09-01, 22 rows were
> repaired that the customer had already verified or acted on, and two were about to ship as
> contradictions - ESF MENA queued as discontinued while they hold an acceptance and a $12,500
> sponsorship decision. The data has been in `client_conferences` since 08-30. The gate ranks by
> rule; the customer ranks by what they can still act on, and those orders are near-inverted.
>
> **Cross the id boundary with `identity.to_canonical`, never by comparing EVENT_IDs.** The
> delivery carries upstream's ids, the client layer carries ours (contract 5.4). The documented
> join scores **87 of 87**; a join to the `conferences` table scores 43 and looks like a finding.
> `identity.assert_mapped` refuses an empty map - a path fault otherwise returns zero findings
> that read as two records agreeing.
>
> **Export a customer sheet with `/export?format=csv`, NEVER `/gviz/tq?tqx=out:csv`.** gviz types
> each column and silently drops non-conforming text - it blanked eight sponsorship deadlines
> including ESF MENA's $12,500, and the diff reported them as customer edits.
>
> **Four defect classes in one day were one cause:** a row fixed downstream, regenerated broken
> by the next research pass. `preserve_repaired_citation` is now in the generator, ordered after
> the R22 filter so it cannot rescue an inadmissible citation.
>
> **Open, and worth doing next: seven rows marked `Verified` with nothing to verify** - blank
> deadline, sometimes no evidence URL at all. R2 only fires on a *date* and R11 reads
> `false` + `Verified` as agreeing, so the gate cannot see it. Past the threshold for a check.
>
> **Also open:** six scripts still parse the seed map themselves (debt that may shrink, never
> grow); 18 client rows unmatched; and the operator's next ask - surface the customer's own
> `status` / `speaker_abstracts_submitted` as filter chips on the HTML, the same way
> "Check against your sheet" was wired.

> **Where the CFP work stood, end of 2026-08-31.**
>
> **OPEN, HIGH: eight SecureWorld rows hold a conference date in `SUBMISSION DEADLINE`** - one
> reads as due tomorrow. They cite an events LISTING; the stored quote is two consecutive rows of
> it, and the first date became the deadline while the second (correctly) became `START DATE`.
> SecureWorld publishes no deadline at all - its real speaker page is a redirect stub. Sent as
> `handoff-files/Defect_SecureWorld_Listing_Dates_20260831.md`. **Upstream's field: do not blank
> it here** - R1 deliberately never touches a deadline value.
>
> **A date is not a deadline unless something says so.** Proposed as a gate check: a quote with
> no deadline vocabulary is inadmissible for `SUBMISSION DEADLINE` unless the cited URL is itself
> a call page. On the current delivery this flags exactly those eight rows and nothing else.
>
> **Ask a site for its own index before trusting a URL.** Five guessed call-for-speakers URLs
> across three SecureWorld hosts all return HTTP 200 with "page not found" bodies - invisible to
> a status-code check. `scripts/check_urls_against_site.py` (read-only) checks a cited URL
> against robots.txt, the sitemap and the homepage nav. **No sitemap step exists anywhere in the
> joint process**; discovery is upstream's side, verification ours.
>
> **`extract_citations` can return a quote that is not on the page.** Three of five came back
> composed from our own fields (`'Threat Defense 2026 2026-09-01'`). Fetch and test every
> extracted quote before applying it. Two recut cleanly and are the only pending changes:
> Climate Change and Hydrogen Technology Expo NA.
>
> **Read `docs/operations/DECISION-TREE.md` before deciding a row needs research.** It is the
> executable specification of what follows from a conference's timing - what the customer sees,
> what we do, what it costs. `src/cfp_monitor/lifecycle.py` is the same thing in code; if they
> disagree, the doc wins.
>
> **`STATUS` is DERIVED at display time, never read from the file.** 126 rows disagreed with the
> stored value; only 8 were corrections. Deriving beats storing **only where a date on the row
> proves the stored value wrong** - never from a blank field, never between two true words.
>
> **Cadence changed:** re-research is now **weekly, Saturday 02:00** (was monthly), so Sunday's
> free verification sweep sees fresh research. `scripts/run_end_to_end.ps1` chains the whole
> loop and **stops at the gate** - a delivery that is not ACCEPTED is never imported.
>
> **The sponsorship fields cannot fill yet, and it is not a research gap.** Upstream's audit
> script emits **36 columns against the agreed 43** - it never picked up v1.3 (lifecycle) or v1.5
> (organizer, sponsorship). A fresh 113-row run on 2026-08-31 was rejected by the gate at check 1.
> They agreed the same day and are updating the export. **Do not tell anyone these fields will
> populate on the next run** - that claim was made twice and was wrong both times.
>
> **Amendment v1.7** (`docs/operations/Contract_v1.7_Amendment_Additive_Sponsorship.md`), agreed
> in principle 2026-08-31: downstream may fill `SPONSOR_*` **only where upstream left it Unknown
> or blank**, marked as ours, never overwriting. The blank is the boundary, so an upstream row can
> only gain. `ORGANIZER` stays theirs alone. **Implementation is deliberately blocked on the
> 43-column export** - building against a schema that is not emitted is how the last gap formed.
>
> **Amendment v1.6** (`docs/operations/Contract_v1.6_Amendment_Deadline_Rounds_And_Sources.md`):
> **R23** - the deadline shown is the NEXT round a person can act on, because conferences run
> tiered rounds and one date cannot hold three. **R22** - a social post or link shortener can
> never evidence a deadline, and may be withdrawn even on a passed deadline.
>
> **67 editions corrected** with every `event_id` byte-identical. That warning had printed every
> Sunday since 2026-08-12 into a log nobody reads; **integrity warnings now reach the digest**
> with an owner and a deadline.
>
> Still blocking, and both upstream's: **27 check-3 citations** (the gate returns REJECTED and
> nothing downstream runs) and **31 dead links** handed back 2026-08-27, unactioned.
>
> ---
>
> **Where the CFP work stood, end of 2026-08-30.**
>
> **The customer's own sheet is now in the system.** Two clients loaded - Utility Global (58 rows,
> Utility) and Arnica (53, Cybersecurity) - into three additive tables: `clients`,
> `client_conferences`, `industry_candidates`. **Per-client values never go on `conferences`**:
> its columns are shared and single-valued, and `status_details` is 349/373 filled with OUR crawl
> text that looks exactly like the customer's column of the same name.
>
> Matcher applied: **80 of 111 rows joined at 100%**, 21 need a human decision (region and edition
> variants), 10 are genuinely absent and are pending promotion candidates. Only certainty sets an
> `event_id`.
>
> **41 rows are marked "Needs Verification" by the customer** - 18 Utility Global, 23 Arnica. A
> work queue aimed at us that nothing had ever read. Ownership and plan are the open question.
>
> **The weekly digest now reads as a report** - definitions, actions, owners, timeframes - after
> its "Recovered since last week (19)" turned out to be 4 real recoveries and 13 of our own
> cleared citations. Three canaries now cover reports that claim unearned success.
>
> **The 31 standing dead links were already sent to upstream on 2026-08-27 and are unactioned.**
> The digest cannot yet tell "needs sending" from "sent, awaiting upstream" and will repeat the
> instruction every Sunday.
>
> Customer deliverables for the 2026-09-02 meeting live in `handoff-files`:
> `Conference Review 2026-08-30.html` and `Customer_Facing_Schema_20260830.md`. The v1.5 sponsor
> fields are **empty by design** until the 2026-09-01 re-research.
>
> ---
>
> **Where the CFP work stood, end of 2026-08-29.**
>
> **CURRENT FILE: `delivery_v14_final_43col.csv`.** Earlier files in that folder are superseded;
> `delivery_r3b_traced_43col.csv` was deleted (it carried 14 wrong withdrawals).
>
> **The delivery is NOT accepted.** An earlier ACCEPTED verdict this morning came from gate runs
> using `--no-network`, which SKIPS criteria 2 and 3 - and the gate printed ACCEPTED anyway.
> Always gate with the network before declaring anything.
>
> The gate now reports **INCOMPLETE** rather than ACCEPTED whenever a check was skipped,
> and exits non-zero - so that specific mistake cannot recur.
>
> On a full networked gate it passes everything except **check 3, at 28 rows** - live calls whose
> cited page does not carry its quote. That is upstream's active research queue, several with
> deadlines in early September.
>
> **Amendment v1.4 is written and implemented** (`docs/operations/Contract_v1.4_Amendment_Citation_Scope.md`).
> Criterion 3 now evaluates ACTIVE deadline claims only - blank and passed deadlines exempt -
> which took the failure from 186 to 28. **R3b is retired**: it tested URL shape as a proxy, and
> of 34 rows it flagged, 14 had their quote present on the cited homepage.
>
> **Three modules now enforce what used to be remembered:** `src/cfp_monitor/rules.py` (business
> rules as pure functions, each returning a reason), `src/cfp_monitor/sitewalk.py` (one
> site-walking implementation, was four), and `tests/canaries.py` (one record per real incident).
> `tests/test_no_reimplemented_crawling.py` fails the build if a fifth crawler appears.
>
> **Never "fix" R8c in the data** - multi-market events legitimately share one `EVENT_ID`
> (section 10); the gate check is per-market and correct.
>
> **`scripts/trace_quote_to_page.py`** is the tool for those 28: it walks the event's own site for
> the cited sentence and either retargets the citation or withdraws it under R1. It refuses to
> withdraw when no page could be read or the deadline has already passed. **Use `--dry-run` first.**
>
> **Upstream is aligned on data and contract as of this evening** - all eight falsifiable claims in
> their summary were checked against the files and hold. They are a day behind on architecture
> (they do not yet know about `sitewalk.py`, `canaries.py`, the enforcement test, the INCOMPLETE
> verdict or the tracer), and their test count of 619 is now 634.
>
> **108 and 184 are different populations.** 108 is the blank-deadline slice of the 186 check-3
> failures; 184 is the total blank-deadline citations cleared across the whole file. Do not
> reconcile them and conclude rows went missing.
>
> Open: upstream's 28 live calls and six organisation-domain searches. `ACCEPTED_COLS` is `{43}`.
>
> **Two joins that matter.** Our canonical `EVENT_ID` does NOT match upstream's (contract 5.4) -
> any script keyed on it silently matches nothing. Join on the URL being replaced. And a
> decision must be applied to every customer-facing URL field, not one: the review page renders
> four.
This file is the shared reference for **Matt + both Hermes instances**
(local dev box and the VPS). It lives in the public repo, so:

- **Read the latest:** `git pull` in your clone, then open this file — never paste long command
  blocks into a terminal; pull the repo and run from files instead.
- **Public web view:** <https://github.com/mattolejarczyk/cfp-monitor/blob/main/HANDOFF.md>
- **Alignment rule:** if something changes, edit this file (and the docs it points to) and
  `git commit && git push`. This doc + the linked docs are canonical; chat threads are not.

---

## 0. TL;DR
Two halves that work together:
1. **Customer app** (runs on each customer's own machine, residential IP): discover → resilient
   crawl → quality gate → source-of-truth DB → human-editable 15-column customer sheet → CSV/feed
   + reconciliation against their master spreadsheet.
2. **Vendor licensing proxy** (runs on Matt's VPS, **LIVE**): all LLM extraction is routed through
   it, keyed by a per-customer license. Revoke a key → that customer's crawling stops. Meters
   tokens for billing. **The only place the real LLM key lives.**

Crawling stays local (keeps the residential-IP anti-bot advantage); the VPS only brokers
LLM + license, so there is **no anti-bot regression** from using the VPS.

3. **Grounding pipeline** (added late July 2026): an upstream Google-Search-grounded research
   process supplies one 35-column CSV per market; we import it as *unverified discovery*, check
   its claims against live pages, and label the customer view by how well-evidenced each row is.
   Upstream claims never overwrite crawled facts — they live in their own table.
   **Start here:** [`docs/operations/pipeline-contract.md`](docs/operations/pipeline-contract.md).

---

## 1. LIVE deployment — the licensing proxy (operational)
- **Public endpoint:** `https://channeled.org/cfp-proxy`
- **Host:** Oracle VPS (`ubuntu@129.80.155.255`).
- **App dir:** `/home/ubuntu/.openclaw/workspace/cfp-proxy` (a git clone of this repo).
- **Runs as:** uvicorn on `127.0.0.1:8800`, behind nginx (`location /cfp-proxy/`, TLS by Certbot),
  kept alive by **PM2** (app name `cfp-proxy`, user `ubuntu`); survives reboot via the existing
  `pm2-ubuntu.service`.
- **Secrets/data on the box:** `.env` (chmod 600 — vendor LLM key + `PROXY_MODEL` + `LICENSE_DB`);
  `licenses.db` (every key + usage — **back this up**).
- **Verified end-to-end:** unknown key → `401`, active key → `200`, `revoke` → `403`.
- **Operator commands:** see [`licenseproxy/OPERATIONS.md`](licenseproxy/OPERATIONS.md) (issue /
  revoke / usage / floor / quota / restart / logs).
- **Update the running proxy:** `cd` to the app dir → `git pull` → `PM2_HOME=$HOME/.pm2 pm2 restart cfp-proxy`.
- **First-time / rebuild setup (no pasting):** `bash scripts/vps_setup.sh` (installs venv+deps,
  writes `start.sh`; it does NOT touch `.env` or nginx).

**Customer build** — in the customer's `.env` (and **no** LLM key on their machine):
```
CFP_LLM_PROXY_URL=https://channeled.org/cfp-proxy
CFP_LICENSE_KEY=cfp_theirkey
```

---

## 2. What we built (2026-07-06 → 07-09)
Grouped by area; file pointers in parentheses. **98 offline tests green.**

**Crawl reliability**
- JS-shell recovery — fast consent check + bounded render (`fetch.py`).
- Aggregator/org navigation — directory page → the specific event via spreadsheet row context
  (`aggregator.py`, wired in `pipeline.py`).
- HubSpot slow-site name recovery — URL dedupe + junk-URL skip + explore time budget +
  extraction time-box (`scoring.py`, `crawler.py`, `pipeline.py`, `config.py`).
- IP protection — never auto-hit a hard anti-bot site (e.g. Reuters) without a signed-in CDP
  browser; CDP is on by default for live/scheduled runs (`fetch.py`, `cdp.py`).

**Data + review**
- Source-of-truth guard — a failed/thin re-crawl can’t wipe good data (`storage.py`).
- Full editable 15-column customer sheet in the app — verify + human-owned columns, persisted;
  URL on every row; CSV export (`app.py`, `customer_format.py`, `storage.py`).

**Reporting**
- Coverage report — worked/failed % + failed links with reasons + resolution-path breakdown
  (`coverage.py`, `scripts/coverage_run.py`).
- Reconciliation annotator — annotate the customer’s master .xlsx with our diffs (highlight +
  comment + summary tab); taxonomy Confirmed/Changed/Gap-filled/Unverified/Not-crawled
  (`reconcile.py`, `reconcile_xlsx.py`, `scripts/reconcile.py`).

**Licensing (Option D) — built AND deployed**
- Vendor-hosted licensed LLM proxy = kill switch + token metering + version/feature gating
  (`licenseproxy/`), client wiring + friendly launch banner (`config.py`, `extraction.py`,
  `licensing.py`, `app.py`). Both OpenAI and OpenRouter supported.

**Distribution & go-live (2026-07-09, after the backup/installer/billing milestone)**
- **Proxy DEPLOYED LIVE** at `https://channeled.org/cfp-proxy` (see §1). Verified end-to-end
  including a **real crawl through the proxy** from the packaged build (Carbon Capture Europe → PASS).
- **Windows customer installer** (`installer/install.ps1`, `installer/README.md`): one script —
  finds/installs **Python 3.12** (winget), downloads the app, builds venv + deps + the Playwright
  Chromium, writes the customer `.env`, drops a **"CFP Monitor" desktop shortcut**. No provider key
  on the customer's machine. **Validated on the dev machine** (`-SkipDeps` for fast checks, then a
  full run). **Hardened for clean-machine unknowns:** graceful message if `winget` is absent (points
  to python.org) + re-verifies Python landed; launcher prints a friendly note when Chrome isn't
  installed (normal sites still crawl); script normalized to ASCII (stray em-dashes were tripping the
  PS 5.1 parser). Remaining: one smoke test on a genuinely clean/fresh Windows profile before mass send.
- **Windows hardening — two real bugs found during install validation, both fixed:**
  1. `.env` was written with a UTF-8 **BOM** (PowerShell's `Set-Content -Encoding UTF8` adds one),
     which corrupted the first line so `CFP_LLM_PROXY_URL` wasn't read → app fell back to
     "direct" mode / no license banner. Fixed: installer writes **no-BOM**; `config.py` loads
     `.env` with `utf-8-sig` so a BOM is tolerated regardless.
  2. A freshly winget-installed Windows Python's default trust store lacks the modern
     Let's Encrypt roots → the license banner's TLS check failed. Fixed: the check verifies via
     **certifi** (`licensing.py`). Crawling was never affected (litellm/httpx already use certifi).
- **Windows validation follow-up (2026-07-16):** actual licensed desktop install completed the
  first-launch license/CDP smoke test and passed a one-conference crawl. Customer output now has two
  cheap guardrails: the extraction prompt requests ASCII punctuation and the final 15-column
  customer table/CSV normalizes fields to Excel-safe ASCII. `.xlsx` intake is intentionally strict:
  only literal URL values in visible Column B become crawl targets; the matching row's A/C/D values
  (name/location/event date) feed the existing one-hop directory/organization resolver. Package XML,
  hyperlinks, notes, and other columns are ignored. A bad source URL is surfaced as an input-quality
  issue, never silently replaced.

- **Ops:** license-DB backup script + weekly cron (`scripts/backup_licenses.sh`), monthly billing
  readout (`admin billing --period YYYY-MM --rate <$/M tokens> [--csv]`).

---

## 3. Canonical docs (detail lives here)

**The grounding pipeline (read in this order):**
- [`docs/operations/pipeline-contract.md`](docs/operations/pipeline-contract.md) — **authoritative.** The upstream/downstream interface: principles, ownership boundary, verification model, the 9-point acceptance gate, the review loop, and rulings on cases that have caused real defects. Cold starts begin here.
- [`docs/operations/market-runbook.md`](docs/operations/market-runbook.md) — the operating procedure: exact commands in order, what to check at each step, and failure modes with their fixes.
- Upstream holds *Specification v4.3* (their mechanics). Where it and the contract disagree, **the contract wins** and v4.3 is amended.

**Everything else:**
- [`docs/design/roadmap-status.md`](docs/design/roadmap-status.md) — status by milestone + capability (is the product built). Its July summaries are stale; the milestone table is current to 2026-08-17.
- `handoff-files/CFP_Pipeline_Status.html` — **the operational one-pager: six macro steps, what is wired under each, and where the loop is open.** Lives in the PRIVATE repo because it names clients. This is the live roadmap for weekly work; regenerate it whenever a step changes state.
- [`docs/design/worklog.md`](docs/design/worklog.md) — append-only session history.
- [`docs/design/model-costs.md`](docs/design/model-costs.md) — LLM model + cost reference (DeepSeek vs GPT-5 vs Claude), per-conference economics, the `PROXY_MODEL` switch note.
- [`docs/operations/windows-desktop-install.md`](docs/operations/windows-desktop-install.md) — canonical licensed Windows install, Desktop shortcut, CDP, update, validation, and recovery runbook.
- [`licenseproxy/README.md`](licenseproxy/README.md) — proxy architecture + deploy.
- [`licenseproxy/OPERATIONS.md`](licenseproxy/OPERATIONS.md) — day-to-day operator commands (issue/revoke/billing/backup).
- `.env.example` (customer/dev) and `licenseproxy/.env.example` (vendor) — every setting explained.

---

## 4. How each party stays aligned
- **VPS Hermes:** clone is at `/home/ubuntu/.openclaw/workspace/cfp-proxy`. `git pull` → read this
  file + `OPERATIONS.md`. For any multi-step task, run scripts from the repo, don’t paste blocks.
- **Local Hermes:** clone is at `C:\Users\matts\cfp-monitor`. `git pull` → read this file.
- **Matt:** this file’s public URL (section top) is the shareable read-only web page.

---

## 5. Cost & models (quick reference — full detail in `docs/design/model-costs.md`)
- **Extraction model:** DeepSeek-V3 (`deepseek-chat`) via OpenRouter — deliberately cheap; the task
  is clean-markdown → structured JSON, where a frontier model buys little.
- **Per-1M tokens:** DeepSeek ~$0.14–0.27 in / ~$0.28–1.10 out · GPT-5 $1.25 / $10 · Claude Sonnet 5
  $3 / $15 · Claude Opus 4.8 $5 / $25.
- **Per ~100-conference run:** DeepSeek **~$0.50–1** vs GPT-5 ~$5 vs Sonnet ~$7–10 vs Opus ~$16
  (frontier = ~10–30× the cost for marginal gain on this task; our misses are *crawl* problems, not
  extractor intelligence).
- **⚠️ Action:** DeepSeek deprecates the `deepseek-chat` name **2026-07-24** (becomes a V4 alias).
  When ready, update `PROXY_MODEL` in the VPS `licenseproxy/.env` + `pm2 restart cfp-proxy` — one
  edit changes the model for **all** customers, no client touch.

---

## 6. Open / next
- ✅ **License DB backups** — `scripts/backup_licenses.sh` + weekly cron (exact `crontab` line in OPERATIONS.md → Backups).
- ✅ **Monthly billing readout** — `admin billing --period YYYY-MM --rate <$/M tokens> [--csv]`.
- 🟢 **Proxy live** at `channeled.org/cfp-proxy`; **customer installer built + validated on the dev
  machine** (Python/BOM/TLS fixes done) and **hardened for clean-machine unknowns** (winget-absent
  and Chrome-absent both handled gracefully; script is ASCII-clean). Remaining before mass send: one
  smoke test on a clean/fresh Windows profile; v2 wrap in an Inno Setup `.exe`.
- Optional later: reconciliation **accept/reject per diff**; **Google Sheets** reconciliation (v2);
  `PROXY_MODEL` bump after the DeepSeek name deprecation.
