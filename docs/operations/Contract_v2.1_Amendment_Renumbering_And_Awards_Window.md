> **STATUS: CURRENT.** Adopted by both sides 2026-09-05. Read alongside
> `Joint_Pipeline_Contract_v2.0.1_CONSOLIDATED_20260905.md`, which it amends. Those two are
> the only documents in this folder that are in force. See `README.md`.

# Joint Pipeline Contract - amendment v2.1

**2026-09-05. Amends v2.0.1.** Three changes in one amendment, because two of them were
already promised for "the next amendment" and the third would collide with the first if
sent separately.

| Part | Change | Status |
|---|---|---|
| **A** | Renumber the v1.4 identity rules to **R24 / R25** | Agreed in principle 2026-09-05 |
| **B** | Awards submission window as **R26**, schema 43 -> 45 | New, for agreement |
| **C** | Correct R20.4's field reference | Defect fix, flagged in v2.0.1 |

Nothing else in v2.0.1 changes. No rule is weakened, no threshold moves.

---

## Part A - the R18 / R19 collision, resolved

### The problem

`R18` and `R19` each mean two different things:

| Number | In the v1.4 amendment | In the v1.5 amendment |
|---|---|---|
| `R18.1` | `EVENT_ID` minted once, `key_year` frozen | `SPONSOR_REQUIRED` is three-valued |
| `R18.2` | Reuse the existing `key_year` | `SPONSOR_COST` is TEXT |
| `R18.3` | The `event_id`/`key_year` invariant | A sponsorship claim carries its own evidence |
| `R19.1` | `EDITION` is the year of `START DATE` | Capture sponsorship opportunistically |
| `R19.2` | No date anywhere: leave as delivered | `Unknown` with the rest blank is complete |
| `R19.3` | Upstream's `EDITION` is no longer authoritative | Dedicated research only on a named list |

Both sets are live. Both are cited in correspondence.

### Which set moves, and why that direction

**The v1.4 identity rules move. The v1.5 sponsorship rules stay.**

That is not a coin toss - it is what the code says. Every `R18`/`R19` reference in the
downstream codebase is to the **sponsorship** rules:

    scripts/accept_delivery.py:46    R18.1  blank read as Unknown
    scripts/accept_delivery.py:444   R18.3  "Yes" is a claim, evidence it
    scripts/accept_delivery.py:455   R18a / R18b  gate check identifiers
    src/cfp_monitor/storage.py:119   R18.1  sponsor_required default
    tests/test_v15_columns.py        R18.1, R18b
    tests/test_v15_import.py:61      R18.1
    tests/test_review_page.py:304    R18.3

**There are no code references to the v1.4 identity rules.** So renumbering them costs
nothing and renumbering the sponsorship rules would cost a sweep through the gate, the
schema and four test files. Moving the cheaper set is the whole argument.

`R18a`, `R18b` and `R19b` are downstream gate-check identifiers tied to sponsorship and
to the `SOURCE_AS_OF` advisory. They are unaffected.

### The renumbered rules - text unchanged, numbers only

**R24 - identity is frozen** (was R18, v1.4):

> **R24.1** `EVENT_ID` is minted once and never recomputed. The year within it is
> `key_year`, a stored value, not a derivation of `EDITION`.
>
> **R24.2** When a conference we already hold appears again, it **reuses its existing
> `key_year`**, whatever year the incoming row carries. This is what actually closes the
> duplicate hole - without it, the next inconsistent EDITION mints another record.
>
> **R24.3** An invariant asserts that every `event_id` still begins with its own
> `key_year`. Implemented as check 7 in `check_invariants.py`, and it is the check that
> would have caught the 2026-08-08 rewrite.

**R25 - edition is the year the conference starts** (was R19, v1.4):

> **R25.1** `EDITION` is the calendar year of `START DATE`. Where `START DATE` is absent,
> the year stated in `CONFERENCE DATES`.
>
> **R25.2** Where neither exists, `EDITION` is left exactly as delivered and flagged. It
> is not inferred from the conference's name.
>
> **R25.3** We stop reading upstream's `EDITION` column as authoritative. **Keep sending
> it** - it is a useful cross-check, and a disagreement between your value and the derived
> one is a signal worth surfacing - but it is no longer what we store.

Every reference elsewhere in v2.0.1 to "R18/R19 (v1.4 identity)" now reads R24/R25. The
Known-gaps entry describing the collision is retired.

---

## Part B - R26, the awards submission window

### Why

Awards are the second module after conferences. The customer's framing, from the
2026-09-02 call:

> "Some of these awards, they might only be open and available for like a month. They'll
> open it and then at the end of the month it's closed. And if you didn't know about it,
> you don't get to even enter."

A conference has a deadline to count down to. **An award has a window, and catching it
while it is open is the product.** The schema cannot express one.

