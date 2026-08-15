# Matching one list against a body of data

**How we match records across two systems that share no key, and how we earn a confidence
figure rather than assert one.**

Written 2026-08-13 from the Utility Global alignment, which went from a confident and entirely
wrong 0% to 50 of 57 rows at genuine certainty across six passes. It is a methodology document,
not a description of one script - the intent is that the next matching problem starts here
rather than rediscovering the same six failures.

For the operational steps of the CFP implementation, see `customer-sheet-matching.md`.

---

## 1. The shape of the problem

You hold a body of records. Someone hands you a list that describes some of the same real-world
things, with no shared identifier. You must decide, for each of their rows, which of yours it
denotes - and you must be honest about the ones you cannot decide.

Three properties make this harder than string comparison, and all three showed up here:

- **Their vocabulary is not yours.** `WFCC2026` is our `World Fuel Cell Conference 2026 (WFCC
  2026)`. Their names are abbreviations, ours are expansions.
- **One attribute can serve many records.** `reutersevents.com` hosts six of our conferences.
  A domain match is not an identity.
- **The same real thing appears more than once on each side.** We hold a 2026 and a 2027
  edition of one conference; they track whichever their client cares about.

---

## 2. The evidence ladder

Not all agreement is equal. Sort every signal into one of three tiers **before** writing any
scoring code, because the tiers behave differently and mixing them is the most common failure.

### Tier 1 - PROOF. Conclusive alone. Returns certainty.

A test is Tier 1 only if you can state the reason it cannot be wrong.

| Test | Why it is proof |
|---|---|
| **Exact identifier** | Their URL is character-for-character ours. There is nothing left to infer. |
| **Uniqueness** | This attribute value maps to exactly ONE of our records in the entire body. **The exclusion is the proof**: no other record could claim it. |
| **Independent triangulation** | Name, city and date all agree. Three facts that could each be wrong independently, agreeing at once, is not coincidence. |

Uniqueness deserves emphasis because it is the most under-used. `ceraweek.com` belongs to
exactly one conference we hold, so a domain match settles it - while `reutersevents.com` proves
nothing at all. **The same test is conclusive for one record and worthless for another**, and
whether it is conclusive is a property of the DATA, not of the test. Evaluate that per row.

### Tier 2 - CORROBORATION. Meaningful, not conclusive.

Domain plus name. Domain plus date. Name plus city. Each narrows the field; none closes it.
These vote.

### Tier 3 - WEAK. Never sufficient, in any combination.

City. Date. Country. Any attribute that thousands of records share.

**The rule that matters: weak signals do not sum to a strong one.** Two conferences in Houston
in the same week are not the same conference. We produced `Barclays CEO Energy-Power
Conference -> CAAFI Biennial General Meeting` and `Jefferies Renewables -> CrowdStrike Fal.Con`
by letting city and date agree in the absence of anything else. **Require at least one
identity-bearing signal before a match is permitted to exist.** Weak signals may only adjust
confidence in a match that some stronger signal has already proposed.

---

## 3. Negative tests: ruling out is how ties break

Positive matching alone leaves you with sets of candidates. Exclusion turns a set into an
answer, and it is the half most often skipped.

**Exclusion in isolation** - a fact that makes a candidate impossible regardless of everything
else:

- The two records name different countries.
- The attribute is unique to a different record.

**Exclusion in combination** - impossible only in the presence of another condition:

- The dates differ by more than a season **and** neither the identifier nor the name agrees.

That second form has to be built carefully, and getting it wrong cost us a correct match:

> We excluded any candidate whose start date was more than 120 days from theirs. `Industrial Net
> Zero Conference` was then unmatchable - their sheet tracks the 2025 edition, we hold 2027. A
> perfect domain-and-name match was thrown away by a date rule.

**An exclusion must never encode an assumption about the other system's freshness.** Their data
being out of date is the normal case; it is often the reason the reconciliation exists at all.
Date distance became a positive signal that can be *outvoted*, not a veto.

---

## 4. Enumerate combinations; evaluate them separately AND collectively

Do not build one scoring function with weights. Build **many small independent tests**, each of
which answers one question and returns one candidate or abstains.

Independence is the point. Each test is a witness that examined different evidence, so their
agreement means something. A single weighted formula cannot tell you that four independent
lines of reasoning converged - it collapses them into one number and loses the fact.

Nine tests served here:

```
exact URL          unique domain       name+city+date        <- Tier 1
domain+position    domain+name         domain+date
domain+city        exact name          name+city             <- Tier 2
```

