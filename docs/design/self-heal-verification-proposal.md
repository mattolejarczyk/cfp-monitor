# Self-heal via targeted verification (proposal)

Status: PROPOSAL, 2026-09-22. Not built. Scope it like the promote guard before building.

## The problem

The QBD layer now produces signals that end at "a person should look": a composed-URL flag
(`citation-host-not-in-sources`), a `not_found` deadline, a duplicate whose two rows disagree.
`grounding_review.py` routes each to a concrete action, but a human still does the work. Many
of these are answerable by a single, specific question - and doing them by hand is slow and,
on a busy week, skipped.

## The insight (and the trap)

A specific question - "is the ACT Expo 2027 abstract deadline September or November 2026?" -
is both answerable and *verifiable*. An open "research this conference" prompt is neither: it
lets the model compose a plausible-but-wrong URL, which is the composed-URL problem itself.

The trap, shown by the two conflicts resolved on 2026-09-22: a grounded-search PROSE answer
hedged (it offered both October and December for the Johannesburg conference) and only the
specific cited pages settled it. **So the self-heal must not trust the prose. It must end at a
page it fetched, with a verbatim quote.** This is the project's standing rule - "move the
question until the answer is checkable" - applied to remediation.

## The flow

```
detect            a flagged row (grounding_review / trail / find_duplicate_events conflict)
  -> form         the single specific question the flag implies
  -> ask          grounded search for a candidate answer AND its source URL
  -> FETCH+VERIFY  open that URL through the ladder; the answer must be a literal substring
  -> propose      a confirmation, or an evidenced recommendation for a person
```

## The boundary (the crux - non-negotiable)

- **Auto-apply ONLY a confirmation.** `not_found` -> verified when a fetched citation backs the
  claim the row already makes; raising confidence on evidence. Safe, because nothing the row
  asserts changes - it only gains the proof it lacked.
- **A CHANGE to a claim, a withdrawal, or a two-verified conflict -> a person.** Rewriting a
  citation is the acceptance gate's job, not a heuristic's. A "conflict" between two verified
  deadlines is usually two ROUNDS of one call (R23) - the self-heal recognises that pattern and
  keeps the next-actionable round, it does not pick a winner between two evidenced dates.
- **Never touch a customer-owned field** (STATUS, STATUS DETAILS, NOTES, PRIORITY - contract 3).
- **Never bypass the gate.** A self-heal writes a candidate; the gate still decides what ships.

## What already exists (this is orchestration, not a new engine)

- `scripts/investigate_event.py` - two blind passes over the event's own site; the model's
  answer must be a literal substring of the page it fetched. This IS the ask+verify engine.
- `scripts/extract_citations.py` - cuts the quote from the page, so a paraphrase cannot survive.
- `src/cfp_monitor/fetch.py` / `cdp.py` - the fetch ladder.
- `scripts/apply_resolutions.py --citations` / `Markets/apply_row_patch.py` - the merge guard
  that already refuses a blank-over-populated or an unverifiable citation.

## What to build

`scripts/grounding_selfheal.py`: read a run's flags, form the specific question per row, run the
verify engine, and either (a) write a CONFIRMATION through the existing merge guard, or (b) hand
`grounding_review` a tighter, evidenced recommendation for the residue. Report-only by default;
`--apply` writes only confirmations, backs up first, and logs every change old -> new.

## Non-goals

Auto-withdrawal. Auto-changing a claim or a customer field. Trusting a prose answer without a
fetched quote. Running over every row - it is targeted at flagged rows only, so it stays cheap
and does not re-open the quota problem.

## Risks

A specific question can still return a confident wrong answer; the fetch-and-verify step is the
guard, exactly as it is for research. If the source cannot be fetched, the row stays flagged for
a person - an outage is never written as a finding (2.5/2.6).

## Motivating cases

ACT Expo 2027 (Sept 10 deadline, a spurious Nov 1 duplicate) and the 19th ICCCIR Johannesburg
(Oct 19 regular / Dec 20 late rounds read as a conflict) were both resolved 2026-09-22 by a
specific question plus a manual page check. The manual page check is the part this automates.
