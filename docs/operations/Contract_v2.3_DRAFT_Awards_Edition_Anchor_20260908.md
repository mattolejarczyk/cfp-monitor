> **STATUS: CURRENT.** Adopted by both sides 2026-09-08, in full. Read alongside
> `Joint_Pipeline_Contract_v2.0.1_CONSOLIDATED_20260905.md` and amendments `v2.1` and `v2.2`,
> which it joins. Those four are the only documents in this folder that are in force.
> See `README.md`.
>
> The filename still says DRAFT. It is kept as-is on purpose: 2.1 labels a document rather
> than renaming it, and every reference already sent to upstream points at this name.

# Joint Pipeline Contract - amendment v2.3

**Amends R19.1 / R25.1.** `EDITION` has no defined derivation for an award, because the rule
anchors it to `START DATE` and most awards have none. We agree with your direction - the
program year, not the year a nomination window happens to open - and this drafts it.

**We also measured it before writing, and the measurement changed the rule.** A mechanical
reading of "use the ceremony year" would have blanked 41 of 127 rows and moved two of them
backwards. Section 3 is that finding; it is the reason this draft is shaped the way it is.

---

## 1. The problem, stated precisely

R19.1 anchors `EDITION` to the year of `START DATE`. For a conference that is exact and
mechanical: the event happens on a day, and that day has a year.

**68 of 127 awards rows have no `START DATE`, and for those the rule has no defined
behaviour.** The results are already inconsistent in the delivery you hold:

    Globee Awards for Cybersecurity            EDITION 2026    deadline 2027-02-04
    Security Excellence Awards - Computing UK  EDITION 2027    deadline 2026-11-27

Same situation, opposite answers, both produced by the same generator on the same day. A rule
with undefined behaviour does not produce blanks; it produces confident answers that disagree
with each other.

Note that 23 of 127 awards rows carry an `EDITION` year that differs from their deadline year,
and **most of those are correct**. An award's nomination window routinely opens in the calendar
year before the prize it feeds. That is the normal shape of an award, not an error - which is
exactly why the rule has to say which of the two years wins rather than leaving it to be
inferred.

---

## 2. Proposed R25.1a - the anchor ladder for an Awards row

`EDITION` is **the cycle year the award itself represents**. Where `OPPORTUNITY_TYPE` is
`Awards`, derive it in this order and stop at the first that answers:

| | Anchor | Condition |
|---|---|---|
| **1** | **The award's own statement of its cycle**, quoted from its page | Always preferred. "2027 (36th) Blue Planet Prize" settles it and nothing else needs consulting. |
| **2** | The year of `ANNOUNCEMENT_DATE` | **Only where that date is not earlier than `SUBMISSION DEADLINE`.** See section 3. |
| **3** | The year of `START DATE` | Unchanged from R19.1, so no conference row moves. |
| **4** | **Leave `EDITION` exactly as delivered and set `IS_PROJECTED` true** | No anchor. Do not blank it, and do not fall back to the deadline year. |

**`SUBMISSION DEADLINE` is never an anchor.** It is the input the rule exists to stop being
used, because it is the one field that systematically disagrees with the answer.

---

## 3. What the measurement changed, and why rung 4 does not blank

We ran the ladder over all 127 awards rows before proposing it.

**41 rows have no anchor at all** - no `ANNOUNCEMENT_DATE`, no `START DATE`. A ladder that
ends in "blank it" would empty `EDITION` on nearly a third of the delivery, replacing a
plausible year with nothing. That inverts principle 2.1: absence is a **label**, not a
deletion. So rung 4 keeps the delivered value and labels it projected. The customer keeps a
usable year and can see it is not verified, which is the honest state of it.

**10 rows would move, and two of them would move the wrong way:**

    Globee Awards for Cybersecurity        2026 -> 2027    correct, deadline is 2027-02-04
    Zayed Sustainability Prize 2027        2026 -> 2027    correct, the row's own name says 2027
    Cleantech Global Cleantech 100 2026    2026 -> 2027    correct
    ...
    The Earthshot Prize 2025               2026 -> 2025    WRONG
    Grist 50 2026                          2026 -> 2025    WRONG

