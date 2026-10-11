# Conference refresh policy: internal justification (we are not wasting money; we are moving it)

INTERNAL. Companion to docs/customer/HOW-WE-KEEP-YOUR-DATA-CURRENT.md (the customer-facing statement). Written 2026-10-11 for ACT-33, approved by the operator the same day. All dollar figures are ESTIMATES at Google's list price for grounded search (about 14 USD per 1,000 search queries, before any free allowance); the real bill is on the AI Studio spend page. All data is from one week (3 to 10 October); treat the rates as indicative, not proven.

## 1. The principle

Spend research money where a fact can still change and a customer can still act on it. Stop paying to re-read pages that cannot have changed. The rule is not "cheaper"; it is "same or better coverage of the things that move, less repetition of the things that do not".

## 2. What the weekend taught us (why this is worth doing now)

- Oct 3-10 logs: about 8,940 grounded searches, about 125 USD at list price. Sponsor checks were about half of it; the rest was research of every row every week, including rows that could not change.
- The customer sheets added about 60 events on 5 October (ACT-51), so Saturday research roughly doubled for Arnica (73 to 134 requests). That growth is deliberate; paying to re-read ended events every week is not.
- One cycle (Saturday 2026-10-10): 204 rows on the two pages: 102 live, 55 Closed with the event already over (32 ended more than 60 days ago, 23 within 60 days), 47 Closed with the event still ahead.

## 3. The rule and the reasoning for each group

| Group | Frequency | Why it is not waste, and why it is not over-spending |
|---|---|---|
| 1 Live (not Closed) | weekly | Deadlines, status and links move here. This is the product. Not touched. |
| 4 Call closed, event ahead, 30 days or less | weekly | Venue, schedule, cancellation and sponsorship news cluster near the event. 17 of the 26 dated rows we compared are in this band. Not touched. |
| 4 Call closed, 31-90 days | every 2 weeks | Changes are real but infrequent. |
| 4 Call closed, over 90 days | every 4 weeks | Slow-moving; a date or venue change is the main risk, and four weeks is soon enough to correct it before a customer plans around it. |
| 3 Event just ended (within 60 days) | ONE check at about 14-21 days, then skip to day 60 | Final dates get confirmed after the event: 3 of the 5 field changes in this group this week were corrections of actual dates (InfoSec World start 12 to 11 Oct; OWASP German Day 23 to 24 Sept). One check captures that; weekly checks in the weeks between add nothing. |
| 2 Ended more than 60 days | every 2 weeks | 13 of the 55 ended rows mention a next edition with dates (Infosecurity Europe 8-10 June 2027, Gartner London 14-16 June 2027, Reuters Global Energy Forum 22-23 June 2027, Asia Pacific Hydrogen Summit 23-24 Sept 2027), so an occasional check does find things; weekly adds little. Changes in old rows were mostly blank past deadlines being filled in, and some flip-flops (CyberDefenseCon deadline 2026-10-02 then 2026-04-23): re-researching settled facts every week is also a quality risk, not only a cost. |
| Overrides | always research | a dead customer-facing link, a named row (customer flag or upstream note), a new event, a blank or unreadable date, every row on the first Saturday of January. These keep the schedule from hiding a real problem. |

Skipped rows carry last week's accepted row (the machinery the Friday awards run already uses: REFRESH_SKIP, carry-over in weekend_import, coverage check exempts them). Nothing leaves the page.

## 4. Estimated saving (per Saturday, estimates)

Cost per researched row about 0.12 USD (8-9 grounded searches).
- Group 2, every 2 weeks: about 31 rows x half x 0.12 = about 1.9 USD.
- Group 3, one check in the window instead of weekly: about 22 rows, about 2.6 checks a week instead of 22: saves about 2.3 USD.
- Group 4 tiers: about 0.7 USD today (most of those rows are within 30 days), more as the list grows.
- Total about 5 USD a week, plus the matching sponsor re-checks (the sponsor prefill, ACT-64, already carries those answers).

## 5. Where this sits in the whole cost picture (we are working down a ladder, not cutting at random)

1. Stop money lost to our own bugs (done 9-10 October; under 1 USD of waste).
2. Stop re-buying answers we already hold: sponsor prefill, about 35 USD a week steady (built, to apply 17 Oct).
3. Stop researching what cannot change: this policy, about 5 USD a week; awards skip already saves about 2.6 USD a week.
4. Not touched on purpose: live rows weekly, events within 30 days weekly, every customer-sheet event stays in the queue (ACT-51).
5. Next candidates, not built: sponsor links in the weekly sweep (ACT-65, done) so a dead sponsor page re-asks by itself; unknown sponsor answers every 2 weeks (needs a change to upstream's research script, about 2 USD).
Rough weekly picture (estimate): about 80 USD a week of Friday plus Saturday grounded search before these changes; about 40 USD after the prefill and this policy are both live.

## 6. How we will know it is not hurting quality

- First live Saturday is a DRY RUN (CFP_REFRESH_APPLY unset): the log shows what would be skipped and we read the list before anything is marked.
- After it is on, measure for 4 Saturdays: (a) spend against the estimate; (b) for every skipped row that comes due, how much changed since its last check, by field. If material changes (status, deadline, start date, link) show up in a group at more than about 10 percent of due rows, shorten that group's frequency. The numbers are settings in docs/operations/refresh_policy.json, so tightening needs no code.
- The next-editions list (a free report from text we already have) shows whether the 2-weekly pass on old rows is finding announcements; if it finds none for a month, lengthen that group.
- Rollback is one switch (unset the variable) or restoring the run_monthly.ps1 backup.

## 7. Honest limits

- One week of data; the change rates will move as the list stabilises (part of this week's changes were first-time research of new customer rows).
- Dollar figures are list-price estimates; the free monthly allowance (5,000 queries per Google's page, per a forum report counted differently) is unknown to us.
- Finding a next edition does nothing by itself: only 8 of those ended rows have a successor row. Turning those mentions into tracked rows is a separate step for the operator or upstream.
