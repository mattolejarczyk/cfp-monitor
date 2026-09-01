# Judgement rules - the conclusions we should reach without being told

The runbook says how to run things. The contract says who owns what. This file is for the
conclusions a careful person reaches in five seconds and a pipeline misses entirely, because
every one of them cost us real time or nearly reached a customer.

Each rule is here because it was learned the hard way. The date is when.

## This file is capped at 21 rules, and a new one has to be paid for

**Growth here was free, so it happened.** Two rules were added on 2026-09-01 alone, on a day
whose defining failure was that rules already written down did not fire. More prose lowers the
odds that any given line is retrieved at the moment it matters - so adding to this file is not
a neutral act, and past a point it is a harmful one.

Before adding a rule, answer two questions in order:

1. **Can this be a test instead?** A guard that fails the build fires at the moment of the
   mistake. A rule fires only if someone re-reads the right paragraph at the right minute.
   `tests/test_identity_join.py` and `tests/test_no_reimplemented_crawling.py` are what this
   looks like, and both caught real duplication the day they were written.
2. **Which existing rule does this replace or merge into?** If none, the file grows, and you
   should be able to say why this one earns that.

A rule that has become executable stays here as **a short entry and a pointer** to its test -
the history is worth keeping, the full paragraph is not. **Rule 17 is the worked example**: it
was the longest rule in the file, it is now `src/cfp_monitor/identity.py` plus a guard, and what
remains is the one part that is still judgement rather than code.

Today's two additions (20, 21) were paid for by that conversion. The file is at its cap.

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

**It happened again on 2026-08-31**, which is why this rule now has executable form. The gate
failed on two rows - SecureWorld New York City and European Biomethane Week - both reading
`STATUS=Open` with deadlines that had passed within 48 hours. Neither needed research, a fetch,
or a request. Writing the rule down had not been enough for three weeks, so it is now
`src/cfp_monitor/lifecycle.py`, specified in **`DECISION-TREE.md`**, and imported by everything
that needs it rather than reimplemented where it happens to be wanted.

The wider lesson: **a judgement rule that keeps being violated needs code, not emphasis.**

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

## 11. A host that does not resolve is a different failure from a page that will not load

Rule 7 says a 403 or a timeout is "blocked, not disproven". True - and it hid six dead domains
for weeks, because a lapsed domain also surfaces as a timeout. The request never reaches a
server, so it looks identical to a site refusing automation.

`scripts/check_dns.py` separates them, costs seconds, and needs no browser. Run it before any
send. On 2026-08-11 it found 6 of 403 hosts gone, across 15 customer-facing URL fields - links
a customer clicks and gets nothing.

**And resolving is not being correct.** `ablc.co` resolves, loads, and reads cleanly. It is
Advanced Body & Laser Center, a medspa, not the Advanced Bioeconomy Leadership Conference. It
would have passed DNS, HTTP and readability checks. The real site was found by following
Biofuels Digest's own navigation - **authority, not resemblance**. When replacing a dead link,
the question is never "does this look like the right name" but "who would know, and what do
they link to".


## 12. Length is not content, and a URL name is not a page

**2026-08-12.** Upstream returned `embedded-world.eu/en/conference/call-for-papers` as a call
page. It is 4,512 characters, which passes every length and status check we had. About 4,400 of
those characters are one base64 SVG logo. The actual copy is twenty-five words of German saying
something went wrong, and the logo belongs to a different company, so the URL redirects.

We got there in two wrong steps, both worth naming:

1. Judged it by the URL. A path called `/call-for-papers` is a claim about a page, not the page.
2. "Checked" it with a regex over the text and reported zero dates found - without noticing the
   text was a data URI. The check ran, returned a number, and the number meant nothing.

`audit_evidence.real_words()` now strips inline data URIs and bare URLs before counting words
longer than three letters, and `readable()` requires 40. Calibrated against measured pages: the
error page scores 25, the thinnest legitimate page we found scores 136.

**The general form:** when a check returns a number, ask what the number is counting. Both of
these failures produced confident output from a measurement that was not measuring the thing.


---

## 13. The code you tested is not the code that runs on Sunday - 2026-08-12

