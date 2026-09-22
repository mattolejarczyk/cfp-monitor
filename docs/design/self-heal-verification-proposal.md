# Self-heal via targeted verification (proposal)

Status: SCOPED + APPROVED, 2026-09-22. Phase 1 next, built report-only first. The builder does
not grade itself - a separate pass verifies each phase before it earns `--apply`.

## Decisions (operator, 2026-09-22)

1. **Auto-apply only on DEFINITIVE evidence** - a verbatim quote located on a page we fetched.
   Anything short of that stays a person's call.
2. **Budget ramps with proof.** 2-3 rows the first run, expand toward ~10 once it is shown
   correct against the gate. Grounded requests (the fallback below) are **sequential and
   human-paced** - a random multi-second gap between requests, one at a time, never hammered -
   reusing the existing rate limiter, never a private one.
3. **A reusable capability, callable anywhere.** The core is "construct a specific question,
   get evidence, verify it" - usable at any point the data needs confirmation, not one wired
   step. It is wired into the workflow at the review stage to start, and exposed as a library
   function others can call.

## Architecture refinement (from the discovery/verification boundary)

`cfp-monitor`'s half is VERIFICATION, not grounded search (see `investigate_event.py` header,
and contract 5). So self-heal is **verification-first**:

- **Primary - VERIFY (free, no grounded request).** For a flagged row, fetch its candidate page
  through the ladder (`investigate_event`'s machinery) and confirm the claim is a literal
  substring. Most `not_found` rows have a page; re-grounding one we can fetch is "paying for the
  wrong thing".
- **Fallback - ASK (grounded, throttled, upstream's half).** Only when verification has no page
  to check does the specific question go to grounded search. The 2-3->10 budget and the
  human-paced spacing govern THIS path. A grounded answer is never trusted until its cited page
  is fetched and the quote confirmed.

So "ask Google a specific question" is the exception, and the common case is a free, checkable
fetch. The reusable core exposes both: `verify_claim(claim, url|site)` and, behind the budget,
`ask_then_verify(question)`.

## Evidence capture from the grounded step (QBD - operator, 2026-09-22)

The grounded ask is not just an answer, it is EVIDENCE, and it is captured - the same signals
the grounding trail already records:

- **Queries + sources go into a self-heal trail** (like `<output>.grounding.jsonl`): what was
  asked, what came back, which page was fetched, the verbatim quote found (or why it failed).
  Every attempt is auditable, and the residue feeds `grounding_review`.
- **The sources ARE the verify targets, and the citation we keep.** `grounding_chunks[].web`
  gives the real domain in `.title` and a Google redirect in `.uri`; **the redirect resolves to
  the actual deep page**, so following it yields the precise URL to fetch, verify, and store as
  the citation. This is the redirect-host fix from the trail work, reused: the ask hands us the
  page, the fetch proves the sentence, and the confirmed URL+quote becomes the evidence on the
  row. One unbroken chain: ask -> capture source URLs -> fetch -> prove -> confirm with citation.

So a self-heal never writes a bare "verified" - it writes a URL and a verbatim quote, exactly
what the gate demands of any citation. Evidence in, evidence stored.

## Provenance - know what produced each piece of evidence (operator, 2026-09-22)

Every result and every stored confirmation carries a **`method`** label, so we always know how
a fact was verified and can trust it accordingly (mirrors `evidence.origin`):

- `fetch:date-context` - the deadline was found on the row's already-cited page (free, Phase 1).
- `ask+verify:grounded` - grounded search found the page, which was then fetched and the quote
  proven (the throttled fallback).
- future methods name themselves; an un-labelled confirmation is a defect.

The self-heal trail and the report group by method, so "what produced this evidence, and by
which route" is answerable for any row.

### The method vocabulary (one definition: `src/cfp_monitor/verify_methods.py`)

Every result names its method from this registry - a label not registered here is a defect.
Categorised on three axes so the data slices any way: SOURCE (how the page was got), MATCH (how
the claim was confirmed), COST (what it spends).

| id | source | match | cost | when it applies |
|---|---|---|---|---|
| `fetch-plain+regex` | plain-http | date-context-regex | **free** | The floor: a plain GET, deadline located in a submission context. A `not_found` row already failed this, so it re-confirms little. |
| `browser-ladder+regex` | real-browser | date-context-regex | **free** | Escalation for JS/403 pages a plain GET cannot read - the signed-in Chrome on :9222 (`render_targets`). No grounded quota; slower. |
| `llm-verbatim` | real-browser | llm-verbatim | llm | The model finds the sentence stating the known deadline; it must be a literal substring of the fetched page. For date forms the regex misses. OpenRouter, not grounded quota. |
| `grounded-search+verify` | grounded-search | date-context-regex | **grounded** | The throttled exception: grounded Google search finds the CURRENT page when the cited one is stale; the answer is then fetched and the quote proven. Budgeted, human-paced. |
| `upstream-grounding` | upstream | none | grounded | The original citation from upstream's grounded research (`evidence.origin=grounding`). Recorded for provenance; not produced by self-heal. |

Phase 1 ships the two **free** methods and escalates plain -> browser only when a page is
unreadable. The two paid methods (`llm-verbatim`, `grounded-search+verify`) are later phases.

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

## Phase 1 finding (measured 2026-09-22, report-only)

Built report-only and run over all 34 not_found rows that carry a deadline + a cited URL.
**Result: 0 confirmable** - 21 flagged (the plain page did not state the deadline in a
submission context), 13 unreadable (403/JS). This is not a failure, it is the lesson: those rows
are `not_found` BECAUSE `verify_grounding` already ran the same cheap `fetch_text` on them.
Re-running the identical primitive reproduces the identical wall.

So the value is NOT in re-verifying with the free primitive - it is in ESCALATING past what
already failed:
- **the 13 unreadable** -> the BROWSER LADDER (investigate_event's real-Chrome fetch), still
  verification, still free / no quota. Read the JS pages plain HTTP cannot.
- **the 21 flagged** -> the cited URL is likely stale; the GROUNDED FALLBACK finds the CURRENT
  page (the quota path), and the answer is then fetched-and-verified as usual.

Correction to the architecture note above: "verification-first is the free common case" holds
for a FRESH row, but NOT for the not_found backlog, which by definition already spent the free
check. The escalation plugs into the same `Verifier` seam - a better verifier, same contract.
The report-only foundation (row selection, customer guard, method provenance, trail, report)
stands; the next build is the escalating verifier.

## Motivating cases

ACT Expo 2027 (Sept 10 deadline, a spurious Nov 1 duplicate) and the 19th ICCCIR Johannesburg
(Oct 19 regular / Dec 20 late rounds read as a conflict) were both resolved 2026-09-22 by a
specific question plus a manual page check. The manual page check is the part this automates.
