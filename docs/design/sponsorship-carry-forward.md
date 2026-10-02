# Sponsorship carry-forward: decision document (2026-10-02)

**Status: for the operator to decide. Nothing is built.** Evidence below is measured from the approved Cybersecurity and Utility files and the audit script; where a figure is an estimate it says so.

## The decision in one paragraph

Every weekend the research asks again, from scratch, whether each event requires paid sponsorship and what it costs. That is about 70% of a weekend's grounded searches (worklog 2026-09-30), and the answers drift in wording from week to week even when the facts have not changed, and sometimes a cost we already knew comes back blank. **Carry-forward** means: when the new research returns Unknown or blank for a row, keep last week's resolved sponsorship answer, with its evidence, instead of overwriting it; and, optionally, do not ask again at all while the answer is fresh. Decide **how far to go** (option A, B or C below) and the three open questions at the end.

## What happens today

- The main audit prompt asks for `SPONSOR_REQUIRED` (Yes, No, Unknown; Unknown is the default and a blank never means No), `SPONSOR_URL` and `SPONSOR_COST` on every row, every run. `SPONSOR_QUOTE` is ours, filled downstream (R20a).
- A separate **sponsor-only pass** (`run_market_audit.py --sponsor-only`) asks one narrow sponsorship question, 14 searches per call, for rows still Unknown. It is already cheap by construction *when run against last week's own output*: a row already Yes or No is written through free.
- The weekly research input list (`Cybersecurity_input.csv`, 22 columns) has **no** `SPONSOR_*` columns, so each Saturday's research starts every row as Unknown and the sponsorship question is asked again. There is a precedent for carrying prior values: `preserve_repaired_citation(record, prior)` already stops a fresh pass overwriting a repaired citation.
- Rule R18b (gate): a sponsorship requirement must carry its own evidence. Anything carried forward must carry its URL and quote with it.

## What the data says (approved files, 2026-10-02)

| | Cybersecurity (58 rows) | Utility (54 rows) |
|---|---|---|
| `SPONSOR_REQUIRED` Yes / No / Unknown | 49 / 2 / 7 | 47 / 0 / 7 |
| Rows with a cost | 43 | 41 |
| Rows with a URL | 51 | 51 |

Week-over-week, for rows with a known answer in both the 09-27-before-promote file and today's file (42 Cybersecurity, 34 Utility):

| Field changed between weeks | Cybersecurity | Utility |
|---|---|---|
| `SPONSOR_REQUIRED` (Yes vs No) | **1** of 42 | **0** of 34 |
| `SPONSOR_URL` | 20 of 42 | 8 of 34 |
| `SPONSOR_COST` (free text) | 23 of 42 | 14 of 34 |
| A cost we had that came back **blank** | **4** | not checked |

Reading: the *fact* (is sponsorship required) is almost perfectly stable, one change in 76 rows. The *wording and the page chosen* churn constantly. Examples seen: "Platinum, Gold, Silver. Specific pricing is not listed publicly" became "Sponsorship opportunities available for community-driven non-profit events" for the same event; "Contact IChemE Events at Redactive" gained an email address. So most of what the customer would see change week to week is noise, and some of it is information loss.

## Cost (estimate, not measured per search)

September's bill was 134.06 USD, 73% of it search queries at 14 USD per 1,000 (worklog 2026-09-30). If the sponsorship passes are about 70% of a weekend's searches and the weekends are most of the search spend, the sponsorship share is **at most about 68 USD a month** (134.06 x 0.73 x 0.70), likely less. Not measured per pass; a shadow week would measure it.

## Options

| | Option | What it does | Saves | Risk |
|---|---|---|---|---|
| **C** | Do nothing | Keep re-asking | nothing | wording churn and blank-over-known continue |
| **A** | **Never lose a known answer** | A merge guard after research: if the new row is Unknown or has a blank URL, cost or quote and last week's approved row (matched through `identity.to_canonical`, contract 5.4) has a resolved answer **for the same edition**, keep last week's fields, evidence included | no searches (still asks); stops the blank-over-known loss and the Unknown flip-back | Low: it only fills gaps, never overrides a fresh non-blank answer. Stale text can persist |
| **B** | **A, plus do not ask while fresh** | Put last week's resolved `SPONSOR_*` into the research input so a resolved, fresh row skips the sponsorship question. Re-ask when: new edition, event date moved, `SPONSOR_URL` now dead, answer older than a set number of days, or any customer marks the row Urgent | most of the roughly 70%, estimated up to about 68 USD a month | Medium: a stale answer survives until a trigger fires; needs `run_market_audit.py` (upstream's) to read the new input columns |

## Recommendation

**Do A now, B after one shadow week.**

- **A is small and safe**: it is the same shape as `preserve_repaired_citation`, it can live on our side in the weekend import (no change to upstream's research script), it changes no fresh answer, and it directly removes the cases where we lose something we knew. Estimated build: a function, a test file and one row in the weekend process doc.
- **B waits** for two things: a measured number (run the existing sponsor-only pass in dry-run mode to count how many rows each rule would skip, no cost), and upstream agreeing to read `SPONSOR_*` from the input list. Without both, B is a guess.

## Guardrails for either option

1. Carry only **within the same edition** (`key_year`/`EDITION`); a new edition starts fresh.
2. Carry **evidence with the answer** (URL, quote, and the date it was last confirmed) as one unit, never the answer alone (R18b).
3. **Never override a fresh non-blank answer**; carry-forward only fills gaps.
4. **Stamp it**: add a per-row `sponsor_confirmed_on` so the page can say "as of", because `SOURCE_AS_OF` is today the only stamp and it does not distinguish a carried answer from a fresh one.
5. Re-ask triggers (B): new edition, moved event date, dead `SPONSOR_URL`, answer older than the TTL, Urgent from any customer.
6. Report what was carried in the weekend recap, so a carried value is never mistaken for fresh research.

## Decisions I need from you

1. **Option**: A now and B later (recommended), A only, or leave as is?
2. **TTL for B**: how old may a carried answer be before it is re-asked? I suggest 90 days, because sponsorship prospectuses are usually published once per edition.
3. **Who implements B's input change**: upstream adds `SPONSOR_*` to `run_market_audit.py`'s input handling, or we feed it through the input list and ask upstream only to honour it.

## Not in scope here

The other roughly 24 fields (city, categories, overview, organizer and so on) have the same "keep, carry forward, or second narrow call" question (PROGRESS-CHECKLIST). Sponsorship is the one with a measured cost and a measured stability, so it is the right one to decide first; the same pattern, once proven here, would be the template.
