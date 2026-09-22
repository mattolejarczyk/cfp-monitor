# The weekly cycle - what runs, when, who owns it, and what each step refuses to do

**Agreed with the operator 2026-09-15.** This is the canonical description of the week. Where
this and anyone's memory disagree, this wins; where this and the contract disagree, the contract
wins.

The cycle exists to produce one thing: **two HTML files in Nicolia's hands on Monday morning**,
good enough that his team can work from them all week. Everything else is in service of that.

    SAT  intake their week, then research ours
    SUN  verify what we hold
    SUN/MON  review, resolve, promote, import
    MON  build and publish
    then repeat

## The rule that governs a bad week

**Publish what is accepted. Leave unresolved rows at last week's values. Say so on the page.**

Never silently mix a half-resolved delivery into a good one. A page that quietly blends this
week's badges with last week's rows is indistinguishable from a good page, which is the failure
this whole document is arranged against.

**The operator verifies before publish.** If the operator is not available, the default above
applies automatically and the run proceeds - a missed review must not mean Nicolia gets nothing.

---

## Step 0 - INTAKE THE CUSTOMER'S WEEK (Saturday, before research)

**Owner: operator, until the service account is finished. Then automatic.**

Snapshot both customer sheets and match them to our rows.

    scripts/snapshot_customer_sheet.py     pull the sheet as CSV
    scripts/match_customer_sheet.py        match it to our canonical rows

**Why it is FIRST and not last.** It is not courtesy, it is cost and correctness. On 2026-08-11
eleven of ninety-three grounded requests were spent hunting calls for conferences that had
already happened. On 2026-09-01 a full day of citation remediation ran without reading the
client layer once, and 22 of the repaired rows had already been verified or acted on by
Nicolia's team - one queued to be marked discontinued while they held an ACCEPTANCE to it and
were weighing a $12,500 sponsorship.

Their status tells us what NOT to research, and what must never be contradicted.

**Their fields are theirs** (contract 3): `STATUS`, `STATUS DETAILS`, `NOTES`, `PRIORITY`. Read
them to decide what is worth doing. Never write them. Never propose "correcting" them.

**Export method matters.** Use `/export?format=csv&gid=<TAB_GID>` in an authenticated browser
tab. **Never `/gviz/tq?tqx=out:csv`** - it types each column and silently drops non-conforming
text. It blanked eight sponsorship figures and five free-text dates once already, and the diff
reported them as customer edits.

**Automatic since 2026-09-16.** `scripts/weekly_intake.py` runs as the FIRST step of the
Saturday 02:00 job (settled 2026-09-15), fetching both sheets through a read-only service
account - the same `/export?format=csv` endpoint, no browser, no signed-in session. Verified
2026-09-16 with a fetch-only run: Utility Global 84 rows, Arnica 125.

    key       AppData\Local\CFP-Monitor\sheets-reader-key.json   (never in this public repo)
    account   the key's client_email - recorded on this machine, not in this public repo
    access    Viewer on both sheets; Google Drive API enabled on the account's project
    library   google-auth, declared in pyproject.toml

It never stops research: exit code is always 0, and INTAKE HEALTH says HEALTHY or DEGRADED with
the client layer's age. A failure a retry cannot fix (missing library or key, a sheet no longer
shared, a changed tab) is reported once with what a person must do, not retried. The browser
export above is the manual fallback when it reports DEGRADED.

Test without saving anything: `python scripts/fetch_customer_sheet.py --client all --no-snapshot`

**First thing after every download: the shape check** (`clients.sheet_shape`, run by intake before
loading, notes under INTAKE HEALTH). It reconciles their sheet against what we load:

    STRUCTURE (degrades the run)   a column we load is gone; a conference name appears twice
    reported, run stays HEALTHY    a new column we do not read; a blank conference name;
                                   credential columns holding data (counts only);
                                   values our logic does not understand; statuses awaiting a ruling

A column that disappears is **kept at last week's values, never blanked** - before 2026-09-16 the
loader would have erased that field on every row. Their values are never corrected: an odd value is
theirs to fix, and ours only to report.

