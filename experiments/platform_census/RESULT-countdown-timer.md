# ACT-25 (c): does a countdown timer on a page reliably signal the next edition? (2026-10-05)

Read-only. Script `countdown_scan.py`: the offline page library (355 readable pages, 70 sites, fetched 2026-10-01) opened mode=ro, the live database mode=ro, nothing fetched. The countdown's target is
`last_fetched_at` plus the time remaining, in UTC, so it is an estimate to about a day.

## What the data shows
- **12 of 355 pages (3 percent), on 4 sites, hold a countdown in their saved text.** Many counters are built by script and may not be in the saved text at all, so 3 percent is a floor, not a rate.
- **A countdown that is labelled 'Starts:' agrees with our stored start date.** ccus-expo.com ('Starts: 132 DAYS 13 HOURS 14 MIN', fetched 2026-10-01) counts to 2027-02-10 15:54 UTC; we store 2027-02-10 for Carbon
  Capture Technology Expo North America 2027. hydrogen-expo.com ('Starts: 132 DAYS 3 HOURS', fetched the same day) counts to 2027-02-10 15:00 UTC; we store 2027-02-10 for Hydrogen Technology Expo North America 2027.
  Both are the NEXT edition (2027), shown on the page while the call is closed. Two of two exact.
- **A countdown is not always the event.** leadventgrp.com counted 'Pre-Registration Sales End In 821 Days' (to 2028-12-30: a sales deadline, not an event). wildwesthackinfest.com carries a 'Countdown!' widget that
  gave three different targets on pages fetched the same afternoon (about 2026-10-08, 2026-10-23, 2026-10-28): it rotates through the site's upcoming events, and the first is a pre-conference training day.
- From the pins (operator verified 2026-10-03): Carbon Capture Technology Expo MENA's page shows the 2027 edition (8-9 June 2027) with a countdown while the 2026 edition is closed, and CarbonZero's page shows
  'October 27 - 29, 2026' with a countdown while our start date was wrong. In both the countdown pointed at the right edition. n = 2, from the operator's reading, not from this scan.

## Verdict
A countdown **can corroborate** a date when its label says what it counts to ('Starts:', 'Event begins'), and then it agreed 2 of 2 here (and 2 of 2 in the pins). It is **not a discovery signal**: it appears on about 3 percent
of pages, the target is sometimes a sale deadline or a side event, and a rotating widget gives several targets on one site. n is small (12 pages, 4 sites); do not treat 2 of 2 as a rate.

## Recommendation
1. Do **not** build a countdown reader to find next editions. Failure point B10's 'a countdown timer signals the next edition' idea should be recorded as 'works when labelled and present; too rare to be the method'.
2. If cheap to add, let the shadow reader (ACT-20) note a labelled 'Starts: N DAYS' countdown as an extra corroboration line (implied date vs stored start date, never a value we ship). `countdown_scan.find_countdown` and
   `implied_date` already do the arithmetic and are tested.
3. The sitemap dates and the next-edition page-title checks (experiments/gap5_next_edition) remain the better discovery routes.
