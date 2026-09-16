# cfp-monitor — Handoff & Single Source of Truth

**Body last fully revised 2026-08-01.** The running session log through 2026-08-28 lives in
[`docs/design/worklog.md`](docs/design/worklog.md) - read it for the latest state until these
sections are refreshed in a verified session.

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
