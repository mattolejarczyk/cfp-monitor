> **STATUS: CURRENT.** Ruled by upstream 2026-09-08. Read alongside
> `Joint_Pipeline_Contract_v2.0.1_CONSOLIDATED_20260905.md` and amendment `v2.1`, which it
> joins. Those three are the only documents in this folder that are in force. See `README.md`.

# Joint Pipeline Contract - amendment v2.2

**2026-09-08. Amends v2.0.1 section 11.** One change: acceptance criterion 2 gains the
passed-deadline exemption criterion 3 was given by v1.4, and gains it on the same reasoning
and the same evidence.

Nothing else changes. No other criterion moves. No threshold is lowered.

---

## The change

**Criterion 2 - "cited pages resolve" - evaluates rows whose deadline is ACTIVE or BLANK.**

Where a row's `SUBMISSION DEADLINE` has already passed, a `404` or `410` on its cited page
is reported as a `NOTE` and does not reject the delivery.

    deadline still ahead    404/410 FAILS      - the case the criterion exists for
    deadline blank          404/410 FAILS      - see "the narrower half" below
    deadline passed         404/410 is a NOTE  - expected decay

Everything else about criterion 2 stands:

- **403, 500, timeouts and empty bodies remain `not_found`, never a disproof** (principle
  5.2). Only 404 and 410 disprove, and after this amendment only on live or unclaimed rows.
- **A dead link never withdraws a deadline** (R1). It may withdraw a CITATION, and only
  where `rules.may_withdraw_citation` permits.
- **The customer-facing "Submit Link Missing" view is untouched.** A reader still sees that
  the link does not resolve. This amendment changes what BLOCKS a delivery, not what the
  customer is told.

---

## Why

An entry page comes down once its window closes and the site rolls to the next cycle. The
link dying afterwards says nothing about whether the citation was sound when it was made.

The measurement, from the first awards delivery on 2026-09-06: **14 cited pages returned
404. Eleven belonged to rows whose deadline had already passed** - Earthshot 2024-12-11,
Japan Prize 2025-01-31, Grist 50 2025-03-14, Carbon Capture 2026-02-25, CRN 2026-04-03,
Houston 2026-08-27, and five more. `rules.may_withdraw_citation` refused every one, and was
right to. So the criterion was rejecting a delivery for a condition **neither side had an
action for**.

Amendment v1.4 (2026-08-29) reached the same conclusion for criterion 3 on a larger sample:
of 186 failures, 108 claimed no deadline and 50 had already passed - 84% of the failure was
the criterion testing rows it should never have been applied to. Its wording applies here
unchanged:

> A criterion that fails good work for getting older is one people learn to ignore - and an
> ignored criterion is worse than no criterion, because it still looks like coverage.

---

## The narrower half, and why it is narrower

**A BLANK deadline is exempt under criterion 3 and is NOT exempt here.** The two criteria
are asymmetric on purpose:

- Criterion 3 asks whether a page **supports the claim the row makes**. A row with no
  deadline makes no claim, so there is nothing to verify and failing it teaches nobody
  anything.
- Criterion 2 asks whether the page **is there at all**. A dead link is a defect whether or
  not the row claims a date: the reader clicks through to a 404 either way.

This is not theoretical. Three of the fourteen 404s in the awards delivery are blank-deadline
rows - Tech Ascension, Goldman Environmental Prize, Innovation Zero. **Those three still fail
criterion 2 after this amendment**, and they should: each is a citation pointing at nothing,
for a claim the row never makes. See the covering note of 2026-09-08 for their disposition.

---

## What we are NOT proposing

**Automatic withdrawal of citations on passed-deadline 404s.** Tried on 2026-08-29: an
automated pass proposed 18 withdrawals, **14 were passed-deadline rows and would have been
wrong**, and one had a deadline 317 days old. The output was discarded and
`may_withdraw_citation` was written because of it. Those rows keep their citations exactly
as they are, and the NOTE exists so that nobody mistakes silence for verification.

---

## Implementation

Downstream, in force from 2026-09-08:

    scripts/accept_delivery.py        check 2 splits 404/410 into `dead` and `decayed`;
                                      `decayed` goes to self.note(), not self.add()
    tests/test_gate_c2_passed_deadline.py   seven tests, including the three that pin the
                                      limits: a live 404 still fails, a blank deadline
                                      still fails, and a 403 is still not a disproof

Gate output now carries a `[NOTE] 2` line naming every decayed link, so the count is
visible in every run rather than absent from it.
