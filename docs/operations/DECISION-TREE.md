# The decision tree - where a conference is in its life, and what follows

**This is the doc to review a decision against.** The contract says who owns what. The runbook
says how to run things. `JUDGEMENT.md` records conclusions we learned the hard way. This one says
what follows, mechanically, from the three facts we hold about time.

It is **executable**: `src/cfp_monitor/lifecycle.py` is this document, and every rule below is a
branch in `assess()`. If they disagree, the code is wrong and this file is the specification.

---

## The principle

> **Derive it. Never store it.**

Judgement rule 5, learned again on 2026-08-31. The acceptance gate failed on two rows:

```
  SecureWorld New York City 2026   STATUS=Open, deadline 2026-08-29
  European Biomethane Week 2026    STATUS=Open, deadline 2026-08-30
```

Both deadlines had passed **within 48 hours**. Neither needed research, a fetch, or a request.
`STATUS` was wrong because it was **stored** - frozen at whatever it was when someone last wrote
it. A derived value cannot go stale, costs nothing, and is right the instant the clock moves.

Everything in this document is computed at read time and written back nowhere.

---

## The three facts

Everything below is decided from these, and nothing else:

| Fact | Column | Question it answers |
|---|---|---|
| When the **event** is | `START DATE` | Has it happened? |
| When the **call** closes | `SUBMISSION DEADLINE` | Can someone still submit? |
| Whether a **successor** exists | other `EVENT_ID`s in the series | Is this row still the live one? |

---

## Layer 1 - edition state (R13)

Which instalment of the series this row is. Derived by `lifecycle.edition_states()`.

| State | Rule | In the delivery today |
|---|---|---:|
| **Active** | Latest edition, and the event has not yet run | 342 |
| **Watching** | Latest edition, the event HAS run, no successor exists yet | 52 |
| **Archived** | A later edition of the same series exists | 2 |
| **Discontinued** | Prose states the series has permanently ended, and it is quoted (R16) | 10 |

Two traps, both paid for:

- **Group by `EVENT_ID` before series.** Rows sharing an `EVENT_ID` are ONE edition in several
  markets, not several editions. Reversing this produced advice to merge 12 rows of correct data.
- **A rotating event is not a dead one.** EMO Hannover 2027 says *"will not be held in
  Hannover... the EMO cycle dictates"*. The series is alive; it moved venue.

---

## Layer 2 - the tree

Read top to bottom. **The first branch that matches decides**, and the cheapest disqualifier is
first (judgement rule 8).

| # | Condition | Customer sees | We do | Cost |
|---:|---|---|---|---|
| 1 | **Discontinued** | Closed | Nothing, ever | free |
| 2 | **Archived** | Upcoming | Nothing - the successor carries it | free |
| 3 | **Watching**, event ran < 60 days ago | Upcoming | **Watch only.** Do not hunt the successor | free |
| 4 | **Watching**, event ran ≥ 60 days ago | Upcoming | Look for the successor (R14) | quota |
| 5 | **Active**, no deadline recorded | Upcoming | **Find the call - discovery** | quota |
| 6 | **Active**, deadline is prose not a date | Upcoming | A human reads it (R23) | human |
| 7 | **Active**, deadline passed | **Closed** | Watch for the next round or edition | free |
| 8 | **Active**, closes ≤ 7 days | Open, **top of the page** | Surface it | free |
| 9 | **Active**, closes ≤ 30 days | Open | Surface it, re-verify the date | free |
| 10 | **Active**, closes > 30 days | Open | Re-verify weekly against the cited page | free |

### Why branch 3 exists

A conference that ran last week needs **almost nothing from the customer for months** - the next
edition is most of a year out. But it does need one cheap thing from us: move it to *Watching*
and stop hunting a call that no longer exists.

Chasing the successor immediately spends requests to be told nothing, because organisers rarely
announce that early. Judgement rule 1 is the harder version of the same point: on 2026-08-11 we
spent **11 of 93 grounded requests** researching submission deadlines for conferences that had
already taken place.

### Why branch 5 is the expensive one

**No deadline recorded is not a verification problem.** Verification checks a claim against its
page; there is no claim. Only research can find a date nobody ever captured. This is the branch
that decides the cadence argument, and it covers **198 of 406 rows** - just under half the file.

It is also exactly the state of the 24 rows in the customer's "Needs Verification" queue that we
hold but have no deadline for. They were never reachable by the weekly sweep, and that is why
they sat untouched since 5 August.

---

## What it says about the real delivery

Run over the 406-row delivery on 2026-08-31:

```
  what we do next                                    cost
  198  find the call - DISCOVERY, not verification   quota
   78  watch for the next round or edition           free
   31  look for the successor edition (R14)          quota
   28  surface it, re-verify before relying on it    free
   28  re-verify weekly against the cited page       free
   21  watch only - do not hunt the successor yet    free
   10  surface it at the top of the page             free
   10  nothing - do not spend a request              free
    2  nothing - the successor carries it            free
```

**229 rows want quota, 177 are free.** That number is the real argument for the cadence change,
and it cuts both ways: a blind full re-audit is ~400 requests, but the tree names the 229 that
would actually learn something. **Scoping the weekly run by the tree is cheaper than the monthly
run it replaces.**

### The finding that needs a decision before it ships

Derived `STATUS` disagrees with stored `STATUS` on **126 of 406 rows**:

```
  Closed  -> Upcoming            65     the event ran; we are watching for the next edition
  Open    -> Upcoming            44     the event already ran but the file still said Open
  Needs Verification -> Upcoming  9
  Open    -> Closed               3     includes both of today's gate failures
  other                           5
```

The 44 and the 3 are unambiguously corrections. **The 65 are a judgement call**: the file says
`Closed` (the call is closed, true) and the tree says `Upcoming` (we are watching for the next
edition, also true). They are answering slightly different questions, and 65 rows changing what
a customer sees is not a change to make on a derivation's say-so.

**Never bless a golden-master diff unread.** Run `scripts/snapshot_delivery.py` before switching
the page over to derived status, and read all 126.

---

## How to use it

```python
from src.cfp_monitor import lifecycle

states = lifecycle.edition_states(rows, today)          # R13, once for the whole file
a = lifecycle.assess(row, states[event_id], today)

a.customer_status   # what the STATUS column should say
a.urgency           # closing this week | closing this month | open | none
a.action            # what WE do next
a.cost              # free | quota | human
a.why               # the reason, in words - always present
```

`a.why` is not decoration. A decision without a reason becomes a rule nobody dares change and
nobody understands, and there is a test asserting every branch has one.

---

## Where this sits

| Document | Answers |
|---|---|
| `pipeline-contract.md` | Who owns what, and what counts as evidence |
| `market-runbook.md` | How to run things, in order |
| `JUDGEMENT.md` | Conclusions a careful person reaches that a pipeline misses |
| **this file** | **What follows mechanically from where a conference is in its life** |
| `src/cfp_monitor/lifecycle.py` | The same thing, executable |
| `src/cfp_monitor/rules.py` | The narrower business rules - withdrawal, sources, rounds |

When adding a rule, ask which of these it belongs in. A rule that fires on **timing** belongs
here. A rule about **whether we may act on evidence** belongs in `rules.py`. A rule that is a
**conclusion we keep failing to reach** belongs in `JUDGEMENT.md` until it can be made executable
- and then it moves here.
