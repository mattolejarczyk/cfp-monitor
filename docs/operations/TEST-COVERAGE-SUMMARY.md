# What the 526 automated tests actually check

**One page, for someone who does not work on the code.** Each test is a specific way the system
could mislead the customer, and the check that prevents it. They run in about a minute.

*Counts verified 2026-08-14: every test file appears in exactly one category and the totals
reconcile to the 526 pytest collects. Regenerate with `pytest tests/ --collect-only`.*

---

## 1. Never state a date we cannot prove — 182 tests (35%)

The largest group, because this is the expensive failure: a wrong deadline costs a client a
speaking slot.

| Tests | What it prevents |
|---|---|
| 82 | The model pointing at a sentence that is not on the page. Whatever it returns must appear word-for-word on the page we fetched, or it is discarded. |
| 52 | A blocked or slow page being recorded as "no deadline here". Only a genuine page-not-found disproves anything. |
| 23 | A quote about one kind of deadline being used to prove another - a *withdrawal* date passed off as a *submission* date. |
| 11 | An error page counting as real content because it contains a lot of HTML. Words are counted after the markup is stripped out. |
| 10 | A closed call still being displayed as open. |
| 4 | Dates being misread - no year given, or day-first versus month-first. |

## 2. Never offer a link we know is broken — 54 tests (10%)

| Tests | What it prevents |
|---|---|
| 31 | A dead link shown as working. A projected date wearing a "Verified" badge. Counts that ignore the market filter. |
| 19 | Citing a social media page or a link shortener as evidence of a deadline. |
| 4 | Malformed or unclickable addresses reaching the page. |

## 3. Keep each conference's identity stable — 28 tests (5%)

| Tests | What it prevents |
|---|---|
| 13 | A tidy-up quietly rewriting hundreds of records. Compares every derived value against a blessed snapshot and fails if anything moved. |
| 9 | Correcting a conference's year silently renaming its identifier and breaking every reference to it. |
| 6 | This year's record being overwritten by next year's, or a live event archived because a duplicate exists. |

## 4. Match the customer's list to ours — 21 tests (4%)

| Tests | What it prevents |
|---|---|
| 14 | Attributing their correction to the wrong conference. Covers web addresses, abbreviated names, editions and dates. |
| 7 | Mis-reading their spreadsheet columns when comparing their records against ours. |

## 5. Never lose or corrupt data — 67 tests (13%)

| Tests | What it prevents |
|---|---|
| 25 | Rows silently dropped or overwritten when upstream research is imported. |
| 17 | Columns shifting in the delivery file, or the customer's own columns being overwritten by ours. |
| 14 | A weak or failed result overwriting a confirmed one. |
| 11 | Malformed files leaving the building. |

## 6. Right conference, right client list — 39 tests (7%)

| Tests | What it prevents |
|---|---|
| 20 | A conference missing from a client's list, or appearing in one where it does not belong. |
| 13 | Duplicates surviving a merge, or valid rows being filtered out. |
| 6 | Mis-labelled subject areas within a conference. |

## 7. The machinery keeps working — 135 tests (26%)

Individually dull; collectively this is what stops a silent breakage.

| Tests | What it prevents |
|---|---|
| 70 | A typo in a script that only runs on Sunday nights. Added after exactly that shipped once. |
| 11 | A delivery reaching the customer without passing its contract checks. |
| 9 | Licensing and access faults. |
| 8 | Discovery spending far more than intended, or researching rows that need no research. |
| 6 | The automation closing a browser window a person is using. |
| 31 | Coverage reporting, review edits, alerts, reference sets, page fetching, proxy and reporting. |

---

## What these tests do NOT cover

Worth stating, so the number is not read as more than it is.

- **They do not prove the data is correct.** They prove the *rules* are enforced. Whether one
  conference's deadline is right is established by reading its page, not by a test.
- **They do not cover deployment.** That the scheduled job runs the current code was checked by
  hand, and needs re-checking whenever the live build is updated.
- **They do not cover how the page looks** - only the decisions behind what it shows.

## What they are for

A **ratchet**. Once something is fixed, a test keeps it fixed. A large share exist because that
exact thing went wrong once and was then locked down - the four covering market-filtered counts,
for instance, exist solely so a defect the customer found in a meeting cannot quietly return.
