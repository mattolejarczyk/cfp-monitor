# Correction package for upstream - four rows (draft, 2026-10-01)

Defend-or-correct format (contract section 9 / runbook section 6). **DRAFT. Nothing in our database or any delivery was changed.** Each finding gives the evidence we read today through the
repo renderer, our proposed answer, and the check to run before it is applied. Every quote below was cut from the fetched page text and is verbatim. Proposed values must still pass
`scripts/apply_resolutions.py --citations` (our own fetch, quote on the page) before they are applied, and v2.4 means the VALUE changes only on upstream's answer or an operator ruling.
Rows are public events; no customer detail is in this file.

| # | Row (EVENT_ID) | Stored | Finding | Proposed answer |
|---|---|---|---|---|
| 1 | `2026-nineteenth-international-conference-on-climate-johannesburg` | 2026-12-19, projected, no quote, no evidence URL | 12-19 is the end of the REGISTRATION regular period, not a proposal date | CORRECT to 2026-10-19 (see below) |
| 2 | `2026-secureworld-government-critical-infrastructure-virtual` | 2026-10-28, not projected, quote = event name + date | the cited page does not state 10-28; it lists the event on Dec 9, 2026 | WITHDRAW the citation and quote, set IS_PROJECTED = true, re-research for a real call page |
| 3 | `2026-india-energy-week-kolkata` and `2027-india-energy-week-kolkata` | 2026-09-30, projected, no quote | the submission page now states 15 October 2026; two rows exist for one conference | CORRECT to 2026-10-15 once the page is confirmed as the organiser's; merge the duplicate |
| 4 | `2027-global-energy-show-canada-calgary` | 2026-12-04, projected, submission link 404 | date is stated on a live page of the same site; the cited link is dead | CORRECT the evidence and submission link, keep 2026-12-04 |

## 1. Climate Change conference
Page: `https://on-climate.com/2027-conference/call-for-papers`. Text as rendered (tabs kept):

    Proposal Periods
    Proposals will be reviewed within two to four weeks of submission.
    Early		Launch to 19 June (26)
    Regular		20 June (26) to 19 October (26)
    Late		20 October (26) to 20 December (26)
    Registration Periods
    The digital media deadline is one week before the conference.
    Early		Launch to 19 July (26)
    Regular		20 July (26) to 19 December (26)

- Stored 2026-12-19 equals the registration regular end. Proposal rounds end 2026-06-19 (passed), 2026-10-19 and 2026-12-20.
- R23: the round a person can act on today is the first whose end is on or after today, **2026-10-19**. The later round (2026-12-20) should be carried as a note, not as the date.
- Proposed quote (two lines, both verbatim; the date is written as the page writes it): `Proposal Periods` + `Regular		20 June (26) to 19 October (26)`. **Open question for the gate:** it is a
  two-line quote (heading plus row) with a two-digit year; the single-sentence rule may reject it. If so, upstream supplies the wording it will accept.
- The `evidence` table already holds 2026-12-20 for this row with verdict `no_quote`; it is the late round, one day off the stored value.

## 2. SecureWorld Government & Critical Infrastructure
Cited page `https://www.secureworld.io/events` lists "Government & Critical Infrastructure / Dec 9, 2026 / Virtual Conference". "Oct 28" and "10-28" appear nowhere on it. The stored quote
`Government & Critical Infrastructure 2026 2026-10-28` is the event name plus the date; it is not a sentence from the page. No submission link is stored; the page has a "Become a Speaker" link.
Proposed: withdraw citation and quote (R1), set IS_PROJECTED = true, and ask for a real call page (the speaker page behind "Become a Speaker"). We found no replacement date.

## 3. India Energy Week 2027
- Two rows, one conference: `2026-india-energy-week-kolkata` ("India Energy Week 2027 (IEW 2027)") and `2027-india-energy-week-kolkata` ("India Energy Week 2027"); both 2026-09-30, both projected.
- Submission form page (stored link `https://bit.ly/4yuBPgO`): `Submission deadline: 15 October 2026` and `Full paper and presentation submission : 15 November 2026`. 2026-09-30 is on no page we read.
- The organiser's own Call for Papers page (`https://www.indiaenergyweek.com/conference/call-for-papers/`) is still last cycle's: "The extended and final deadline for abstract submissions is 19 September 2025."
- Not established: that the short link resolves to the organiser's own site. Upstream should supply the final URL; the quote above is for the abstract deadline (the full-paper date is a later stage, not the submission deadline).
- 2026-09-30 passed yesterday, so the stored value is already stale either way.

## 4. Global Energy Show Canada 2027
- Cited submission link `https://www.globalenergyshow.com/speak/abstract-submission/` renders "ERROR 404 Sorry! Page Not Found".
- Live page `https://www.globalenergyshow.com/conferences/2027-call-for-submissions/` states, verbatim: `all submissions must be completed through the online submission form by the December 4, 2026 deadline.`
- Proposed: keep 2026-12-04; set the evidence URL to the live page with that sentence as the quote; replace the dead submission link with the live page's "SUBMIT AN ABSTRACT" target (upstream to supply).

## Before anything is applied
1. Run `scripts/customer_context.py` again on the day (done 2026-10-01: three of these rows are on a customer sheet; their fields are theirs and are not touched).
2. Run `scripts/apply_resolutions.py --citations <csv>` in report mode first; apply only what passes our fetch.
3. After import: `scripts/check_invariants.py`, then diff the delivery against the previous one and read it; do not bless it unread.
