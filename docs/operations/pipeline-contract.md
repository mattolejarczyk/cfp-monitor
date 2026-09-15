# Joint Pipeline Contract - the operative text

    STATUS:        CURRENT
    BASE:          Consolidated v2.0.1, adopted by both sides 2026-09-05
    IN FORCE:      v2.0.1 plus amendments v2.1, v2.2, v2.3, v2.4, v2.5
    LAST AMENDED:  2026-09-14 (v2.5)

**Read this file plus the five amendment files beside it. Together they are the rules.**

## Why this header exists

Until 2026-09-15 this file held **Version 1.1, dated 2026-08-01**, while the contract actually
in force was v2.0.1 plus five amendments. Six weeks and five adopted amendments out of date,
and the `cfp-protocol` skill sends every new session here to read it as "the why". A session
following the documented procedure got rules that had been superseded.

The file's own opening rule is what makes that worse rather than merely untidy: *"One text,
both sides. This file is versioned in the downstream git repo and sent whole after any change.
Replace any earlier copy with it verbatim rather than merging - two divergent copies of a joint
document is the exact failure this contract exists to prevent."* We had exactly that
divergence, and this repo held the older half.

## The amendments in force, newest first

| Amendment | What it changes | Adopted |
|---|---|---|
| [v2.5](Contract_v2.5_Amendment_Opportunity_Type_Narrowing_20260914.md) | `OPPORTUNITY_TYPE` restricted to actionable submission opportunities - `Speaking` (default, unsuffixed), `Awards`, `Exhibiting`. **`Registration` is retired.** Booth closing dates supplied with citations where published, blank where the site is silent. | 2026-09-14 |
| [v2.4](Contract_v2.4_Amendment_Downstream_Mechanical_Repairs_20260912.md) | Downstream may repair how a claim is WRITTEN, never what it claims: (A) re-copy a quote from the already-cited page, (B) carry a replacement URL to every field holding the identical dead link, (C) plain-text cleanup of prose fields, (D) R1 withdrawal of a browser-confirmed dead citation. | 2026-09-12 |
| [v2.3](Contract_v2.3_DRAFT_Awards_Edition_Anchor_20260908.md) | The four-rung anchor ladder for an awards `EDITION`, rung 2's `ANNOUNCEMENT_DATE >= SUBMISSION DEADLINE` guard, non-retroactive scope, key freeze. **The filename says DRAFT and the document is CURRENT** - 2.1 labels rather than renames. | 2026-09-08 |
| [v2.2](Contract_v2.2_Amendment_Criterion2_Passed_Deadline_20260908.md) | Acceptance criterion 2 gains the passed-deadline exemption v1.4 gave criterion 3. A blank deadline is deliberately NOT exempt. | 2026-09-08 |
| [v2.1](Contract_v2.1_Amendment_Renumbering_And_Awards_Window.md) | R24/R25 renumbering, R26 awards window (schema 43 -> 45), R20.4 field correction. | 2026-09-05 |

## Where the canonical copy lives, and the rule that keeps it here

**This repo holds the operative text** - that is what the contract itself specifies, and it is
what the acceptance gate, the runbook and the `cfp-protocol` skill all read.

`handoff-files` holds the **correspondence record**: the same documents as they were sent, plus
every request, ruling and reply that produced them. Its `README.md` is the index of what is in
force. The two are copies of one text on purpose, per "one text, both sides".

**WHEN AN AMENDMENT IS ADOPTED, IT LANDS IN BOTH PLACES IN THE SAME CHANGE.** Copy the file
here, add its row to the table above, and update the four header lines. The staleness this
header describes happened because that was nobody's step. `tests/test_contract_current.py`
now fails the build when the header does not name every amendment file present.

## One known inconsistency, deliberately not edited

The consolidated text below opens by saying it plus v2.1 "are the only two documents in this
folder that are in force". That was true on 2026-09-05 and has been overtaken by v2.2 through
v2.5. It is **adopted two-sided text and is not rewritten here** - correcting a jointly agreed
document unilaterally is the wrong move even when the correction is obvious. The table above
is authoritative on what is in force; raise it with upstream at the next amendment.

---

> **STATUS: CURRENT.** Adopted by both sides 2026-09-05. This document plus
> `Contract_v2.1_Amendment_Renumbering_And_Awards_Window.md` are the only two documents in
> this folder that are in force. See `README.md`.

# Joint Pipeline Contract - CONSOLIDATED v2.0.1

> **CORRECTION, 2026-09-05, same day as adoption. One rule's placement changed; nothing else.**
> v2.0 said tiered deadline rounds live "in the row's notes", carried forward from the v1.6
> amendment's own wording. **That contradicted section 3 of the same document**, which assigns
> `NOTES` to the customer - on Cybersecurity and Utility it holds their live working text, and
> upstream writing there would overwrite it.
>
> **Rounds go in `STATUS DETAILS`**, which is upstream's field and which R4 already defines as
> the prose a human reads. Corrected in section 4 (R23) and in Known gaps 3. R20.4 carries the
> same error in v1.5's agreed text; it is quoted verbatim with the conflict flagged beside it
> rather than silently rewritten, and the wording is for v2.1 to settle.
>
> **Replace any v2.0 copy with this one.** No other rule, threshold or column has changed.