Today `SUBMISSION DEADLINE` carries the close. The open has no home, so an award that has
not opened yet is indistinguishable from one whose date we simply failed to find: both are
a blank deadline with `STATUS = Upcoming`.

**The seed this is drawn from:** 135 award rows across the two customer sheets hold **2
live deadlines** between them. Nearly every row is spent or unannounced, so the value here
is telling the customer when a window is about to open, not re-confirming closed ones.

### Two new columns, appended

    SUBMISSION_OPENS        the date entries open. ISO YYYY-MM-DD.
    ANNOUNCEMENT_DATE       the date winners are named. ISO YYYY-MM-DD.

Column count **43 -> 45**. Both append; no existing position moves.

`ANNOUNCEMENT_DATE` earns its place because for an award the announcement, not the
deadline, is the PR moment the client plans around. Conferences have no equivalent and
will leave it blank.

### One column that is NOT needed

The operating body of an award - Globee, Cyber Defense Magazine, RSA - matters, because
these bodies each run several programmes and one crawl can yield several award records.
**`ORGANIZER` already carries this.** No new column; we simply populate it for awards rows.

### R26 - an award's window is a pair

**R26.** `SUBMISSION_OPENS` and `SUBMISSION DEADLINE` together describe when entries are
accepted.

**R26.1** `SUBMISSION_OPENS` is a claim and carries evidence like any other - the cited
page and a verbatim quote, on the same terms as a deadline. An open date with no quote is
projected, not verified.

**R26.2** Blank is a complete answer (2.6). An award whose open date is not published gets
a blank, not a guess, and not a date carried over from last cycle.

**R26.3** Not knowing the window is never grounds to drop the award (2.1). Absence is a
label, not a deletion.

**R26.4** `STATUS` follows the window, evaluated against the run date:

| condition | STATUS |
|---|---|
| today is before `SUBMISSION_OPENS` | `Upcoming` |
| today is between open and deadline, or a rolling form | `Open` |
| today is after `SUBMISSION DEADLINE` | `Closed` |
| window not established | `Needs Verification` |

**R26.5** Where only one end is known, the known end still stands. A verified deadline with
an unknown open date is a normal, useful row. Do not withhold one because the other is
missing.

**R26.6** A window that has closed does not disprove the next cycle. Report the cycle that
closed and say so in `STATUS DETAILS`; do not mark the award discontinued. R16's lifecycle
evidence is what discontinuation requires, and it is unchanged here.

### Why R26 and not R24

The awards window was drafted on 2026-09-03 as R24, before the renumbering in Part A was
proposed. Sending both as written would have put two different rules at R24 - the same
defect Part A exists to fix, created knowingly. R24 and R25 are consumed by Part A, so the
window is R26.

---

## Part C - R20.4 points at the wrong field

v1.5's R20.4 closes: *"Where it is genuinely contested, say so in `NOTES`."*

`NOTES` belongs to the customer under section 3, and on the live markets it holds their own
working text. v2.0.1 flagged this beside the quote rather than editing agreed wording
unilaterally.

**R20.4 now reads:** `ORGANIZER` needs no separate evidence field. It is read from the
event's own site alongside everything else, and unlike a cost figure nobody spends money on
the strength of it. **Where it is genuinely contested, say so in `STATUS DETAILS`.**

This is the same correction v2.0.1 already made for tiered deadline rounds. Anything
upstream writes as prose for a human to read goes in `STATUS DETAILS` (R4). `NOTES` is the
customer's.

---

## The gate

`scripts/accept_delivery.py` pins `ACCEPTED_COLS = {43}`. On acceptance this becomes
`{43, 45}` so both shapes pass while the change lands, then `{45}` once a 45-column
delivery has been accepted. Same transition v1.5 used, for the same reason: flipping
straight to 45 rejects every delivery already in flight.

The header check that guards the last five columns extends to the two new ones. A count is
not a schema.

**Part A changes no code and no gate behaviour.** It is a documentation change only.

---

## What does not change

- `SUBMISSION DEADLINE` keeps its exact meaning: the close.
- R5 opportunity typing is untouched. `Awards` was already one of the four values.
- No conference row changes except by gaining two blank columns.
- Customer-owned fields are untouched.
- Every rule in v2.0.1 not named above stands exactly as written.

---

## Open question for the customer, not for upstream

The customer's own February research notes treat **pay-to-play screening** as a first-order
filter:

> "If an award requires a high registration fee to be recognized, or has unclear judges,
> vague criteria, or looks like a certificate mill, treat it as marketing spend, not a
> credibility asset."

That judgement never reached either spreadsheet, so it lives only in their head and the
client cannot see it. Whether it becomes a column, a note, or an exclusion at ingest is
**their** call. We are not inventing one, and this amendment does not assume an answer.
