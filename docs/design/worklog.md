# cfp-monitor — Worklog (running memory)

Append-only log of what changed each work session. Newest first. Keep entries short and factual
(what + why); the current-state snapshot lives in `roadmap-status.md`, deep design notes elsewhere.

---

## 2026-09-14 - awards verified for the first time, 18 duplicate rows merged out, contract to v2.5

**The question that started it** (operator): how could the customer files have gone out with the
awards verification step missed - was it done and not logged? Neither. **The step did not exist.**
`audit_evidence.py` and `export_checks.py` read the `evidence` table joined to `grounding_facts`,
the CONFERENCES table, and every writer of `verify_state` in the repo targets that same table.
`check_award_deadlines.py` was written as the awards sibling on 2026-09-08 and wired to nothing.

Worse than the gap: `weekly_deliverable.py` passed the CONFERENCE checks CSV to the awards page.
Zero of its 162 rows are awards, so the page built with `NO_EVIDENCE=false` and shipped reading
**"0 Deadline confirmed - we read it on their page"**. An omission rendered as a result - the exact
failure `build_review_page.py`'s `--no-evidence` guard exists to prevent. A CSV matching no rows
walks straight around that guard, and **run health reported HEALTHY because every step it knew
about succeeded. Health counts steps that ran, not steps that should have existed.**

First awards pass: 100 cited deadlines over 95 pages - 41 verified, 53 no_quote, 6 unreadable, 19
with no cited page. All 53 no_quote have deadlines already past, which is award pages rolling to
the next cycle rather than bad data. Of the 19 rows whose deadline is still ahead, 16 are
confirmed. `--apply` writes the verdicts; `unreadable` is deliberately NOT recorded as a verdict -
it says we could not open the page, which is about us, not the date.

**Asked whether the corrected page was worth re-sending: no, and it was checked rather than
assumed.** Only `chk`, `chku`, `chkq` differ, and all 41 "what we found" quotes are already the
quote the page was showing. The pass confirmed sentences the customer could already read and
discovered none.

**Duplicates: 21 groups, not the 9 previously recorded** - the old number came from a stricter
detector. Two corrections to what had been written down: the earlier claim that the customer could
see both copies was WRONG (both pages are one row per event, 112 of 112 and 127 of 127 distinct),
and this is database hygiene, not a delivery defect.

`find_duplicate_events.py` classifies by WHICH key component moved, because the causes want
different fixes: SAME_TODAY (both rows mint the same key today and differ only in the key each was
born with - `fix_edition.py`'s frozen `key_year` working as designed, and the strongest evidence of
one event), PLACE, NON_OPPORTUNITY, OPPORTUNITY, YEAR, MIXED. CONFLICT is reported separately
because it is the only part that can reach a customer. Exactly one group had disagreeing deadlines
and **it was not an error**: the Nineteenth International Conference on Climate Change runs two
submission rounds off one page, Regular to 2026-10-19 and Late to 2026-12-20, both verified. The
schema has no column saying which round a deadline belongs to. The customer page carried the
regular date, which is the safer one.

18 rows merged out, 419 -> 401, across three batches (7 SAME_TODAY, 5 PLACE, 6 NON_OPPORTUNITY).
All 111 client links intact, none orphaned, invariants green. No event lost coverage: the five
name strings that disappeared are alternate spellings of rows that survive.

**Every merge rule came from drafting and reading the output, not from reasoning about it first.**
The survivor is the row the CUSTOMER is joined to, never the freshest - 6 of 7 SAME_TODAY links
pointed at the older row, and keep-newest would have orphaned ACT Expo (Drafting Abstract, Urgent)
and World Future Energy Summit (Submitted). The citation moves as a unit or not at all. R1 outranks
that atomicity: a citation edit never blanks the deadline. The event's own name breaks a city tie
(St. Louis vs Clayton, the venue's town - invariant 3 cannot catch it because Clayton is a real
place). And under v2.5 a retired Registration row never survives - the Gartner IAM draft kept the
registration row and deleted the SPEAKING row, taking its speakers URL with it.

**The merge was not finished until the seeds were repointed, and `check_invariants.py` said so
within a minute.** It failed on "no delivered row is missing" naming all 7 deleted keys, because
`identity.seed_map` reads `EVENT_ID_CANON` straight out of `market_sheets/*_seed.csv`. The next
import would have recreated every duplicate, every Saturday, for ever. 27 seed rows over 6 files
repointed, each file backed up.

**Contract Amendment v2.5** requested and accepted in full the same day, numbered by upstream.
`OPPORTUNITY_TYPE` is restricted to `Speaking`, `Awards`, `Exhibiting`; `Registration` is retired.
The argument was one measurement - 17 suffixed rows, zero submission deadlines - plus the concrete
harm: SIEW's registration row quotes "Registration is now open for the 19th Singapore International
Energy Week", and the merge would have carried it onto the SPEAKING row as its deadline quote with
STATUS Open. That is the CES 2027 false contradiction retracted in round 3, reproduced exactly.
Submission fields can no longer travel off a row minted under an attending label.

**ACT Expo checked against the live page** while resolving a customer contradiction: the call IS
closed ("The 2027 Call for Speakers is now closed"), submitters hear back before end of December
2026, and questions go to speakers@trccompanies.com. Notable that the row asserting "Closed" had a
blank quote and blank evidence URL - it was derived from a passed date, not read. The customer page
already showed Closed, so nothing needed sending.

**Still open:** `docs/operations/pipeline-contract.md` is STILL VERSION 1.1 (2026-08-01) while the
contract in force is v2.0.1 plus amendments through v2.5 - and the `cfp-protocol` skill sends every
new session to read it as "the why". That file's own opening rule forbids exactly this divergence.
`weekly_deliverable.py` has never run and no customer page has been built from a 401-row database;
its first scheduled fire is Mon 2026-09-21 07:00.

---

## 2026-09-13 - the loop meets live services: grounding proven, run health built, links unsolved

**Quality by design became a requirement** (operator): a run must count and log its own failures
and say HEALTHY or DEGRADED, instead of failures being found afterwards. Every failure below was
found afterwards, which is why.

### Fail points, in the order they bit

Gemini answer step (`Markets/answer_findings.py`), 17 calls, no usable answer:
1. **Ours** - `flatten_json_lists()` ran on the reply and turned the `answers` array into a string;
   the paid answer was lost in the crash.
2. **Ours** - no request timeout: one call hung 77 minutes. `run_market_audit.py` had `--timeout 90`
   all along; it was not copied.
3. **Ours** - `--max-requests` capped rows while each row retried 3 times: 3 calls approved, 9 made.
4. **Theirs** - 504 DEADLINE_EXCEEDED on most calls, on gemini-3.5-flash and gemini-3-flash-preview,
   for whole rows and single questions alike. The 2026-09-12 Saturday log has 66 of the same.
5. Answers that did arrive were plausible, composed, dead URLs; one quote was not on its page; one
   proposed changing six fields including STATUS when asked for one link.
6. **Diagnostic** - with JSON mode on, grounding ran (8 searches, 4 sources). Sources are recorded per
   domain and supported only the dates; the URL path was the model's own. Quotes come from Google's
   rendering, not the page's characters. Grounding is good for facts and structurally bad for exact
   URLs and verbatim quotes - which also explains the week's quote rounds.

Verification holes (closed unless stated):
7. A plain-fetch 403 hid real 404s; every tool browser-checked only 404/410, so Twin Cities shipped a
   dead link. Now 403 goes to a browser in recheck_dead_links and mechanical_repairs. **The gate's
   check 2 still does not.**