**2026-09-05.** One text, folding the base contract (v1.1) and every amendment agreed since
(v1.2 through v1.7). It replaces those eight documents. Per v1.1's own rule: *"Replace any
earlier copy with it verbatim rather than merging - two divergent copies of a joint document
is the exact failure this contract exists to prevent."*

**Numbered sub-rules are reproduced verbatim from their source amendments.** Where this
document summarises, it says so. Punctuation is normalised to plain ASCII (no em-dashes or
smart quotes) at the operator's standing instruction; no wording is otherwise changed.

**Why v2.0 and not v1.9.** A v1.8 amendment (awards submission window) was drafted 2026-09-03
and is not yet agreed. Numbering this consolidation v1.9 would put it ahead of a pending v1.8,
so the agreed set is closed at v2.0 and the awards window becomes v2.1 if and when it is
agreed. It is deliberately NOT part of this document.

---

## 0. What this consolidates, and what each source says about its own status

Read this table before adopting. **Two entries need confirmation** - flagged rather than
assumed, because the previous consolidation attempt asserted agreement the source files do not
record.

| Source | Date | Status per the document itself |
|---|---|---|
| `Joint_Pipeline_Contract_v1.1.md` | 2026-08-01 | Authoritative, supersedes v1.0 in full |
| `Contract_v1.2_Amendment_FORMAT_column.md` | 2026-08-05 | Header says DRAFT; v1.5 records it as **agreed 2026-08-13** |
| `Contract_v1.3_Amendment_Edition_Lifecycle.md` | 2026-08-07 | Header says DRAFT; v1.5 records it as **agreed 2026-08-13** |
| `Contract_v1.4_Amendment_Identity_And_Edition.md` | 2026-08-12 | Header says DRAFT; v1.5 records it as **agreed 2026-08-13** |
| `Contract_v1.4_Amendment_Citation_Scope.md` | 2026-08-29 | **Agreed by both sides 2026-08-29**, implemented |
| `Contract_v1.5_Amendment_Organizer_And_Sponsorship.md` | 2026-08-14 | **Header still says DRAFT - CONFIRM.** Its 43-column schema is live and gated, and v1.7 treats it as standing, so it was evidently agreed; no document records the agreement |
| `Contract_v1.6_Amendment_Deadline_Rounds_And_Sources.md` | 2026-08-31 | Specifies R22 and R23; both implemented and enforced both sides |
| `Contract_v1.7_Amendment_Additive_Sponsorship.md` | 2026-08-31 | **Agreed in principle by upstream 2026-08-31**; implementation deliberately blocked on the 43-column export |

**Not included:** `Contract_v1.8_Amendment_Awards_Window.md` (2026-09-03), not yet agreed.

---

## 1. What this describes

Two independent systems produce one deliverable for the customer (Nicolia Wiles / PRIME|PR).

| | |
|---|---|
| **Upstream** | A Google-Search-grounded research process. Discovers events, deadlines, statuses and citations. Emits one CSV per market. |
| **Downstream** | `cfp-monitor` - a local, residential-IP crawler and verification layer. Imports the CSV, crawls and checks claims against live pages, derives the customer view. |

Neither side is subordinate. Upstream has reach we cannot match; downstream has verification
upstream cannot perform. **The contract is the interface between them.**

---

## 2. Principles

**2.1 Discovery is innocent until proven guilty.** An upstream claim stays in the customer's
sheet unless a page positively contradicts it. "We could not verify it" is *never* a disproof -
it is a label (`Unconfirmed`), not a deletion. This is the single most important rule; several
bugs were fixed by restoring it after code had quietly started treating silence as refutation.

**2.2 Derive, don't mutate.** Gates and labels are computed at display time against the current
date, never written into storage. Stored gates go stale the day after they are written.

**2.3 Status outranks the date.** The customer's question is *"can my client still submit?"*,
not *"what was the date?"*. Closure language is first-class evidence and is checked **before**
any date comparison.

**2.4 Correction-precedence.** A human-verified value is never silently overwritten by a later
crawl or a later delivery.

**2.5 Decline rather than guess.** Where a match, a merge or a verdict is ambiguous, produce
nothing. An unlabelled row is honest; a row wearing another event's evidence is wrong in a way
nobody downstream can see.

**2.6 An honest blank beats a confident guess.** Applies to both sides, and it is why upstream
is never scored on how many rows it verifies. Pushing that number up produces invented
citations.

**2.7 (v1.3) An edition is finalised once, not maintained forever.** See section 6.

---

## 3. The boundary - who owns which field

| Owned by upstream | Owned by downstream | Owned by the customer |
|---|---|---|
| Event discovery | Crawling and verification | `STATUS` (their submission pipeline) |
| Deadlines, statuses, citations *(see the note below)* | `GATED_STATUS`, `ISSUES`, `CONFIDENCE` | `NOTES` |
| `OPPORTUNITY_TYPE`, `FORMAT` | Canonical keys (`EVENT_ID`), market membership | `SUBMISSION DATE VERIFIED`, `PRIORITY` |
| `IS_PROJECTED` (claim) *(see the note)* | `RESEARCH STATUS`, `EDITION` (derived), `TRACK` | `SPEAKER & ABSTRACTS SUBMITTED` |
| `ORGANIZER`, `SPONSOR_REQUIRED`, `SPONSOR_URL`, `SPONSOR_COST` | `SPONSOR_QUOTE`, `DEADLINE_QUOTE` | |