**Then their rows are linked to ours** (since 2026-09-16, every run): `match_customer_sheet.py`
scores each row, `apply_client_match.py` writes only CERTAIN links. A link we already hold is never
rewritten - a different certain answer is reported as a CONFLICT for a person - and a website match
is certain only when their name adds no word ours lacks, because one organiser site hosts sibling
events (SANS, OWASP, Nullcon). The notes say how many links were added, how many wait for review,
and how many conferences they track that we do not research at all: those are pending candidates,
and nothing joins an industry list without a person deciding. First run: Utility 39 -> 53 linked
of 84, Arnica 39 -> 43 of 125.

**The step's QA report** (`scripts/qa_intake.py`, run by intake after loading) - per client, per
column: filled in the previous copy, filled now, the change, filled in our database, match or not.
Saved as `runs_out/qa/<date>/intake.md` for a person and `intake.json` for a dashboard. PASS means
the database holds exactly what their sheet holds. "Previous" is the newest copy from an earlier
DAY, so two runs in one morning are never compared with each other.

**Open ruling: what "Closed" and "Not Appropriate" mean.** 17 rows. Most Closed rows have a passed
deadline, but Black Hat Asia and USENIX Security are Closed with deadlines still ahead. Until ruled,
the review page counts Closed as settled and `customer_context.py` does not - their pre-existing
behaviour, now written in one place (`clients.UNDECIDED_STATES`).

