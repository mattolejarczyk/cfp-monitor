# Awards - build plan and findings

Awards is the second module after conferences (Nicolia, 2026-09-02 call, 51:14):
conferences -> **awards** -> pod pitch -> SEO/backlinking. It reuses the conference
infrastructure; what differs is recorded here.

Customer sheets, live (export via `/export?format=csv&gid=`, never gviz):

| Sheet | Rows | Market |
|---|---|---|
| Arnica Awards 2026 | 64 | Cybersecurity |
| Utility Global Award List 2026 | 71 | Utility |

## The premise

**135 rows, 2 live deadlines** (both Cyber Defense Magazine, 2026-09-18). Everything
else is past, blank or free text. So this is a DISCOVERY job, not a verification job:
re-verifying the other 133 mostly returns "closed", which is accurate and nearly
worthless to the client. The existing rows are a known-name set that tells discovery
what we already carry so it hunts the unannounced 2027 cycles instead.

## Stages

| # | Stage | State |
|---|---|---|
| 1 | Plan | done 2026-09-03 |
| 2 | Seed list | done 2026-09-03 - `Markets/Awards_seed_20260903.csv` |
| 3 | Schema + gate + row context | row context and DUP_OF done; schema awaits the v1.8 amendment |
| 4 | Discovery run | not started |
| 5 | Gate + reconcile | not started |
| 6 | Customer deliverable (awards page, separate from conferences) | not started |
| 7 | Automate onto the scheduled cadence | not started |

Running beside all of it: the two 2026-09-18 deadlines are a hand-check this week.
They expire regardless of when the pipeline lands.

## Stage 2 outcome

`scripts/build_awards_seed.py` -> 135 rows, 28 columns, no BOM, generator-readable
(`run_market_audit.py --dry-run` recognises all 135). **127 to research** once
`DUP_OF` is honoured.

Customer layer carried through and verified: 675 field values checked against both
source sheets, 0 mismatches. 57 Verified, 6 with PRIORITY, 25 with STATUS.

**The seed speaks the generator's dialect, not the sheets'.** `run_market_audit.py`
line 608 derives `EVENT_ID` from `record.get('CONFERENCE', '')`, so an `AWARD`-keyed
seed yields empty ids with no error. Hence `CONFERENCE` column names plus
`OPPORTUNITY_TYPE = Awards`. Stage 3 introduces a real name-col, once, with a test.

## What the sheets actually contain

**The two sheets have diverged from each other.** Same 15 columns, two conventions:

| | Arnica | Utility Global |
|---|---|---|
| Customer status column | `STATUS` | `SUBMISSION STATUS` |
| `LOCATION` | 37/64 | 0/71 |
| `EVENT DATE` | 33/64 | 0/71 |
| `COORDINATOR CONTACT` | 39/64 | 0/71 |

A script keyed on one status name reads the other sheet as entirely blank - the
`CONFERENCE ` trailing-space class of bug that `customer-sheet-matching.md` warns
produces a confident, entirely wrong 0%.

**`customer-sheet-matching.md` lines 167-179 are now stale.** They record (checked
2026-08-13) that awards sheets carry no `LOCATION`. Still true for Utility Global,
no longer true for Arnica.

**`CATEGORIES` holds a URL on 24 of 71 Utility Global rows, 12 of them exactly equal
to `SUBMISSION URL`. Arnica: 0 of 64.** That equality is the tell: residual text from
copy/pasting column J across. It is not weak category data, it is not category data.
The seed blanks it and keeps the original in `SEED_DISCARDED`. On 18 of those 24,
`ANNOUNCEMENT` is not date-shaped either, so the displacement runs a column further;
those are flagged, never relocated - moving values across columns on our own
inference is the guess 2.5 says to decline. Usable `CATEGORIES`: 102 of 135.

**Eight duplicate name pairs in Utility Global.** Six identical across every compared
field, two differing. Labelled `DUP_OF`, never merged - collapsing them resolves a
disagreement that belongs to the customer (2.1: a label, never a deletion).

