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

    promote   the accepted delivery becomes Cybersecurity_audited.final.csv / Utility_audited.final.csv
    import    scripts/import_grounding.py
    reconcile scripts/check_invariants.py        A MUTATION NEEDS A RECONCILIATION

Monday's conference page is built from those two `.final.csv` files; the evidence badges come
from the database. **If the delivery is gated and repaired but not promoted and imported, Monday
publishes last week's rows with this week's badges, reports HEALTHY, and looks entirely normal.**

Invariants earn their keep here. On 2026-09-14 a merge deleted seven canonical rows and the
seeds still named them; `check_invariants.py` failed within a minute on "no delivered row is
missing". Left alone, the next import would have re-created every duplicate, every week, for
ever.

**Refuses to:** clear rows before importing - import upserts, then reconcile, then delete only
what is positively identified as superseded, declaring anything held in `held_rows.txt`.

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
- **The chain does not yet refuse to build from a stale delivery.** That guard is the next thing
  worth building, and step 4 is why.