**Downstream never edits the customer's Google Sheet.** Output is a file they import.

Two columns exist in the schema but are computed downstream and ignored on import:
`GATED_STATUS` and `ISSUES`. Upstream leaves them blank.

**Note - paper has not matched practice, and the amendment is still owed.** Since the
citation-extraction round, downstream has in fact been writing `SUBMISSION DEADLINE`,
`DEADLINE_EVIDENCE_URL`, `DEADLINE_QUOTE` and `IS_PROJECTED`, though section 3 assigns all four
to upstream. v1.5 flagged this as **R20b**, a separate amendment formally moving them, and that
amendment was never sent. It is still owed and is not resolved by this consolidation. Until it
is: **upstream supplies the claim and the candidate page; downstream extracts and proves the
quote** - the same division for every quote field in this contract.

---

## 4. Upstream obligations

**R1 - Citation withdrawal is a citation-only edit.** Clear `DEADLINE_EVIDENCE_URL` and
`DEADLINE_QUOTE`; `SUBMISSION DEADLINE` is untouched. A date change is new research and needs a
new citation. **Exempt: `LIFECYCLE_EVIDENCE_URL`/`LIFECYCLE_QUOTE` (R16.2) and
`SPONSOR_URL`/`SPONSOR_COST`/`SPONSOR_QUOTE` (R18.4) never clear on a dead deadline link.**

**R2 - `IS_PROJECTED`.** `false` only when the deadline is past with `STATUS = Closed`, or a
future date is backed by a live citation carrying the claim. Otherwise `true`. **Broadened by
R17:** "a future date" means any dated fact about the edition, not the deadline specifically.

**R3 - What counts as a citation.** The exact page the sentence was read on. It must (a)
resolve, (b) be the specific page - never a homepage, section index or `/exhibit` page, (c)
contain the claim. **HTTP 403 is acceptable** - the page exists but blocks readers; keep the
deep URL and downstream marks it *Blocked-but-Trusted*. Never substitute a shallower URL to
obtain a 200.

*(R3b, a shape test on citation URLs, was **retired** by the v1.4 citation-scope amendment. Of
34 rows it flagged, 14 had their quote present on the cited page. The outcome is now tested
directly by gate criterion 3.)*

**R4 - Prose matches evidence.** `STATUS DETAILS` is what a human reads. "Active" / "Open" /
"Closed" only when read on a page and quoted. Otherwise the projection form:
`[Call for Speakers Pending / Expected Fall 2026]`.

**R5 - Opportunity typing.** `OPPORTUNITY_TYPE` in `Speaking` | `Awards` | `Exhibiting` |
`Registration`. One row per real opportunity. `Exhibiting`/`Registration` rows carry no
submission deadline. The citation must match the row's type.

**R6 - Declare the pass type.** `correction` (only the fields named in feedback; no rows added
or removed, no dates changed) - `re-research` (anything may change; manifest required) -
`schema` (structure only). **The audit runs against the previous file, not just the new one.**
An undeclared re-research forces a full re-verification instead of checking the handful of
fields that changed.

**R7 - Change manifest** on every re-research: row counts, added, removed *with a reason each*,
deadlines changed, dates changed, citations added and withdrawn.

**R8 - File format.** RFC 4180 via a real CSV writer. **Exactly 43 columns, in the order in
section 8.** `CITY` holds a city - venues belong in `LOCATION`. `GATED_STATUS` and `ISSUES`
blank.

**R9 - Name stability.** Do not rename an existing event between deliveries. Our canonical key
is derived from the name, so a rename creates a second record for one event. If unavoidable,
list it under `RENAMED: <old> -> <new>` in the manifest.

**R10 - Call-level identity.** One event may run two distinct `Speaking` calls - IBC has
Technical Papers *and* the Accelerator programme, with different deadlines. `OPPORTUNITY_TYPE`
does not separate those. Emit them under distinct event names, or populate `CALL_NAME`.

**R11 (v1.2) - `FORMAT`.** `In-Person` | `Virtual` | `Hybrid`. `Virtual` only when the event is
online-only with no physical venue. `Hybrid` when the page states both in-person and online
attendance. `In-Person` otherwise. Where the page is silent, leave it blank rather than
inferring from the presence of a venue string - a hybrid event has a venue too, so inference
produces confident errors. Rows researched before v1.2 carry `FORMAT` blank; that is valid, not
a defect. **Do not backfill by inference.**

**R13, R14, R15, R17 (v1.3) - edition lifecycle.** See section 6.

**R16 (v1.3) - a lifecycle claim needs its own evidence.** Verbatim:

> **R16.1** - Any row in state `Discontinued`, or asserting in prose that an event has ended,
> merged, been cancelled or been superseded, **must** carry both fields.
>
> **R16.2** - These fields are **exempt from R1 withdrawal**. A dead deadline citation never
> clears them. They are separate claims with separate evidence.
>
> **R16.3** - The same rules that govern deadline citations apply: the exact page, not a
> homepage or index (R3); 403 is acceptable, only 404/410 disprove (5.2); the quote must appear
> on the page (gate check 3).
>
> **R16.4** - Where the event has a **successor**, name it in `LIFECYCLE_QUOTE` or the prose and
> record the relationship in the manifest, so the series history stays connected.
>
> **R16.5** - A row may not be moved to `Discontinued` on prose alone. Without a citation it
> stays `Watching`, and the honest label is "we could not confirm the next edition", not "the
> event has ended".

