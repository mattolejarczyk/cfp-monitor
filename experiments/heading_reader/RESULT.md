# Heading-aware reader, Phase 1 - result (2026-10-01)

Design: `docs/design/heading-aware-reader-design.md`. Deterministic, no model, no new network use beyond rendering 10 holdout pages once. Reader code: `experiments/purpose_audit/purpose_audit.py`
(units, purpose, years) driven by `heading_reader.py`. Answer keys: `experiments/sentence_picking/labels.json` (15 pages) and `holdout_labels.json` (10 pages, locked with a
sha256 and committed before the reader ran: commit 8346fba). Rules were frozen by commit b88b578 before the holdout was run.

| Run | Pages | Accepted | Correct | Wrong purpose | Precision | Recall |
|---|---|---|---|---|---|---|
| Labelled, FIRST run as designed | 15 | 34 | 22 | 9 | 0.65 | 22/24 (sentence step alone: 12/24) |
| Labelled, after 4 general rule fixes (post-hoc, fitted on these pages) | 15 | 24 | 24 | 0 | 1.00 | 24/24 |
| **Holdout, one run, rules frozen** | 10 | 6 | 2 | 4 | **0.33** | 2/2 |

The four fixes (all general, none page-specific): "opened" counts as an opening word; "Dates/Location", "main conference", "trainings" and "show days" count as event wording;
tier words (Early, Regular, Late, Launch, Round n) carry no purpose of their own; on a page whose URL names exhibitors or sponsors, weak words (application, deadline) are not a submission.

## Read against the criteria fixed in advance
- Recover at least 7 of the 8 missed labels and lose none of the 16: **met** on the labelled pages (24 of 24), but that figure is fitted.
- Zero wrong-purpose dates accepted: **met on the labelled pages only after the fixes; NOT met on the holdout (4 wrong).**
- No year invented: met (year-less dates are never accepted). Every accepted unit is cut from the page text: met.

## Why the holdout failed, and what it shows
Accepted dates by how their purpose was decided:
- from the line's OWN words: 19 right, 0 wrong (labelled 18/0, holdout 1/0);
- inherited from a HEADING: 9 right on the labelled pages, **1 right and 4 wrong on the holdout**.

The holdout's four wrong dates: three on a page that writes **date first, label underneath** (`Monday, 7 July 2025` / `Call for Papers Opens`): the reader takes the label ABOVE the
date, so every date inherits the previous line's purpose; one bare page date (`2017-09-18`, a post date) that inherited "submission" from a nearby menu-like heading.
Also not handled: a column table (a line of labels, then a line of dates), seen on one holdout page, where the right date was accepted only because the closing label sat directly above it.

## Limits of this evidence
The holdout has only **2 submission labels** on 10 pages (8 pages were thin, login, error or event-date pages), so its power is low in both directions. The labelled score is not independent.
A larger, fresh holdout is needed before any claim of reliability.

## Conclusion for use
Own-words judgments are safe so far (19 of 19). Heading-inherited judgments are not safe as an automatic acceptance. Until a revised rule passes a fresh holdout:
use the reader only as an advisory list for a person (as in the purpose audit), accept automatically only own-words units, and show heading-inherited ones as "needs a person".
Candidate fixes, NOT applied (the holdout is now spent): read a date-above-label layout in the other direction; do not inherit purpose onto a bare date line unless it is a table row or list item.
Nothing is wired into any job; nothing was written to the database.
