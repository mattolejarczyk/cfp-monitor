# RESULT: can the reading we already do prove "sponsorship is required to speak"? (2026-10-19)

Question (operator, 2026-10-19): do not pay to look for it; add it to the pages we already read, and where a page does not say it the answer is Unknown (contract R19.1, R19.2, R21).
Sample: 57 events of the two customer markets (45 where upstream says Yes, 2 No, 10 no answer), random, seed 20261019. For each: the page upstream cited (control) and up to 4 sponsor-type pages
picked from the site's own sitemap and menu; 208 pages read by the cheap model with the same instruction and code checks as scripts/extract_sponsor_quotes.py. Cost about 0.12 USD, read-only.
Raw output: RESULT-raw.md (every proven sentence).

## Numbers
| | Events | Result |
|---|---|---|
| Upstream says Yes | 45 | proven from the cited page alone: 2 (4 percent); from ANY page read: 6 (13 percent) |
| Upstream says No | 2 | 0 |
| No answer (Unknown) | 10 | 0: nothing found to turn an Unknown into a Yes |
| Pages unreadable (walls, scripts, blank) | 65 of 208 | 31 percent |

Together with the earlier single-page trial (13 of 216 proven, 6 percent; 122 pages read and silent), the picture is stable: event sites rarely STATE that speaking requires sponsorship.

## What the 6 proven sentences actually say (read by a person)
None says speaking REQUIRES sponsorship. They say a sponsorship or exhibitor PACKAGE INCLUDES a speaking opportunity: "Speaking slots, panel seats and fireside chats..." (a sponsor page), "1 Delegate Pass + Limited Speaking
Opportunity (Exhibitor speaking slots are strictly limited...)" (three sites on one template), "speaker opportunities" (a benefits bullet, two sites), "Present to hyperengaged audiences with speaking and thought leadership
opportunities" (Gartner Tokyo). That is a pay-to-play ROUTE, not a requirement, and a customer could still apply through an open call. A "Sponsor required" badge on these would overstate.

## Conclusions
1. Finding the sentence is not a matter of reading more pages: the finder adds 4 events of 45 and none of them proves the claim as stated. It is a poor use of effort and the wording on the page ("requires") would be wrong.
2. The honest answer for almost every row is Unknown (R19.2), which is what the operator accepted.
3. The 211 upstream "Yes" claims are largely inferences (tiers and prices on a sponsorship page) rather than statements. They stay as upstream's text in the open row, with no badge (QA-REGISTER A44).
4. The paid sponsor-only grounded pass buys claims we cannot verify. Recommended: stop it after the 2026-10-24 lean week (see docs/design/sponsor-check-cost-plan.md); keep carrying existing answers (ACT-64).
5. Not built: no sponsor reader step, no sponsor_proof table, no page overlay. The 2 rows the customers' own sheets confirm keep the badge.
