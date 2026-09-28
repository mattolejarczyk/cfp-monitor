# Gap 5 - next year's editions are not picked up

**Status:** theory written 2026-09-28, not started. Found while checking gap 4a.
**Priority:** the most customer-relevant gap - "when does the next one open?" is the question the
customer actually plans around. Sits UPSTREAM of gap 4a: design this first, then switch 4a on as
part of it, not before.

## What happens today (measured on the 2026-09-27 research)
Of 41 rows whose event had already run ("Watching"), the research re-examined the OLD edition and
reported it concluded. It almost never moved to next year. Its own notes show the next edition was
often visible and not captured:
- Infosecurity Europe 2026 - "the official site has transitioned to promoting the 2027 edition";
  the row stayed 2026, Closed.
- Gartner Security & Risk Management Summit (National Harbor, Japan) - "concluded"; no 2027 row.
- Future Fuels MENA Summit 2026 - "rescheduled to April 2027"; the row stayed 2026.

## Why
The research is asked about the row as named ("Infosecurity Europe 2026"), so it answers about 2026.
The pipeline contract (section 6, v1.3) already agreed what should happen and it was never built
into the research runner:
- **R13** - an edition that has run is `Watching`: "do not re-research this row's own facts; search
  only for the successor". Its values are final.
- **R14** - a successor is accepted only if its start date is more than 25 days after the concluded
  edition's, is in the future, and is the same series (same organiser and identity, not a co-located
  event). Annual cadence is never assumed; "no successor yet" is a normal outcome. The successor
  inherits identity only (name stem, site, market, categories, opportunity type); dates, deadline,
  status and every citation are researched fresh. Names with ordinals or year ranges are read from
  the event's own page, never generated.
- **R15** - any addition is checked against the WHOLE list, archived rows included, on four signals
  (series key, name similarity, website, city + organiser). Partial matches are declined and
  flagged, never merged on a guess.
Once a successor exists, the old row becomes `Archived` automatically (lifecycle.edition_states).

## A trap in what was built this weekend
The automatic load (weekend_import) holds back any row without a permanent id, so a rename cannot
create a duplicate. A genuine next edition IS a new event with no id yet - today it would be held
back forever. The design must give a successor that passed R14/R15 a new permanent id deliberately,
while still refusing every other unknown row.

## Ideas to test, one at a time
- **5a Measure what is out there (free, no AI).** For each Watching row, open the event's own site
  (our crawler) and look for the next edition: a later year with dates, "save the date", a new CFP
  page. Measures how many successors are already announced and findable without AI.
- **5b Ask the successor question (costs AI - budget to be agreed).** For a sample of ~10 Watching
  rows that 5a says have an announced successor, research "<series> <next year>" instead of the old
  edition. Measure: successor found, dates correct against the event's own page, R14 tests passed,
  R15 finds no duplicate.
- **5c How it lands (free, on copies).** Run weekend_import's rules over the 5b results in a
  sandbox: the successor gets a new permanent id only after R14 + R15 pass; the old row goes
  Archived; the customer sheet match (a customer tracking "DEF CON 34" with a 2027 estimate) points
  at the new edition. Invariants must hold.

## "Proven" means
Successors found for rows whose next edition is announced, each with correct dates from the event's
own page, zero duplicates, zero co-located events mistaken for a successor, and the customer's
tracked rows following the new edition.

## Relation to the other gaps
- 4a (skip past events) becomes part of this: a Watching row's own facts are not re-researched (R13),
  and the research effort moves to the successor question instead.
- Independent of gaps 1-3 (how a single question is researched); a successor row goes through the
  same research, links and quote fixes as any other row once those land.
