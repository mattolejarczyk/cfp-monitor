# QA register: every check, what it catches, when it runs, and where its result goes

**Why this file exists (2026-10-03).** Over two days a large share of the quality work was done by hand and in throwaway scripts: reading pages in a
browser, comparing a candidate file with last week's by column, counting blanks, tracing upstream's ids to our files. Each of those found a real
defect, and each lived only in a chat. This register lists every check that matters, says which are **automatic** (they run in the weekend job and report
without anyone remembering) and which are **manual procedures** (you run them, here is the exact command), and records the incident that created each one.
If you do a quality check by hand and it is not listed here, add it: that is how the gap closes.

How to read the columns: **Auto** = runs inside a scheduled job and its result is in the recap or a QA report. **Manual** = a named command at a named
moment (runbook section in brackets). **Report** = where the result lands.

## A. Saturday research and load (automatic)

| # | Check | What it catches | Mode | Report | Born from |
|---|---|---|---|---|---|
| A1 | 5-row canary before the run | a broken key, quota or prompt, before 130 calls are spent | Auto | recap line "5-row test" | 2026-09-26 stopped run |
| A2 | Grounding trail: share of calls with a real Google search, 504 count, retries | research that answered from memory; the share fell to about a third on 2026-09-27 | Auto | recap table "Researched with real Google searches"; `<Market>_audited.health.json` | 2026-09-30 reliability experiment |
| A3 | Mechanical repairs (contract v2.4) | a quote copied slightly wrong | Auto | `<Market>_audited.repairs.md` | 2026-09-12 |
| A4 | Narrow overlay: last week's value for fields the short question does not ask, same edition only | organizer blank on 130 rows, a venue in CITY on 28, input-list dates on 66 | Auto | the import report `narrow_overlay` | 2026-10-03 rehearsal |
| A5 | Evidence carry: a blank quote never replaces verified evidence (same deadline, or a future deadline) | RSA Conference 2027, Black Hat Asia's call for summits and Nullcon lost their evidence in the first live load | Auto | import report `evidence_carried` | 2026-10-03 live load |
| A6 | Sponsorship carry-forward | a known Yes/No replaced by Unknown | Auto | import report `sponsor_carried` | 2026-10-02 |
| A7 | Year checks Y1-Y4 on every row | a 2027 start date inside a 2026 edition; conference-dates year differing from start year; a past start still Open; a deadline after the start or 18 months before it | Auto | a failing row keeps last week's version (decision list in the import report) | 2026-10-03 (Hydrogen Technology Expo MENA) |
| A8 | The acceptance gate, 23 checks, with the row-by-row rule | wrong format, dead or invented pages, quotes not on the page, past deadlines marked open, placeholders | Auto | `<Market>_audited.candidate.gate.json` | contract |
| A9 | Gate note **S** (substance): rows with no deadline and no quote | a file that is ACCEPTED only because it claims nothing | Auto (advisory) | the gate output | 2026-10-03: six-event delivery passed 22 of 22 with no research |
| A10 | Database health check (invariants) with automatic rollback | missing rows, duplicate ids, keys that moved | Auto | recap | 2026-08-08 |
| A11 | **Load QA** (`scripts/post_load_qa.py`): what the load changed and what it lost | evidence, deadline or link lost on a future deadline; verified turned projected; blank-rate rise; venue words in CITY; start date vs dates text; year checks on shipped files; a start date the load introduced on a projected row with no evidence; approved files signed and fresh; the named-row watch-list | Auto | `runs_out/qa/<Monday>/load.md` and the recap section "Did the load lose anything?" | 2026-10-03 (all found by hand after the load) |
| A12 | Publish guard: approved file signed, accepted, unchanged, fresh | Monday's page built from a hand-edited or stale file | Auto (Monday) | recap "will publish / will NOT publish" | 2026-09 |
| A13 | **Per-step failure count** (`scripts/failure_steps.py`, shown in the load report and the recap): rows that did not ship this week's research, by the step that failed: FIND (dead or composed page), PROVE (quote not on the page), READ (claim wrong or inconsistent), IDENTITY (no permanent id), FORMAT; history in `runs_out/qa/step_failures.jsonl`; a rise of five or more is flagged | Auto | load report, recap, `step_failures.jsonl` | 2026-10-03 (needed to say where a tool change would pay off: FIND 7, PROVE 6, READ 2, IDENTITY 11 on the first load) |
| A14 | **Complete % and Accurate % on the board** (`board_metrics.py split_scores`; tests in `test_board_metrics.py`). COMPLETE = expected fields filled (a pinned honest blank counts) averaged with coverage; call fields (deadline, link, evidence) are excused while the event starts more than 90 days ahead and no call is open. ACCURATE = proven / (proven + contradicted) over stated facts (deadline vs page, year vs edition, pins, customer dates, spot checks); unproven is shown, never counted wrong; a contradiction is never excused by the 90 days. Passed events and deadlines are not scored | Auto | board, `status.json` quality.split | 2026-10-03 (operator rule: no evidence is expected for a far-off event) |
| A15 | **Provable and customer-agreement metrics, refined** (`board_metrics.py`): a deadline you pinned counts as proven (a person read it); an event more than 90 days off with no firm call is excused from the proof figure; a customer row that holds another edition (more than 180 days apart) or an earlier round (their date passed, ours ahead) is reported beside the agreement figure, not as a different date; our blank on an event more than 90 days off is excused. Excused and other-edition counts are always shown, never hidden | Auto | board, `board_metrics.py` output | 2026-10-03 |
| A16 | **Old six-component weighted index RETIRED 2026-10-03** (proof, no_error, alignment, freshness, coverage, other; weights were a judgment and two pairs counted the same check twice). Replaced by Complete % and Accurate % (A14). Freshness of the last run and the share of research calls that grounded stay on the board as process health, never scored | Auto | board | 2026-10-03 |
| A17 | **Shadow run of the real-URL finder, every Saturday, read-only** (`scripts/shadow_finder.py`, last step of `run_monthly.ps1`): for each live row, pages found from the site's own sitemap/menu and read by a cheap model, deadline accepted only with a verbatim quote on the page; compared with what we ship; the disagreements emailed. Time-boxed (120 min, 0.60 USD, 4.25 h since the job started; about 2.7 min per event measured), never writes data, never fails the job. Evidence base 2026-10-04: 12 of 14 known deadlines right, 0 wrong, vs 8 of 14 grounded; agreement 7 of 7 right | Auto (changes nothing) | `runs_out/shadow/`, recap email | 2026-10-04 |
| A18 | **Awards refresh plan** (`scripts/refresh_plan.py`, Friday step 3b): dormant Closed awards (next cycle not near) are marked REFRESH_SKIP and not researched; live, date-ahead, opening-within-60-days, new and 56-day-stale awards always are; a quarter of the rest rotate in each week; fuse: skips nothing above 70%. Skipped awards keep their last accepted row (carried over) and are reported, never counted as stale. Estimated saving about $2.60 a week (about 35% of rows) | Auto | `Awards_input.csv` REFRESH_SKIP, load_awards report | 2026-10-04 |
| A19 | **Awards load QA** (`post_load_qa.py --markets Awards`): the Saturday 'did the load lose anything we had proven?' check and the per-step failure count, for awards, in `load_awards.md`; the Friday recap carries its flags | Auto | `runs_out/qa/<Monday>/load_awards.md`, Friday recap | 2026-10-04 |
| A20 | **Awards grace in Complete %** (`board_metrics.py expected_fields`): a Closed award with no new cycle announced, and an award whose research says the dates are Not Announced, Invitation Only or Rolling Form, is not expected to carry a deadline or its evidence. Awards Complete 68% -> 77% on 2026-10-04; what is left is real (12 missing submission links, 6 missing main pages, 4 deadlines) | Auto | board | 2026-10-04 |