**Then evaluate them both ways.** Separately, so you can see which fired and which dissented.
Collectively, so agreement can accumulate. Reporting only the aggregate throws away the
diagnostic; reporting only the individuals throws away the conclusion.

---

## 5. Structural signals: order is evidence

Where one list derives from the other - an export, a copy, a sync - **the ORDER of rows carries
information**, and it is often the only thing that resolves the ambiguous cases. Six events
share a domain, but they sit at six different positions.

Two hard-won rules:

**Align on the most STABLE attribute, not the most readable one.** Aligning on names drifted,
because their names are abbreviations of ours, and produced three confidently wrong pairs -
`Carbon Capture Technology World Expo` matched to `Reuters Events: Energy Transition Europe`
purely because they landed in the same slot. Aligning the same two lists on **domain** gave a
0.85 similarity and 47 of 57 rows agreeing on domain and position together.

**Never accept position alone.** A positional pair whose domain and name both disagree is a
coincidence of layout. Position corroborates; it does not prove.

Use a proper sequence alignment (the machinery behind `diff`), not index-by-index comparison,
so a deleted row shifts everything after it without breaking the alignment.

---

## 6. Calibration: measure your tests, do not rate them

Intuition about which signals are strong is unreliable. Ours produced 47% confidence on a
perfect domain+name+date match and 28% on a Brussels-versus-Houston mismatch.

**Establish anchors** - rows matched by two independent strong signals at once - then measure
every test against them. Precision and coverage are then observed, not assumed, and weights
follow from the measurement.

Doing this told us all nine tests ran at 97-100% precision. Nothing needed discarding, which is
worth knowing, and cost nothing to establish.

**One caution that generalises.** A test used to DEFINE the anchors cannot be validated against
them - its precision comes out 100% tautologically. Ours was `domain+position`. Treat any
self-defining test as unproven no matter what the number says, and be more cautious about rows
that rest on it alone.

---

## 7. Collapse equivalent candidates before you count disagreement

Two of our records for the same conference in different years are **one answer, not two**. If
the candidate set collapses to a single series, the entity is identified; choosing among its
editions is a second, easier question - pick by date proximity.

Failing to do this had two costs. It suppressed correct matches, and it discounted confidence
for a defect in OUR data: `Carbon Capture Technology Expo North America` scored 47% on *same
domain, name 100%, start date matches*, purely because our own near-duplicate came second.

**Ambiguity in your own records is not uncertainty about their row.** Say which it is.

A useful by-product: once collapsed, a dissenting test that points at a sibling record is
evidence of a duplicate on your side. The matcher becomes a duplicate detector for free.

---

## 8. Confidence: abstention is not disagreement

Confidence is **purity among the tests that actually fired**, scaled by how many independent
confirmations there were. It is not the fraction of all tests that agreed.

A test that cannot run - `name+city` when their location column is blank - has said nothing.
Counting silence as doubt punished rows that were perfectly well evidenced, and moved thirty
rows out of the top band for no reason.

```
purity = weight of tests agreeing with the winner / weight of all tests that fired
depth  = how many tests agreed, saturating at four
conf   = purity x (base + span x depth)
```

Report a **floor**, below which nothing is filled at all. A 5% match to an unrelated event
invites a wrong paste; a blank with a reason does not. An honest blank beats a bad guess.

---

## 9. Never let the decision truncate the record

The procedure that DECIDES and the record that EXPLAINS are different concerns.

Our certainty tests short-circuited: the first to fire wrote the justification and returned, so
a row proved by exact URL never recorded that seven other tests also agreed. Certainty should
decide the score and nothing else.

Every matched row should carry, in one place:

- the verdict, and which test proved it
- how many of N tests agreed, and which
- which tests **dissented, and the record each pointed at**
- which tests were **silent**, counted separately from dissent

That is what a reviewer acts on, and it is the only durable record of how each test performed.

---

## 10. Failures we actually hit, and the general lesson

| What happened | The general lesson |
|---|---|
| A trailing space in their header (`'CONFERENCE '`) made every name read as empty. The run reported a confident **0% match rate**. | **A clean, extreme result is more likely a broken measurement than a finding.** Assert your inputs before believing your outputs. Refuse to report if a required column reads empty across every row. |
| Matched against the delivery's `EVENT_ID`, which is the upstream party's, not our canonical one. | **Know which key you are joining on.** Two systems can have a column of the same name meaning different things. |
| City + date alone produced Barclays -> CAAFI. | **Weak signals do not sum to a strong one.** |
| A 120-day date rule excluded a correct domain+name match. | **Exclusions must not assume the other system is current.** |
| Our own duplicate as runner-up dragged a perfect match to 47%. | **Your data problems are not their row's ambiguity.** |
| Name-based sequence alignment produced three confident wrong pairs. | **Align on the most stable attribute, not the most readable.** |
| Confidence divided by all nine tests punished rows where five abstained. | **Abstention is not disagreement.** |
| Certainty short-circuited and hid the corroborating evidence. | **Deciding and recording are separate jobs.** |

