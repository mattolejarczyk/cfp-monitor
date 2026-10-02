Gate result on the eight status corrections: statuses are right, two rows fail, and the rows replaced content that was not part of the correction

Thank you for the quick turnaround. The decisions are what we wanted: STATUS = Closed with the last known deadline kept (R1) on H2 MEET and the six awards, and the CGI citation withdrawn. All eight deadlines are unchanged. The file is strict CSV (45 fields on every row). We ran it through the acceptance gate and it is REJECTED on two checks. We have not applied anything.

## 1. Two gate failures (please fix and re-send)

- **R11 on CGI** (`2026-clinton-global-initiative-cgi-commitments-to-action-2026-unknown-registration`): `GROUNDING_CONFIDENCE = Unverified` with `IS_PROJECTED = true`. R11 binds the two: a projected row reads `Projected (2026)`, a verified row `Verified (2026)`. Please use `Projected (2026)`. (The row's `Speaking` OPPORTUNITY_TYPE and `Not Announced` CFP MODEL TYPE are fine.)
- **2.6 on World Green Energy Awards 2026** (`2026-world-green-energy-awards-2026-unknown-awards`): `LOCATION = TBD`. An honest blank beats a placeholder; please leave LOCATION blank (CITY, STATE and COUNTRY are already blank).

Everything else passes, including that each cited page resolves and each quote is on its page. The CSO and SANS pages return 404 to our reader; that is expected decay on rows whose deadline has passed (v2.2), reported as a note, not a failure.

## 2. The rows replaced much more than the correction asked for

You corrected status. Our field-by-field comparison with what we hold shows each row was regenerated, not patched. Across the eight rows, populated fields that came back blank: SUBMISSION DATE VERIFIED (8), SUBMISSION URL (8), NOTES (8), COORDINATOR EMAIL (6), VENUE_EVIDENCE_URL (4), START DATE (4), SUBMISSION_OPENS (3), PRIORITY (2), and one each of TRACK, STATE_PROVINCE, SPONSOR_URL, SPONSOR_COST, ANNOUNCEMENT_DATE, MAIN_INFO_URL, CFP_SUBMISSION_URL, DEADLINE_EVIDENCE_URL and DEADLINE_QUOTE. Fields that changed to new text: OVERVIEW and CATEGORIES on all eight (richer descriptions replaced by one-line generic ones; for example H2 MEET's overview now reads only "H2 MEET 2026 Call for Speakers."), LOCATION and CONFERENCE DATES on all eight, ORGANIZER on seven, plus CONFERENCE URL, MAIN_INFO_URL, CFP_SUBMISSION_URL and the evidence URL and quote on most rows. On H2 MEET the English page quote was replaced with a Korean one from the /ko/ page.

Contract 2.4 and R6: a correction repairs how a claim is written, never what it claims, and a status fix should change status only. Our merge tool is built so that a blank never overwrites a populated field, which is why we have not simply applied these rows.

Please re-send as a minimal correction: for each of the eight rows, keep every field exactly as in the row you delivered before (our approved files for H2 MEET, `Awards_20260905_out.csv` for the awards) and change only:

- all seven closed rows: `STATUS` (Closed), `STATUS DETAILS` (one plain sentence that the call closed on the stated date), and `LATEST UPDATE` / `SOURCE_AS_OF`;
- CGI: withdraw `DEADLINE_EVIDENCE_URL`, `DEADLINE_QUOTE` and the dead submission links as you did, set `IS_PROJECTED = true`, `GROUNDING_CONFIDENCE = Projected (2026)`, STATUS `Needs Verification`, and leave everything else as it was.

For H2 MEET please also keep the English page (`https://www.h2meet.com/html/en/speaker.php`) and its quote where that page states the round dates; if only the Korean page does, keep both.

## What we do when it arrives

Gate it, then load it through the normal path and run the health check. Until then the rows stay as they are, and the customer page already shows passed deadlines as Closed, so nothing is wrong on the page in the meantime.

Please reply with the eight rows in one CSV block, 45 fields per row, comma-containing fields quoted.
