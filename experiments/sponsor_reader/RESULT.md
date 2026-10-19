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

---

# ROUND 2 (2026-10-19, later): the method was the problem, as the operator suspected

## Audit of how we ask
1. UPSTREAM's question (run_market_audit.py, `_SPONSOR_ONLY_RULES`) sets SPONSOR_REQUIRED=Yes when the event "states OR IMPLIES that supplier/vendor participation (speaking, exhibiting, or attending as a company) requires
   payment". That mixes three different things (sponsor packages exist and cost money; exhibiting costs money; speaking requires payment). Result: 211 of 220 approved rows say Yes, and the cost texts show the stretch
   ("enquiry required", "must contact the organizer"). The field means "sponsorship packages exist", and the page told the customer "speaking at this event requires sponsorship".
2. OUR question (extract_sponsor_quotes.py) hunted ONE verbatim sentence on ONE page saying speaking requires sponsorship. The real question is about the ROUTE to a speaking slot and spans pages: is there a public call
   anyone can submit to (call-for-speakers page), does the sponsorship page sell or promise speaking slots, does any page say vendors MUST sponsor to speak. A one-page sentence hunt cannot answer it.

## The corrected question (judge.py, prompt v3) and its test
All pages of an event together (home, the cited sponsorship page, up to 3 sponsor pages, up to 3 call-for-speakers pages), labelled by kind; four answers, each with a word-for-word quote; CODE checks every quote is on the
pages AND says what it claims (`SAYS` patterns), then derives the route. Sample: 36 random events (all upstream "Yes"), cheap model deepseek-chat, 220k tokens in total, about 0.06 USD.
Result (v3b): OPEN_CALL 14, OPEN_CALL_AND_PAID_SLOTS 5, PAID_SLOTS_NO_CALL_SEEN 2, UNCLEAR 15, MUST_SPONSOR 0.
Read by a person (every decided quote): 22 decided, at least 19 right; the doubtful ones are a "Call for Program Committee" counted as a speakers call (VulnCon), a stale-year call still counted (AFCC: "Due July 30, 2021"),
and one dropped paid slot (CarbonZero) after the quote check; a "Call for Papers has now closed" answer that the first draft turned into INVITE_ONLY is now caught by the code check.
THE FINDING THAT MATTERS: 0 of 36 events say vendors must sponsor to speak, 19 of 36 run a public call, and only about 7 of 36 sell or include speaking slots in sponsor packages. "Sponsor required" was wrong for most rows.
A second cheap model (deepseek-v4.1-flash) returned too little JSON at max_tokens 700 (it reasons first): not a fair test, not pursued.

## What this means
- Cheap model + the right question + code-checked quotes works: about 60 percent of events get a clear, quoted answer at about 0.002 USD each; the rest stay Unknown (R19.2).
- The useful customer-facing fact is the ROUTE (public call / public call plus paid slots / paid slots, no call seen), not "sponsor required".
- Next steps proposed to the operator: (1) stop saying "requires sponsorship" on unconfirmed rows; (2) show the route, with its source quote, in the open row where decided; (3) hand-back to upstream to redefine SPONSOR_REQUIRED
  (Yes only on a stated requirement, else Unknown) and stop the paid sponsor-only pass; (4) run judge.py weekly on rows without a route (rotating), cost cents.
