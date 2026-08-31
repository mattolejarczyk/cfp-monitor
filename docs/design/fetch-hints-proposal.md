# Proposal: per-domain fetch hints

**2026-08-31. Scope only - not built.**

## The observation

We record which rung of the fetch ladder produced every piece of evidence. Nothing reads it
back. `fetch.py` contains no reference to history: every run starts at the top and escalates
from scratch, and CDP is chosen from a **hard-coded domain list** rather than from what has
actually worked.

From the 4,039 fetches we already hold:

| | Domains | |
|---|---:|---|
| **Never** resolved cheaply - every fetch needed a browser | **23** | 219 fetches |
| Never needed a browser | 243 | |
| Genuinely varies | 79 | |

The 23 include the entire SEMI family - `semiconwest.org`, `semiconkorea.org`,
`semicontaiwan.org`, `semiconeuropa.org`, `semi.org`, `semiconsea.org`, 105 fetches between
them - and `events.reutersevents.com` at 53. Every one of those fetches tried the cheap rungs
first, failed, and escalated. **That repeats every week.**

## What this is, and what it is not

**A hint is a starting point. It is never a rule, and it never excludes a rung.**

This is the crux, and it is the whole difference between a useful optimisation and the 2026-08-08
failure - *logic whose assumption stopped being true and nothing re-checked it*. A site that
needed a browser for a year can be redesigned on a Tuesday. A cache that says "this domain is
browser-only" and stops trying anything else would be permanently wrong from that Tuesday
onward, and nothing would report it.

So:

- If the hinted rung **succeeds**, we saved two attempts.
- If the hinted rung **fails**, we fall through the **complete** ladder exactly as today. The
  hint costs one wasted attempt and then gets out of the way.
- The hint is **evidence about the past**, never a claim about the present.

## The self-healing part

A hint that only ever escalates would ratchet: once a domain is marked browser-only it would
stay browser-only forever, because we would never try the cheap way again and never learn that
it now works.

So the hint **probes downward on a schedule**: roughly one fetch in every four on a
browser-hinted domain starts from the top anyway. If the cheap rung works, the hint downgrades
immediately.

That makes the cost of a wrong hint bounded and self-correcting, with no fixed expiry to tune.
It also produces something worth reading: **a domain that gets easier is news** - it usually
means the site was redesigned or dropped a bot-check - and it belongs in the weekly digest.

## Shape

```
fetch_hints
    domain            registrable domain, via sitewalk.registrable()
    hinted_rung       http | crawl4ai | playwright | cdp
    consecutive       how many fetches in a row landed on that rung
    observations      total fetches recorded for this domain
    last_success_at   when the hinted rung last worked
    last_probe_at     when we last deliberately started from the top
    downgraded_at     when a hint last got CHEAPER - the interesting event
```

**Rules for writing it**

1. **Three consecutive** landings on the same rung before a hint exists at all. One observation
   is a coincidence; the 23 domains above all have three or more.
2. A hint only ever points at a rung we have **seen work on that domain**. Never inferred from
   a sibling domain, never from the URL's shape.
3. **Probe every fourth fetch** on any domain hinted above `crawl4ai`. Record the probe whether
   it succeeds or not.
4. A **failed hinted rung resets `consecutive` to zero** and falls through the full ladder. Two
   failures in a row drop the hint entirely.

**Rules for reading it**

5. The hint chooses a **starting rung**. It never removes a rung, never shortens the ladder, and
   never ends a fetch.
6. **A hint may never influence whether a page is dead.** Only 404/410 disprove (contract 5.2),
   and that judgement stays exactly where it is. A domain hinted as CDP-only that returns 404 to
   plain HTTP is *blocked*, not gone - which is the rule today and must not change.
7. If the hinted rung is unavailable - CDP hinted but no Chrome on 9222 - fall back to the
   normal ladder. **Never skip the fetch.**

## What it is worth

Honestly: **measure it, do not promise it.** The arithmetic suggests 219 fetches × 2 avoided
attempts, at roughly 8-30 seconds each, so of the order of an hour per full pass. That matters
against a run we measured today at 1.4 min/row.

But the dominant cost in that run was **browser dead-link confirmation**, which is a different
code path and this proposal does not touch it. The right sequence is:

1. Build the recording half first, wired into `fetch.py` where the rung is already known.
2. Let it run for two weekly cycles **without reading it**. That gives fresh data and costs
   nothing.
3. Then turn on reading, and measure the difference against those two cycles.

Turning both halves on at once would leave us unable to say whether it helped.

## Where it must not go

- Not into the customer's view. This is backend telemetry and says nothing about a conference.
- Not into `evidence`. That table records what we learned about a CLAIM; this records what we
  learned about a HOST, and mixing them makes both harder to query.
- Not into the acceptance gate. A delivery is judged on its contents, never on how we fetched
  the pages behind it.

## Open questions

1. **Registrable domain or full host?** `semiconwest.org` and `semiconkorea.org` behave
   identically but are separate registrable domains, so we would learn each one separately.
   Grouping by owner would learn faster and risks over-generalising. Start per-domain; the data
   will show whether grouping is warranted.
2. **Does the hint help `browser_confirm_dead` too?** A domain known to refuse plain HTTP but
   answer a browser could skip the plain-HTTP attempt when confirming a dead link. Possibly a
   bigger win than the ladder itself, and it is the path that dominates runtime - worth
   measuring second.
3. **Does it belong in the weekly digest?** A domain that got cheaper is a real signal. Probably
   yes, in the existing "watch items" category, once there is enough history to be worth reading.
