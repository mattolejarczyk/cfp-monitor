# Whole-page reader over the offline page library: result (2026-10-01)

Reader: frozen `reader.py` (prompt v2b, the code gate, tolerant parser), `deepseek/deepseek-chat`, run by `run_library.py` over the 347 usable pages of `page_library/page_library.db` (350 usable minus 3 below the 300-character floor). Approved cap 0.60 USD / 420 requests. **Spent 0.453 USD, 347 requests, 0 errors, 0 unparseable outputs.** 23 pages were longer than 16,000 characters and were read from their first 16,000. 2 malformed items skipped. Advisory only; nothing was written to the conference database, the deliveries or the customer sheets. There is no answer key for these pages, so this is NOT a score; it is a first full look, with a hand check of the new-looking findings.

## Headline
- 40 of 347 pages state at least one submission deadline the gate accepted (123 accepted dates on 18 sites). Most pages (agenda, sponsor, exhibitor, venue pages) have none, which matches the earlier tests: the model labelled 5,610 dates "other", 1,188 event dates, 335 exhibitor or payment, 135 registration, 48 notification and 24 call-opens.
- **18 accepted dates are still ahead of 2026-10-01, on 9 sites.** I read the page text around the 6 that looked new. 5 are real submission deadlines and match the pages; 1 is a false positive.

## The deadlines still ahead (checked against the page text where marked)
| Date | Site | What the page says | Checked |
|---|---|---|---|
| 2026-10-06 | on-climate.com | Emerging Scholar Awards "Final Deadline: 6 October 2026" | yes, real |
| 2026-10-12 | blackhat.com | Call for Summits Sessions, Black Hat Asia 2027, "Close date: 12 October 2026" | yes, real |
| 2026-10-15 | indiaenergyweek.com | "Submission deadline: 15 October 2026" | yes (already in our database) |
| 2026-10-19 | on-climate.com | Regular proposal round ends 19 October (26) | yes (already corrected) |
| 2026-10-19 | sans.org | "Deadline for submission is October 19, 2026" (CTI and OSINT summits, Feb 2027) | yes, real |
| 2026-10-20 | blackhat.com | Call for Briefings closes 20 October 2026 | consistent with the answer key |
| 2026-10-30 | nullcon.net | "CALL FOR PAPERS CLOSES ON 30th October 2026" (Nullcon Goa 2027, opened 11 Sep) | yes, real |
| 2026-11-20 | actexpo.com | Nominations due 5 p.m. PT 20 November 2026 (awards, not the speaker call) | consistent |
| 2026-12-04 | globalenergyshow.com | "all submissions must be completed ... December 4, 2026" (twice) | yes (already in our database) |
| 2026-12-20 | on-climate.com | Late proposal round | consistent |
| 2027-02-28, 2027-03-31 | troopers.de | CfT ends / CfP ends (TROOPERS27) | consistent |
| 2027-06-25, 2027-10-25, 2027-12-26 | on-climate.com | 2028 conference rounds | matches the answer key |
| 2026-10-28 | industrylink.eu | "Call for Nominations ... (awarded on October 28" | **FALSE POSITIVE**: the awards ceremony date, not a deadline |
| 2026-11-15 | indiaenergyweek.com | "Full paper and presentation submission" | **by our definition not a call deadline** (comes after acceptance) |

So of the 18, 16 look right and 2 are the same family of error seen before (a ceremony date; a post-acceptance upload). Rough precision about 0.89 on this listing: a hand check, not a measurement.

## Compared with what we store (rough: matched by site address, so other editions of a site can mix in)
25 conference rows in the two customer markets matched a library site: 10 stored deadlines appear among the dates the library found; 6 rows have a blank stored deadline where the library found dates; 9 differ. Worth a person's look:
- **Nullcon Goa 2027: stored blank, status Needs Verification; the page says the call closes 2026-10-30.** An open call missing from our data.
- **Black Hat Asia 2027 summit sessions (close 12 Oct) and SANS CTI/OSINT summits 2027 (19 Oct)** are next-edition calls; our rows read Black Hat Asia 2026 and SANS CDI 2026 (Closed). Whether the 2027 editions are tracked at all needs checking.
- **WHEC 2026:** stored 2026-02-26; the page says 27 February 2026 (one day off; the deadline has passed).
- Gastech 2026: stored 2026-02-20; the library found 2026-02-06 (passed). Troopers 2026 stored 03-31 closed; the library holds the TROOPERS27 call (ends 2027-03-31).
These "different" rows are leads, not errors: the site-level match mixes editions.

## Limits
No answer key for these pages. 23 long pages were truncated at 16,000 characters. Pages with script-built tables were not specifically tested. The model's two failure types are the known ones: ceremony and post-acceptance dates. A larger labelled set (the benchmark, brief 01) is still needed before any number here is quoted as accuracy.
