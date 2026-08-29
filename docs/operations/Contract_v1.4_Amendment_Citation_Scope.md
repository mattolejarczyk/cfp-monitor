# Contract Amendment v1.4 - what a citation is tested against

**Date:** 2026-08-29 · **Amends:** Joint Pipeline Contract v1.1, section 8 (acceptance gate)
**Agreed by:** downstream 2026-08-29, upstream 2026-08-29
**Status:** implemented in `scripts/accept_delivery.py`; canaries in `tests/canaries.py`

---

## What changes

**Criterion 3 - "Cited page contains its quote" - now evaluates ACTIVE deadline claims only.**
It does not fire when:

1. `SUBMISSION DEADLINE` is **blank**. No claim is made, so there is nothing to evidence.
2. `SUBMISSION DEADLINE` has **already passed**.

**Rule R3b is retired.** It tested the SHAPE of a citation - is this URL a homepage - as a proxy
for whether the cited page carries the sentence. Criterion 3 tests that outcome directly.

Nothing else changes. A **live call whose cited page does not carry its quote still fails**,
which is the case the criterion exists for.

## Why - the measurement, not the argument

On 2026-08-29 every cited row in the delivery was re-fetched with the gate's own reader and
classified. Criterion 3 was failing **186** rows:

| | Rows | Share |
|---|--:|--:|
| No deadline claimed at all | **108** | 58% |
| Deadline already passed | 50 | 26% |
| **Genuinely live call** | **28** | **15%** |

So 84% of the failure was the criterion testing rows it should never have been applied to.
After both exemptions the same delivery fails on **28** - and those 28 are a real, workable
research queue rather than a wall.

### On blank deadlines

108 rows carried a `DEADLINE_QUOTE` and a `DEADLINE_EVIDENCE_URL` while claiming no deadline.
Reading a sample by hand showed what the quotes actually were:

- *"June 2-3, 2027 - Boston, MA."* - the event date
- *"2026 Event Calendar. 8/19 (Wed.) 8/20 (Thu.)..."* - a calendar strip
- *"The content on munich_i pertains to automatica 2025..."* - a site disclaimer
- *"Information on both 2028 events will be launched in the coming months."*

A citation is evidence FOR something. Where nothing is claimed there is nothing to verify, and
failing the row teaches neither side anything. Under 2.6 the honest form is a blank quote and a
blank evidence URL. Upstream is clearing these as a separate cleanup pass.

### On passed deadlines

A call-for-papers page is routinely taken down once its deadline passes and the site rolls to
the next edition. The quote going missing afterwards is **expected decay** and says nothing
about whether the citation was sound when it was made. One of the 50 had a deadline that passed
317 days earlier.

Without this exemption, every delivery accumulates criterion-3 failures purely by ageing, with
nobody at fault. A criterion that fails good work for getting older is one people learn to
ignore - and an ignored criterion is worse than no criterion, because it still looks like
coverage.

**This exemption is also a deletion guard.** Before it existed, an automated pass proposed
withdrawing 18 citations; 14 were passed-deadline rows and would have been wrong. That output
was discarded. `rules.may_withdraw_citation` now refuses those automatically.

### On retiring R3b

R3b flagged 34 rows on 2026-08-27. We checked each against our evidence table: **14 of them had
their quote present on the cited homepage.** The citations worked. A hardened shape rule would
have rejected them, and the only way to satisfy it would have been to invent a deeper URL - the
exact behaviour R3 forbids.

Testing the outcome passes those 14 and fails the 20 that deserve it, without anyone editing a
row to satisfy a rule. The check is kept in the source behind `REPORT_SHAPE_ADVISORY = False`,
because the reasoning is worth more than the check was.

## What this does NOT do

- It does not relax criterion 2. A cited page returning 404/410 still fails, whatever the
  deadline says.
- It does not excuse a live call. The 28 remain a failure and block acceptance.
- It does not permit deleting stale citations. A missing quote on a passed-deadline row is not
  grounds for withdrawal; those rows are left exactly as they are.

## Ruling log entry

| Date | Ruling |
|---|---|
| 2026-08-29 | Criterion 3 evaluates active deadline claims only - blank and passed deadlines exempt. R3b retired: the outcome is tested directly, so the shape proxy is redundant and, on 14 of 34 measured rows, wrong. |
