# Joint Pipeline Contract - amendment v1.7: additive sponsorship capture

**2026-08-31. Agreed in principle by upstream the same day; this is the formal specification.**

Supersedes nothing. v1.5 stands unchanged - the four discovery fields remain upstream's and
`SPONSOR_QUOTE` remains downstream's. This adds one narrow permission on top.

---

## Why

v1.5 divided the sponsorship claim the same way a deadline is divided: upstream supplies the
claim and the page, downstream fetches the page and proves the sentence is on it.

That division is right, and it makes downstream's half **entirely dependent** on upstream's.
`extract_sponsor_quotes.py` selects rows where `SPONSOR_URL` is non-empty. On 2026-08-31, zero
rows had one, so the tool had never run on a single row since it was written.

Meanwhile R19.1 - in upstream's half of the contract - already establishes the principle:

> Populate `SPONSOR_*` **while already on the conference site for another reason**. If a speaking
> page says sponsorship is required, or links a prospectus, capture it then. **The marginal cost
> is close to zero.**

That reasoning describes downstream as accurately as upstream. The weekly verification sweep
fetches every cited page through the full escalation ladder, for every row, every week. It reads
the deadline and walks past a sponsorship requirement in the same paragraph, because the field is
not ours to write.

The two passes differ usefully: upstream's is **thorough and periodic**, downstream's is
**shallow and weekly**. Neither replaces the other.

---

## R21 - Sponsorship capture is additive, and the blank is the boundary

**R21.1 - Downstream may fill only what upstream left empty.**
Downstream may populate `SPONSOR_REQUIRED`, `SPONSOR_URL` and `SPONSOR_COST` **only** where
upstream has left the field `Unknown` or blank. A value upstream has set is never overwritten,
never contradicted, and never cleared by downstream.

*Consequence:* an upstream row can only gain. It cannot change under this rule, which is what
makes the permission safe to grant without a conflict-resolution procedure.

**R21.2 - Provenance is recorded, and it stays out of the delivery.**
Every value downstream writes is attributed in downstream's own store, not in the delivery
schema. The delivery carries the value; the database carries who established it and when.

*Two reasons this is not a 44th column.* Provenance is an audit fact about our process, not a
fact about the conference - the customer-facing schema deliberately excludes exactly this kind
of field. And the schema has just cost both sides a blocked delivery by drifting; widening it
again in the same week to carry internal bookkeeping would be poor sequencing.

Downstream reports what it filled in the ordinary hand-back, so upstream can adopt, correct or
reject any of it.

**R21.3 - The evidence bar does not move.**
Anything downstream writes carries a `SPONSOR_QUOTE` extracted from a page downstream fetched
itself, proven a literal substring of that page. The model selects from text we hold; it never
composes. A cost figure with no provable source is worse than no answer - it either kills an
opportunity or commits real budget.

**R21.4 - `ORGANIZER` remains upstream's alone.**
It is an identity fact established at discovery, not something picked up opportunistically, and
two sources naming an organisation differently is a conflict with no clean resolution. Downstream
does not write it under any circumstance.

**R21.5 - `Unknown` is still a complete answer.**
This amendment does not turn `Unknown` into a defect. R19.2 stands: where nothing is visible,
`Unknown` with the rest blank is honest and finished. R21 covers the narrower case where the
information is **on a page we have already downloaded** and simply going unread.

---

## What this does not change

- **The four fields are still upstream's** to research, and upstream remains the source of
  record. R21 is a gap-filler, not a transfer.
- **R18.1** - `SPONSOR_REQUIRED` stays three-valued with `Unknown` as the default.
- **R18.2** - `SPONSOR_COST` stays TEXT. It is rarely one figure.
- **R18.3** - a sponsorship claim still carries its own evidence.
- **R18.4** - these fields remain exempt from R1 withdrawal.
- **R19.3** - dedicated sponsorship research still happens only on a named list. R21 should
  *reduce* how often that path is needed, not replace it.

---

## Implementation on downstream's side

1. The weekly sweep already fetches the page. Sponsorship extraction rides on that fetch - no
   additional request, no additional quota.
2. `extract_sponsor_quotes.py` gains a second source of candidate pages: where `SPONSOR_URL` is
   blank, the conference's own submission or speaking page already in hand.
3. A row is written only when `locate_verbatim` proves the quote is in the fetched text. The
   existing safety property is reused, not reimplemented.
4. Every write is attributed and appears in the next hand-back.

**Not to be built until upstream's 43-column export lands.** Until then there is no column to
write into, and building against a schema that is not yet emitted is how the last gap was
created.

---

## Status

| | |
|---|---|
| Proposed | 2026-08-31, with the hand-back on the 36-column defect |
| Agreed in principle | 2026-08-31, upstream: *"pragmatic, low-risk, and mutually beneficial"* |
| Formal specification | this document |
| Implementation | **blocked on the 43-column export**, deliberately |
