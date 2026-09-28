# Gap 3 - AI answering from memory

**Status:** theory written, not started. The only gap whose test costs AI requests - budget to be
agreed before any run.

## What happens today
The AI decides for itself whether to run a Google search. On 2026-09-27, 89 of 178 answers that came
back ran NO search; each was thrown away and retried, costing roughly a third of the run's requests.

## Ideas to test, ONE AT A TIME (each its own sample run)
- **3a Hand it the search.** Put an explicit query at the top of the prompt ("Search Google for:
  '<name> call for speakers <year> deadline'").
- **3b Short search-first retry.** When an answer ran no search, retry with a short prompt that asks
  only for the search and the deadline, instead of repeating the long prompt.
- **3c Model comparison.** Same prompt, a different Gemini model.

## How it would be measured
- Same 20 rows for every variant (mixed markets, mixed difficulty), taken from the 2026-09-27 input.
- The grounding trail already records, per attempt, whether a search ran - so the measure is simply
  "share of answers with a search behind them" and "requests spent per researched row".
- Budget per variant: about 20-40 requests. To be agreed before spending.

## "Proven" means
A clearly higher share of searched answers AND fewer requests per researched row, on the same rows,
with answer quality not worse (gate result on the same rows).
