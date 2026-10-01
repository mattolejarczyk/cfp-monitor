# Purpose audit of stored deadlines - result (2026-10-01)

Design: `docs/design/heading-aware-reader-design.md` section 5 (Phase 2). Advisory only: page loads (43 new, 2 s apart), no model, no database or delivery writes.
Script: `purpose_audit.py` (`--fetch`, `--report`). Rules are deterministic (own label words, then heading, then legend). Page text and per-row output stay local (git-ignored).

Scope: 39 distinct stored deadlines in Cybersecurity and Utility (the earlier "48" counted a conference once per market).

| Outcome | Rows | Meaning |
|---|---|---|
| CONFIRMED | 9 | a submission unit on the cited page carries the stored date |
| MISMATCH | 1 | the date sits only in a registration unit (the Climate Change conference, found independently on 09-30: the audit reproduces it) |
| UNCLEAR | 1 | date present, purpose not decidable (DEF CON 34: a "Call for Papers is Now Closed" line mixes notification and registration words) |
| ABSENT | 16 | the date is on no page read |
| NO_PAGE | 12 | no readable page (soft 404, shell or no URL) |

Cross-check: for all 16 ABSENT rows the repo's own `verify.find_date` also fails to find the date, so ABSENT is not a reader miss.

## What matters
1. The method works where it can be tested: it flags the one known bad row and passes 9 of 9 spot-read confirmations as real submission lines. Only one known positive exists, so this is not a measured recall.
2. 15 of the 16 ABSENT rows and 11 of the 12 NO_PAGE rows have already-passed deadlines; the page has plausibly dropped the date since. Those are not errors.
3. Not passed, and worth a person's look:
   - SecureWorld Government and Critical Infrastructure, stored 2026-10-28, `[L2] page states 2026-10-28`; the cited events page no longer states that date (11 other dates read).
   - India Energy Week 2027, stored 2026-09-30, status verified; its page lists submission dates 2026-10-15, 2026-11-15 and 2027-01-31 (extended or later rounds).
   - Global Energy Show Canada 2027, stored 2026-12-04: page unreadable (soft 404).
4. Of the 12 rows verified through the call-status layer (`[L0s]`): 3 CONFIRMED by date, 1 MISMATCH (Climate Change), 4 ABSENT and 4 NO_PAGE (all passed deadlines). So 8 of the 12 remain unconfirmed by date.

Limitations: DEF CON's UNCLEAR is a rule-set limit (conflict, not guessed). Year-less dates take the nearest heading year, a weak fallback. Phase 1 (labelled pages plus holdout) is not yet run, so recall of the reader on tables is unmeasured. Nothing was changed.