Wiring weekly discovery, everything passed: 467 tests, both refusal paths, the batch control
flow exercised with the interpreter calls stubbed. It would not have run.

The scheduled task does not point at the repo. It runs
`AppData\Local\CFP-Monitor\scripts\run_weekly.bat`, a **file copy**, and that copy had drifted
32 files behind - still on the pre-reorg layout, still running the old `extract_citations.py`
and `apply_resolutions.py`, which is to say the old merge gate. Copying the new scripts alone
would not have helped: live `verify.py` has neither `_parse_date` nor `is_homepage`, so the job
would have died at import, unattended, at 01:00, with the failure visible only in a log nobody
opens unless something else goes wrong.

Two further defects in the same wiring, both invisible to every test:

- `%ERRORLEVEL%` inside a parenthesised batch block expands when the block is **parsed**, so
  the exit code logged for discovery would have been a stale value. Moved to a subroutine.
- `sys.executable` cannot run upstream's discovery script - it needs `google-genai` and
  `pandas`, which our venv has no reason to carry. And searching PATH does not fix it: under
  `uv` the venv shadows `python`, and `python3` here is the WindowsApps stub. Candidates are
  now proved by import before use, including the `py` launcher.

**The general form:** a green test suite says the code is correct. It says nothing about
whether that code is the code being executed, by which interpreter, or in which copy of the
tree. For anything scheduled, verify the deployed artefact, not the source - and run it once
by hand, reading the log, before trusting the schedule.

---

## 14. A key is a name, not a fact - 2026-08-12

`EDITION` is downstream's field under contract section 3, but we had been importing it verbatim
from upstream and never checking it against anything. 67 of 392 rows carried an edition that
disagreed with the conference's own start date: `AWE USA 2027` at edition 2026, `analytica 2028`
at edition 2026.

Cosmetic, except `event_id()` builds the canonical key out of the edition. Two duplicate
records exist because of it - Decarb Connect North America 2027 and Carbon Capture Technology
Expo North America 2027 each appear under both a `2026-` and a `2027-` key, same name, same
city. The same event arriving twice with two different EDITION values became two rows.

**The obvious fix is the dangerous one.** Correcting the edition and re-deriving the keys would
rewrite 67 canonical keys in one pass, with every test still green. That is 2026-08-08 again.

The right move is to stop reading meaning out of the key. An identifier has to be stable and
unique; it does not have to be true. So `key_year` freezes at creation and is never recomputed,
and `EDITION` becomes a derived fact. Nothing moves, the customer sees the right year, and the
L0 edition guard starts working again.

Two things this taught beyond the fix itself:

- **Check where the truth actually lives before promising a derivation.** The first instinct was
  "derive it from the conference dates" - but *zero* of the 67 had a crawl record carrying
  dates. The delivery had been sending `START DATE` all along and we had simply never imported
  it. The recommendation was wrong for a day because nobody measured the source.
- **Right 66 times out of 67 is the worst kind of rule.** Reading the year out of the event's
  name would have worked almost always, and silently corrupted `International Wafer-Level
  Packaging Conference 2026`, which runs in February 2027 and whose edition was already right.
  A date is a fact; a name is a label.

**The general form:** when a derived value turns out to be wrong, ask whether the thing built
on top of it is a *fact* or an *identifier*. Facts should be corrected. Identifiers should be
frozen and routed around. Correcting an identifier is a rename, and a rename breaks every
reference to it at once.

---

## 15. A number computed before the thing that gives it meaning is an artefact - 2026-08-31

Rule 10 asks *who* produced a number. This asks **when**. Three times in two days a count was
arithmetically correct, clearly labelled, and meant nothing, because it was computed before the
step that would have given it meaning:

| Reported | Actually | Why |
|---|---|---|
| "111 promotion candidates" | ~27 | Computed at LOAD time, before the matcher had run. Every row had a null `event_id` because nothing had looked yet. |
| "Recovered since last week (19)" | 4 | Counted rows leaving `contradicted` before asking WHY they left. 13 were citations we had cleared the day before. |
| "35 row(s) need someone to act" | 32 | Inferred "actionable" from having an owner, above three rows whose own instruction read "nothing to do now". |

