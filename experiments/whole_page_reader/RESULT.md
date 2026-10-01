# Whole-page model reader: result (2026-10-01)

Plan: `docs/design/whole-page-reader-experiment.md`. Model `deepseek/deepseek-chat` via OpenRouter, one request per page, temperature 0. Code (not the model) decides what is accepted: label must be `submission_deadline`, the unit text must be a literal substring of the page, the date's day and month must be written in it, and its year must be stated in the unit or its heading. Budget approved: 60 requests, 0.50 USD. **Spent: 56 requests, 0.082 USD.**
Answer keys: dev = `experiments/sentence_picking/labels.json` (15 pages, the prompt was developed on these only); holdout = `experiments/heading_reader/holdout_labels.json` (10 pages, locked before this reader existed); fresh = `fresh_labels.json` (17 pages, locked by commit 593584e before any model run on it). Prompt v2 and the gate were frozen by commit 5da7c7e before the holdout and fresh runs.

## As run (prompt v2 frozen, strict JSON parsing)
| Set | Pages | Accepted | Correct | Wrong purpose | Precision | Recall | Unparseable outputs |
|---|---|---|---|---|---|---|---|
| Dev (v1 on 8 pages, v2 on 7; developed on) | 15 | 21 | 21 | 0 | 1.00 | 18/24 | 1 |
| Holdout | 10 | 3 | 3 | 0 | 1.00 | 2/2 | 1 |
| Fresh | 17 | 10 | 8 | 0 | 0.80 | 7/10 | 3 |
| Holdout + fresh | 27 | 13 | 11 | 0 | 0.85 | 9/12 | 4 |

Pre-registered thresholds: precision at least 0.95, recall at least 0.80, zero registration, event or notification dates accepted as submissions, every quote verbatim, cost within 2x. **As run: precision and recall fail; the zero-wrong-purpose and verbatim criteria pass; cost passes (about 0.1 cent per page).** The combined set has only 12 submission labels, below the 20 planned, so the test is low power.

## Why it missed, and what was changed AFTER seeing results (post-hoc, labelled as such)
1. **My two key errors, found by the model.** Both "unlabelled" accepted dates are real submission deadlines that my hand labelling missed: DEF CON 34, 2026-05-01 ("The deadline for submissions is May 1, 2026 at Midnight UTC", on a long line my scan cut off) and a German OWASP page, 2026-06-21 ("CfP schliesst: 21. Juni 2026"; my scan only knew English months). The key is NOT edited; they are reported separately.
2. **Runaway outputs.** On 4 pages the model looped on near-empty items ("finished 8 days ago", "Copyright 2026") until its output was cut off mid-string, which broke the JSON. The correct items were at the START of those outputs. An item cap in the prompt (v2b, re-run on those 4 pages, 4 requests) fixed 1 of 4. A tolerant parser that recovers the complete leading items from a cut-off output fixed the other 3 at no model cost; the gate still checks every item.
3. **One strict-gate miss:** BSides Las Vegas "Closes: May 8th" carries no year in the unit; the heading's year was not available, so the gate rejected it. That is the designed behaviour (a year is never invented), and it is now a recall cost, not an error.

## Post-hoc (item cap on 4 pages plus tolerant parsing; no other change)
| Set | Accepted | Correct | Wrong purpose | Precision as keyed | Recall as keyed |
|---|---|---|---|---|---|
| Dev | 25 | 25 | 0 | 1.00 | 22/24 |
| Holdout | 3 | 3 | 0 | 1.00 | 2/2 |
| Fresh | 13 | 11 | 0 | 0.85 (1.00 if my 2 key errors are credited) | 9/10 (11/12 corrected) |
| Holdout + fresh | 16 | 14 | 0 | 0.875 (1.00 corrected) | 11/12 (13/14 corrected) |

## Read
- The model reader beat my rules reader on every comparable page and found two true deadlines my own scan missed. It never accepted a registration, event, notification or exhibitor date as a submission deadline in any set (0 wrong-purpose in 69 accepted dates across all sets).
- It is **promising but not proven**: as run it failed the strict thresholds; the passing post-hoc numbers were reached after looking at the results and rest on only 12 to 14 labels, on pages skewed to security events and to calls that have already closed.
- Two real engineering needs, both small: a tolerant parser (or a repetition guard) for runaway outputs, and a year rule for pages that omit one (a nearest-heading-year fallback was rejected on purpose).
- Limits: pages over 16,000 characters were not tested (the IEEE and USENIX pages were excluded); script-built tables not tested.

## Next
Run the model reader on a fresh, larger answer key (the 40-event benchmark, brief 01) with the tolerant parser and the item cap in the frozen version, before wiring anything. Recommended: hand brief 01 to Hermes, whose browser reading passed its first test today.
