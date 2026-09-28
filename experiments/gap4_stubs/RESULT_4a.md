# Gap 4a result - skip rows the decision tree says are free (2026-09-28)

**Measured, read-only, no AI.** Script: `gap4a_measure.py`. Row detail: `gap4a_rows.txt`.
Customer check: `gap4a_customer_context.txt`. Baseline: the 2026-09-27 research (113 rows, ~280
requests), assessed against last week's approved files as of Saturday 2026-09-26.

## What the rule would have done

| | Cybersecurity | Utility | Total |
|---|---:|---:|---:|
| Rows skipped (event over, next one not yet worth hunting) | 14 | 5 | **19** |
| AI requests saved | 32 | 13 | **45** (~16% of the run) |
| Failed ("not researched") rows avoided | 3 | 1 | **4** of 24 |
| Rows where the skipped research changed something shown | 3 | 1 | 4 (below) |

## What would have been lost - nothing of value
- CrowdStrike Fal.Con 2026: "September 03" -> "September 3". Formatting only.
- SecureWorld St. Louis / Quantum Cryptography: research BLANKED a deadline that had already passed.
  Skipping keeps the dated past deadline - arguably better.
- Hydrogen Technology Expo MENA 2026 (series ended): research filled in the past edition's dates.
  Nobody is acting on it.

## Customers
0 of the 19 are LIVE for a customer. 17 are on no client sheet; Climate Week NYC is MOOT (submitted,
then withdrawn by the customer). DEF CON 34 is TRACKED by Arnica with an internal 2027 estimate; the
research this weekend changed nothing on it, and the tree resumes researching it 60 days after the
event (early October), which is when a successor call could first appear.

## Correction to the earlier diagnosis
Earlier today I said 9 of the 24 failed rows were events already over. The tree skips only 4 of them:
the other 5 ran more than 60 days ago, where the agreed rule is to LOOK FOR THE NEXT EDITION (branch 4,
costs quota). That is the rule working as intended, not waste.

## Limits
One weekend. The skip rule is the existing tree, unchanged; no new judgement was added.

## Recommendation
Adopt, with one extra guard: never skip a row a customer marks LIVE. When built, skipped rows keep
last week's approved version automatically (weekend_import already carries over any event the
research did not cover); the research-completeness check must count skipped rows as intended, not
missing. Wiring it in is a separate, reviewable change - not done here.