**Unexamined is not absent. Left a category is not recovered. Owned is not due.**

The test: for any count, ask *what has to have happened for this number to mean what its label
says* - and check that it has. In all three cases it had not.

## 16. Never let a report congratulate you on your own edits - 2026-08-31

The nastiest form of rule 15, and worth its own entry because it reads as good news.

On 2026-08-30 the weekly digest announced **19 recoveries**. Thirteen were rows whose citations
**we had cleared the day before** - with no citation there is nothing left to contradict, so the
row falls to `not_found` mechanically. The sweep was reporting our own cleanup back to us as the
world improving. The standing dead-link backlog told the same lie in the same run: 80 to 32, with
**nothing repaired** - 49 URLs had simply stopped being referenced.

Any report that measures change must be able to say whether the change came from **outside** or
from **us**. If it cannot, it will eventually tell you things are getting better on a week when
all you did was tidy up.

## 17. Across a boundary, join on the value, not the key - 2026-08-31

**NOW EXECUTABLE - `src/cfp_monitor/identity.py`, guarded by `tests/test_identity_join.py`.**

Keyed on `EVENT_ID`, a citation fix corrected **0 of 406** rows and reported success
(2026-08-31); the same trap then took a client-sheet join to 43 of 111 and produced a written
"finding" recommending we abandon the correct key (2026-09-01). Both were documented in advance,
in two places. The translation now lives in one function and a test fails the build without it.

The half that is still judgement: **every bulk edit must print how many rows it changed.** A
silent zero looks exactly like a clean run, and that print is the only reason the 0-of-406 was
ever noticed.

## 18. Brittle parsing fails confidently, not loudly - 2026-08-31

Checking whether 31 dead links had been handed back, a throwaway regex pulled URLs from a
markdown table without excluding backticks. Every URL came back with a trailing character, the
overlap computed as **0 of 31**, and the conclusion would have been "these were never sent."

The truth was **31 of 31**, sent four days earlier and simply unactioned. The next step would
have been telling upstream to re-do work already sitting with them.

Bad parsing does not throw. It returns a clean, plausible, wrong answer. When a number is
surprising, **suspect the parsing before believing the finding** - the implausible result is the
warning, and it is the only one you get.

## 19. A check that asks a question is not reporting a finding - 2026-08-31

We told upstream that a uniform `SOURCE_AS_OF` on 113 rows had destroyed the inspected/
uninspected signal, called it the most important of five findings, and asked them to change
their process. **They agreed and planned the work. It was wrong.**

That pass was a full re-audit - 59 of 59 Cybersecurity, 54 of 54 Utility, recorded in progress
ledgers we already had. When every row is genuinely visited, every row genuinely advances, and
one date is the CORRECT output.

The part that makes this a rule rather than an apology: **our own gate had already said so.**
`R19b` is a `note`, not a `FAIL`, and its text reads:

> "If this delivery re-researched every row, that is correct and expected. If it was a
> structural re-export, SOURCE_AS_OF should have been left as it was."

Someone wrote both branches because they knew the ambiguity existed. We read the headline, took
the branch that looked like a finding, and sent it to another party.

```
[FAIL]  a conclusion.        act on it.
[warn]  a conclusion, ranked. act on it in order.
[note]  a QUESTION.          go and answer it before repeating it.
```

A note is the check saying *"I cannot tell from here."* Passing one outward as a finding
launders our uncertainty into someone else's work queue. **Answer it first, from data we already
hold - which in this case was two files on disk.**

What survived was real and much narrower: 9 rows that failed every retry were stamped as
though established. Nine, not 113 - and the difference between those two numbers is the
difference between a process change and a bug fix.

## 20. A rule may reject on a fact; an inference may only ask someone to look - 2026-09-01

Two checks were added to the gate on the same day. Both are about bad URLs. Only one of them
is allowed to reject a delivery, and the difference is what the check KNOWS.

**R22 rejects.** `facebook.com` is not the organiser on the record. That is settled before any
page is fetched, and no fetch can change it. On the first run it found 8 rows - 7 of which were
sailing through the quote check, because the quote genuinely was on the Facebook page.