Earthshot and Grist are both long past - deadlines 2024-12-11 and 2025-03-14. Their
`ANNOUNCEMENT_DATE` records the announcement of a cycle that has **already happened**, so
using it as the anchor drags the edition backwards into history rather than forwards into the
cycle the row is meant to describe.

Hence the condition on rung 2: `ANNOUNCEMENT_DATE` anchors the edition only when it is not
earlier than the submission deadline. An announcement before the deadline it supposedly follows
belongs to a previous cycle and is evidence about the past, not about this row.

**This is the same failure the passed-deadline exemptions exist for** - v1.4 for criterion 3,
v2.2 for criterion 2. A stale row's fields describe a cycle that has ended, and any rule that
reads them as current gets a confidently wrong answer. Three amendments have now hit it from
three directions.

---

## 4. Not retroactive, and it must not move a key

**Two constraints we would ask to be written into the amendment rather than left to
implementation.**

**4.1 It applies to future runs. It does not rewrite the 51 rows it would change.** Amendment
v1.4's implementation made exactly this call: where no date existed, `fix_edition.py` changed
nothing rather than guessing from the name. A rule adopted today should not silently rewrite a
third of a delivery the customer has already read.

**4.2 Changing `EDITION` must not move a canonical key.** This is the expensive one and it is
already on the record: `event_id()` builds its key from `EDITION`, so when 67 of 392
conference rows were found carrying an edition that disagreed with their start date, the
mismatch had **already created two duplicate database records**. The fix was not to rewrite 67
keys - it was to freeze `key_year` first, so the key stops being read as a fact.

**A key is a name, not a fact.** Any implementation of this amendment freezes `key_year` from
the current edition before deriving anything, and never touches `event_id`. Under R24/R25 the
identity of a row does not change because we improved our description of it.

---

## 5. What does not change

- **Conferences.** Rung 3 is R19.1 unaltered. The ladder is scoped to `OPPORTUNITY_TYPE`
  `Awards`, so no conference row consults it at all; a conference with a `START DATE` derives
  its edition exactly as it does today.
- **`IS_PROJECTED` and `GROUNDING_CONFIDENCE`** keep their existing meanings. Rung 4 sets
  projected because an unanchored edition is a projection, which is what the flag is for.
- **No new column.** `ANNOUNCEMENT_DATE` already exists - v2.1 added it as part of R26 for
  precisely this shape of award, and this is the second use it has earned.
- **No schema change**, so the `{43, 45}` transition window is unaffected.

---

## 6. What we asked, and what was agreed

Agreement on the four-rung ladder, on rung 2's condition, and on 4.1 and 4.2.

**Accepted in full, 2026-09-08**, with the ladder, rung 2's `ANNOUNCEMENT_DATE >=
SUBMISSION DEADLINE` guard, the non-retroactive scope and the key freeze all confirmed.
Upstream carries the ladder into the generator's research sweeps; downstream implements it in
its derivation logic.

---

## 7. Implementation note - which side owns which rung

Recorded here because it is not obvious from the ladder alone, and a reader of the code should
not have to rediscover it.

**Rung 1 is upstream's and cannot be computed downstream.** It reads the award's own statement
of its cycle off the page. That is an evidence judgement made while looking at the source, not
a calculation over a delivered row: `cloud-awards.com/programs/` states four different years
for four sibling programmes on one page, so a downstream regex over a stored quote would
produce exactly the confident wrong answers this amendment exists to stop.

**Rungs 2, 3 and 4 are computable from a delivered row** and are what downstream implements.

Where an edition upstream evidenced under rung 1 disagrees with what downstream's rung 2 would
derive, **downstream reports the disagreement and does not overwrite it.** An evidenced answer
outranks a derived one, and a silent overwrite would discard the better of the two.