**Refuses to:** write any customer-owned column; run on a `gviz` export; match on the delivery's
`EVENT_ID` directly (that is upstream's key - cross it through `identity.to_canonical`).

---

## Step 1 - RESEARCH (Saturday 02:00, automatic)

`CFP Weekly Re-Research (live markets)` - about 120 grounded requests, **Cybersecurity and
Utility only**. The other six markets are speculative coverage and run every fourth Wednesday.

Runtime is hours, not minutes. Browser dead-link confirmation dominates: a real browser opens
per suspect URL at a 25s timeout.

**Refuses to:** run two audits against one database at once - which is why research and
verification are on different days, deliberately. A quota error is terminal for the window; the
run stops itself rather than retrying or switching models, because quota is account-level.

---

## Step 2 - VERIFY (Sunday 01:00, automatic)

`CFP Weekly Verification` - no LLM calls, no cost. Re-checks what is already loaded: dead
links, moved deadlines. Writes a digest to `runs_out\weekly_verify_<stamp>.md`.

**Only research discovers events we do not already track.** Verification never adds anything.

**Refuses to:** call a model. Declare a link dead on anything but 404/410 - 403, 500, timeouts
and empty bodies mean blocked-or-broken, and need the browser second opinion.

---

## Step 3 - REVIEW AND RESOLVE (Sunday or Monday morning, operator + assistant)

The human step, and the reason the weekend has slack in it.

    scripts/accept_delivery.py        the one gate. Never build a second opinion.
    scripts/mechanical_repairs.py     v2.4 classes A-D: how a claim is WRITTEN, never what it claims
    scripts/delivery_loop.py          gate -> repairs -> gate, with run health

Read the RUN HEALTH line first. A DEGRADED run is a finding, not a formality.

**Conflicts that need upstream go to upstream** as a hand-back, and those take round trips -
sometimes days. **A conflict unresolved by Monday does not hold the delivery.** Its row keeps
last week's values and the page says so. See the governing rule at the top.

**Refuses to:** accept a delivery that fails the gate. Repair meaning rather than form. Delete a
row on suspicion - discovery is innocent until proven guilty (2.1).

---

## Step 4 - PROMOTE AND IMPORT (Monday morning, before the build)

**The step most easily forgotten, and the one that fails invisibly.**

    promote   scripts/promote_delivery.py    the accepted delivery becomes <Market>_audited.final.csv
    import    scripts/import_grounding.py
    reconcile scripts/check_invariants.py        A MUTATION NEEDS A RECONCILIATION

Monday's conference page is built from those two `.final.csv` files; the evidence badges come
from the database. Forgetting to promote used to publish last week's rows with this week's badges,
HEALTHY and entirely normal-looking. **That gap is now guarded (2026-09-22):** `promote_delivery.py`
refuses to promote a delivery the gate did not ACCEPT and leaves a signed manifest, and Monday's
build (`publish_guard.check_publish_fresh`) marks the run DEGRADED - nothing publishes - if a
`.final.csv` is unmanifested, non-ACCEPTED, changed since promotion, or older than 4 days.

Invariants earn their keep here. On 2026-09-14 a merge deleted seven canonical rows and the
seeds still named them; `check_invariants.py` failed within a minute on "no delivered row is
missing". Left alone, the next import would have re-created every duplicate, every week, for
ever.

**Refuses to:** clear rows before importing - import upserts, then reconcile, then delete only
what is positively identified as superseded, declaring anything held in `held_rows.txt`.

**The step's QA report** (`scripts/qa_import.py`) runs first thing in Monday's build, before the
build writes anything, so it records what this step left behind: each live delivery against the
database field by field (a delivered row MISSING from the database is the invisible failure
above), the database's totals against last cycle's, how many of each customer's rows link to a
conference we research, and the invariants result. The database keeps no history, so the report
saves its own numbers and next cycle reads them back. A fall in row count is checked against the
merges recorded in `merged_rows.txt`; declared holds are counted apart. Run it by hand straight
after importing, too.

---

## Step 5 - BUILD AND PUBLISH (Monday 07:00, automatic)

`CFP Weekly Customer Pages` -> `scripts/weekly_deliverable.py`, eight steps, no API cost:

    1   audit_evidence.py --recheck          re-read every cited conference page
    2   export_checks.py                     verdicts -> the CSV the page reads
    2a  check_award_deadlines.py --apply     both of the above, for awards
    2b  submission-link re-check + link_check_awards.py --apply
    3   combine the live markets
    4   build the conferences page
    5   build the awards page
    6   publish, ONLY from a healthy run

**Nothing is published from a DEGRADED run.** The pages stay in the work folder, the manifest
says why, and the exit code is 2. A page built from a failed evidence pass looks exactly like a
good one, and would tell Nicolia's team that nothing was verified.

**Refuses to:** publish while degraded. Give a row a verdict from a page it no longer cites - a
superseded verdict is set aside, and the row reads "not yet checked", which is true.

**The step's QA report** (`scripts/qa_build.py`, run after the build, published or not) reads the
built pages themselves - exactly what Nicolia's team receives - and compares them with the last
published pages: what each page shows, and every row whose deadline, status, confidence, check
verdict, opportunity label or name changed. **Read `runs_out/qa/<cycle>/build.md` before sending.**
It flags a deadline that moved EARLIER, a row that disappeared, an Open row past its deadline, a
disputed deadline, a dead link on an open call, and a retired opportunity label (v2.5).

All of a week's QA reports share one folder, named for the Monday that cycle publishes
(`src/cfp_monitor/qa_report.py`), so a drill-down can open any step of any week.

---

## Step 6 - SEND (Monday morning, operator)

Both HTML files to Nicolia and team. **The weekly HTML file is the only thing sent** - no
separate per-conference notes, no commentary unless something genuinely needs a decision.

Not yet automated: the digest waits on disk for a person. SMTP is deliberately unconfigured.

---

## What this cycle still cannot do by itself

Named so nobody rediscovers them:

- **Steps 0, 3, 4 and 6 are manual.** The automation covers research, verification and the
  build. The middle - review, promote, import - is where the operator's week actually goes.
- **Replacement links for dead pages need a person.** Neither grounded research nor crawling
  solved it: grounding composes plausible URLs that 404, and the crawler finds form plumbing
  rather than the real submission page.
- **Nothing is emailed.**
- ~~The chain does not yet refuse to build from a stale delivery.~~ **Built 2026-09-22** -
  `promote_delivery.py` + `publish_guard.check_publish_fresh`; the Monday build goes DEGRADED
  rather than publish an unmanifested, non-ACCEPTED, tampered or week-old `.final.csv` (Step 4).
