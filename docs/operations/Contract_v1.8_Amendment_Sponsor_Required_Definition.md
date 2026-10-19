# Contract v1.8 amendment: what SPONSOR_REQUIRED means (2026-10-19)

Status: AGREED by upstream on 2026-10-19 (relay message 20261019T201322Z-e079, journal verified). Proposed by downstream (the operator's direction). Changes R18.1 wording and R19.3 practice; R19.1, R19.2, R21 stand.

## Why
In the two customer markets 211 of 220 approved rows carried SPONSOR_REQUIRED Yes. The sponsor-only pass counted an event as Yes when it "states or implies" that supplier participation (speaking, exhibiting, or attending as a company)
requires payment. That mixed three different things: sponsorship packages exist, exhibiting costs money, and speaking requires payment. Downstream read 36 random Yes events from their own pages: 19 run a public call for speakers
(5 of them also include speaking slots in sponsor packages), 2 offer speaking slots with sponsor packages and no public call was found, 0 state that vendors must sponsor to speak, 15 were unclear. A one page sentence hunt on the
cited page proved a requirement for only 13 of 216 rows (experiments/sponsor_reader/RESULT.md).

## What changes
a) SPONSOR_REQUIRED is Yes only where a page states that speaking requires, or is reserved for, sponsors, exhibitors or other paid participation, and upstream can name the page. Otherwise Unknown (R19.2). No only where a page says
   sponsoring does not buy or guarantee a speaking slot.
b) SPONSOR_COST and SPONSOR_URL may still describe the sponsorship packages when upstream is on that page for another reason (R19.1), but they no longer imply Yes.
c) The dedicated sponsor-only pass stops. Downstream's switch: `CFP_SPONSOR_PASS` (patch ACT-71 in run_overnight.ps1; the pass runs only when it is 1). Last week's settled answers are still carried by the prefill (ACT-64).
d) The existing 211 Yes values are kept as they are and shown downstream as unconfirmed (no badge). No retroactive re-research.

## What downstream does (R21)
Downstream establishes the route to a speaking slot from the event's own pages (scripts/speaking_route.py), with word for word quotes checked by code, stores it in its own database with who and when (R21.2), shows it to the customer, never
overwrites or contradicts a value upstream set (R21.1), and reports what it filled in.

## Still for upstream (not yet done on their side)
Upstream's own research prompt (run_market_audit.py, items 12 and 16 of the main prompts and `_SPONSOR_ONLY_RULES`) still carries the old "states or implies" wording. It should say Yes only on a stated requirement. Until it does,
any new Yes from the main research should be read as "packages exist" and is not shown as a requirement.
