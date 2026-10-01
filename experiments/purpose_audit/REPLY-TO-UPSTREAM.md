# Reply to upstream on the accepted correction package (draft for the operator to forward, 2026-10-01)

Thank you. Three of the four corrections check out against the pages as we fetched them today. Three things need to change before this can be imported, because as written they would fail our own acceptance check. Per contract section 12 we verified your corrections as rigorously as the original claims.

## 1. India Energy Week 2027: the cited page does not contain the quote (must change)
You set `DEADLINE_EVIDENCE_URL` and `SUBMISSION URL` to `https://www.indiaenergyweek.com/conference/call-for-papers/` with the quote `Submission deadline: 15 October 2026`.
That page, fetched today, does not contain that sentence and does not contain "15 October" at all. It still reads "The extended and final deadline for abstract submissions is 19 September 2025."
The sentence is on the page the short link `https://bit.ly/4yuBPgO` resolves to, which is on the organiser's own domain:
`https://www.indiaenergyweek.com/forms-2027/conference-call-for-abstract-submission/`
(the redirect adds `utm_` tracking parameters; please use the URL without them).
Please set `DEADLINE_EVIDENCE_URL` (and the submission link) to that URL, keep the quote and the date 2026-10-15. This also resolves our earlier doubt about whether the short link was the organiser's: it is.
The duplicate merge (`2026-india-energy-week-kolkata` into `2027-india-energy-week-kolkata`) is accepted on our side.

## 2. Climate Change conference: the date format will not pass our date check (decision needed)
Quote `Regular 20 June (26) to 19 October (26)` is on the page (the page separates the words with tab characters; ours matches with whitespace normalised), but the page writes the year as `(26)`. Our current date check does not read a two-digit year in brackets, so it cannot confirm 2026-10-19 from that quote and the row would read `not_found`.
We can extend the check, or you can accept `not_found` on this row for now. We will tell you which; no change is needed from you.
Also note the quote alone does not say it is a proposal period: the heading above it (`Proposal Periods`) does. Please keep `STATUS DETAILS` as drafted.

## 3. Column names
`SUBMISSION URL` and `STATUS DETAILS` appear in section 3 (the customer's columns) in our patch tooling, which refuses them. Please confirm you mean `CFP_SUBMISSION_URL` (section 2) for the link, and send `STATUS DETAILS` text in the same way as in earlier rounds.

## Confirmed as proposed
- **SecureWorld Government & Critical Infrastructure:** citation and quote withdrawn, `IS_PROJECTED = true`, deadline left in place and flagged unevidenced. Agreed.
- **Global Energy Show Canada 2027:** deadline 2026-12-04, evidence URL `https://www.globalenergyshow.com/conferences/2027-call-for-submissions/`, quote `all submissions must be completed through the online submission form by the December 4, 2026 deadline.` This quote is verbatim on that page. Agreed.

## Timing
Our customer page is built Monday 2026-10-05 at 07:00. A stored deadline that has passed shows as Closed, so the India Energy Week row will read Closed unless the corrected row is imported before then. Please re-emit the four rows as a correction pass (R6) with the changes above as soon as you can; we will report and verify before importing.
