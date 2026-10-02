# Note to upstream, round 3: new leads from the page library, and what is still open (draft for the operator to forward, 2026-10-01)

Two parts. Part 1 is new and dated: five calls that close in the next four weeks, plus two more. Part 2 repeats the items from our previous note that are still open; **the Saturday 02:00 item there is time-critical**, so if the previous note was already sent, please read only that item again.

## Part 1. New leads (all closing dates are as the pages state them)
How we found these: we saved the 364 pages our site discovery selected (on 2026-10-01, through a real browser), and had a model read every page and list the dates it could tie to a call. Code then accepted a date only if the quoted text is literally on the page and the date is written in it. We read the surrounding page text for each one below. We have **not** checked whether each event is in your input list or already tracked under another edition; identity is yours (5.4). We do not currently run discovery for new editions, so these come from re-reading pages we already hold. Where a quote is two lines (a label above a date), that is how the page lays it out.

| # | Closes | Event | Page and exact text | What our database holds |
|---|---|---|---|---|
| 1 | **2026-10-06** | Climate Change conference, Emerging Scholar Awards (an Awards opportunity) | `https://on-climate.com/2027-conference/emerging-scholar-awards`: "Final Deadline: 6 October 2026" (the line above reads "Early Deadline: 6 June 2026") | unknown whether tracked as an Awards row |
| 2 | **2026-10-12** | Black Hat Asia 2027, Call for Summits Sessions | `https://blackhat.com/html/call-for-sessions.html`: "Close date: 12 October 2026 (23:59 Singapore Time GMT/UTC +8)"; same block: "Summit Date/Location: Monday, 1 March. Marina Bay Sands, Singapore" | we hold Black Hat Asia 2026 (closed); not checked whether 2027 is tracked |
| 3 | **2026-10-19** | SANS Cyber Threat Intelligence Summit and OSINT Summit (1-2 February 2027, Alexandria VA) | `https://www.sans.org/cyber-security-summit/speak-at-a-summit`: "Deadline for submission is October 19, 2026." | we hold SANS Cyber Defense Initiative 2026 (closed); different event |
| 4 | **2026-10-20** | Black Hat Asia 2027, Call for Briefings (opened 4 September 2026) | `https://blackhat.com/call-for-papers.html`: "Call for Briefings Closes: 20 October 2026 (23:59 Singapore Time GMT/UTC +8h)"; same block: "Briefings Dates/Location: 2-3 March 2027, Marina Bay Sands, Singapore" | as row 2 |
| 5 | **2026-10-30** | Nullcon Goa 2027, Call for Papers (opened 11 September 2026) | `https://nullcon.net/event/nullcon-goa-2027/call-for-papers/`: "CALL FOR PAPERS CLOSES ON" then "30th October 2026" (two lines) | **our row Nullcon Goa 2027 has a blank deadline and status Needs Verification** |
| 6 | 2026-11-20 | ACT Expo Fleet Awards (Awards) | `https://www.actexpo.com/fleet-awards/`: "Nominations are due by 5 p.m. PT on Friday, November 20, 2026." | not checked |
| 7 | 2027-03-31 (call for papers); 2027-02-28 (call for trainings) | TROOPERS27 | `https://troopers.de/troopers27/contribute/`: "CfP ends on: March 31st, 2027" and "CfT end: February 28th, 2027" (heading "Important Dates") | we hold Troopers 2026 (closed); the 2027 edition may not be tracked |

One correction to an existing row, low priority because it has passed: **WHEC 2026** is stored as 2026-02-26, but `https://whec2026.org/abstract-submission-guidelines/` shows "Abstract submission deadline" above "27 February 2026" (one day later; two lines).

What we left out on purpose: an awards-ceremony date ("awarded on October 28") and India Energy Week's "Full paper and presentation submission: 15 November 2026", which is a post-acceptance upload, not a call deadline.

Please tell us, for each row, whether it is already tracked, whether it should be added as a new row (and under which EVENT_ID), or whether you disagree with the reading. Rows 1, 2, 3 and 4 are close enough that a reply this week would still be useful to the customer.

## Part 2. Still open from our previous note (round 2)
1. **Before Saturday 02:00 (time-critical).** Saturday's job re-researches every conference; a row whose new research fails our approval check falls back to "last week's approved version", which comes from your approved market files. If `Utility_audited.final.csv` still holds the old values, the four corrected rows can revert just before Monday 07:00 (09-30 for India Energy Week, 12-19 for Climate Change, the old SecureWorld citation, the old Global Energy Show link). Please apply the four corrections to your approved files and tell us when done.
2. **Global Energy Show Canada 2027 submit link.** The "Submit an Abstract" button goes to `https://www.dmgeventsconferences.com/global-energy-show-2027/submitter/login`. Our operator set that on our row on 2026-10-01 as a logged stopgap; please send it as `CFP_SUBMISSION_URL` and carry it in your approved file, or Saturday's load can bring the old 404 address back.
3. **`IS_PROJECTED`.** You set it to false for India Energy Week, Climate Change and Global Energy Show; our merge guard does not carry that flag, so all three still read true here. Please include it in a delivery we import normally.
4. **India Energy Week duplicate.** We hold both `2026-india-energy-week-kolkata` and `2027-india-energy-week-kolkata`. Our tools cannot retire an identity; please confirm the survivor and send the retirement (R15).
5. **Pass type.** That pass moved two dates and retired a row, so it is a `re-research` pass (R6, with the R7 manifest), not a `correction`.
6. **For information:** the Climate Change quote with `(26)` cannot yet be read by our date check, so that row's date verdict reads `not_found` until we extend it after Monday.