The two fields are `LIFECYCLE_EVIDENCE_URL` (the exact page the lifecycle change was read on)
and `LIFECYCLE_QUOTE` (the verbatim sentence stating it).

**R18, R19 (v1.4) - identity and edition.** See section 7. **Note the number collision with
v1.5's R18/R19 - see Known gaps.**

**R18, R19, R20, R20a, R20b (v1.5) - sponsorship and organizer.** See section 7.

**R21 (v1.7) - additive sponsorship capture.** See section 7.

**R22 (v1.6) - some sources can never evidence a deadline.** Verbatim:

> **R22.1** A deadline citation on a **social media host or a link shortener** is inadmissible.
> Not weak, not stale - inadmissible. The full list is `rules.INADMISSIBLE_HOSTS`.
>
> **R22.2** Admissibility is judged on the **host, before the page content**. What a social post
> happens to say does not make it a source.
>
> **R22.3** An inadmissible citation **may be withdrawn under R1 even when the deadline has
> passed.** The passed-deadline refusal exists because a CFP page routinely comes down after its
> deadline - that excuses a missing quote. It says nothing when the objection is to the host: a
> Facebook page could not evidence a deadline the day it was cited, and the deadline passing does
> not improve it.
>
> **R22.4** A legitimate third-party **submission platform is admissible** - pretalx, Oxford
> Abstracts, EasyChair, cvent and their kind host the real call. R22 targets a host category, not
> third parties in general.

**Scope note (added 2026-09-01, enforced both sides):** R22 covers
`DEADLINE_EVIDENCE_URL`, `LIFECYCLE_EVIDENCE_URL` and `SPONSOR_URL` alike.

**R22b (advisory, 2026-09-03).** A URL that is a machine form-submission endpoint rather than a
readable page (for example `forms.hsforms.com/submissions/v3/...`) is flagged **once fetched and
found unreadable**, not rejected on its shape alone. Deliberately advisory: a regex is an
inference, and a delivery is not rejected on one. Legitimate hosted form pages such as
`share.hsforms.com` remain admissible.

**R23 (v1.6) - `SUBMISSION DEADLINE` is the NEXT ACTIONABLE deadline.** Verbatim:

> **R23.1** `SUBMISSION DEADLINE` carries the **next round a person can still act on**: the
> earliest round whose close is not yet past.
>
> **R23.2** When every round has closed, it carries the **last** one, so the row states what was
> missed rather than falling silent.
>
> **R23.3** **Every round is recorded**, whichever one is displayed. A passed round explains what
> was missed; a later round is the fallback if the next is missed too. Nothing is discarded because
> it is not the headline date.
>
> **R23.4** A round we cannot parse into a date is **dropped, not guessed**. A date we cannot read
> is not a date (2.5).

**What R23 asks of upstream, in the amendment's own words:** *"R23 asks for something new: every
round, not just one. Where a conference publishes tiered rounds, send them all with their
labels. We will decide which is displayed; we cannot decide it from a single date."*

**Where the rounds go until the column exists (corrected 2026-09-05, see Corrections).** In
`STATUS DETAILS`, upstream's field under section 3, in the order the conference states them,
each marked passed or next. **Not in `NOTES`** - `NOTES` belongs to the customer under section 3
and on the live markets it holds their own working text.

A `DEADLINE_ROUNDS` column is the acknowledged durable answer and **is not built**. It should be
added the next time the schema is opened.

---

## 5. Downstream obligations

1. **Never overwrite a grounding claim.** Claims live in their own table (`grounding_facts`);
   crawled facts live in `conferences`. A failed or thin crawl can neither confirm nor erase a
   claim.
2. **Only positive contrary evidence contradicts.** 404/410 disproves a link. A page stating a
   different deadline disproves a date, *but only on the page cited for it*. Timeouts, 403s,
   blocked pages and empty fetches resolve to `not_found`, and the claim stands.
3. **Match evidence to the right record.** Editions must agree; sibling calls and regional
   variants must not borrow each other's evidence; where ambiguous, attach nothing.
4. **Recompute keys.** We derive `EVENT_ID` ourselves, market deliberately excluded so one event
   can serve several markets. Upstream's `EVENT_ID` column is not read.
5. **Report the market vocabulary.** Unknown market labels are surfaced for a human decision,
   never auto-registered.
6. **Gate at display time.** Past deadlines read `Closed`; the row self-corrects as dates pass.
7. **Never modify a frozen edition** (`Archived` or `Retired`), and never rewrite a field on a
   `Watching` row.

---

## 6. Edition lifecycle (v1.3: R13, R14, R15, R17)

**The problem:** a conference used to be one row rewritten every cycle. That let a concluded
edition's facts silently change, wasted budget re-researching the past, and never asked the
customer's real question - *"when does the next one open?"*

**Edition** = one `EVENT_ID`. **Series** = the `EVENT_ID` with the leading year removed. Rows
sharing an `EVENT_ID` are ONE edition appearing in several markets; lifecycle logic groups by
`EVENT_ID` first.

**R13 - edition state, derived not stored. No new column.**

| State | Rule | Operational rule |
|---|---|---|
| `Active` | Latest edition of its series, event has not yet run | Research normally each cycle |
| `Watching` | Latest edition, event HAS run, no successor exists yet | **Do not re-research this row's own facts.** Search only for the successor (R14). The row's values are final. |
| `Archived` | A later edition of the same series exists | **Frozen. Never researched, never modified.** |
| `Retired` | Latest edition, prose states the event has permanently ended, with R16 evidence | Frozen. Do not search for a successor. |