**Award operators are leverage conferences do not have.** 100 distinct operators, 22
running more than one programme: globeeawards.com x5, cyberdefenseawards.com x5,
fastcompany.com x4, rsaconference.com x3. One crawl of an operator can yield several
award records, including ones we do not carry.

## Stage 3 - the work

State as of 2026-09-03:

| item | state |
|---|---|
| 1. Row context in the grounding prompt | **done**, guarded by `Markets/test_grounding_context.py` |
| 4. Honour `DUP_OF` | **done**, guarded by `Markets/test_dup_skip.py` |
| 2/3. Window columns + gate | **drafted**, blocked on the v1.8 amendment being agreed |
| 5. `AWARD` / `CONFERENCE` rename | deferred as debt - the seed works without it |

The amendment is `handoff-files/Contract_v1.8_Amendment_Awards_Window.md`. It proposes
`SUBMISSION_OPENS` and `ANNOUNCEMENT_DATE` (43 -> 45 columns) plus rule R24, and notes
that **`ORGANIZER` from v1.5 already carries the operating body**, so the operator needs
no new column. Not sent - Matt reviews and sends.

While drafting it, a fix fell out: the final check in `Markets/test_preserve_guard.py`
was malformed and could not fail. It read only the FIRST assignment in the guard, asked
whether "DEADLINE" appeared in "DEADLINE_EVIDENCE_URL" - always true - and printed the
answer instead of asserting it. It printed False on every run for a guard that was
correct. It now collects every assignment target and asserts the deadline is not among
them.

### 1. Row context in the grounding prompt (highest value)

`build_grounding_prompt` in `run_market_audit.py` passes **five** fields:

    CONFERENCE, CONFERENCE URL, LOCATION, PRIORITY, NOTES

It never passes `SUBMISSION URL`, `SUBMISSION DEADLINE`, `SUBMISSION DATE VERIFIED`,
`OVERVIEW`, `CATEGORIES`, `ANNOUNCEMENT`, `STATUS`, `EDITION` or `OPERATOR` - most of
what the row already knows.

Two consequences:

- **It re-derives from scratch what we already hold**, and we then compare its answer
  to a baseline it was never shown. `CATEGORIES == SUBMISSION URL` is trivially
  visible with row context and structurally invisible without it.
- **A generator that never sees the baseline submission URL cannot know it is
  overwriting a repaired one.** Same shape as the regeneration problem
  `preserve_repaired_citation` was built to catch on the conference side: the guard
  sits downstream because the generator is blind upstream. **Hypothesis worth testing,
  not yet a conclusion.**

This changes what every future row costs and how often it churns, on both modules.

### 2. Awards-specific schema

- **`SUBMISSION_OPENS`** - the window. Nicolia, 19:50: *"some of these might only be
  open and available for like a month... if you didn't know about it, you don't get to
  even enter."* A conference has a deadline to count down to; an award has a window,
  and catching it open is the product. R5 currently gives `Awards` rows a single
  submission deadline, which cannot express "opens March 11".
- **`ANNOUNCEMENT`** - when winners are named. The PR moment the client plans around.
  Conferences have no equivalent.
- **`OPERATOR`** - already in the seed; earns its place per the leverage above.
- **Pay-to-play screening.** Nicolia's own February research doc treats it as a
  first-order filter ("requires a high registration fee, unclear judges, vague
  criteria - treat it as marketing spend, not a credibility asset") but it reached
  neither spreadsheet. **Open question for the customer:** column, note, or an
  exclusion rule at ingest. Do not invent one.

### 3. Gate and contract

Changing the schema changes the gate: `EXPECTED_COLS` in `accept_delivery.py` moves in
the same change, and the contract is amended. `OPPORTUNITY_TYPE` is already
contract R5, so awards rows are not new to the gate - the window fields are.

### 4. Honour `DUP_OF`

The generator would currently research all 135. Pre-filter the seed, or teach the
generator the column.

### 5. The `AWARD` / `CONFERENCE` rename

Once, with a test, so the seed can stop speaking the generator's dialect.
