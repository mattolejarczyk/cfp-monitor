# Gap 4 - rows never researched

**Status:** theory written, not started.

## What happens today
24 of 113 rows came back "not researched" after 4 tries each. 9 of the 24 were events that had
already happened. Most failures were Google 504 timeouts (98, ~35% of all attempts) - on Google's
side: a longer wait limit was tested on 2026-09-19 and did not help.

## Ideas to test, separately
- **4a Skip events already over.** Use the existing lifecycle rules (DECISION-TREE.md,
  src/cfp_monitor/lifecycle.py) to leave concluded events out of the research list; last week's
  version stays on the page. Measure (no AI): how many 2026-09-27 rows it would have skipped, and
  that none of them was a row a customer is acting on (customer_context).
- **4b Retry failures once, later.** At the end of the run, after a pause, re-research only the rows
  that failed (the existing --redo-stubs option). Measure: of the failed rows, how many succeed on a
  delayed retry. Costs about 1-2 requests per failed row - budget to be agreed.

## "Proven" means
4a: fewer requests and fewer failed rows, with no customer-relevant row skipped.
4b: a clear share of failed rows recovered for a small, bounded cost.