**R22b was written to reject, and that was wrong.** It matches a regex against a URL path to
guess that something is a form endpoint rather than a page. That is an inference. It was
corrected the same day to be advisory offline, and to fail only once the URL has actually been
fetched and answered 405.

The asymmetry is the whole argument, and it is worth applying beyond URLs:

    a false negative   ships something bad, which the note surfaces and a later check catches
    a false positive   REJECTS, someone "fixes" a working value, and the thing we needed is
                       gone with nothing left to show it was ever right

We had just refused to ban `hsforms.com` precisely to protect four conferences' working
submission links - and then built a mechanism that could have deleted them anyway. **Arguing a
principle and violating it one commit later is easy, because the second commit feels like
tightening.**

"Zero false positives across 1,897 URLs" was the tempting justification. It is precision
measured on the only data we have, which is not the same as being right - the same reasoning
that produced 14 wrong withdrawals out of 18 (rule 3) and a link scorer that ranked headshots
as call pages.

One more piece worth copying: when a flagged URL answers with a real page, R22b reports
`PATTERN TOO BROAD, review it` - a finding against **the rule**, not the row. A bad pattern
that quietly rejects deliveries for months is exactly how R22 sat unenforced from v1.6 until
someone tripped over it.

## 21. The gate ranks by rule; the customer ranks by what they can still act on - 2026-09-01

A full day of citation remediation ran row by row, correctly, against the wrong queue. Every
fix was sound. Almost none of it mattered.

Checked afterwards against `client_conferences`, **22 of the repaired rows had already been
verified or actioned by Nicolia's team.** World Future Energy Summit was `Submitted` - the form
already filed for the end client. it-sa: submitted. ADIPEC: `Client Declined`.

Two were not merely wasted:

- **ESF MENA was queued to be marked `Closed` as a discontinued event.** The customer holds an
  **acceptance** to it and is weighing a **$12,500 sponsorship**. Their note says so.
- **Horizons Asia was queued for a discontinuation note** with their submission already in.

Downgrading a row to `Projected` tells a customer their own verified, acted-on entry is
unevidenced. The gate cannot see any of this, and nothing was missing from the data: the client
layer has carried `status`, `speaker_abstracts_submitted`, `submission_date_verified` and
`priority` since 2026-08-30. What was missing was the habit of reading it.

The orders are close to inverted:

    gate      structure, citations, quotes, labels        - correctness of the FILE
    customer  can I still act on this, did I already      - usefulness of the ROW

**The most actionable thing found all day was not a gate failure.** H2 MEET: the customer is
`Drafting Abstract` at `High` priority against a deadline of 08/31/2026, which has passed. Our
row correctly holds 2026-09-30 - the second round, under R23. They are drafting to a dead date
and we hold the live one. No check fires on that, because the file is right.

`scripts/customer_context.py` buckets rows LIVE / TRACKED / MOOT / UNTRACKED, and the
cfp-protocol skill now requires running it before remediating a row or working a queue.

**Their fields stay theirs.** `status`, `status_details`, `NOTES`, `priority` are the customer's
under contract section 3. Read them to choose the work and to catch contradictions; never write
them.

### A footnote that is its own rule

Comparing the two sides, the first attempt joined `client_conferences.event_id` to the
delivery's `EVENT_ID` and reported **zero disagreements** - a clean, wrong answer. Those ids
belong to different systems (contract 5.4); the join matched nothing at all. That is rule 17,
repeated the same day it was written, in the very analysis meant to widen the context.

Re-joined on the conference name: 11 agree, **5 disagree**, two of them live - Troopers, `High`
priority for Arnica, where we hold a 2026 deadline that has passed and they track 2027.

**A join across a boundary that returns zero should be read as a broken join until proven
otherwise.** Zero findings and no matches look identical in the output.

## The shape all of these share

Every one is a case where the code was correct when written and the assumption quietly
stopped holding, or where something looked like a result and was actually an artefact. None
would have been caught by a passing test suite.

The habit that catches them: **before believing a number, ask what would have to be true for
it to be wrong, then check that thing specifically.**