**Ordering, comparison and supersession must use `EDITION` or `START DATE` - never the year
embedded in `EVENT_ID`** (v1.4 section 4). Applied to a duplicate pair, the naive reading would
mark a live 2027 conference `Archived` on the strength of a duplicate of itself.

**R14 - finding the successor, without assuming a cadence.** Annual cadence must not be assumed.
A candidate is accepted only if: (1) its start date is **more than 25 days after** the concluded
edition's start date; (2) that date is **in the future**; (3) it is the **same series** - same
organiser and event identity, not a co-located or sibling event. The 25-day floor stops a
satellite day or co-located summit being mistaken for the next edition. Any qualifying future
date is accepted regardless of the year gap, so annual, biennial and irregular cadences work
with one rule. **No qualifying date is a normal outcome, not a failure.**

A successor row inherits **identity only** - series identity and name stem, `CONFERENCE URL`,
`Market`, `CATEGORIES`, `OPPORTUNITY_TYPE`, and the usual `CITY` as a hint. Researched fresh and
never inherited: `CONFERENCE DATES`, `START DATE`, `SUBMISSION DEADLINE`, `STATUS`, every
citation, quote and evidence URL, `GROUNDING_CONFIDENCE`, `IS_PROJECTED`, `FORMAT`. **The new
row starts fully unverified.**

**Naming a successor:** where the name contains an ordinal or a year range, it must be **read
from the event's own page, not generated**. Where it is a plain year, bumping it is acceptable.
Ambiguity means decline and flag (2.5).

**R15 - additions checked against the entire list, including `Archived` and `Retired`.** Match
on four signals: series key (name-slug plus city, ignoring year); name similarity (after
stripping parentheticals, allowing ordinals to change); website host; city plus organiser.

| Finding | Action |
|---|---|
| Matches an existing edition | **Not new.** Reject, point at the existing row |
| Matches a series in `Watching`, date clears the 25-day test | **This is the successor.** Create via R14 |
| Matches a `Retired` series | Flag for a human - the event may have restarted |
| No match on any of the four | Genuinely new. Add it |
| Matches on some signals but not others | **Decline and flag** (2.5). Never merge on a guess |

Where a conference rebranded its website, signals 1, 2 and 4 catch it. The correct outcome is
the successor of the existing series with `URL CHANGED: old -> new` in the manifest, not a new
series.

**R17 - what "verified" means with no deadline announced.** `IS_PROJECTED = false` requires **at
least one dated fact** - a deadline OR a confirmed event date - backed by a live citation
carrying it. `true` where no dated fact is confirmed. Customer-facing display distinguishes
three states:

| Shown | Condition | Means |
|---|---|---|
| **Verified** | `IS_PROJECTED=false` AND a deadline is present | The deadline was read on the official page |
| **Verified dates** | `IS_PROJECTED=false` AND no deadline | Event dates confirmed; deadline not announced yet |
| **Projected** | `IS_PROJECTED=true` | Estimate; nothing on the page confirms it |

A call that has not opened yet is **normal for events 6-12 months out, and not a gap in the
research.** The gate must NOT flag "verified with no deadline"; it flags only verified with no
dated fact of any kind.

---

## 7. Identity, sponsorship and organizer (v1.4, v1.5, v1.7)

### 7a. Identity - a key is a name, not a fact (v1.4)

**A canonical key must be stable and unique. It does not have to be true.** Once an identifier
is issued, changing it to make it more accurate is a rename, and a rename breaks every reference
to it. Verbatim:

> **R18.1** `EVENT_ID` is minted once and never recomputed. The year within it is `key_year`, a
> stored value, not a derivation of `EDITION`.
>
> **R18.2** When a conference we already hold appears again, it **reuses its existing
> `key_year`**, whatever year the incoming row carries. This is what actually closes the
> duplicate hole - without it, the next inconsistent EDITION mints another record.
>
> **R18.3** An invariant asserts that every `event_id` still begins with its own `key_year`.
> Implemented as check 7 in `check_invariants.py`, and it is the check that would have caught
> the 2026-08-08 rewrite.

> **R19.1** `EDITION` is the calendar year of `START DATE`. Where `START DATE` is absent, the
> year stated in `CONFERENCE DATES`.
>
> **R19.2** Where neither exists, `EDITION` is left exactly as delivered and flagged. It is not
> inferred from the conference's name.
>
> **R19.3** We stop reading upstream's `EDITION` column as authoritative. **Keep sending it** -
> it is a useful cross-check, and a disagreement between your value and the derived one is a
> signal worth surfacing - but it is no longer what we store.

The year is never read out of the name: it is right 66 times in 67 and wrong once, which is the
worst kind of rule. A date is a fact; a name is a label.

### 7b. Sponsorship and organizer (v1.5)

| Column | Populated by | Contents |
|---|---|---|
| `ORGANIZER` | **Upstream** | The organization running the event, as named on its own site |
| `SPONSOR_REQUIRED` | **Upstream** | `Yes` / `No` / `Unknown` |
| `SPONSOR_URL` | **Upstream** | The sponsorship or prospectus page the answer was read on |
| `SPONSOR_COST` | **Upstream** | Free text - a tier table, a range, or a figure with its currency |
| `SPONSOR_QUOTE` | **Downstream** | The verbatim sentence, proven a literal substring of the fetched page |

