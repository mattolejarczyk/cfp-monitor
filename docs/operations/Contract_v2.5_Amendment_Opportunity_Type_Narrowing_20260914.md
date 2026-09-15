# Contract Amendment v2.5 - OPPORTUNITY_TYPE narrowing

    STATUS:        CURRENT
    DATE ADOPTED:  2026-09-14 - accepted by upstream in full, number assigned by upstream
    AMENDS:        Joint Pipeline Contract v2.0.1 (consolidated), as amended through v2.4
    REQUEST:       Handback_Opportunity_Column_20260914.md

## The rule

`OPPORTUNITY_TYPE` is restricted to **actionable submission opportunities**:

    Speaking      the default, and unsuffixed in the canonical key
    Awards        an awards entry with its own deadline
    Exhibiting    a booth, stand or exhibitor application

`Registration` is **retired** and will no longer be emitted.

## Why

`event_id` is minted as `<year>-<name>-<city>[-<opportunity>]`. OPPORTUNITY is in the key
deliberately, because one event can run several calls with different deadlines - a call for
presentations **and** an awards entry - and a single key would silently lose one of them.

That justification does not reach attending. Measured on 2026-09-14, across both live and
prospect markets:

    OPPORTUNITY = Exhibiting     9 rows
    OPPORTUNITY = Registration   8 rows
    ------------------------------------
    rows carrying a SUBMISSION DEADLINE:   0 of 17

Seven had additionally split a record in two against the same event's unsuffixed speaking key.
Three of those pairs were empty on both sides - SANS Cyber Defense Initiative 2026 carried no
deadline and no submission URL on either row, and both were `contradicted`.

## The failure mode this closes

A registration row's evidence reads exactly like call evidence until it is read. Singapore
International Energy Week's registration row cited `https://www.siew.gov.sg/` and quoted:

    "Registration is now open for the 19th Singapore International Energy Week (SIEW),
     taking place from 26 to 30 October 2026 in Singapore"

A true sentence about a ticket desk. Merging the two SIEW rows would have carried it onto the
speaking row as its **deadline quote**, with `STATUS = Open` beside it. The same confusion - an
open registration page read as an open call for speakers - produced the CES 2027 false
contradiction retracted in round 3.

**An open ticket desk says nothing about whether a call is open.**

## Exhibiting - upstream's operational commitment

Booth application, exhibitor entry and early-bird sponsorship closing dates exist on select
events and **will be supplied with supporting citations where published on the event's site**.
Where a site is silent, `SUBMISSION DEADLINE` stays blank and `CFP MODEL TYPE` defaults to
`Rolling Form` or `Not Announced`. No date is inferred.

This is the same standard as every other date on the row: an honest blank beats a confident
guess (2.6), and declining beats guessing (2.5).

## Downstream handling of the existing rows - approved by upstream

Where a `Registration` row duplicates a `Speaking` row for the same event, the **speaking row
survives and keeps its key**, and only NON-SUBMISSION metadata crosses to it - organizer,
overview, categories, sponsorship. A retired row never supplies a deadline, a quote, an
evidence URL, a verify state or a submission URL.

Applied 2026-09-14: 6 groups merged, 407 -> 401 rows, all 111 customer matches intact, the
acceptance invariants green. Every deletion is recorded in `docs/operations/merged_rows.txt`
with its reason and every field change, and the seeds' `EVENT_ID_CANON` is repointed at the
survivor so a later import updates rather than re-inserting.

Two rules were added downstream while applying it, both from cases the drafts walked into:

- **A retired row never survives a merge.** The first Gartner IAM draft kept the registration
  row and deleted the speaking row, taking the speakers URL off the row it was deleting. The
  surviving record of a speaking opportunity would have been keyed, and named, as a ticket desk.
- **A customer match to a retired row BLOCKS the merge** rather than being re-pointed.
  Re-pointing someone's own match is not a merge decision (contract 3).

## Two rows kept, not retired

`Registration` rows with no speaking counterpart are **not duplicates** - they are the only
record we hold of that event, and deleting one would lose the event rather than a copy (2.1):

    2026-rng-conference-dana-point-registration            RNG Conference 2026
    2026-international-pulp-week-vancouver-registration    International Pulp Week 2027

Both are kept as they stand. Under this amendment the next research cycle should emit them as
`Speaking`, which mints an unsuffixed key; the duplicate that creates is expected, will be
reported by `find_duplicate_events.py`, and will be merged under the rule above. Flagged here so
neither side reads it as drift.

## Not changed

Upstream's `EVENT_ID` values are unaffected (5.4). This amendment governs what the
`OPPORTUNITY_TYPE` column may contain, and nothing else.
