# Input-list audit 20261008-111835 (read-only; changes nothing)

2 rows audited (0 skipped as duplicates or already marked DUP_OF); 0 rows with no readable page; cost 0.0018 USD; 4 minutes. Today 2026-10-08.

**DIFFERS: 3 fields. UNSUPPORTED: 3 fields.** AGREES 2, FILLS 0, NO_VALUE 0.

| field | AGREES | DIFFERS | UNSUPPORTED | FILLS | NO_VALUE |
|---|---|---|---|---|---|
| START DATE | 1 | 1 | 0 | 0 | 0 |
| CONFERENCE DATES | 1 | 1 | 0 | 0 | 0 |
| LOCATION | 0 | 1 | 1 | 0 | 0 |
| SUBMISSION DEADLINE | 0 | 0 | 2 | 0 | 0 |

DIFFERS: the page states another value for THIS edition (verbatim quote); one of the two is wrong and a person looks. UNSUPPORTED: no page of this edition states the hint; unproven, NOT wrong. A date of another year never counts for the edition.

## DIFFERS (3)

- **Decarb Connect Europe 2027** (Utility, edition 2027) START DATE: ours `6/8/2027`, page `2027-04-14`; ok
  - https://decarbconnecteurope.com/  "14 - 15 April, 2027"
- **Decarb Connect Europe 2027** (Utility, edition 2027) CONFERENCE DATES: ours `June 8 - June 10, 2027`, page `2027-04-14 to 2027-04-15`; ok
  - https://decarbconnecteurope.com/  "14 - 15 April, 2027"
- **Decarb Connect Europe 2027** (Utility, edition 2027) LOCATION: ours `Hamburg, Germany`, page `city Vienna, country Austria`; differs in city and country
  - https://decarbconnecteurope.com/  "Vienna, Austria"

## Rows whose id year differs from the edition (1); frozen keys by design, NOT errors

- 2026-nullcon-goa-bambolim  (Nullcon Goa 2027 (18th Edition), Cybersecurity): id year 2026, edition 2027
