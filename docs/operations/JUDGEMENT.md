# Judgement rules - the conclusions we should reach without being told

The runbook says how to run things. The contract says who owns what. This file is for the
conclusions a careful person reaches in five seconds and a pipeline misses entirely, because
every one of them cost us real time or nearly reached a customer.

Each rule is here because it was learned the hard way. The date is when.

---

## 1. If the EVENT is over, stop looking for its call

**2026-08-11.** We spent 11 of 93 grounded requests researching submission deadlines for
conferences that had already taken place. World PM 2026 ran 25-29 June; we were still hunting
its CFP page in August, and upstream was too.

A past event has no call to find. The page is usually gone, and finding it would change
nothing - nobody can submit.

```
event date has passed  ->  the row is "watch for the next edition", not "find the deadline"
```

Check the EVENT date before spending anything on the CALL. This applies to us, to upstream's
discovery, and to what we show the customer. Nine percent of the delivery is in this state.

**Do not confuse it with a closed call.** A closed call on a future event still matters - the
customer wants to know they missed it, and next year's date is predictable from it.

## 2. A date can be right and still be the wrong answer

The most common defect this year is not a wrong date. It is a correct date attached to the
wrong thing:

| Seen | Actually |
|---|---|
| "1 July 2026" | the deadline to WITHDRAW a presentation (CCUS) |
| "Aug 5 at 12 pm CT" | the LATE-BREAKING deadline, not the main call (RSNA) |
| "September 7" | the co-located CEDIA call, not ISE's own (ISE 2027) |
| "September 1, 2026" | a co-located society's call, on their domain (MD&M West) |
| "October 30, 2026" | when you will be NOTIFIED, not when to submit (NAMM) |
| "August 12, 2026" | manuscripts due, months after abstracts closed (Solid Freeform) |
| "June 22" | first paper to peer review, a later milestone (IMAPS) |

Before accepting any deadline, ask **which call, and whose**. A quote that does not name the
call settles nothing. A quote on a different organisation's domain is almost always a
co-located event.

## 3. Nomination, application and entry are all submitting

**2026-08-11, GreenBiz.** "Nomination Deadline: January 23, 2026" was treated as a different
fact, leaving that row eight months wrong. At many events being nominated IS how you get on
the programme. Treat nominate, apply, propose, enter and "call for presenters" as submitting.

## 4. A missing input must never read as a finding

This one keeps coming back in different clothes:

- A page built without `--checks` showed "Deadline confirmed 0" - not an obviously broken
  page, a confident claim that nothing was verified.
- A merge run without the seed map reported five per-row DATA rejections for a path problem.
- An unparseable deadline turned every date check into a no-op and an unrelated sentence
  became a citation.
- A refresh whose ID mapping failed matched 0 of 406 rows.

**If an input is absent, refuse or shout. Never continue quietly.** Zero is a number and
readers believe it.

## 5. A stored judgement goes stale; derive it instead

STATUS said "Open" on rows whose deadline had passed, because it was written when the delivery
was produced and nothing updated it. The page even showed "passed" beside the Open badge on
the same line.

Anything that depends on today's date - open/closed, days remaining, is-the-event-over - must
be derived at read time, never stored. Contract 2.2.

## 6. Verify the whole answer, not the convenient part

When a model returns several fields, the check usually covers one of them. The citation quote
was substring-checked from day one; the CALL label beside it was not, and a wrong label looks
like precision. Anything returned that the check does not cover needs its own check, or should
not be asked for.

## 7. "Not disproven" is not "confirmed"

A 403, a timeout or an exception means blocked or unreachable. Only 404/410 disprove. But the
inverse is equally true and easier to forget: a page that loads is not a page that supports
your claim. Two upstream rows asserted a page was "now accessible" that returns a 200 while
saying "Page not found".

## 8. Check the cheapest disqualifier first

Ordered by cost, before spending a request or a fetch:

1. Has the event already happened? (rule 1)
2. Has the deadline already passed?
3. Is the URL a proxy, a social post, or a homepage?
4. Does the target date even parse?
5. Only then: fetch, read, extract.

We ran this pipeline in roughly the reverse order for a week.

## 9. Read the diff, and know which guard fired

Never bless a golden-master or a merge diff unread - a tidy-up once rewrote 26 cities with
every test passing. And when a test you wrote to fail does fail, confirm it failed for your
reason: a probe sentence containing "Registration" was rejected by the wrong-purpose regex,
not by the check under test, and looked like a pass.

## 10. When a number looks like a finding, check who produced it

Before reporting anything outward:

- Did we compute it from data, or infer it?
- Would it change if an input were missing? (rule 4)
- Is the sample the hard subset or a fair one?

**2026-08-11:** a pilot returned "1 candidate URL in 5 rows" and read as a failed fix. Four of
the five rows were closed calls - we had chosen them - so "nothing to find" was the correct
answer. We were one step from telling upstream their work had failed.

Eighteen "contradictions" went the same way: thirteen were our own date parser not knowing
"May 8th", "9-28-2026" and "28.9.2026". Had they been sent, most would have been withdrawn.

---

## The shape all of these share

Every one is a case where the code was correct when written and the assumption quietly
stopped holding, or where something looked like a result and was actually an artefact. None
would have been caught by a passing test suite.

The habit that catches them: **before believing a number, ask what would have to be true for
it to be wrong, then check that thing specifically.**
