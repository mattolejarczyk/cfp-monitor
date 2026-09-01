# Using the customer's own edits as a work signal

**2026-09-01.** Three questions came out of the ESF MENA reconciliation: what counts as
discovery versus verification, what a human "Verified" is worth once it ages, and whether we can
use per-cell edit history the way a person can by right-clicking a cell.

## 1. Three jobs, not one queue

They cost different amounts and are worth different amounts, and running them as one queue is
what produced a day of correct work on rows nobody was acting on.

| | what it is | cost | where the value is |
|---|---|---|---|
| **Discovery** | conferences we do not hold at all | grounded API requests - the only expensive one | coverage: what are they missing entirely |
| **Verification** | rows the customer has not acted on | our own crawl, effectively free | **the biggest bucket and the highest value** |
| **Re-verification** | rows they verified, where their check has aged | our own crawl | catching what changed after they looked |

**The numbers, 2026-09-01, across both client sheets (111 rows):**

    53 rows carry no status at all              <- the verification queue
    52 rows last updated more than 60 days ago  <- the re-verification queue
    13 rows last updated more than 90 days ago
       median age of their last update: 26 days; oldest: 126 days

ESF MENA is the re-verification case and it is why the category matters: verified by them on
28 May, `Accepted`, $12,500 pending - and the organiser announced afterwards that the 2026
standalone event would not run. **A human "Verified" is a fact about a date, not a permanent
property of the row.**

## 2. What "verified by their team" should mean to us

    Verified + acted (Submitted / Accepted / Declined) + deadline passed   STOP. Done.
    Verified + acted + event still ahead                                   watch for cancellation only
    Verified + no action + check is recent                                 leave alone
    Verified + no action + check is 60+ days old                           RE-VERIFY - cheap, and this is where ESF MENA sat
    Not verified, no action                                               verify - our core job

The trap is treating "Verified" as a permanent stop signal. It is a stop signal with a
timestamp, and their `LATEST UPDATE` column supplies the timestamp on 110 of 111 rows.

## 3. Per-cell edit history: we cannot read theirs, and we do not need to

**Google's Sheets API does not expose it.** The right-click "Show edit history" is a UI feature.
The Drive Activity API reports file- and range-level activity, needs OAuth, and does not give
reliable per-cell attribution for this purpose.

**We can derive the same signal ourselves, and better, by diffing our own snapshots.**

`scripts/snapshot_customer_sheet.py` already exists, `src/cfp_monitor/sheet_diff.py` already
computes week-over-week change, and `customer_snapshots/` already holds one snapshot per client.
**Exactly one** - taken 2026-08-30 - which is why nothing can be diffed yet. The machinery is
built and has never had a second data point.

A second snapshot turns on all of this:

- **which cells a human changed since we last looked** - objective, and not dependent on them
  maintaining a column
- **rows to stop working**, because they acted
- **rows to prioritise**, because nobody has touched them in months
- **a deadline they changed that disagrees with ours** - they may know something we do not, and
  that is a lead, not an error to correct

### Two signals, and they check each other

    LATEST UPDATE (their column)   what they BELIEVE they last touched - self-reported,
                                   and only as good as their discipline in maintaining it
    snapshot diff (ours)           what ACTUALLY changed - objective, no API, no auth,
                                   survives them changing tools or columns

Use the diff as the fact and their column as the cross-check. Where the two disagree - a cell
changed but `LATEST UPDATE` did not move - that is worth knowing on its own.

### What this needs

Snapshotting is currently a manual export (their choice, agreed 2026-08-30). One snapshot per
week, taken before the Sunday verification sweep, is enough to make every point above work. It
does not need to be automated to be useful; it needs to happen twice.

## 4. What we must never do with this data

`status`, `status_details`, `NOTES` and `priority` are the customer's fields under contract
section 3. We read them to choose our work and to catch contradictions. We never write them, and
we never propose "correcting" their pipeline state - a row they marked `Declined` is not a
defect.
