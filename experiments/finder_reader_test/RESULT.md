# RESULT - finder + reader, end to end (option 3, 2026-10-04)

Question: can real URLs from a site's sitemap and menu, picked by the frozen v3.1 rules and read page by page by the cheap model (deepseek-chat), find the submission
deadline of a currently-open call, WITHOUT being told the answer? Code accepts a date only if its quote is on the page, states that day, month and year, and uses call wording.

Gold (nobody re-verifies): 14 events with a deadline still ahead: 10 customer-verified dates that match ours, 4 operator pins (GES, Nullcon, CODASPY, Apres-Cyber).
Cost: 73 page reads, about 2 cents, no new keys. Files: `run.py`, `results.json`, `pages.json` (git-ignored). Gold dates were never shown to the model.

## Results
| | Events |
|---|---|
| A selected page states the gold deadline (finder) | **11 of 14** |
| The reader accepted the gold deadline from a page it was handed | **11 of 14** (the same 11: whenever the right page was selected, the reader got it) |
| Hit on the first selected page | 7 of 11 (rank 2 or 3 in the rest) |
| Selected page read but the deadline is NOT the main call's | 3 events (see below) |
| Accepted date that is wrong for the call | **0 of 73 reads** |

Hits include sites with no sitemap at all (RSAC, WSED, ICRAI, RAAI, AAIML, BASC, CODASPY: menu links only) and Global Energy Show Canada, where the page the database cited does NOT state the date
(control: no) but the finder's rank-1 page does: the finder found a better page than the one we hold.

## The 3 misses (all finder or access, none reader)
- **AAIML:** the homepage render failed in this run (0 candidate URLs; an earlier plan-only run found 3 pages). A flaky render, not a selection result.
- **ICRAI:** the date is on the HOME page only (the control); the selected pages (submission, awards, programme) state none. Reading the home page as a standing extra page would have found it.
- **FEW Sustainable Fuels Summit:** a sub-summit inside a larger event site; the plan selected awards and sponsor pages. The date is on the summit's own page (the database's page).

## "Wrong" accepted dates (3 events): other calls on the same site, not errors
CO2 Fuels (call for POSTERS 2027-04-05 beside the abstracts deadline), FEW (the Awards page's 2027-05-07), CODASPY (call for POSTERS 2027-02-15 beside the paper deadline). Each is a real, quote-proven
date for a different submission type. **A finder that reads several pages needs a rule for which is the main call** (a page named for the call for papers/speakers/abstracts, then the earliest open date), or the weekly
row will carry whichever page happened to answer first. That rule is the next piece to design; it is not solved here.

## What this says
- **Finding the page is the harder step; reading is not.** Where the plan selected the right page the reader never missed (11 of 11) and never made a wrong claim.
- Menu + sitemap + the v3.1 rules reach the right page for 11 of 14 gold events at about 2 cents for the lot, with real URLs only (nothing composed, nothing a model invented).
- Caveats: n = 14, gold biased toward events a customer already tracks and calls that are open; the render of one site failed once. Direction, not a rate.

## Next (not started)
1. Always read the home page as one extra page (cheap; fixes the ICRAI kind of miss).
2. A main-call rule so several accepted dates resolve to one (call-for-papers page first, then earliest open date).
3. Repeat the run once more to separate flaky renders from real misses.
4. Compare with the grounded call on the same 14 events (the current weekly path found 10 of 13 gold deadlines on 10-03).