Verbatim:

> **R18.1 - `SPONSOR_REQUIRED` is three-valued and `Unknown` is the default.** Never a boolean,
> and a blank never means `No`.
>
> **R18.2 - `SPONSOR_COST` is TEXT, never a number.** It is rarely one figure. "Gold $25,000 /
> Silver $12,000 / Bronze $6,000" is the normal shape, as are ranges, "from EUR 8,000", and
> "POA". Record the currency as written.
>
> **R18.3 - A sponsorship claim carries its own evidence.** `SPONSOR_URL` and `SPONSOR_QUOTE`
> together, on the same terms as every other claim in this contract.
>
> **R18.4 - These fields are exempt from R1 withdrawal.** A dead deadline citation never clears
> them. Separate claims, separate evidence.
>
> **R18.5 - Sponsorship is independent of `CFP MODEL TYPE`.** Of the 21 rows marked `Invite
> Only`, one mentions sponsorship anywhere, and that one is generic prose. Please do not fold one
> into the other.

> **R19.1** Populate `SPONSOR_*` **while already on the conference site for another reason**. If
> a speaking page says sponsorship is required, or links a prospectus, capture it then. The
> marginal cost is close to zero.
>
> **R19.2** Where nothing is visible, leave `SPONSOR_REQUIRED` as `Unknown` and the rest blank.
> That is a complete and honest answer, not a gap.
>
> **R19.3** Dedicated research happens only on a named list, when the customer flags conferences
> they intend to pitch.

> **R20.1** The organizer as stated by the event, not inferred. "Reuters Events", "Fab Owners
> Alliance", "HKTDC". Where the page does not name one, leave it blank (2.6).
>
> **R20.2 - It is an IDENTITY signal, not just a contact detail.** R15's fourth matching signal
> is *"city plus organiser - catches a rebrand where both name and URL moved."* We have been
> unable to use it, because we do not hold the field.
>
> **R20.3** No phone number. `COORDINATOR EMAIL` is already populated on 338 of 392 rows and is
> the channel that actually gets used.
>
> **R20.4** `ORGANIZER` needs no separate evidence field. Where it is genuinely contested, say so
> in `NOTES`.

**Conflict flagged, text left verbatim.** R20.4's closing instruction sends upstream to `NOTES`,
which section 3 assigns to the customer. The quote is reproduced as written rather than silently
corrected, because it is v1.5's agreed text. **In practice use `STATUS DETAILS`**, and settle the
wording in v2.1.

**R20a - `SPONSOR_QUOTE` is populated by downstream**, from the page in `SPONSOR_URL`, on the
same terms as `DEADLINE_QUOTE`. Upstream may leave it blank. If upstream supplies one, it is
treated as a candidate and re-cut from the page.

**R20b - still owed.** A separate amendment formally moving `SUBMISSION DEADLINE`,
`DEADLINE_EVIDENCE_URL`, `DEADLINE_QUOTE` and `IS_PROJECTED` to downstream, matching what both
sides have done since the citation round. Not folded in here because it changes existing columns
rather than adding new ones. **Flagged, not resolved.**

**Acceptance gate:** a row with `SPONSOR_REQUIRED = Yes` must carry `SPONSOR_URL` and
`SPONSOR_QUOTE`. `Unknown` requires nothing. `No` requires evidence only if a cost is also
stated, which would be contradictory.

### 7c. Additive sponsorship capture (v1.7)

Verbatim:

> **R21.1 - Downstream may fill only what upstream left empty.** Downstream may populate
> `SPONSOR_REQUIRED`, `SPONSOR_URL` and `SPONSOR_COST` **only** where upstream has left the field
> `Unknown` or blank. A value upstream has set is never overwritten, never contradicted, and
> never cleared by downstream.
>
> **R21.2 - Provenance is recorded, and it stays out of the delivery.** Every value downstream
> writes is attributed in downstream's own store, not in the delivery schema. The delivery
> carries the value; the database carries who established it and when.
>
> **R21.3 - The evidence bar does not move.** Anything downstream writes carries a
> `SPONSOR_QUOTE` extracted from a page downstream fetched itself, proven a literal substring of
> that page. The model selects from text we hold; it never composes.
>
> **R21.4 - `ORGANIZER` remains upstream's alone.** It is an identity fact established at
> discovery, not something picked up opportunistically. Downstream does not write it under any
> circumstance.
>
> **R21.5 - `Unknown` is still a complete answer.** This amendment does not turn `Unknown` into a
> defect. R19.2 stands.

**The four fields are still upstream's to research. R21 is a gap-filler, not a transfer.**
Downstream reports what it filled in the ordinary hand-back, so upstream can adopt, correct or
reject any of it.

---

## 8. The 43-column schema

Read from the header of `delivery_v19_final_43col.csv` - the delivery that closed the 38-column
window on 2026-08-29 - and re-verified against `delivery_v23_check4_43col.csv` on 2026-09-05.
Both carry 43 columns with the same last five.

