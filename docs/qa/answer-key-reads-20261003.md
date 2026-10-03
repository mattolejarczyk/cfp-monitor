# Answer key: page reads of the upcoming events (2026-10-03)

Read by Claude in the built-in browser on the event's own page. These are the READS; a value becomes part of `docs/qa/answer-key.csv` only when the operator confirms it
(the key file records who confirmed it and when). The draft with every field for all 40 events is `docs/qa/answer-key-DRAFT.csv`; proof status per field is what the
event's own page states (a plain text read), not a person's confirmation.

| Bench id | Event | What we ship | What the page says (verbatim from the page) | Result |
|---|---|---|---|---|
| B05 | SecTor 2026 | start 2026-10-06, Toronto | "October 6-8, 2026 ... METRO TORONTO CONVENTION CENTRE" (https://blackhat.com/sector/) | page states our value |
| B22 | CERAWeek 2027 | start 2027-03-08, Houston | "MARCH 8-12, 2027 \| HOUSTON, TEXAS" (https://www.ceraweek.com/en; the same page still shows the 2026 edition "MARCH 23-27, 2026") | page states our value |
| B19 | SecureWorld Government & Critical Infrastructure 2026 | start 2026-12-09, Virtual | "Government & Critical Infrastructure Dec 9, 2026 Virtual Conference" (https://www.secureworld.io/events) | page states our value |
| B37 | CarbonZero Global Conference & Exhibition 2026 | start **2026-11-12** | "27-29 October 2026" and "October 27 - 29, 2026" (Brussels, from the page library and the gate's own read) | **page differs: our start date is wrong** (operator to confirm) |
| B36 | Industrial Net Zero Conference 2027 | start blank, Sydney | the page title is "Industrial Net Zero Conference 2026": "13 - 14 October 2026 \| Greenhouse \| Sydney" | blank is right for 2027; the page shows the 2026 edition (a wrong-edition trap) |
| B28 | Decarb TechInvest 2027 | start blank, Boston | "09 - 10 September, 2026 \| Boston, USA" (the 2026 edition, already held) | blank is right for 2027 |
| B29 | ESF MENA 2026 | start **blank**, Dubai | "14-17 SEPTEMBER 2026 \| DUBAI" (https://europetro.com/esfmena) | we hold no start date; the page states 2026-09-14 (a completeness gap, the event has passed) |
| B23 | CES 2027 | start 2027-01-06, Las Vegas | the home page prints no CES 2027 dates in its text (only CES Unveiled / CES Asia dates) | unproven by text: operator to confirm |
| B15 | Nullcon Goa 2027 | start blank | the home page text has no dates | unproven: operator to confirm |
| B31 | Global Energy Show Canada 2027 | start 2027-06-08, Calgary | the page returned no text to the browser read (script-built) | unreadable: operator to confirm |
| B12 | OWASP German Chapter Conference | (not in the approved file) | not read | needs a row or an exclusion |
| B27 | Decarbonization Congress 2026 | (not in the approved file under this name) | not read | needs a row or an exclusion |

**What the rest of the draft shows.** 26 of the 40 events have a start date no page states. Most are 2026 editions that have already happened (Black Hat USA, CYBERUK, Fal.Con,
Infosecurity Europe, BSides Las Vegas and others): their pages now show the 2027 edition, so a plain read cannot prove the 2026 date (the wrong-edition trap again).
For scoring forward quality the key should hold the upcoming events and every city, country and organizer; past editions are historical.
