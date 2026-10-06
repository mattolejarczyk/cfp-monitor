# ACT-51 part 2: scripts/customer_coverage.py reproduces the ACT-44 classification (2026-10-06)

Every number below comes from a run made on 2026-10-06 (machine date) with the tool in this branch. The tool is read-only: the live database was opened `mode=ro`, the live input lists were not
touched (the 2026-10-05 pre-change input lists were COPIED to a scratch folder). NOT fixture-only: this is the live database and the real input lists.

## What was run

```
# TODAY: live database, live input lists
python scripts/customer_coverage.py --out-dir <scratch>/today
COVERAGE: 131 of 155 customer rows ahead of 2026-10-06 are in the research queue; 24 are NOT; 34 linked rows disagree on date or place

# BEFORE: the same live database, the input lists as they were BEFORE the 2026-10-05 additions
#   (Markets/Cybersecurity_input.pre-customerrows-20261005-193133.bak.csv = 73 rows,
#    Markets/Utility_input.pre-customerrows-20261005-193133.bak.csv = 59 rows, copied to scratch)
python scripts/customer_coverage.py --today 2026-10-05 --markets-dir <scratch copy> --propose <scratch>/repro.csv
COVERAGE: 77 of 155 customer rows ahead of 2026-10-05 are in the research queue; 78 are NOT; 34 linked rows disagree on date or place
```

So the number of customer rows ahead and not in the queue went from 78 (before the by-hand additions) to 24 (today). (A first version, pairing by URL alone, said 76 and 20; the reviewer's rule that the same website is not a pairing without a matching date
added 2 and 4: ECML PKDD, whose customer date 2026-09-07 is stale for the 2027 edition on our list, and a few same-site rows of other editions.)

## Reproduction against docs/qa/customer-unmatched-classified-20261003.csv (84 rows: 57 C, 23 D, 2 B, 2 A)

Compared by name or normalised URL, the 78 rows of the BEFORE run against the ACT-44 classes:

| ACT-44 class | rows | found by the tool |
|---|---|---|
| C (not held, still ahead) | 57 | 57 (all, re-run after the date rule) |
| B | 2 | 1 (Google Cloud Next Las Vegas) |
| A (matcher miss: held under another name) | 2 | 0 (correct: it-sa Expo & Congress, ACS Green Chemistry Institute are held, so not missing) |
| D (event already over) | 23 | 0 (correct: excluded as over) |

One finding came out of the reproduction and was fixed with a test (`test_a_past_date_with_a_later_year_in_their_url_is_not_called_over`): ECML PKDD carries a 2026 start date on the sheet but its
URL is the 2027 edition (https://ecmlpkdd.org/2027/). The first version treated it as over and missed it; a past date whose own URL names a later year is now treated as ahead (a date is not proof
of the right edition).

## What the tool finds that the 2026-10-03 matcher did not (about 19 rows in the BEFORE run; 24 not in the queue today)

These customer rows were matched on 2026-10-03 (to a held event, rightly or not), so the ACT-44 unmatched list never showed them, but NO row of the research input lists has their id or URL.
Six are linked to an event we hold in the database (Sustainable Aviation Futures (NAM), Clean Tech Forum, CO2-based Fuels and Chemicals Conference, ARPA-E Summit, European Biomass Conference &
Exhibition, CES): held but not on the Utility input list, so not researched weekly. Fourteen are unlinked (no event id): Hydrogen Technology Expo MENA, Carbon Capture Technology Expo MENA,
Gartner Identity & Access Management Summit, Google Cloud Next, Google Cloud Next Las Vegas, OWASP Global AppSec EU, OWASP Global AppSec USA, Wild West Hackin' Fest @ Mile High, World Summit AI
Amsterdam (starts 2026-10-07, before add_customer_rows.py's --min-start, so skipped on purpose), ODSC West, SANS AI Cybersecurity Summit, Nullcon Berlin, SXSW AI Track, FIRST Con.
Several of these are probably a DIFFERENT EDITION of an event we do research (our Gartner IAM row is the 2026 edition; the customer's is 2027-03-08). Whether each is a true gap is a judgement the
reviewer should make row by row; the tool states only that no input row has the id or the URL. Excluded today: 69 rows (event over, removed from the customer's sheet, DUP_OF, ledger), each with its
reason in `coverage.md`.

## Limits, said plainly

* "In the queue" means an input row of that market carries the same canonical id or the same normalised URL. Same URL on a different edition counts as in the queue (a different-year URL does not
  match); the tool cannot tell an edition from its page.
* A row with no start date is treated as ahead.
* The ledger `docs/operations/customer_not_researched.csv` is empty; only the operator adds to it.

## LINKED BUT DISAGREES (added at the reviewer's request, 2026-10-06)

34 customer rows today are linked to an event whose start date is more than 30 days from the customer's date, or whose city is not named in the customer's location. Hack In The Box is
among them (customer: Alila SCBD, Jakarta, 2026-04-29; linked event 2026-hack-in-the-box-phuket, Phuket, 2026-08-24, 117 days and a different city). Most of the others are a customer row for
one edition linked to the neighbouring year's event (for example Black Hat USA: customer 2027-07-31, linked event 2026-08-01). A few city hits are noise (the customer's text names a venue, the
event's city is its suburb: Goyang vs KINTEX, Kissimmee vs Orlando). The list is report-only; a person decides which side is right.