| # | Column | # | Column | # | Column |
|---|---|---|---|---|---|
| 1 | `EVENT_ID` | 16 | `CATEGORIES` | 31 | `IS_PROJECTED` |
| 2 | `CONFERENCE` | 17 | `NOTES` *(customer)* | 32 | `SOURCE_AS_OF` |
| 3 | `CONFERENCE URL` | 18 | `TRACK` | 33 | `GATED_STATUS` *(blank from upstream)* |
| 4 | `LOCATION` | 19 | `GROUNDING_CONFIDENCE` | 34 | `ISSUES` *(blank from upstream)* |
| 5 | `CONFERENCE DATES` | 20 | `EDITION` *(downstream-derived)* | 35 | `OPPORTUNITY_TYPE` |
| 6 | `LATEST UPDATE` | 21 | `START DATE` | 36 | `FORMAT` |
| 7 | `SUBMISSION DEADLINE` | 22 | `Market` | 37 | `LIFECYCLE_EVIDENCE_URL` |
| 8 | `SUBMISSION DATE VERIFIED` *(customer)* | 23 | `CITY` | 38 | `LIFECYCLE_QUOTE` |
| 9 | `PRIORITY` *(customer)* | 24 | `STATE_PROVINCE` | 39 | `ORGANIZER` |
| 10 | `STATUS` | 25 | `COUNTRY` | 40 | `SPONSOR_REQUIRED` |
| 11 | `STATUS DETAILS` | 26 | `MAIN_INFO_URL` | 41 | `SPONSOR_URL` |
| 12 | `CFP MODEL TYPE` | 27 | `CFP_SUBMISSION_URL` | 42 | `SPONSOR_COST` |
| 13 | `SUBMISSION URL` | 28 | `DEADLINE_EVIDENCE_URL` | 43 | `SPONSOR_QUOTE` *(downstream)* |
| 14 | `COORDINATOR EMAIL` | 29 | `VENUE_EVIDENCE_URL` | | |
| 15 | `OVERVIEW` | 30 | `DEADLINE_QUOTE` | | |

The gate mechanically enforces **43 columns total** and **columns 39-43 in exactly this order**.
It does not separately re-check the order of 1-38.

**Note on `STATUS` (column 10).** v1.1 section 7 named this field `RESEARCH STATUS` specifically
to avoid colliding with the customer's own sheet, which has its own `STATUS` column holding
their submission-pipeline value (Submitted, Accepted, Declined). **In practice the delivery
column is simply called `STATUS`.** The same word means two different things in two different
files. Stated explicitly so nobody merges them.

**Never write** `CONFIDENCE`, `VERIFICATION`, `TRUST`, or a hand-computed `GATED_STATUS` /
`ISSUES` value into a delivery. These are derived downstream at display time, always.

---

## 9. Verification model

Three layers, cheapest first.

| Layer | What it does | Cost |
|---|---|---|
| **L0 / L0s** | Cross-check against pages already crawled. `L0s` compares status first, `L0` the deadline | free |
| **L1** | HTTP check of the submission link. Only ever returns a negative: 404/410 means dead | fast |
| **L2** | Fetch the cited page, check status then date. Reads PDFs | slow |

**Outcomes:** `verified` / `contradicted` / `not_found` (claim stands) / `unverified`.

**Guards, each earned from a real false positive:** L0 declines when editions differ; when our
own record has expired; and when our crawl quality is not `PASS`, including for confirmation -
grounding confirming grounding is circular. L2 accepts a rival date as a contradiction **only on
the cited page**. L2 labels the result by the page actually read, so a fallback page's silence is
never reported as the cited page's silence.

---

## 10. What the customer sees

| Label | Meaning |
|---|---|
| **Confirmed** | We read this deadline on the event's own page |
| **Verified dates** | Event dates confirmed; deadline not yet announced (R17 - normal, not a gap) |
| **Unconfirmed** | Research we could not confirm, including every projected forecast |
| **Check link** | The submission link did not resolve |
| **Disputed** | A page positively contradicts the claim |
| *(blank)* | No deadline and no claim |

A projected deadline can never read `Confirmed`, even if it later proves right: at the time of
writing, nothing on the page said it.

---

## 11. Acceptance gate

| # | Criterion | Threshold |
|---|---|---|
| 1 | Every row parses to exactly 43 fields, columns 39-43 correct and in order | 100% |
| 2 | Cited pages returning 404/410 | 0 |
| 3 | Cited page contains its quote - **active deadline claims only** | 100% of active claims |
| 4 | Confident prose on an `IS_PROJECTED = true` row | 0 |
| 5 | `Exhibiting`/`Registration` row carrying a speaking deadline | 0 |
| 6 | Past deadline still presented as open | 0 |
| 7 | Row wearing another event's evidence | 0 |
| 8 | Open rows labelled `Confirmed` or `Unconfirmed`, never blank | 100% |
| R22 | Citation host admissible (offline, no fetch needed) | 0 inadmissible hosts |
| 9 | Verified count | **reported, never targeted** |

**Criterion 3 scope (v1.4 citation-scope amendment).** It does not fire when `SUBMISSION
DEADLINE` is blank (no claim is made, so there is nothing to evidence) or has already passed (a
CFP page is routinely taken down after its deadline; the quote going missing is expected decay).
Measured on 2026-08-29: of 186 failures, 108 claimed no deadline and 50 had passed. **84% of the
failure was the criterion testing rows it should never have applied to.** A criterion that fails
good work for getting older is one people learn to ignore. This exemption is also a deletion
guard: an automated pass once proposed withdrawing 18 citations, 14 of them passed-deadline rows
that would have been wrong.