8. A 403 replacement link that was a soft 404 was accepted; all replacement links now browser-checked.
9. SUMMARY.md truncated a failing proposal's verdict; the verdict now leads.

Crawl link-finder (`find_replacement_links`):
10. The page-reading LLM (openrouter/deepseek/deepseek-chat, provider StreamLake) returned 429
    "rate-limited upstream" on nearly every page. Errors were swallowed and 11 sites reported "nothing
    found"; found by reading 112 suppressed banners. Not our quota - paid key, no OpenRouter cap on
    paid models; shared provider capacity. The fallback provider was degraded too. Credits ~$18.
11. **Ours** - links checked and fine became replacement questions: 9 of 14 crawls wasted.
12. **Ours** - a crawl answer was applied to VENUE_EVIDENCE_URL; the crawler only finds submission pages.
13. `classify()` trusted a `#become-a-speaker` fragment on a listing page.
14. **Health gap** - a site with 0 pages read still said "No live page found".
Rerun with retries and health: HEALTHY, 22/22 reads, 0 usable links - SecureWorld's real form sits on
another host behind a HubSpot CTA, and the crawl finds the CTA (-> Contact Us) and form-post endpoints.

Also found: 9 real duplicate event pairs from key drift (CITY changed or blank, EDITION year changed).

### Built
`src/cfp_monitor/run_health.py`; retries in `extraction.py`; health through `pipeline.py`,
`find_replacement_links.py` and `delivery_loop.py` (health first in SUMMARY.md, `health.json`, exit 2
when DEGRADED); `rules.NEEDS_BROWSER_STATUS`; `--links-via crawl|gemini`; Markets `grounding_summary`,
`CallHealth` and "RUN HEALTH" lines. Tests: test_run_health.py, test_delivery_loop.py additions,
Markets test_call_health.py and test_grounding_metadata.py. Full suite 1012 passed.

Friction worth remembering: bash heredocs turned `\\n` into real newlines and broke Python patch
scripts four times; direct edits were reliable.

---

## 2026-09-12 - both live markets in, and the hand-back loop taught to close itself

**Cybersecurity and Utility ACCEPTED, imported, reconciled.** Seven hand-back documents crossed
with upstream to get there, carried by copy and paste. Two of them unwound our own mistakes:
round 4 told upstream `secureworld.io/events` states no deadlines when it has a "Speaker Deadlines"
list above the "Schedule" list (retracted in round 5, citations restored with the page's ISO
strings), and our H2 MEET close-out never compared the row's event dates to the page (gate 6b
caught it). CES 2027 is correctly Closed; round 3's "the page says OPEN" came from a verifier
crawl dated 2026-07-20 and was retracted.

**Known-good snapshot and tags first**, at the operator's request, before any process change.

**Why the rounds kept recurring:** the rules agreed in the chat never reached the run. Upstream
reported three prompt updates; `run_market_audit.py` had not changed since 2026-09-08 and still
said "Verbatim quote or direct sentence". Three steps, each tested:

- `Markets/standing_rules.md` - eleven rules the run reads at import and appends last. Missing file
  stops the run. Plus `flatten_json_lists()`: model arrays had reached three customer rows as
  Python list reprs.
