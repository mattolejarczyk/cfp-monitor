> **STATUS: CURRENT.** Accepted by upstream in full, all four classes, 2026-09-12. Read
> alongside v2.0.1, v2.1, v2.2 and v2.3, which it joins. Numbered v2.4 by upstream's ruling.

# Joint Pipeline Contract - amendment v2.4

## Downstream may repair mechanical defects without a round

    DATE:     2026-09-12
    AMENDS:   section 9 (the review loop)
    RULED:    2026-09-12, accepted in full by upstream

## Why

Seven hand-back documents crossed between us on 2026-09-12. Several existed only to fix defects where
both sides already agreed on the facts - the deadline was right, the page was right, only the
way it was written down was wrong. Each cost a full round trip through a human.

    Round 2    Climate Change quote failed on an added comma and full stop
    Round 2    STATUS DETAILS arrived wrapped in brackets, with en-dashes and curly quotes
    Round 3    three dead URLs you replaced in two fields each were still in a third field
    Rounds 3-4 two SecureWorld quotes wrote "September 19, 2026" where the page says "2026-09-19"

The SecureWorld pair is the costly one. A one-line mechanical fix at round 3 became a wrong
diagnosis at round 4 and a retraction at round 5. A repair rule would have closed it at the
first failure, before anyone had to reason about it.

What still needs you, and always will: every round that needed a new URL, a new date, a
status decision or a duplicate ruling. This amendment does not touch any of those.

## The principle

**Downstream may repair how your claim is WRITTEN, never WHAT it claims.** A repair never
changes a date, a status, a projection flag, an event's identity, or which page is cited. It
never introduces a URL you did not send. If a fix would need any of those, it is not a
repair; it is a finding, and it comes back to you as today.

This keeps downstream obligation 5.1 intact - a grounding claim is never overwritten - and
keeps the two sides independent: you research, we verify, and neither does the other's job.

## The four repair classes

### A. Quote copied from the cited page

**When:** check 3 reports "paraphrase, date IS on page". The cited page resolves and states
the row's own deadline; only the quote's wording differs.

**Repair:** replace `DEADLINE_QUOTE` with the page's own text containing that deadline - the
shortest span that pairs the event or call with the date, copied character for character.

**Only if all hold:**
- `DEADLINE_EVIDENCE_URL` is unchanged and resolves.
- The row's deadline appears on that page, and the chosen span contains it.
- The span is unambiguous: it does not also match a different event, round or date type.
  A page listing the same date for two events, or a span that could be the event date
  rather than the deadline, is NOT repaired.

**Examples from today:** SecureWorld Twin Cities, `September 19, 2026` -> `Twin Cities, MN 2026
2026-09-19`. Climate Change, `Regular, 20 June (26) to 19 October (26).` -> `Regular 20 June
(26) to 19 October (26)`.

### B. Your replacement carried to every field that held the same dead link

**When:** you replace a dead URL in one or more fields, and the identical dead URL is still
present in another field on the same row.

**Repair:** put your replacement in those fields too.

**Only if:** the old URL is byte-identical, it is 404/410 in a real browser, and your
replacement resolves. We never choose a replacement ourselves - this only finishes applying
yours. (On round 3 we withdrew those three third-field links rather than copy your
replacement across; under this class we would have copied it.)

### C. Plain text in prose fields

**When:** `STATUS DETAILS`, `OVERVIEW`, `TRACK` or `CATEGORIES` contain square brackets
wrapping the whole value, en- or em-dashes, curly quotes, or non-breaking spaces.

**Repair:** unwrap the brackets; dashes to a hyphen; curly quotes to straight; non-breaking
to a normal space. Nothing else. Words are never changed.

**Never applied to a quote field** - a quote keeps the page's own characters (standing rule S1).

### D. Withdrawing a citation that is genuinely dead

**When:** a cited URL on a row with a live or blank deadline returns 404 or 410 in a plain
fetch AND in a real browser, and you have not supplied a replacement.

**Repair:** R1 withdrawal only - clear that URL (and its quote, if it was the evidence URL).
The deadline is untouched. `IS_PROJECTED` follows section 9 as written today.

**Never on** a 403, a timeout, an empty page or a CAPTCHA - those stay `not_found` and the
claim stands (5.2).

## Safeguards on every repair

1. **Logged.** Row, field, before, after, which class, and the evidence (for A, the page text
   around the span). Nothing is repaired silently.
2. **Reported to you.** Every repair is listed in the next hand-back or weekly report. You can
   reverse any of them, and a reversal is honoured without argument.
3. **Re-gated.** A repaired delivery goes through the full gate again. A repair can only clear
   the failure it names; it never lowers a check.
4. **Twice means it is a pattern.** If the same row needs the same class of repair on two
   consecutive deliveries, it stops being repaired and comes back to you - the generator is
   producing it, and repairing it forever would hide that.
5. **Customer fields are out of scope.** `NOTES` and `SUBMISSION DATE VERIFIED` are never
   touched by any class.

## One related request: send rules as rule text

As of today, the rules we agree live in a file the research run reads every time
(`standing_rules.md`, eleven rules S1-S11, all from today's rounds). Before today, an update you
made existed only in the chat, so the Saturday run never saw it.

**When you change or add a rule, please send the rule itself** - two or three sentences and the
real case it came from - rather than "the prompt has been updated". We add it to the file, and
the next run uses it.

## Ruling

Upstream's reply, 2026-09-12:

    CLASS-A (quote from cited page):     accept
    CLASS-B (carry your replacement):    accept
    CLASS-C (plain text in prose):       accept
    CLASS-D (withdraw a dead citation):  accept
    RULE-TEXT (send rules as text):      acknowledged

Upstream restated the boundary in its own words: downstream may repair how a claim is written
without altering what it claims; dates, statuses, projections, canonical identities and
original source assignments remain protected. Repairs are logged, reported in subsequent
hand-backs and re-gated, and upstream retains explicit authority to reverse any of them.

On rule text, upstream committed to sending future prompt and operational rule changes as
structured blocks - **context, rule text, primary motivation** - for `standing_rules.md`.
