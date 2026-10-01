# Whole-page model reader: experiment plan (drafted 2026-10-01, NOT yet run beyond a one-page demo)

**Question.** Can a cheap model (DeepSeek) read an entire high-potential page, label every date on it from a closed list, and give the submission rounds correctly, with code proving each answer is on the page?
**Why this, why now.** Our rule-based reader failed a fresh test (precision 0.33) after weeks of fitting, and our date check cannot read forms like `19 October (26)`. A one-page demo on the Climate Change table was right: Regular 2026-10-19, Late 2026-12-20, registration kept apart, every quote verbatim, 21 s, $0.0009. One page proves nothing; this plan measures it.
**The principle being tested** (STRATEGY.md): when a rule set grows complex, try a cheap model first, with code verifying its output and an answer key scoring it, before building more rules.

## Cost scope (measured price from the demo: about $0.00098 per page at the page sizes we have)
| Run | Pages | Estimated cost |
|---|---|---|
| Development set (15 labelled pages) | 15 | $0.015 |
| Holdout (10 pages, key locked before the reader existed) | 10 | $0.010 |
| Fresh set (new pages, labelled by me before any run) | about 25 | $0.025 |
| One pass over the full 364-page plan | 364 | $0.36 |
| Weekly pass, 364 pages, one month | 4 x 364 | $1.42 |
Proposed hard cap for the whole experiment: **60 requests and 0.50 USD**, whichever first, stopping and reporting at the cap. (The September Gemini bill was 134 USD for comparison.)

## Method (fixed before running)
1. Same model as the best sentence-picking arm: `deepseek/deepseek-chat` via OpenRouter, temperature 0, one request per page, page text up to 12,000 characters. Reuse `experiments/sentence_picking/sentence_pick.py` (call pattern, caps, logging) and `scripts/extract_citations.py` (`locate_verbatim`).
2. The model returns, for every date: nearest heading, the unit text copied exactly, the closing date (a range's END; `(26)` means 2026), a label from a closed list (`submission_deadline`, `submission_opens`, `notification`, `registration`, `event_dates`, `other`), and a round name if any.
3. **Code decides what is accepted:** a date is accepted as a submission deadline only if the model labelled it so AND the unit text is a literal substring of the page (whitespace normalised) AND the stated date parses from the unit text (including `(yy)`), or from its heading plus the unit. The model never writes data directly.
4. **Rounds are kept, not collapsed.** Every submission round is returned with its tier. The rows you act on: the first round whose end is on or after today is the DEADLINE; the later rounds go in `STATUS DETAILS` in the order the conference states them (contract v2.0.1: `STATUS DETAILS` is upstream's field; `NOTES` is the customer's). When the first round passes, the next becomes the deadline on re-read.
5. Prompt developed on the 15 labelled pages only. Frozen and checksummed. Then run once each on the 10-page holdout and on the fresh set. Report the as-run score first; label any later change and score it on pages not yet seen.

## Pass criteria (fixed in advance)
- Accepted submission dates: precision at least 0.95 and recall at least 0.80 against the labels, on the holdout and fresh sets combined.
- Zero registration, event or notification dates accepted as submission deadlines.
- Every accepted unit verbatim on the page; no year invented.
- Cost per page within 2x of the estimate above.
Known weak spot to watch: the demo labelled the Early round "opens" when it is an early proposal deadline. That date has passed, but tier rows are where mislabelling will show.

## Decision this feeds
Pass: wire the model reader in as the table and schedule step (replacing the rules reader), then extend the same pattern to the other fields. Fail: record why, and fall back to advisory use.

## Limits
Holdout has only 2 submission labels, so the fresh set carries the weight; it must hold at least 20 submission labels. All pages so far come from sites that publish text, not script-built tables; those need a render step first.