- **Contract v2.4 adopted** and `scripts/mechanical_repairs.py` built on it. Declines on ambiguity
  (date twice on a page, another date in the span, serialised lists, withdrawals that break check 4,
  links upstream changed, R4's bracketed projection form). Replay closed the SecureWorld case the
  gate needed three rounds for. It first overwrote the unrelated `repair_delivery.py`; restored from
  git and renamed.
- `scripts/delivery_loop.py` + `Markets/answer_findings.py` - questions to Gemini as structured
  findings, answers verified against the live page before use, claim changes left for a person.
  Dry-run only so far; the live pilot is next.

Tests: 28 + 13 new here, full suite 974 passed; four new Markets test files, all nine pass.

---

## 2026-09-11 - the weekly research job had been doing nothing, and N5 is closed

**Both scheduled research tasks reported success weekly while auditing zero rows.** Task
Scheduler showed exit 0 on 2026-09-02 and 2026-09-05; their own transcripts said
`Completed : none`. The task ran `powershell.exe -File run_monthly.ps1 -Markets A,B`, and
`-File` does not send arguments through the PowerShell language parser, so `-Markets`
bound one literal string and the run looked for a market input file by that name. Fixed on
both tasks with `-Command "& 'run_monthly.ps1' -Markets A,B"`, verified against the real
script. Changing a registered task needs a genuinely elevated shell.

**So the last productive research run was 2026-08-31, by hand - and its output was never
imported.** The live database's newest import is 2026-08-29, and the delivery holds 8 rows
the database does not. Two different kinds of stale, neither visible from the gate.
Importing that output is the open item.

This Saturday's run (2026-09-12) was deliberately skipped in favour of a manual run: the
weekly trigger's start boundary moved to 2026-09-19, so the cadence resumes with nothing
to re-enable.

**`scripts/fetch_customer_sheet.py` closes N5**, the last manual step in the weekly loop.
It fetches each customer sheet as CSV with a read-only Google service account and hands
the bytes to `snapshot_customer_sheet.py`, which keeps owning the snapshot store. A
service account rather than a browser session on purpose: a session expires and wedges and
waits for a human, which is exactly the failure mode already costing the Skool sync, and
Viewer access makes "we never write their sheet" physical rather than a promise.

It refuses anything that is not really the sheet - an HTML sign-in redirect (200 OK, looks
like success), a wrong gid, an empty export - because a bad file stored today is diffed
next week as though the customer had deleted their list. 401/403/404 get distinct messages,
since "never shared with the service account" and "wrong id" otherwise look identical.
Sheet ids live in `%LOCALAPPDATA%\CFP-Monitor\customer_sheets.json`; this repo is public
and the example config in the file uses placeholder client names.

On branch `feat/fetch-customer-sheet`, not merged. Blocked on the operator creating the
service account and sharing both sheets as Viewer; the script cannot create credentials.

---

## 2026-09-08 - awards ACCEPTED, imported, and a page that finally carries evidence

**Two amendments adopted in one day, and measuring each one changed it.**

`v2.2` gives criterion 2 the passed-deadline exemption v1.4 gave criterion 3. Measured: all 14
dead cited pages belonged to rows `may_withdraw_citation` refuses to touch, so the check was
rejecting a delivery for a condition **neither side had an action for**. A blank deadline is
deliberately NOT exempt - check 3 excuses a blank because nothing is claimed, check 2 does not
because a dead link fails the reader either way. So it went 14 failures to 3, not to zero.

We also corrected a claim already sent upstream: the note said all 14 were passed-deadline
rows. Eleven were. We had read it off `may_withdraw_citation` refusing all 14 without
separating why it refused each.

`v2.3` is the awards `EDITION` anchor ladder. R19.1 anchors to `START DATE` and 68 of 127
awards rows have none, so the rule had no defined behaviour - which produced confident answers
that disagreed with each other. **Running the ladder over the file before proposing it changed
the rule twice**: a mechanical reading would have blanked 41 rows (rung 4 now keeps the
delivered value), and 2 of its 10 moves went BACKWARDS because a stale `ANNOUNCEMENT_DATE`
records a closed cycle (hence rung 2's `>= deadline` guard). Third amendment to hit that same
stale-row failure. **Rung 1 is upstream's and is deliberately not implemented here**, so an
evidenced edition outranks a derived one and disagreements are reported, never applied - which
makes non-retroactivity structural rather than a matter of discipline.

**Upstream's first patch was unusable, and the reason is on the record.** 0 of 9 keys matched;
5 of 6 citations did not survive a fetch. Same signature as the pilot in `extract_citations`'s
header - the URL is non-deterministic while the quote stays stable, because the model knows the
fact and guesses where it lives. The candidate-URL split fixed it. Note for next time: three of
those 404 pages returned 2712, 3430 and 2752 characters, so **a successful fetch is not a
successful citation** and a length check would have passed all three.

**Built:** `apply_row_patch.py` (a blank in a patch is ambiguous, so clears are declared per
row with `--withdraw`), `label_seed_duplicates.py`, `import_awards.py`, `link_check_awards.py`,
`check_award_deadlines.py`, and `rules.award_edition`.

**Three things the work found before they shipped.** `DUP_OF` means two different things - six
labels name a row in the delivery, eight older ones name a coordinate in the customer's sheet -
and treating them alike excluded 7 real rows including one whose citation we had withdrawn by
agreement hours earlier. Reading pages through the crawl4ai ladder instead of
`verify.fetch_text` contradicted the gate on 12 active rows, because the ladder returns
markdown and splices `[label](href)` through the prose; the flat fetch now goes first and the
ladder is a second opinion. And the awards page called awards "conferences" in five places -
tab title, first column, deadline column, legend, plus a badge reading "Golden Bridge Awards
Awards" - because the heading had been given a vocabulary at stage 6 and nothing else had.

**`link_checks` needed no sibling table**: it is keyed by URL, not by event, so it was already
domain-neutral and the conference scoping lived entirely in which rows got harvested.
`award_markets.award_key` is the `event_id`, deliberately unlike `conference_markets`, which
keys by host - cloud-awards.com runs four programmes with four deadlines.

**End state:** gate 23/23 ACCEPTED; 119 rows imported with conferences untouched at 392/391;
171 awards URLs link-checked, 16 dead and 0 false 404s; page showing 43 confirmed deadlines,
10 dead links, 57 needing verification. 944 tests.

**Open:** the awards verify pass (all 119 rows still `unverified`), no `check_invariants` for
the award tables, `Reply_Batch1_ACCEPTED_20260908.md` unsent, and the page reads "0 Opening
soon" - the chip the module exists for, worth confirming rather than assuming.

---

## 2026-09-06 - awards through the gate, and the checks that were wrong

**Stages 5 and 6.** The first awards delivery went through a full networked gate. Of five
failing checks on the first run, **two were our own checks being wrong rather than the data**.

**Criterion 4 matched a bare "active"** with a single negation guard, and fired on rows
reading *"No active 2026 cycle was found"* and *"have not been active since"* - three false
positives from four hits, and never awards-specific: any conference row saying "no active
call" failed the same way. **6b is a conference assumption** - an award's late-entry window
legitimately closes during the ceremony week, quoted verbatim on three rows. Awards exempted.

**We were overwriting the customer's `NOTES`.** Section 3 assigns it to them. Joining through
`identity.to_canonical`: the conference delivery preserved their text on **zero of 96** joined
rows; the awards delivery replaced 65 and deleted 8. Theirs are decision notes ("CISO track is
invite-only"); ours were descriptions of the event.

**And the cause underneath it: `ORGANIZER` was empty on 406 of 406 conference rows since v1.5
created it on 2026-08-14** - the prompt never asked for it, so the organiser went into `NOTES`
instead. 278 of 406 conference notes name an organiser and every one has `ORGANIZER` blank.
**No 46th column**: 68% belongs in `ORGANIZER`, 31% in `LOCATION`, the rest in `STATUS DETAILS`.

**R16 guard in the generator, label only.** R22 acts on a fact; this acts on an inference, so
it moves `STATUS` and never the prose - suppressing a sentence would delete a finding that may
be true for want of a citation. A first attempt made the pattern tighter than the gate's and
missed *"appear to have been discontinued"*; patterns are now asserted identical across repos.

**Citations 14 -> 5.** `extract_citations`, not `trace_quote_to_page` - its own docstring
stopped that: *"Send a paraphrase here and a sound citation is lost."* Vetting compares the
quote AND the call against the row name; comparing only the call would have rejected three
good citations while still catching the row that picked the A.I. Awards three times running.

**Stage 6: `--kind` selects vocabulary and chips, everything else shared.** Awards gain
"Opening soon", "Open now", "Winners announced soon"; lose "Event soon". **A zero must mean
zero** - evidence views now read "not yet checked" rather than 0 when no pass has run.

---

## 2026-09-05 - one contract at last, and a bug at the seam between two repos

**Both sides now run from one text: v2.0.1 plus amendment v2.1**, adopted the same day over
four round trips. The agreement had been spread across nine documents, several of whose own
headers still read DRAFT while their rules were live and gated.

**A parallel session's consolidation (v1.9) was reviewed and rejected before sending.** It
declared the v1.6 amendment "could not be located" and reconstructed R22/R23 from secondary
sources - the file is in this repo at `docs/operations/`. Measured across all eight sources:
**v1.9 dropped 34 numbered sub-rules; the rebuild dropped none.** The costly ones were R22.3
(withdraw an inadmissible citation even past deadline), R23.3 (**every round is recorded** -
the only new obligation R23 places on upstream) and R23.4.

**What closed with upstream:** v1.5 confirmed as agreed; the R18/R19 collision renumbered to
R24/R25, with which set moved decided by grep (every code reference is to sponsorship, none to
identity); the awards window taking **R26** rather than R24 to avoid recreating the collision;
row counts reconciled by running `check_invariants` rather than accepting the explanation; and
a four-week-old R7 breach (AES Convention) retired.

**Our error, found by upstream acting on it:** v2.0 said tiered rounds live "in the row's
notes", carried out of v1.6's wording while contradicting v2.0's own section 3. `NOTES` is the
customer's. Corrected to `STATUS DETAILS` in v2.0.1 before any delivery wrote there.

**Schema 43 -> 45 (R26).** `SUBMISSION_OPENS`, `ANNOUNCEMENT_DATE`. The gate verified the
sponsorship block with `header[-5:]`; the generator placed it at 39-43. Both correct until v2.1
appended two columns, at which point the block stopped being last and the gate would have
rejected a correct delivery. **Nothing compared the two - they live in different repos with no
shared package.** Now checked by position, and `Markets/test_schema_agrees_with_gate.py` is the
comparison.

**`handoff-files/README.md`.** 106 documents, nothing said which were the rules.
`Joint_Pipeline_Contract_for_Upstream.md` - no version, no date, 35 columns, Spec v4.3 - reads
as current to anyone not told otherwise. Every superseded contract now carries a STATUS banner,
because the index only protects a reader who finds the index.

**Repo visibility established rather than assumed:** `cfp-monitor` is public, `cfp-handoff-files`
is private. So the contract cannot be fetched by URL and is still couriered.

---

## 2026-09-03 - awards module started; the architecture claim I made was wrong

**Stages 1-3 of 7 done.** `scripts/build_awards_seed.py` -> `Markets/Awards_seed_20260903.csv`,
135 rows, 127 to research after 8 are labelled `DUP_OF`. Customer layer verified byte-identical
against both source sheets: 675 values, 0 mismatches.

**The premise inverts the obvious approach.** 135 award rows carry TWO live deadlines between
them. Awards is a DISCOVERY job; re-verifying the rest mostly returns "closed", which is
accurate and nearly worthless to the client.

**I claimed the crawl layer was already awards-aware. It is not ours.** That came from grep hits
in `discovery.py`, `extraction.py`, `fetch.py`, `grounding.py`. Reading `audit_conference()`
properly: `run_market_audit.py` imports NOTHING from this repo. Retrieval is one Gemini call per
row with the `google_search` tool - the model searches, we never crawl to discover. The
crawl4ai/playwright/cdp ladder is downstream's and the generator never touches it. **A grep is
not an architecture review; say which one you did.**

**Row context.** `build_grounding_prompt` passed five fields and dropped the baseline
`SUBMISSION URL` and `SUBMISSION DEADLINE`, so the model re-derived what we already held and we
compared its answer to a baseline it had never seen. Rule 0 now labels the prior record
unverified and forbids copying it into any output field. **10-row pilot: zero rows echoed the
baseline without a fresh quote.** It did rename 4 of 10 rows, and `EVENT_ID` derives from the
name - the awards prompt now forbids renaming.

**Awards and conferences ask separate questions, share one engine.** Two rule constants, neither
referencing the other, dispatched on `OPPORTUNITY_TYPE`; a row without it takes the conference
path. Conference prompt captured before the split and byte-identical after (5909/5633/5680).
The engine stays shared because a second copy of the retry and citation machinery is the
parallel-validator failure. `Markets/test_prompt_separation.py` asserts rule 0 is byte-identical
in both prompts. Full reasoning in `docs/design/awards-plan.md`.

**pandas `nan` is truthy, so `(v or '').strip()` guards nothing.** It killed the first pilot on
all ten rows, and a quieter second instance rendered the literal text `nan` into the prompt
without crashing. Both now route through one `cell()` helper. **The test missed it because it
passed a dict of strings while the run passes a Series** - it now drives the real seed through
pandas.

**Awards need their own tables.** `conferences` has no `opportunity_type` column at all, so an
award imported today is indistinguishable from a conference.

**Contract v1.8 drafted** (`handoff-files/`): `SUBMISSION_OPENS` + `ANNOUNCEMENT_DATE`, 43 -> 45,
rule R24. `ORGANIZER` from v1.5 already carries the operating body.

---

## 2026-09-01 - the day's own failure pattern became build-failing tests

**Four gate checks closed; two check-3 rows and the manifest stub section from ACCEPTED.**
Current files: `delivery_v23_check4_43col.csv`, `audit_cybersecurity_utility_43col_r10_20260901.csv`.

**The operator's call, and it was right: repeated mistakes on things already solved.** Three
rules broken today were written down in files read the same day - the gviz export ban, the
EVENT_ID join, and reading the client layer before remediating. The diagnosis: **zero of the
day's errors were caught by documentation.** Several were caught by tests; the rest by the
operator. Docs are read at session start; failures happen four hours later at one specific line.

Four changes, all committed:

- **Guards as tests** (`tests/test_identity_join.py`) - fails the build on a re-parsed seed map,
  the gviz endpoint, writing a customer-owned field, or the client layer going unread. **Found
  six more scripts with their own seed parser on its first run.**
- **`src/cfp_monitor/identity.py`** owns the id boundary. `apply_resolutions._seed_map` is a thin
  delegate, verified byte-identical at 394 entries. `assert_mapped` refuses an empty map, because
  a path fault otherwise yields zero findings that read as agreement.
- **The protocol asks for a citation, not a read** - name the governing decision before writing
  the line, with the four that keep biting tabulated *with* their answers.
- **The docs have a budget** (`tests/test_docs_stay_small.py`) - 21 rules, no line headroom.
  Adding one must answer "can this be a test instead". Rule 17 was converted to pay for it.

**Read the customer's sheet before repairing a row.** 22 of the rows repaired today had already
been verified or acted on by Nicolia's team, and two were about to ship as contradictions - ESF
MENA queued as discontinued while they hold an acceptance and a $12,500 sponsorship decision.
`scripts/customer_context.py` buckets rows LIVE / TRACKED / MOOT / UNTRACKED and the protocol
requires it. The gate ranks by rule; the customer ranks by what they can still act on.

**One root cause behind four defect classes.** A row fixed downstream, regenerated broken by the
next research pass - InfoSec World's citation, all twelve dead links (twelve of twelve back in
the audit, zero in both), SecureWorld's listing dates, five prose rows. **Check 2 closed by a
merge, not research.** A `preserve_repaired_citation` guard is now in the generator, ordered
after the R22 filter so it cannot rescue an inadmissible citation.

**R22 enforced in the gate**, offline, across all three evidence columns - 8 rows on its first
run, 7 of them *passing* the quote check. **R22b added**: a machine endpoint is not a page.
Deliberately a path test, not a host ban - eight legitimate `share.hsforms.com` form pages across
four conferences would have been deleted to catch one endpoint. Advisory offline, failing only
once fetched, because a regex is an inference and a delivery is not rejected on one.

**The customer page now shows lifecycle evidence.** It read neither `LIFECYCLE_QUOTE` nor
`LIFECYCLE_EVIDENCE_URL`, so 13 rows carried discontinuation evidence no customer could see. New
**"Check against your sheet"** view carries 12 disagreements - not called sheet errors, because
we are the wrong side twice and those rows say so.

**Customer snapshots are diffable for the first time** - a second snapshot, byte-identical to
08-30. The gviz endpoint is lossy and banned: it blanked eight sponsorship deadlines including
ESF MENA's $12,500 and the diff read them as customer edits.

**Six client matches promoted by human review, not eleven** - SecureWorld Expo is a series row,
and four others are editions or successors missing from our lists. **Six conferences discovered**
that Arnica marked `Info Needed`; ACCEPTED first run, zero inadmissible citations.

## 2026-08-31 (late) - a listing scrape wearing a deadline, and asking sites for their own index

**Eight SecureWorld rows store a conference date in `SUBMISSION DEADLINE`.** One reads as due
tomorrow. The rows cite `secureworld.io/events`, a listing of conferences and the dates they are
held, and the stored quote is two consecutive listing rows scraped together - the FIRST date
became the deadline, the SECOND became `START DATE`. The second is right; the first is the
previous edition's event date. The events page contains no deadline vocabulary at all. Written
up as `handoff-files/Defect_SecureWorld_Listing_Dates_20260831.md`; the deadline is upstream's
field and R1 never touches a deadline value, so nothing was changed here.

**Found while checking, not while assuming.** Four rows were classified "paraphrase" by the gate
and sent to `extract_citations` - the right tool this time. Two recut cleanly (Climate Change,
Hydrogen Technology Expo NA) and are the only changes we would take. The three SecureWorld
results came back as strings like `'Threat Defense 2026 2026-09-01'`, which are **not on the
page** - composed from our own fields rather than copied. Fetching each page before applying
anything is what caught it. Nothing was applied.

**Why the deadline came from a listing: five guessed CFP URLs, all soft 404s.** Across three
SecureWorld hosts, every candidate call-for-speakers URL returns HTTP 200 with a "page not
found" body, so a status-code check calls them alive. All five have the shape
`sitewalk.FALLBACK_PATHS` invents. The site's own sitemap - named in `robots.txt`, 11,237 URLs -
holds the real page, `www.secureworld.io/speaker-submissions`, which all five near-missed on host
or path. It is a redirect stub with no dates, so **SecureWorld publishes no deadline** and the
honest value is blank.

**`sitewalk` gains sitemap discovery**: `origin`, `sitemaps_from_robots`, `sitemap_candidates`,
`parse_sitemap`. New read-only `scripts/check_urls_against_site.py` answers three questions per
site - is a cited URL one the site publishes or one we invented, does the site publish a call
page we are not using, does the cited page return content or a soft 404. It proposes nothing: a
URL existing is not proof it carries the claim.

**No sitemap step exists anywhere in the joint process** - not in the contract, the runbook or
the tooling index. Proposed to upstream as two process changes: (A) a quote with no deadline
vocabulary is not admissible for `SUBMISSION DEADLINE` unless the cited URL is itself a call
page - this flags exactly the eight SecureWorld rows and nothing else; (B) check candidate URLs
against the site's sitemap before citing them. Discovery is upstream's side, verification ours.

**The new script's own tests caught two defects in it before use.** `relevance()` scores on the
path, so headshots under `/hubfs/speakers/` ranked as call pages until `NOT_A_PAGE` was applied
to sitemap URLs; and a bare length threshold called a genuine three-sentence CFP page a shell,
which would have pushed someone to abandon a sound citation. 805 tests pass.

---

## 2026-08-31 - the rules got teeth, and a nineteen-day-old warning finally reached someone

**Two new contract rules, both from the customer's own queue.** Working the four answerable
"Needs Verification" rows produced amendment v1.6:

- **R23** - `SUBMISSION DEADLINE` is the **next round a person can still act on**. The
  Nineteenth International Conference on Climate Change runs three rounds; the customer held
  19 October (Regular close) and we held 20 December (Late close) and **both were right**. Our
  schema could not express three deadlines. Showing the last implies runway that does not
  exist; showing the first implies the chance is gone.
- **R22** - a **social post or link shortener can never evidence a deadline**. `aggregator.py`
  and `sitewalk.py` have refused to treat those hosts as authoritative since July; nothing
  carried that across to citations. Applied to the delivery it flagged **four** rows, not the
  two the customer noticed.

**Two citations fixed.** DEF CON 34 retargeted from `openssf.org` (a third party writing about
the call) to DEF CON's own page, which carries the sentence verbatim. InfoSec World withdrawn
under R1 - cited to Facebook, and six pages of their own site carry no replacement.

**The decision tree.** `src/cfp_monitor/lifecycle.py`, specified in **`DECISION-TREE.md`**,
answers what follows from where a conference sits in its life: what the customer sees, what WE
do next, what it costs, and why. `edition_states` MOVED there from the page builder, where it
had been correct but invisible to the gate and the weekly job - which is why `STATUS` went on
being read from the file and went stale.

**Status is now derived.** 126 rows disagreed with the file. Only **8** were corrections:
deriving beats storing only where a **date on the row** proves the stored value wrong, never
when reasoning from a blank field, and never when both words are true. Reviewing that list
caught two flaws in my own tree before it shipped.

**The edition fix, nineteen days late.** `check_invariants.py` had printed "run fix_edition.py
(71)" every Sunday since 2026-08-12 - into the log, unread. **67 rows corrected**, every
`event_id` byte-identical (the tool freezes `key_year` and derives only `edition`). The warning
is now 5, all rows with no date to derive from. Two duplicate records existed because a wrong
edition fed `event_id`; their editions are fixed, the duplicate keys are a separate decision.

**Integrity warnings now reach the digest** with an owner and a deadline. Detection was never
the gap - the check was right every week. A warning with no owner is furniture.

**Cadence changed**: re-research moved monthly to weekly, Saturday 02:00, so Sunday's free sweep
sees fresh research. `run_end_to_end.ps1` chains the whole loop; **the gate decides** and stops
the run when a delivery is not ACCEPTED - proven, because it stopped.

**JUDGEMENT gained rules 15-18**, all dated today or yesterday: a number computed before the
thing that gives it meaning; never let a report congratulate you on your own edits; across a
boundary join on the value not the key; brittle parsing fails confidently, not loudly.

754 tests.

---

## 2026-08-30 - the customer's own sheet enters the system

**The weekly digest was reporting our own cleanup as good news.** First scheduled run under the
NEW-vs-STANDING split fired clean, and its headline read "Recovered since last week (19)".
Measured: **4** rows actually verified. Of the other 16, **13 were citations we cleared on
08-29** - a row with no citation has nothing left to contradict, so it drops to not_found
mechanically. Same shape as the gate printing ACCEPTED for skipped checks; second occurrence in
three days. `build_digest` now splits the three cases and `still_cited` has no default.

"Standing backlog 80 -> 32" was likewise not 48 repairs: 49 URLs stopped being referenced when we
cleared their citations. **Zero were fixed.**

**The digest now reads like a report** - every category states what it MEANS, the ACTION, the
OWNER and the TIMEFRAME, with an At-a-glance table. The first draft printed "35 row(s) need
someone to act" above three rows reading "nothing to do now", because actionable was INFERRED
from having an owner. Owned and due-now differ; it is declared per category now. Real answer: 32.

**Canaries generalised to cover reports that lie.** Every entry before today was about data or
rules, implying our reports had never been the problem. 17 canaries now.

**The customer sheet layer.** Two client sheets (Utility Global, Arnica) snapshotted, hashed and
loaded. What they contain that changes the design: `STATUS DETAILS` is a dated field-research
log; **41 rows marked "Needs Verification"** aimed at us; call windows with timezones where we
hold one date; sponsorship hand-typed into the deadline column. **`LOGIN` and `PW` columns
exist** - empty today, but the snapshot rewrites rather than copies so they can never reach a
git repo.

**Layer 2 - the client dimension.** The database had no client concept at all. `conferences`
columns are single-valued and shared, so two cybersecurity clients tracking Black Hat would
overwrite each other. Three additive tables: `clients`, `client_conferences`,
`industry_candidates`. **`conferences.status_details` is 349/373 filled with OUR crawl text** and
looks exactly like the customer's column - importing theirs would have destroyed it.

**Same defect a third time:** first load reported 111 promotion candidates, every row, because
nothing had been matched yet. Candidates now require the matcher to have run and found nothing.

**Matcher applied** - 80 of 111 joined at 100%, 21 need a human, 10 are genuinely absent. Only
certainty sets an `event_id`. The middle band is region and edition variants. My earlier crude
"27 missing" was wrong; the real number is **10**.

**The 31 standing dead links were already sent** - 2026-08-27, unactioned. A regex that did not
exclude backticks first said "0 of 31 sent"; the truth is 31 of 31. The digest still cannot tell
"needs sending" from "sent, awaiting upstream".

**Customer deliverables:** `Conference Review 2026-08-30.html` (406 rows, 29 fields, sponsor and
organizer wired) and `Customer_Facing_Schema_20260830.md` for their UI/UX developer, superseding
the 38-column list in `Backend_Data_Design_20260807.md`. The v1.5 sponsor fields are **empty by
design** and populate on the 2026-09-01 re-research.

---

## 2026-08-29 (evening) - the tracer moved in, and upstream's alignment summary was checked

**The quote tracer is now `scripts/trace_quote_to_page.py`.** One of the six delivery-folder
scripts was a real capability - "find the page that actually carries this quote, or withdraw the
citation honestly". The other five apply a named list of rows to a named file on a particular
day; putting those in `scripts/` would say "run this again", which is false, and is how a tools
directory stops being trusted.

Moving it forced the refactor. It carried its own crawler, so `test_no_reimplemented_crawling.py`
would have rejected it. It now uses `sitewalk.plan` and `rank_links` - **the first entry
`PENDING_MIGRATION` has lost rather than gained** (11 remain). It is the most destructive tool in
the repo, so the safety is not the script being careful: every decision routes through
`rules.may_withdraw_citation`, which refuses when no page could be read and when the deadline has
already passed. Seven tests, two of which read the source: it must call sitewalk rather than
`urljoin`, and must not contain the 35-character prefix match that could attach a citation to
whichever page shared an opening phrase. Smoke-tested on ProMat 2027 from the live queue: 10
pages walked, withdrawn under R1, stamp advanced, dry run wrote nothing. **634 tests green.**

`auto_trace_r3b_high.py` was DELETED from the Markets folder rather than left beside it. A
superseded file in a working folder gets picked up eventually - that is exactly how
`delivery_r3b_traced_43col.csv` nearly shipped with 14 wrong withdrawals. It stays in git history.

**Upstream sent an alignment summary and every falsifiable claim in it was checked against the
files, not agreed to.** All eight hold: 406 x 43; `SOURCE_AS_OF` = 2026-08-29 on exactly 5 rows
with 401 historical (08-03 x20, 08-05 x54, 08-06 x162, 08-07 x165); `delivery_r3b_traced_43col.csv`
absent from disk; check-3 categories 108 / 50 / 28; zero blank-deadline rows still carrying a
citation (230 blanks, 0 cited); `ACCEPTED_COLS = {43}`; v1.4 recorded; R3b retired. Their
inspection-stamp protocol matches `rules.withdrawal_changes(fetched=...)` exactly.

**Two things to correct back.** Their test count (619) predates the evening work (634), and their
summary does not mention `sitewalk.py`, `tests/canaries.py`, the enforcement test, the INCOMPLETE
verdict or the tracer - so they are aligned on data and contract but a day behind on
architecture. Also **108 and 184 are different populations**: 108 is the blank-deadline slice of
the 186 check-3 failures, 184 is the total blank-deadline citations cleared across the whole
file. Nobody should later "reconcile" those and conclude rows went missing.

---

## 2026-08-29 (afternoon) - the acceptance was wrong, and v1.4 came out of finding out why

**Supersedes the entry below, which says the cycle closed accepted.** It did not.

**The acceptance came from a partial gate.** Every run had used `--no-network`, which SKIPS
criteria 2 and 3 - the two that fetch pages - and the gate printed `RESULT: ACCEPTED` anyway. On
a full networked run, check 3 failed on **183** rows. FIXED the same day: the gate now reports
INCOMPLETE, never ACCEPTED, when any check was skipped, and exits non-zero.

**The 183 were then nearly mishandled twice.** First we assumed they were our own blindness,
since `fetch_text` deliberately skips the browser - sampled 10, and 9 were genuine. Then an
automated tracer proposed withdrawing 18 citations; **14 had deadlines that had already passed**,
one by 317 days. A CFP page comes down after its deadline. That output was discarded.

**Measuring instead of estimating changed the whole picture.** All 314 cited rows re-fetched and
classified:

    no deadline claimed at all   108  (58%)   a citation for a claim the row never makes
    deadline already passed       50  (26%)   expected decay
    genuinely live call           28  (15%)   the real work

We had predicted "most of it is staleness". It is 26%. The dominant category was one neither
side had considered - rows carrying a `DEADLINE_QUOTE` that is an event date, a calendar strip
or a site disclaimer, with no deadline to evidence.

**Amendment v1.4** (`docs/operations/Contract_v1.4_Amendment_Citation_Scope.md`) exempts both,
taking check 3 from 186 to 28, and **retires R3b** - of 34 rows it flagged, 14 had their quote
present on the cited homepage, so a hardened shape rule would have rejected working citations.

**Three defects recurred in scripts written hours apart**, which produced the day's real output:
- `src/cfp_monitor/rules.py` - the business rules as pure functions, each returning a reason.
  `withdrawal_changes` takes `fetched` with NO DEFAULT, so a withdrawal cannot skip the
  `SOURCE_AS_OF` decision the way ours did.
- `src/cfp_monitor/sitewalk.py` - one site-walking implementation. There were four, and the same
  three bugs had been fixed in some copies and not others.
- `tests/canaries.py` + `test_no_reimplemented_crawling.py` - one record per real incident, and
  a test that fails the build if a fifth crawler appears.

**Corrections we sent after being wrong:** the "most of it is staleness" prediction; classifying
136 rows as live calls when blank deadlines were being read as "not yet passed"; and withdrawing
four rows without advancing `SOURCE_AS_OF` after rendering 11-14 pages of each site - upstream's
rule was right and ours was not.

Current file: **`delivery_v14_final_43col.csv`**. 622 tests pass.

## 2026-08-29 (morning)
**The v1.5 cycle closed.** `delivery_phase2_remediated_43col.csv` gates ACCEPTED with zero
failures, five days ahead of the 2 September backstop. The entry below was written before this
happened and says the delivery is still rejected - it was, at that moment. This supersedes it.

Getting from rejected to accepted took three things, and only one of them was upstream's:
- Upstream's remediation script fixed check 6 and R11 correctly, and applied the R2 safeguard we
  asked for - no `IS_PROJECTED=false` without a live citation.
- We made three edits rather than round-trip: narrowed the check 4 prose fix from **81 rows to
  7** (the sweep was replacing accurate text with something FALSE for concluded events - "Google
  Cloud Next '26 ... has concluded" became "awaiting official announcement"), added SCOPE Summit
  to the R11 list, and added GreenBiz 27 to the past-deadline list because it is `Fixed
  Deadline`, not rolling.
- **The last blocker was our own gate.** R8c compared `EVENT_ID` globally when section 10
  excludes market from the key precisely so one event stays one record across markets. Fixed to
  key on (EVENT_ID, Market), guarded both ways. That is the check that produced our "merge them
  under R9" advice - retracted the day before, cause fixed now.

Imported and reconciled: 392 rows, no loss, invariants hold, zero rows still citing a dead URL,
`sponsor_required` populated on 391. **`SOURCE_AS_OF` untouched** - every stamp still from the
original July/August passes, nothing stamped with the import date. The discipline held through
upstream's export, our propagation fixes, the remediation and the import.

`ACCEPTED_COLS` dropped to `{43}`; the two transition tests were INVERTED rather than deleted so
the record of why the window existed survives. 595 tests pass.

One correction sent after acceptance: upstream's manifest declared the wrong seven rows as
ungrounded stubs - they used our check 4 list, because our acceptance note asked them to
"declare the 7 ungrounded stub rows" without listing them and that was the only list of seven in
the document. Our ambiguity, their reasonable reading. Reissued with the real seven.

## 2026-08-28
Long CFP day: the weekly digest was root-caused, the dead-link backlog was drained into an
actual correction list, and the v1.5 delivery was pulled forward from 2 September to today.

**Weekly verification digest, root-caused.** The 2026-08-27 run emailed 119 dead submission
links. Every line was TRUE - ten probed independently, all genuine 404s - and the report was
still close to useless. Three defects, all fixed:
- 119 lines described only **80 distinct URLs**, because a URL living in several of the four
  customer-facing fields was emitted once per FIELD. Now keyed by (event, url). 119 -> 82.
- **Zero of the 80 were new**; all were in the 2026-08-16 digest. The digest now leads with
  NEW SINCE LAST RUN and follows with the standing backlog, and only new failures count toward
  the subject-line issue count.
- `link_checks` was `(url primary key, state, checked_at)`, overwritten every run, so it could
  not say whether a link broke this week or had never worked. Added `http_status`, `first_seen`,
  `last_alive`. Answer, once it could be asked: **of 80 dead links, 4 have ever worked. 76 have
  never resolved on any check we have run.**

**Backlog drained into corrections.** `find_replacement_links` over the dead set produced 15
CONFIDENT replacements with evidence and **21 calls confirmed OPEN** - moved pages, not ended
calls. New `find_event_pages.py` chases dead MAIN_INFO_URL / CONFERENCE URL, which the submission
chaser never touched (38 of 82 links).

**v1.5 expedited.** Live build was 12 files stale with the gate hard-coded to `EXPECTED_COLS =
38`, so upstream's 43-column file would have been rejected on arrival. Synced, rehearsed the full
chain on Utility against a DB copy, and added `R19b` - an advisory that fires when 20+ rows share
one `SOURCE_AS_OF`, because with `SPONSOR_REQUIRED` defaulting to Unknown that stamp is the only
thing separating "inspected, nothing found" from "never looked at".

Phase 1 (15 replacements + 2 event pages + 51 R1 withdrawals) and Phase 2 (7 REVIEW verdicts,
4 disputes, 1 org page) applied and gated. Delivery still REJECTED on check 4 (7), check 6 (11),
R11 (7); R8c (12) is our own false positive.

**Four claims went out unverified today and had to be corrected** - three of them ours:
- Told upstream the 12 duplicate `EVENT_ID`s were R9 name-drift and to **merge** them. All 11
  are one event in several markets - same name, distinct markets, zero duplicates inside any
  per-market file, and contract section 10 says market is excluded from the key precisely so
  this works. Merging would have deleted real market memberships. Retracted before they acted.
- Disputed Pittcon 2027's deadline. The page runs **eight** calls; we quoted the Invited Symposia
  one and upstream's `2026-09-28` matches a live call. **Our dispute was wrong.** Withdrawn.
- Claimed the rehearsal covered `SPONSOR_QUOTE` extraction before running that step.
- Reported `mem-save.ps1` missing. `agentos\tools` is HIDDEN; `Test-Path` on the exact path
  would have said so in one line.

**The characteristic failure of this codebase, named:** a value presented as verified when the
check either did not run or measured something else. Today it appeared as the "dead site" label
(wrong for 4 of 5), `link_checks` with no history, the digest that could not tell new from
standing, "no live page found" counting 38 pages nobody searched for, a relative URL that
`link_status` could not verify and therefore passed, and a hand-back naming an attachment
filename frozen three weeks earlier. Six instances, one shape.

## 2026-08-21
- **Multi-edition false positive fixed** (`consolidate.py`). The caution compared raw
  date strings with only `.strip()`, so `AUGUST 10-13, 2026` vs `August 10-13, 2026` -
  a pure case difference - counted as two values, tripped `len(date_vals) >= 2` and put
  a customer-facing "Caution: crawled pages disagree on dates" on rows that agreed. New
  `_date_key()` builds a canonical COMPARISON key (case, dash style, comma/period,
  spacing, month abbreviations - deterministic aliases only). It deliberately does NOT
  parse dates: an uninterpretable string keeps its own key rather than being guessed
  into one, so real disagreements still report. Raw strings are still what gets
  displayed. 4 tests added in both directions (cosmetic variants collapse; genuinely
  different dates and uninterpretable strings still flag). 569 green, golden-derivation
  diff clean.
- **Two stale brief items retired, measured not assumed.** The daily brief had recycled
  three "CFP polish" items since ~2026-07-26 from a v3-era TODO block in the (now frozen)
  cross-project Project Log. Verified against the code: the cosmetic `Submit via :` item
  was already fixed and regression-tested (`test_consolidate.py`); the date-normalize item
  was real and is the fix above. The stretch item ("capture explicit CFP open/close dates
  more aggressively - only Bioprocessing yielded a deadline in the v3 run") is obsolete:
  measured on the live DB, `conferences.cfp_close_date` is populated on 81/373 rows (21.7%)
  and `grounding_facts.deadline` on 168/392 (42.9%), so the v3-era premise no longer holds.
  There is also no `cfp_open_date` COLUMN in `conferences` and no open-date field anywhere
  in the pipeline contract - the customer deliverable does not include one. Not built. Note
  the standing rule: the verified count is reported, never targeted.
- **Why those items kept coming back (fixed upstream of CFP).** They were being mined from
  a v3-era TODO block in the cross-project Project Log, which was frozen 2026-08-20. Root
  cause found in the AgentOS brief engine: its exclusion rules are written with `/` but the
  note paths come from `path.relative()`, which on Windows uses `\` - so the Archive and
  dashboard exclusions had never fired on this machine. Fixed in agentos (`9389bbe`), and
  the three TODO boxes are now ticked with outcomes. Relevance to CFP: a stale doc that
  onboarding is FORCED to read is worse than no doc - the same reason this worklog and
  HANDOFF must stay current (see the 2026-08-21 EOD process change: daily wraps now update
  THIS repo, not a shared cross-project log).

## 2026-08-20
- **Investigator hardened + run across every unconfirmed row.** `investigate_event.py`
  now follows the site's own menu (reads homepage links, follows the promising ones)
  instead of guessing paths (`335b4d6`); `diagnose_silence()` separates domain-gone /
  404 / 403 / JS-shell / our-ladder-failing and retries live sites through a real browser
  (`a2ff286`). Ran over all 24 unconfirmed rows: 11 returned the call OPEN with a verbatim
  quote; 5 corroborate deadlines already held (Pittcon, SEMICON China, ISE, DIA, ALD/ALE).
  3 commits, 565 tests green.
- **Two of my own claims fell over (kept as lessons).** (1) "model-only = 0" does NOT
  prove the regex triage is sound - the model only sees pages the regex already flagged,
  so it measures the regex opinion, not the triage; measuring triage needs an ablation
  nobody has run. (2) The tool labeled 5 sites "DEAD"; direct probing showed 4 of 5 wrong
  (two 403 refusals, two answered a plain request while our ladder came back empty, one
  truly gone). A confident wrong negative is worse than a plain failure.
- **FEW host migration - fixed.** `fuelethanolworkshop.com` 404s at the root; its own
  redirect names the successor `2027-few.bbiconferences.com` (same pageId, host only), so
  every BBI URL can be rewritten mechanically. New citation names the 2027 call and the
  Feb 12 2027 deadline unaided. Per contract section 3 this is upstream's field - a
  correction for the hand-back, not a DB edit. `overrides_20260820_few.csv` is local-only.
- **v1.5 readiness: not ready.** Utility has 0 of 44 rows on all five v1.5 fields (columns
  exist, no wide delivery landed). Upstream's local `run_market_audit.py` is stale (7 Aug,
  36 columns, no v1.5) - a Utility run today would spend ~54 grounded requests to produce
  a file our own gate rejects. No confirmed 43-column delivery date exists on disk.

## 2026-08-17
- **CFP weekly digest email activated** (M6/M7): `CFP_SMTP_*` + `CFP_ALERT_TO` set as
  user-level env vars; a real send verified end to end. Traps: `weekly_verify.py` does NOT
  read a .env file, and user-level `setx` is sufficient (tasks run InteractiveToken).

> Catch-up note (2026-08-21): 2026-08-11 through 2026-08-14 were logged as Obsidian memory
> notes (Agent Inbox) during that stretch and not mirrored here - see those notes for the
> evidence-table / outbound-gate / weekly-discovery / customer-sheet-matching detail. This
> worklog resumes normal per-session updates via the one-step /eod.

## 2026-07-18
- **UI: live crawl progress + non-destructive downloads** (`app.py`, `pipeline.py`). `run_urls`
  gained an optional `on_progress(done,total,current)` callback (best-effort); the Run tab shows
  "Crawling 15 of 51: <site>… · ~ETA left" with the in-flight site name. Results/table/downloads
  now render from `st.session_state` OUTSIDE the Run-button block, so a download no longer reruns
  the page into a blank state. Run tab is explicitly read-only; editing stays in Review & Verify.
- **Competitive review → 3 borrowed, componentized improvements** (commit, 117 tests green):
  1. **TRACK column** (`tracks.py`) — coarse Speaking/Awards/Other, derived purely from the
     `opportunity_types` we already extract; appended LAST in `CUSTOMER_HEADERS` (client's 15-col
     order untouched); read-only in the Review editor. Blank when nothing detected — never guessed.
  2. **Edition stale-trap** (`consolidate.edition_consistency`) — downgrades a shaky Open to Needs
     Review when the deadline belongs to a different/past edition; only ever downgrades, never
     fabricates, fires only on unambiguous years (guards against false flags).
  3. **"Watching this page" status copy** — honest "located the CFP page, not open yet" wording.
  Each is isolated from conference identification. Rival was an independent prototype for the same
  client; its own honest recall was 1 find / 54 sites → **open frontier: measure our recall on the
  same list** (higher value than more features). Shareable write-up published as a Claude Artifact.
- **Industry dimension + run input-audit + Tier-1 review filters** (127 tests). Driven by the PR-firm
  workflow (speaking/awards across industries, worked to deadlines):
  - **Industry**: per-run label in the Run tab, overridden per-row by an optional "Industry" column in
    the upload (`ConferenceResult.industry`, `run_urls(industry=)`, `uploads` header scan). Persisted
    non-tracked in `storage` (migrated; never blanked by a run without one).
  - **Run input-audit** (explains the 54→51): `uploads.normalize_urls_and_contexts_audited` returns a
    manifest {raw/kept/dropped[{url,reason,duplicate_of}]}; stored per run (`runs.input_manifest`,
    `Store.recent_runs`); shown in the Run tab after upload and a Review "Run history + input audit" panel.
  - **Tier-1 filters** in Review & Verify: Industry / Status / Track / Deadline-window / text search,
    applied to the editable sheet (save + CSV download honor the filter). INDUSTRY is a read-only column,
    NOT added to the customer 15-col export. `filtering.parse_deadline` accepts only a full y-m-d (no
    guessing) so a PR user never sees a false "closing soon". `python-dateutil` declared explicitly.
  - Deferred (noted for the user): true per-run historical snapshots ("show the sheet as of run X");
    current model = living master record + change history, so "latest run" == current state.

## 2026-07-09
- **License proxy DEPLOYED LIVE** at https://channeled.org/cfp-proxy (Oracle VPS, nginx→uvicorn:8800,
  PM2). Verified: unknown 401 / active 200 / revoked 403.
- **Reconciliation annotator** shipped (`reconcile.py` + `reconcile_xlsx.py`): annotated .xlsx copy
  of the customer master sheet.
- **Licensing go-live extras:** friendly client license banner; OpenAI+OpenRouter support.
- **Ops:** `scripts/backup_licenses.sh` (weekly cron), `admin billing` (per-customer token/$ readout),
  `installer/install.ps1` (Windows one-shot customer installer, now hardened for clean-machine unknowns).
- **Handoff:** `HANDOFF.md` (single source of truth for Matt + both Hermes), `scripts/vps_setup.sh`.
- **Installer validated on dev + Windows hardening (two real bugs fixed):** (1) `.env` written with a
  UTF-8 BOM dropped `CFP_LLM_PROXY_URL` → installer now writes no-BOM; `config.py` loads via
  `utf-8-sig`. (2) fresh-Python TLS trust store lacked modern roots → the license banner check now
  verifies via certifi (`licensing.py`). Crawling was never affected (litellm/httpx use certifi).
  Installer pins Python 3.11/3.12; literal launcher here-string; `-SkipDeps`/`-ShortcutDir` for
  validation. Proved the packaged build crawls end-to-end through the live proxy (Carbon Capture → PASS).
- **Model/cost reference** added (`docs/design/model-costs.md`): DeepSeek-V3 extraction ~10–30× cheaper
  than GPT-5/Sonnet/Opus for this task; per-conference economics; `PROXY_MODEL` switch; DeepSeek
  `deepseek-chat` name deprecates 2026-07-24 (update `PROXY_MODEL` then). 98 offline tests green.
- **Installer hardened for clean-machine unknowns.** `install.ps1`: graceful message when `winget`
  is absent (points to python.org, "Add to PATH") + re-verifies Python landed after winget; launcher
  `.bat` now prints an explicit friendly note when Google Chrome isn't installed (normal sites still
  crawl; only hard anti-bot needs Chrome) instead of silently no-opping; non-fatal Chrome heads-up at
  install time. Also normalized the whole script to ASCII — stray UTF-8 em-dashes in a no-BOM `.ps1`
  were tripping the PowerShell 5.1 tokenizer. Validated: parses clean, `-SkipDeps` completes, `.env`
  written without a BOM.

## 2026-07-07
- **M5 closed.** Coverage report (`coverage.py`, `scripts/coverage_run.py`): worked/failed % +
  failed links with concise reasons + **resolution-path breakdown** (Core crawl / Browser control /
  Signed-in browser / Unresolved) + which bypass was deployed. Plain-terms labels (no tool names leak).
- **Full editable 15-column customer sheet in the UI** (`app.py` Review tab): edits to crawl-produced
  fields use correction-precedence; human-owned columns save directly; added `NOTES` column (+ migration)
  and `set_fields/correct/set_verified`. Run tab now shows a customer-format table (URL included) + CSV.
- **IP protection.** Stopped an orphaned coverage run that was hammering Reuters' CAPTCHA and flagged the
  home IP. `fetch.py` no longer auto-hits a hard anti-bot domain without CDP (flags "Manual/signed-in").
- **CDP on by default** for live/scheduled runs (`cdp.py` `ensure_cdp()` auto-detects/starts a
  dedicated-profile Chrome on :9222); coverage runner refuses the unsafe path.
- **HubSpot no-name fix.** URL dedupe (drop hsLang/utm_/hs_ params) + `is_crawlable()` skips CTA/asset
  URLs + explore stops at `CFP_EXPLORE_FRACTION`=0.6 + extraction time-boxed to 90% (homepage first).
  industrialnetzero + connectinghydrogen now PASS with names.
- **Source-of-truth guard.** A failed/thin re-crawl can no longer wipe good stored data (skip tracked
  fields on ERROR/BLOCKED; never overwrite non-null with null).
- **Licensing Option D** (`licenseproxy/`): vendor-hosted licensed LLM proxy = kill switch +
  token metering + version-floor/feature gating. Customer build routes extraction through the
  proxy with a license key (no provider key locally); `admin revoke <key>` stops their crawling.
  Pure-stdlib `policy.py` enforcement core; `server.py` (FastAPI) shell; `admin.py` CLI.
- **Reconciliation annotator** (`reconcile.py` + `reconcile_xlsx.py`, openpyxl): writes an
  annotated copy of the customer's master .xlsx — changed cells highlighted + commented (our
  value + source + last-checked) + a summary tab. Taxonomy: Confirmed / Changed / Gap-filled /
  Unverified / Not-crawled. Date columns compared by (year, month); STATUS not diffed.
- **Licensing go-live:** friendly client license check (`licensing.py` → `/v1/license`) wired
  into the app (banner + Run disabled when inactive); proxy + client now support **both OpenAI and
  OpenRouter** (`provider_key()` / `PROXY_MODEL` by prefix); `.env.example` for client + proxy;
  `scripts/run_proxy.bat`. Proved live over real HTTP: active key → 200, `revoke` → 403 (kill
  switch), plus a TestClient proof of allow→forward→meter with the provider mocked.
- 97 offline tests green; all pushed to `main`.

## 2026-07-06
- **JS-shell recovery**: fast consent presence-check + bounded fallback render (cybertech PARTIAL→PASS).
- **Aggregator/org navigation** (`aggregator.py`): use spreadsheet row context (name/location/dates) to
  hop from a directory/org page to the specific event once, before spending LLM budget.
- **LOCATION + START DATE captured from the customer xlsx** (`GoldRecord.context()`, `load_inputs()`),
  threaded via `run_urls(contexts=)` so navigation runs on the real lists.
