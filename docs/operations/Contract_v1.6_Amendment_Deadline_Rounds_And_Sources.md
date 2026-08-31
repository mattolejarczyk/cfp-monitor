# Joint Pipeline Contract - amendment v1.6: deadline rounds, and admissible sources

**2026-08-31.** Both rules came out of the same afternoon: the first pass through the customer's
"Needs Verification" queue, which is the first time a real person's corrections reached our rules
rather than our data.

---

## R23 - `SUBMISSION DEADLINE` is the NEXT ACTIONABLE deadline

### The case that produced it

The Nineteenth International Conference on Climate Change runs three submission rounds. Read from
the conference's own *Proposal and Registration Periods* page on 2026-08-31:

| Round | Window |
|---|---|
| Early | launch to **19 June 2026** |
| Regular | 20 June to **19 October 2026** |
| Late | 20 October to **20 December 2026** |

The customer's sheet held **19 October**. We held **20 December**. **Both were correct** - they
had recorded the Regular close and we the Late one. No amount of re-verification would have
settled it, because the disagreement was never about the facts. Our schema simply could not
express a conference with three deadlines.

### The rule

**R23.1** `SUBMISSION DEADLINE` carries the **next round a person can still act on**: the
earliest round whose close is not yet past.

**R23.2** When every round has closed, it carries the **last** one, so the row states what was
missed rather than falling silent.

**R23.3** **Every round is recorded**, whichever one is displayed. A passed round explains what
was missed; a later round is the fallback if the next is missed too. Nothing is discarded because
it is not the headline date.

**R23.4** A round we cannot parse into a date is **dropped, not guessed**. A date we cannot read
is not a date (2.5).

### Why "next actionable" and not first or last

Both alternatives mislead, in opposite directions:

- **The last round** implies more runway than exists. On 2026-08-31 our row said 20 December when
  the useful answer was 19 October - seven weeks of imaginary time.
- **The first round** implies the opportunity is gone when it is not. On 2026-08-31 the Early
  round had closed ten weeks earlier and the call was still open.

Only the next open round answers the question the field exists to answer: *what do I do now.*

### Where the other rounds live

Short term, in the row's notes, in the order the conference states them, each marked passed or
next. **The durable answer is a `DEADLINE_ROUNDS` column**, and it should be added the next time
the schema is opened - a structured list belongs in a field, not in prose that a UI has to parse.
Flagged here rather than done, because a column change is a gate change and this amendment is
already carrying one.

This is the same gap as the call open/close windows with timezones the customer records by hand
in the Arnica sheet: `Call for Briefings opens: 09/04/2026 00:00 SGT, closes: 10/16/2026 23:59
SGT`. One date cannot hold it.

### Implementation

`rules.next_actionable_deadline(rounds, today)` returns `(chosen, reason, notes)`. It sorts the
rounds rather than trusting their order, drops undated ones, and returns every round in `notes`.
Eight tests, including that a **single-deadline conference behaves exactly as before** - the
2026-08-08 lesson that every test asserted a repair FIXED bad input and none that it LEFT GOOD
INPUT ALONE.

---

## R22 - some sources can never evidence a deadline

### The case that produced it

Working the same queue, two of the four rows had citations that could not support their claims:

| Row | Cited | Problem |
|---|---|---|
| InfoSec World 2026 | `facebook.com/InfoSecWorld/` | A social post is not the organiser on the record |
| DEF CON 34 | `openssf.org/event/cfp-defcon-34/` | A third party writing *about* DEF CON's call |

The crawler has known this since July - `aggregator.py` and `sitewalk.py` both refuse to treat
social hosts as an event's authoritative site. **Nothing carried that knowledge across to
citations**, so we accepted as evidence a host we would not accept as a source.

### The rule

**R22.1** A deadline citation on a **social media host or a link shortener** is inadmissible.
Not weak, not stale - inadmissible. The full list is `rules.INADMISSIBLE_HOSTS`.

**R22.2** Admissibility is judged on the **host, before the page content**. What a social post
happens to say does not make it a source.

**R22.3** An inadmissible citation **may be withdrawn under R1 even when the deadline has
passed.** The passed-deadline refusal exists because a CFP page routinely comes down after its
deadline - that excuses a missing quote. It says nothing when the objection is to the host: a
Facebook page could not evidence a deadline the day it was cited, and the deadline passing does
not improve it.

**R22.4** A legitimate third-party **submission platform is admissible** - pretalx, Oxford
Abstracts, EasyChair, cvent and their kind host the real call. R22 targets a host category, not
third parties in general.

### What it found

Applied to the 406-row delivery, R22 flagged **four rows, not the two the customer noticed**:

```
  InfoSec World 2026            facebook.com/InfoSecWorld/          fixed 2026-08-31
  All-Energy Australia 2026     facebook.com/cleanenergycouncil/    open, deadline passed
  ADIPEC 2026                   facebook.com/adipecofficialpage/    open, deadline passed
  PDA Annual Meeting 2027       hubs.ly/Q04rnYWc0                   open, DEADLINE 2026-08-31
```

That ratio is the argument for writing the rule rather than fixing the two rows by hand.

**PDA is the one to look at first.** Its deadline is today and its evidence is a shortened link,
which does not even name what it points at. Withdrawing it would flip `IS_PROJECTED` on the day
the date matters, so a replacement citation should be sought before anything is downgraded.

### Implementation

`rules.citation_source_admissible(url)` returns `(ok, reason)`. Host matching is anchored to a
host boundary: an unanchored `x.com` also matches `matrix.com`, which is the same bug already
fixed once in `sitewalk`'s `NOT_A_PAGE`. `may_withdraw_citation` consults it first, and the
passed-deadline refusal is otherwise untouched - 14 tests hold that.

---

## What this changes for upstream

**R22 is a citation-quality rule and it binds their side.** A deadline cited to a Facebook page
or a shortener will be withdrawn by us and handed back. The remedy is the same as ever: cite the
page that states the sentence, on the event's own site or its real submission platform.

**R23 asks for something new: every round, not just one.** Where a conference publishes tiered
rounds, send them all with their labels. We will decide which is displayed; we cannot decide it
from a single date.