## B. Sunday, Monday and the board (automatic)

| # | Check | Mode | Report |
|---|---|---|---|
| B1 | Weekly verify: every cited page re-read, dead links confirmed in a real browser | Auto Sunday | Sunday recap and digest |
| B2 | Build QA: what the customer pages show against last week's | Auto Monday | `runs_out/qa/<Monday>/build.md`; "INTERNAL - Build QA" next to the pages |
| B3 | Board metrics: live-deadline proof, customer agreement, coverage, freshness; per-kind quality index | Manual: `python scripts/board_metrics.py --examples 0 --update-status` | the status board |

## C. When something arrives or you change something (manual procedures: runbook section 7)

| # | Moment | Command | What it answers | Born from |
|---|---|---|---|---|
| C1 | A delivery arrives from upstream | `python scripts/check_delivery_ids.py <csv> --market <Market>` | do their ids exist HERE, and is each event on the input list? A sparse patch cannot apply on an unknown id (5.4) | three false "it is in the file" claims, 2026-10-02/03 |
| C2 | Same | `python scripts/accept_delivery.py <csv>` (network) and read note S | ACCEPTED is not the same as researched | 2026-10-03 |
| C3 | A cited page is walled or script-built | read it in the built-in browser (or the page library) and record the verbatim sentence | the plain fetch cannot see it | Black Hat Asia, OWASP BASC, AI Con USA |
| C4 | Two dates disagree for one event | `python scripts/start_date_arbiter.py <csv>` (reads the event's own pages, year-specific), then a person reads the unproven ones | which is right; never a guess | 66 start-date conflicts, 2026-10-03 |
| C5 | Before loading a changed process or file | rehearse: `weekend_import.py --markets ... --sandbox <ABSOLUTE dir>`, then `post_load_qa.py --db <sandbox>\cfp_monitor.db --markets-dir <sandbox> --previous-db <live backup>` | what the load would change and lose, with the same checks as production, and nothing live touched | 2026-10-03 rehearsals |
| C6 | Replaying a past situation against a new rule | copy the research files and the OLD approved file into a scratch markets dir, run the sandbox with `--markets-dir` | does the rule fix the case it was written for | evidence-carry replay |
| C7 | Any hand edit of `Markets\*_audited.final.csv` | re-gate with the network, then `promote_delivery.py` (re-signs it) | otherwise Monday's page refuses to publish | 2026-10-03 recap dry run |
| C8 | An operator ruling (you verified a page by hand) | edit BOTH `Utility_audited.csv`/`Cybersecurity_audited.csv` and the `*_input.csv` row, backups first, log it in `OPERATOR-EDITS-LOG.md` (template: `experiments/purpose_audit/operator_rulings_20261003.py`) | otherwise next Saturday copies the wrong value back from the input list | 5 Utility rows |
| C9 | Re-verifying only some rows | `verify_grounding.py --market <M> --seed-csv <seed of just those rows> --apply`; `--apply` alone is now refused | a whole-database rewrite by accident | 2026-10-03 |
| C10 | The importer will not blank a start date | clear it by one guarded UPDATE and log it (or pin the blank: C14) | Future Fuels MENA kept a stale date; a page that states nothing must be able to clear one | 2026-10-03 |
| C11 | After ANY load, by hand or scheduled | `check_invariants.py`, `watchlist_check.py --previous-db <backup>`, a second-process read-back | corrections still hold | 2026-10-01 |
| C12 | Before sending a recap by hand | `weekend_recap.py ... --dry-run` and read it | wording that does not match what happened | 2026-10-03 ("loaded automatically" after a by-hand load) |
| C13 | The weekend job looks hung or did not load | `Get-ScheduledTaskInfo`; read `Markets\logs\run_monthly_<stamp>.log`; run the import by hand (runbook section 7) | the 2026-10-03 load step that never ran | 2026-10-03 |
| C14 | **You verified a fact on the event's own page** (a date, a city, a link, 'the page states nothing') | Add a pin to `docs/operations/pinned_rows.json` with the pages you checked (`links`), the date and a one-line why; do not edit files by hand. The weekly load applies it before the gate, clears the database for a blank, and the board's "Verified by you" panel lists it. | You are never asked about the same fact twice and the research cannot override it. | 2026-10-03: nine verified events |
| C15 | A page the plain fetch cannot read (empty text, or text with no dates) | `src/cfp_monitor/render_text.render_text(url)` renders it in the real Chrome; the read-the-page experiment does this automatically when `looks_dateless` | a script-built page printed no dates to the plain reader | 2026-10-03 |

## D. Standing principles the checks enforce

1. A blank answer never replaces a verified one (A4, A5, A6, A11).
2. A year is part of an identity: no check, carry or match crosses editions (A4, A7, C4).
3. "Accepted" means the claims checked out, not that research happened (A9, C2).
4. A claim about our own files is checked on disk (C1).
5. A hand edit is re-signed and logged, never left as a silent difference (C7, C8).
6. A change is rehearsed on a copy with the production checks before it touches the live database (C5, C6).
7. We read, they format (UPSTREAM-QA-PROTOCOL.md).
8. **Verify once, then learn.** A person's verification is entered ONCE (C14) and then does four jobs: it is a pin (the weekly run cannot override it), a line in the answer key (every method is scored on it), a row on the board's "Verified by you" panel (so it is not asked again), and, when it exposed a way the research goes wrong, a trap case and a rule or check. See section F.

## E. Known gaps (measured or suspected, not yet closed)

| Gap | Evidence | Next step |
|---|---|---|
| Non-deadline facts (city, venue, format, organizer) are only spot-checked | 3 of 7 upstream events carried a wrong city, venue or date (`docs/design/field_spotchecks.json`) | extend the arbiter's page-proof to venue and format |
| Sponsorship "Yes" has a link but never a quote | about 90% Yes, 0 quotes, in both weekly files | sponsorship option B and a quote requirement (contract question for upstream) |
| The narrow prompt may state a start date for an edition no page states | no confirmed case yet (ODSC East 2027 looked like one and was NOT: its page header states May 10-12th, 2027) | A11 lists any start date the load introduces on a projected row with no evidence page, for a person to confirm; a prompt rule is the real fix if a real case appears |
| Research can return a different, evidenced deadline for a row we corrected by hand (CODASPY abstract vs paper, Apres-Cyber) | 2026-10-03 | a per-row "operator-pinned" list the carry rule honours |
| Rows loaded by hand into the database but missing from the approved file get no carry the first Saturday | RSA/Black Hat Asia on 2026-10-03 | add hand-loaded rows to the approved file at load time |
| `run_monthly.ps1` has only static tests | the flattened-array bug | a PowerShell dry-run mode that exercises the post-research steps |

## F. The learning loop: how manual verifications turn into rules (so they are needed less and less)

Every manual verification is a one-time cost and also a lesson. The loop, in order, for each one:

1. **Pin it** (C14). Immediate: the fact holds, the board shows it, nobody re-verifies it.
2. **Put it in the answer key** (`docs/qa/answer-key.csv`, with who confirmed it and when). It becomes a test every future method is scored on.
3. **Ask what went wrong** and name the failure mode in one line: a wrong-edition page, a venue read as a city, an aggregator that does not list the event, two deadlines on one page, an input list that is stale.
4. **Make it a trap case** (`docs/qa/trap-cases.json`) with the page text we saw, the wrong answer and the right one.
5. **Turn it into a rule or a check** where the failure can be detected by code: a year check, a carry rule, a gate note, a load-QA flag, a prompt rule. Today's examples: the wrong-year start date became checks Y1-Y4; an introduced start date with no evidence page became a load-QA flag (a flag is for a person to confirm, not proof the date is wrong: ODSC's was right); the empty delivery became gate note S; the stale dates text became an overlay rule.
6. **Record what is still a gap** (section E) until a rule closes it, and measure whether the rule worked on the next run.

What a pin cannot do: it holds one edition. When next year's edition appears it is a NEW row with no pin, and the research must get it right or a person verifies once more. The point of steps 3-5 is that the
research gets it right more often every month, so that second verification is rare. Track the share of events that needed a manual verification each month on the board; it should fall.