Note how many are the same error in different clothes: **treating absence of evidence as
evidence of absence.** A blank column, a silent test, a stale date, a missing header - each was
read as a finding rather than as nothing-to-say.

---

## 10a. Before a hypothesis becomes a rule

Added 2026-08-14, after proposing a gate that would have broken 14 correct rows.

A keyword heuristic flagged 14 rows as "asserting a deadline from a quote with no submission
language". It looked like a defect. It was proposed as a fix. The operator asked how we knew
those rows were wrong before changing them, and the answer was that we did not - nobody had
opened the pages. Eleven were verified correct within minutes: the source is a two-column table
(Speaker Deadlines | Schedule) whose flattened text hides the heading, and the extraction had
picked the right column all along. The other three used phrasings the keyword list simply did
not contain.

**The standard:**

> Hypothesise freely. Before a hypothesis becomes a rule: validate it against the actual data,
> state the population it was derived from, present the metrics, and get sign-off. Re-measure
> before extending it to a new population.

Three things that make this more than a platitude:

**Mechanical rules generalise; content rules do not.** Stripping whitespace from headers, taking
the close rather than the open, treating a unique domain as proof - these are about structure,
and one dataset is enough to find them. Stopword lists, similarity thresholds, scoring weights
and keyword gates encode what *this particular data* looks like. The failed gate was a content
rule wearing the costume of a mechanical one, which is how it got past scepticism.

**State the population, every time.** Every threshold in the CFP matcher was calibrated on 47
anchors from a single market. Reporting "all nine tests scored 97-100% precision" without
saying "on Utility" presents a property of one dataset as a property of the method. Utility is
energy and hydrogen; the semiconductor market is IEEE ordinals and digest submissions. Those
numbers will move.

**Suppression needs a higher bar than flagging.** A rule that downgrades, hides or rejects fails
SILENTLY - the row simply becomes less useful and looks like caution. A rule that flags or adds
fails loudly and gets fixed. The proposed gate would have marked 14 correct rows as unconfirmed
and nobody would ever have noticed. Weight the evidence bar by how visible the failure would be.

---

## 11. Checklist for the next matching problem

1. List every attribute both sides carry. Sort each into proof / corroboration / weak.
2. For each proof candidate, write the sentence explaining why it cannot be wrong. If you
   cannot, it is not proof.
3. Check uniqueness **per row**, not per attribute - the same test is conclusive for some rows
   and worthless for others.
4. Write the exclusions, and for each ask: *does this assume anything about how current the
   other system is?*
5. Ask whether one list derives from the other. If so, align on the most stable attribute.
6. Build many small independent tests, not one weighted function.
7. Establish anchors and measure each test. Do not rate them by intuition.
8. Collapse equivalent candidates before counting disagreement.
9. Score purity among tests that fired. Set a floor and emit honest blanks below it.
10. Record verdict, agreement, dissent-with-target, and silence - all of it, always.
11. Verify the output preserves the input exactly: same rows, same order, original cells
    untouched. A reconciliation file that quietly reorders is worse than none.
12. **Before any heuristic becomes a rule, open the pages it flags.** State which population it
    was measured on, show the metrics, get sign-off, and re-measure on the next population
    before extending it. See section 10a.

---

# Addendum: future enhancements from the record-linkage literature

*Recorded 2026-08-13, in answer to "are there expert techniques that would make this world
class, and is there existing best-in-class work that does exactly this?"*

**Yes - and the literature caught a bug in our output.**

Two of their rows both claim `2026-reuters-events-energy-transition-europe-amsterdam`, each at
100%: *Energy Transition Europe* and *Industrial Decarbonisation Europe*. Different conferences,
same Reuters domain, same city, similar dates. Our matcher has no notion that a target can only
be claimed once.

That is a textbook **one-to-one assignment** problem, and it is the clearest evidence that the
field has thought about this harder than we have.

### What the collision turned out to be - 2026-08-13, checked the next day

It was **not** two of our records competing, and **not** a matcher error. Both of the customer's
rows carried the **same `CONFERENCE URL`**, pointing at the Energy Transition Europe page. We
hold the two events correctly and separately:

