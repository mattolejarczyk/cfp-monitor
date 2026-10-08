# Input-list audit 20261008-114906 (read-only; changes nothing)

10 rows audited (3 skipped as duplicates or already marked DUP_OF); 4 rows with no readable page; cost 0.0045 USD; 1 minutes. Today 2026-10-08.

**DIFFERS: 3 fields. UNSUPPORTED: 35 fields.** AGREES 2, FILLS 0, NO_VALUE 0.

| field | AGREES | DIFFERS | UNSUPPORTED | FILLS | NO_VALUE |
|---|---|---|---|---|---|
| START DATE | 1 | 1 | 8 | 0 | 0 |
| CONFERENCE DATES | 1 | 1 | 8 | 0 | 0 |
| LOCATION | 0 | 1 | 9 | 0 | 0 |
| SUBMISSION DEADLINE | 0 | 0 | 10 | 0 | 0 |

DIFFERS: the page states another value for THIS edition (verbatim quote); one of the two is wrong and a person looks. UNSUPPORTED: no page of this edition states the hint; unproven, NOT wrong. A date of another year never counts for the edition.

## DIFFERS (3)

- **Cloud & Cyber Security Expo London 2027** (Cybersecurity, edition 2027) START DATE: ours `3/3/2027`, page `2027-03-10`; ok
  - https://www.cloudsecurityexpo.com/  "WEDNESDAY 10 MARCH 2027 - 09:00 - 17:00"
- **Cloud & Cyber Security Expo London 2027** (Cybersecurity, edition 2027) CONFERENCE DATES: ours `March 3 - March 4, 2027`, page `2027-03-10 to 2027-03-11`; ok
  - https://www.cloudsecurityexpo.com/  "WEDNESDAY 10 MARCH 2027 - 09:00 - 17:00 || THURSDAY 11 MARCH 2027 - 09:30 - 17:00"
- **Cloud & Cyber Security Expo London 2027** (Cybersecurity, edition 2027) LOCATION: ours `ExCeL London, London, United Kingdom`, page `city London, country UK`; differs in country
  - https://www.cloudsecurityexpo.com/  "Excel London || The UK's Leading Cyber Security & Cloud Event"

## Rows whose id year differs from the edition (7); frozen keys by design, NOT errors

- 2026-nullcon-goa-bambolim  (Nullcon Goa 2027 (18th Edition), Cybersecurity): id year 2026, edition 2027
- 2026-industrial-net-zero-conference-sydney  (Industrial Net Zero Conference 2027, Utility): id year 2026, edition 2027
- 2026-nineteenth-international-conference-on-climate-johannesburg  (International Conference on Climate Change: Impacts and Responses 2027 (19th ICCC), Utility): id year 2026, edition 2027
- 2026-decarb-connect-north-america-houston  (Decarb Connect North America 2027, Utility): id year 2026, edition 2027
- 2026-act-expo-las-vegas  (ACT Expo 2027 (Advanced Clean Transportation Expo), Utility): id year 2026, edition 2027
- 2026-co2-based-fuels-and-chemicals-conference-cologne  (CO2-based Fuels and Chemicals Conference, Utility): id year 2026, edition 2027
- 2026-european-biomass-conference-exhibition-reims  (European Biomass Conference & Exhibition, Utility): id year 2026, edition 2027
