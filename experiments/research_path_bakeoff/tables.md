## T1 totals (40 rows)

| arm | answered | right | wrong | blank | no-key | cited page states the date (yes / no / unreadable / no URL) | quote on page (yes / no) | USD | searches | mean s | median s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A grounded (current) | 40 | 18 | 2 | 3 | 17 | 12 / 11 / 0 / 1 | 3 / 20 | 4.854 | 306 | 23 | 25 |
| B search+fetch+extract+prove | 40 | 12 | 1 | 10 | 17 | 14 / 0 / 0 / 0 | 14 / 0 | 0.383 | 0 | 25 | 19 |
| C OpenAI web_search (via OpenRouter) | 40 | 15 | 2 | 6 | 17 | 15 / 3 / 0 / 0 | 11 / 7 | 0.818 | 72 | 8 | 8 |
| D Codex CLI --search | 40 | 16 | 0 | 7 | 17 | 16 / 1 / 0 / 0 | 12 / 5 | 0.000 | 0 | 17 | 15 |

## By key source (hard = person-confirmed or customer-verified; soft = the shipped value, which came from the grounded path)

| arm | hard: right / wrong / blank (n) | soft: right / wrong / blank (n) |
|---|---|---|
| A grounded (current) | 6 / 1 / 1 (8) | 12 / 1 / 2 (15) |
| B search+fetch+extract+prove | 5 / 1 / 2 (8) | 7 / 0 / 8 (15) |
| C OpenAI web_search (via OpenRouter) | 6 / 1 / 1 (8) | 9 / 1 / 5 (15) |
| D Codex CLI --search | 8 / 0 / 0 (8) | 8 / 0 / 7 (15) |

## Agreement between arms (rows where both gave a date)

| pair | both dated | agree | agree and right | agree and wrong | disagree: first right | second right | neither |
|---|---|---|---|---|---|---|---|
| A vs B | 13 | 12 | 11 | 0 | 0 | 0 | 1 |
| A vs C | 16 | 14 | 12 | 1 | 1 | 1 | 0 |
| A vs D | 16 | 14 | 13 | 0 | 0 | 2 | 0 |
| B vs C | 11 | 9 | 9 | 0 | 1 | 0 | 1 |
| B vs D | 11 | 10 | 10 | 0 | 0 | 1 | 0 |
| C vs D | 16 | 14 | 13 | 0 | 0 | 2 | 0 |

## Every row