```
2026-reuters-events-energy-transition-europe-amsterdam   .../energy-transition-europe
2026-industrial-decarbonisation-europe-amsterdam         .../industry-europe/
```

Their *Industrial Decarbonisation Europe* row simply has the wrong URL pasted into it. Given
identical input URLs, one answer is the only correct output - the matcher behaved properly and
the defect is upstream of it.

**This changes the recommendation below, and the change is the important part.** The instinct
was to use bipartite matching to *resolve* the collision by awarding the target to the
best-scoring claimant. That would have been wrong: it would have quietly reassigned a row and
**concealed a real data error in the source**.

> **A one-to-one violation is a FINDING, not a problem to optimise away.** Build it as a
> detector that flags both claimants and explains the conflict. Only consider automatic
> resolution once you have established that collisions in your data are genuinely competition
> between your own records, rather than corruption in theirs.

The wider lesson: **constraint violations are the cheapest data-quality detector you will ever
build.** A rule the data ought to satisfy, checked and reported rather than enforced, finds
errors that no similarity function can see. Here it found a bad cell in a customer spreadsheet
that had been invisible to everyone, including them.

## The field, and where to look

It is called **record linkage** (statistics), **entity resolution** (computer science), or
**data matching**. Two anchors:

- **Fellegi & Sunter (1969), "A Theory for Record Linkage"** - the foundational paper. Still the
  basis of most production systems.
- **Peter Christen, *Data Matching* (Springer, 2012)** - the standard textbook, and readable.

## The five techniques worth adding

**1. Fellegi-Sunter m/u weights - the biggest upgrade.** For each field compute `m` = P(agrees |
true match) and `u` = P(agrees | *not* a match, i.e. the random agreement rate), then weight
agreement as `log2(m/u)`.

**`u` is precisely what we intuited as "uniqueness is proof", but quantified.** A domain shared
by six Reuters events has high `u` - it agrees by chance often - so it earns almost no weight.
`ceraweek.com` has `u` of about 1/392, so agreement is worth an enormous amount. We hand-coded
that as a special case per row; Fellegi-Sunter derives it for every field automatically, and
gives you the two decision thresholds (auto-accept / clerical review / reject) that we picked by
eye.

**2. TF-IDF token weighting instead of a stopword list.** We hard-coded
`{conference, summit, expo, world...}` as noise. TF-IDF is the principled version: "Hydrogen"
appears across dozens of our rows so it should count for little; "CERAWeek" appears once so it
should count for a lot. This would very likely have prevented *European Hydrogen Week ->
Houston* without any hand-tuning. Combined with Jaro-Winkler (which favours matching prefixes,
good for conference names), this is "soft TF-IDF", the standard for name matching.

**3. One-to-one assignment - as a DETECTOR first.** The constraint is that each of their rows
claims at most one of ours, and each of ours is claimed at most once. Check it and **report
every violation with both claimants and the reason**; do not silently award the target to the
best score. See the correction above: the first violation we found was a wrong URL in their
sheet, and automatic resolution would have hidden it.

Max-weight bipartite matching (Hungarian algorithm) is the right machinery *once* you know your
collisions are genuine competition rather than upstream corruption. Reach for it then, not
before - and even then, log what it moved.

**4. Blocking.** We compare all 57 x 392 pairs. Fine now; quadratic later. Sorted-neighbourhood,
canopy clustering, or MinHash/LSH are the standard answers when this becomes many markets x many
clients.

**5. A labelled evaluation sample.** We have *no ground truth* - our anchors are self-defined,
which is why `domain+position` scores 100% tautologically. Hand-labelling 30 random rows would
give real precision and recall instead of an internally-consistent estimate.

## Existing tools

**Splink** (UK Ministry of Justice, open source) is the one to look at first. Fellegi-Sunter with
EM parameter estimation, so it learns m/u **without labelled data**, scales to millions, and is
actively maintained with good documentation. Others: **dedupe** (Python, active-learning based),
**Zingg** (Spark/ML), **recordlinkage** (Python toolkit). Commercially: Senzing, Tamr, Quantexa.

## Recommendation

**Do not adopt Splink for this job.** At 57 x 392, our matcher is accurate, fully explainable,
and produces the per-test justification that was specifically wanted - a probabilistic score of
14.2 bits does not. Reach for Splink if this grows to many clients x many markets, or if
calibration needs to stop resting on self-defined anchors.

**Do take three things now:** the `u`-based weighting (it makes uniqueness general rather than
special-cased), the one-to-one **check as a detector** (it has already earned its place by
finding a bad cell in the customer's own sheet), and TF-IDF tokens (removes hand-tuned
stopwords).