**On criterion 9.** A verification rate is a property of the market, not a score. Targeting it
pushes upstream back toward inventing citations.

---

## 12. The review loop

```
upstream delivers -> downstream audits -> defend-or-correct -> re-emit -> accept
```

Every finding offers three answers, all acceptable: **defend** (supply the exact URL, we
re-check), **correct** (supply the right value with a working citation), **withdraw** (blank the
citation and quote, keep the deadline, set `IS_PROJECTED = true`).

**Verify corrections as rigorously as original claims.** Every cycle so far has had at least one
problem introduced *by* a fix: a deadline moved silently behind a withdrawal, a homepage
substituted for a blocked deep link, an exhibiting page cited for an awards deadline. The
diagnosis has consistently been sound; the execution is where data moves unnoticed.

---

## 13. Rulings on hard cases

Do not re-litigate without new evidence.

| Case | Ruling |
|---|---|
| Venue vs city | `CITY` is the city. City-states protected - dropping "state" would destroy Berlin, dropping "country" would destroy Hong Kong |
| One event, several calls | Different calls at one event never share evidence (R10) |
| Regional siblings | `Europe`/`USA`/`East`/`West`/`Spring`/`Fall` separate distinct events that may share 75% of their words. Similarity alone must not merge them |
| Renamed duplicates | Match on substance, not substring |
| Editions | Never compare across editions, in either direction, except explicit lifecycle logic (R13-R15) |
| A canonical key is a name, not a fact | `key_year` frozen forever once minted; accuracy lives in `EDITION` |
| PDF citations | Valid and welcome. An unreadable PDF resolves to `not_found`, never a disproof |
| HTTP 403 | Real but blocked. Never a disproof, never grounds to substitute a shallower URL |
| Social-host / shortener citations | Inadmissible outright, judged on the host (R22) |
| Multi-market events | One `EVENT_ID`, market excluded from the key |
| Near-duplicate markets | Merge threshold 0.70, measured: real variants scored >= 0.75, distinct markets <= 0.44 |

---

## 14. Ruling log

| Date | Ruling |
|---|---|
| 2026-07-29 | Grounding claims live in their own table; a crawl never overwrites them |
| 2026-07-30 | Status verified before date; closure language is decisive without a date |
| 2026-07-30 | Quality gate precedes confirmation as well as contradiction |
| 2026-07-30 | PDF citations read and accepted |
| 2026-07-31 | A result is labelled by the page actually read, not the page cited |
| 2026-07-31 | Status cross-check must respect edition and staleness |
| 2026-07-31 | A rival date disproves only on the cited page |
| 2026-07-31 | R9 name stability, R10 call-level identity added |
| 2026-08-01 | Contract v1.1 issued as one shared text |
| 2026-08-12 | A canonical key is a name, not a fact. Identity frozen at creation; accuracy lives in derived fields |
| 2026-08-29 | Criterion 3 evaluates active deadline claims only. R3b retired: the outcome is tested directly, and the shape proxy was wrong on 14 of 34 measured rows |
| 2026-08-31 | R22 and R23 issued together from the first pass through the customer's own corrections |
| 2026-09-05 | Consolidated as v2.0 |
| 2026-09-05 | Adopted by upstream. v1.5 confirmed agreed; R18/R19 renumbering to R24/R25 agreed for v2.1 |
| 2026-09-05 | v2.0.1: tiered rounds go in `STATUS DETAILS`, not `NOTES`. `NOTES` is the customer's under section 3, and v2.0 contradicted itself by repeating v1.6's wording |

---

## Known gaps - flagged, not silently resolved

1. **Rule numbers R18 and R19 mean two different things.** v1.4 uses R18.1-R18.3 for identity
   (`EVENT_ID`, `key_year`) and R19.1-R19.3 for edition derivation. v1.5 uses R18.1-R18.5 for
   sponsorship and R19.1-R19.3 for sponsorship cost control. **Both are live and both are cited
   in code and correspondence.** This document keeps both and labels every reference with its
   source amendment. **Proposed fix, needing both sides' agreement:** renumber v1.4's identity
   rules to R24/R25 in a future amendment. Not done unilaterally, because renumbering an agreed
   rule is itself a change.

2. **R20b is still owed** - the amendment formally moving `SUBMISSION DEADLINE`,
   `DEADLINE_EVIDENCE_URL`, `DEADLINE_QUOTE` and `IS_PROJECTED` to downstream ownership, matching
   practice since the citation round. Flagged in v1.5, never sent.

3. **`DEADLINE_ROUNDS` is not built.** R23.3 requires every round to be recorded, and until the
   column exists they go in `STATUS DETAILS` - not `NOTES`, which is the customer's. The column
   is the durable answer and should be added the next time the schema is opened.

4. **v1.5's own header still reads DRAFT**, though its 43-column schema is live, gated, and
   treated as standing by v1.7. Worth an explicit confirmation from both sides rather than an
   assumption.

5. **The awards submission window (drafted as v1.8, 2026-09-03) is excluded.** It would add
   `SUBMISSION_OPENS` and `ANNOUNCEMENT_DATE`, taking the schema to 45. Not agreed; do not build
   against it. If agreed it becomes v2.1.

6. **The `STATUS` naming collision** between the delivery and the customer's sheet is described
   in section 8 and not fixed. Both sides should know the same word means two different things.