| # | event | key (source) | A | B | C | D |
|---|---|---|---|---|---|---|
| 1 | AI Summit New York | (blank) (shipped) | - (no key); page no-date | - (no key); page no-url | - (no key); page no-url | - (no key); page no-url |
| 2 | Carbon Capture Technology Expo MENA 2026 | (blank) (shipped) | 2026-04-24 (no key); page no | - (no key); page no-url | - (no key); page no-url | - (no key); page no-url |
| 3 | Carbon Capture USA 2026 | (blank) (shipped) | - (no key); page no-url | - (no key); page no-url | - (no key); page no-url | - (no key); page no-url |
| 4 | CarbonZero Global Conference & Exhibition 202 | 2026-09-10 (shipped) | - blank; page no-date | - blank; page no-url | - blank; page no-url | - blank; page no-url |
| 5 | Future Fuels MENA Summit 2026 | (blank) (shipped) | - (no key); page no-date | - (no key); page no-url | - (no key); page no-url | - (no key); page no-url |
| 6 | OWASP German Chapter Conference (AppSec Karls | 2026-06-21 (shipped) | 2026-06-21 RIGHT; page no-url | - blank; page no-url | 2026-06-21 RIGHT; page yes (with-year) | 2026-06-21 RIGHT; page yes (with-year) |
| 7 | Hack In The Box (OOTB 2026 Jakarta) | (blank) (shipped) | 2026-03-01 (no key); page no | - (no key); page no-url | 2026-03-01 (no key); page no | 2026-03-01 (no key); page no |
| 8 | 17th ACM Conference on Data and Application S | 2026-11-16 (person-confirmed) | 2026-11-23 WRONG; page yes (with-year) | 2026-11-24 WRONG; page yes (with-year) | 2026-11-23 WRONG; page yes (with-year) | 2026-11-16 RIGHT; page yes (with-year) |
| 9 | Apres-Cyber Slopes Summit 2027 | 2026-11-20 (person-confirmed) | 2026-11-20 RIGHT; page yes (with-year) | 2026-11-20 RIGHT; page yes (with-year) | 2026-11-20 RIGHT; page yes (with-year) | 2026-11-20 RIGHT; page yes (with-year) |
| 10 | Carbon Capture Europe Summit 2027 | (blank) (shipped) | - (no key); page no-url | - (no key); page no-url | - (no key); page no-url | - (no key); page no-url |
| 11 | Carbon Capture Global Summit | (blank) (shipped) | - (no key); page no-date | - (no key); page no-url | - (no key); page no-url | - (no key); page no-url |
| 12 | Carbon Capture Technology Expo MENA 2027 | (blank) (shipped) | - (no key); page no-date | - (no key); page no-url | - (no key); page no-url | - (no key); page no-url |
| 13 | CES 2027 (Consumer Electronics Show - Smart E | 2026-10-02 (shipped) | 2026-10-02 RIGHT; page no | - blank; page no-url | - blank; page no-url | - blank; page no-url |
| 14 | Decarbonization Congress 2027 | (blank) (shipped) | - (no key); page no-date | - (no key); page no-url | - (no key); page no-url | - (no key); page no-url |
| 15 | ECML PKDD European Conference on Machine Lear | (blank) (shipped) | 2027-01-31 (no key); page yes (with-year) | 2027-01-31 (no key); page yes (with-year) | - (no key); page no-url | - (no key); page no-url |
| 16 | European Carbon Capture, Utilization & Storag | (blank) (shipped) | - (no key); page no-date | - (no key); page no-url | - (no key); page no-url | - (no key); page no-url |
| 17 | Global Energy Show Canada 2027 | 2026-12-04 (person-confirmed) | 2026-12-04 RIGHT; page no | - blank; page no-url | 2026-12-04 RIGHT; page yes (with-year) | 2026-12-04 RIGHT; page yes (with-year) |
| 18 | ODSC East 2027 (Open Data Science Conference) | 2027-01-08 (customer-verified-agrees) | - blank; page no-date | 2027-01-08 RIGHT; page yes (with-year) | 2027-01-08 RIGHT; page yes (with-year) | 2027-01-08 RIGHT; page yes (with-year) |
| 19 | Sustainable Fuels Global Summit 2027 | (blank) (shipped) | - (no key); page no-url | - (no key); page no-url | - (no key); page no-url | - (no key); page no-url |
| 20 | Zero Trust World (ZTW by Threatlocker) | 2026-11-09 (shipped) | 2026-11-09 RIGHT; page no | - blank; page no-url | - blank; page no-url | - blank; page no-url |
| 21 | AAIML Conference 2027 | 2026-11-10 (shipped) | 2026-11-10 RIGHT; page no | 2026-11-10 RIGHT; page yes (with-year) | 2026-11-10 RIGHT; page yes (with-year) | 2026-11-10 RIGHT; page yes (with-year) |
| 22 | RAAI 2026: International Conference on Roboti | 2026-11-10 (shipped) | 2026-11-10 RIGHT; page yes (with-year) | 2026-11-10 RIGHT; page yes (with-year) | 2026-08-01 WRONG; page no | 2026-11-10 RIGHT; page yes (with-year) |
| 23 | CO2-based Fuels and Chemicals Conference | 2026-11-16 (customer-verified-agrees) | 2026-11-16 RIGHT; page yes (with-year) | 2026-11-16 RIGHT; page yes (with-year) | 2026-11-16 RIGHT; page yes (with-year) | 2026-11-16 RIGHT; page yes (with-year) |
| 24 | IEEE Symposium on Security & Privacy | 2026-11-17 (shipped) | 2026-11-18 WRONG; page no | - blank; page no-url | 2026-11-17 RIGHT; page yes (with-year) | 2026-11-17 RIGHT; page yes (with-year) |
| 25 | FIRST Cyber Threat Intelligence Conference (F | 2026-11-23 (shipped) | 2026-11-23 RIGHT; page yes (with-year) | 2026-11-23 RIGHT; page yes (with-year) | 2026-11-23 RIGHT; page yes (with-year) | 2026-11-23 RIGHT; page yes (with-year) |
| 26 | Clean Tech Forum | 2026-12-01 (shipped) | 2026-12-01 RIGHT; page no | - blank; page no-url | - blank; page no-url | - blank; page no-url |
| 27 | American Fuel & Petrochemical Manufacturers ( | 2026-12-11 (shipped) | - blank; page no-url | - blank; page no-url | 2026-12-11 RIGHT; page no | - blank; page no-url |
| 28 | ARPA-E Summit | 2027-01-08 (shipped) | 2027-01-08 RIGHT; page yes (with-year) | 2027-01-08 RIGHT; page yes (with-year) | - blank; page no-url | - blank; page no-url |
| 29 | OWASP Boston Application Security Conference  | 2027-01-15 (customer-verified-agrees) | 2027-01-15 RIGHT; page yes (with-year) | 2027-01-15 RIGHT; page yes (with-year) | - blank; page no-url | 2027-01-15 RIGHT; page yes (with-year) |
| 30 | AI For Good Global Summit | 2027-01-31 (shipped) | 2027-01-31 RIGHT; page yes (with-year) | 2027-01-31 RIGHT; page yes (with-year) | 2027-01-31 RIGHT; page yes (with-year) | - blank; page no-url |
| 31 | Fuel Ethanol Workshop and Expo & Sustainable  | 2027-02-12 (customer-verified-agrees) | 2027-02-12 RIGHT; page yes (with-year) | - blank; page no-url | 2027-02-12 RIGHT; page yes (with-year) | 2027-02-12 RIGHT; page yes (with-year) |
| 32 | 31st Annual Green Chemistry & Engineering Con | 2027-02-15 (shipped) | 2027-02-15 RIGHT; page yes (with-year) | - blank; page no-url | 2027-02-15 RIGHT; page yes (with-year) | 2027-02-15 RIGHT; page yes (with-year) |
| 33 | World of Concrete 2028 | 2027-02-18 (shipped) | 2027-02-18 RIGHT; page no | 2027-02-18 RIGHT; page yes (with-year) | 2027-02-18 RIGHT; page yes (with-year) | 2027-02-18 RIGHT; page yes (with-year) |
| 34 | TROOPERS27 | 2027-03-31 (customer-verified-agrees) | 2027-03-31 RIGHT; page no | 2027-03-31 RIGHT; page yes (with-year) | 2027-03-31 RIGHT; page yes (with-year) | 2027-03-31 RIGHT; page yes (with-year) |
| 35 | AIST Material Science and Technology (MS&T) | 2027-05-01 (shipped) | 2027-05-01 RIGHT; page yes (with-year) | 2027-05-01 RIGHT; page yes (with-year) | 2027-05-01 RIGHT; page yes (with-year) | 2027-05-01 RIGHT; page yes (with-year) |
| 36 | Cloud & Cyber Security Expo London 2027 | (blank) (shipped) | - (no key); page no-date | - (no key); page no-url | - (no key); page no-url | - (no key); page no-url |
| 37 | SANS Cyber Defense Initiative 2026 (CDI 2026) | (blank) (shipped) | 2026-05-26 (no key); page no | - (no key); page no-url | - (no key); page no-url | - (no key); page no-url |
| 38 | Cyber Security Summit Jacksonville | (blank) (shipped) | - (no key); page no-date | - (no key); page no-url | - (no key); page no-url | - (no key); page no-url |
| 39 | GITEX Global | (blank) (shipped) | - (no key); page no-date | - (no key); page no-url | - (no key); page no-url | - (no key); page no-url |
| 40 | AI & Big Data Expo Global | (blank) (shipped) | - (no key); page no-date | - (no key); page no-url | - (no key); page no-url | - (no key); page no-url |
