# Reply to upstream: the seven rows, gate result and one re-emit needed (2026-10-02)

Thank you for the IDs and the CSV. We ran it through our acceptance gate. The content is good: with the file repaired mechanically on our side, **21 of 22 checks pass**, including that every cited page resolves and every quote is on its page verbatim. Two things need a clean re-emit before we can import, because the gate is the only authority and we do not import a file we had to repair.

## 1. The file is not valid CSV (check 1)

Header has 45 columns. As received:

- Rows for Climate Change Emerging Scholar Awards, Black Hat Asia summits, Black Hat Asia briefings, SANS and Nullcon have **44 fields**: one empty field is missing between `SUBMISSION DEADLINE` and `CFP MODEL TYPE`. The result is that `CFP MODEL TYPE` ("Fixed Deadline") lands in `STATUS DETAILS`, and every later field is shifted one column left.
- **ACT Expo Fleet Awards** has 46 fields: `DEADLINE_QUOTE` ("Nominations are due by 5 p.m. PT on Friday, November 20, 2026.") is not quoted and contains two commas.
- **TROOPERS27** has 45 fields for the same reason (the quote "CfP ends on: March 31st, 2027" contains a comma and is not quoted), on top of the missing empty field.

Please re-emit all seven rows as strict RFC 4180: 45 fields on every row, and any field containing a comma wrapped in double quotes.

## 2. A placeholder where a blank belongs (check 2.6)

ACT Expo Fleet Awards has `CITY = TBD` and `LOCATION = TBD`. Contract 2.6: an honest blank beats a guess. Please leave both blank. Nothing else about the row needs to change; the identity stays `2026-act-expo-fleet-awards-tbd-awards` (the identity is yours, 5.4; tell us if you want to rename it once the city is known and we will handle it as a rename).

## What did not need any change

- All seven deadlines and quotes: confirmed on their cited pages by the gate.
- `2026-nullcon-goa-2027-bambolim-speaking`: this is already in our copy of the approved Cybersecurity file with exactly these values, so it is consistent with what Saturday's run will read. No action beyond including it in the re-emit.
- Customer-owned columns are blank, as they should be.

## Timing

Climate Change Emerging Scholar Awards closes 2026-10-06 and Black Hat Asia summits 2026-10-12, so a re-emit today lets us import and health-check before Saturday 02:00 and well before Monday's customer pages.

Please reply with the seven rows in one CSV block.
