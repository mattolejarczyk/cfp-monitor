# Market runbook — processing a delivery end to end

**Audience:** whoever is operating the pipeline, including a session starting cold.
**Read `pipeline-contract.md` first** — it says *why*. This says *how*.
**Last executed:** 2026-08-11 (all 8 markets; 4,021 claims audited against their own cited pages).

> **Schema is 38 columns, not the 35 the contract still says.** `FORMAT` was added as 36 and
> `LIFECYCLE_EVIDENCE_URL` / `LIFECYCLE_QUOTE` as 37-38. `EXPECTED_COLS` in
> `accept_delivery.py` is already 38. The contract text lags because it is a JOINT document
> and amendments **v1.2 and v1.3 are still drafted-but-unsent** in `handoff-files`. Do not
> edit the contract unilaterally to close the gap - send the amendments.

---

## The map, before the commands

Two principles govern every method choice below. **Cheapest first, escalate only on failure.**
And **only positive evidence disproves** - silence, a timeout or a block is never a "no".

| # | Step | What it answers | Method |
|---|---|---|---|
| 1 | **Preflight** | Worth spending requests on? | local analysis + cheap HTTP |
| 2 | **Research** | What conferences and calls exist? | grounding: LLM + Google Search |
| 3 | **Validate** | Did the run lose anything? | output vs input, by name |
| 4 | **Gate** | Does the file meet the contract? | structure + citation fetches |
| 5 | **Import** | Load as unverified discovery | normalise, derive the key |
| 6 | **Verify** | Do the claims survive live pages? | L0 own crawl, L1 link, L2 cited page |
| 7 | **Second opinion** | Is an unreachable link really gone? | real browser, then CDP |
| 8 | **Reconcile** | Does the DB still match the delivery? | six invariants |
| 9 | **Remediate** | Where did the page move to? | full pipeline: crawl + extract |
| 10 | **Classify** | Is this candidate offerable? | contract rules |
| 11 | **Audit** | **Can we prove it to someone who disagrees?** | re-read every cited page |
| 12 | **Hand back** | What must upstream fix? | defend-or-correct |
| 13 | **Publish** | What the customer sees | derived at display time |
| 14 | **Watch / Rediscover** | What changed? What is new? | weekly / monthly, scheduled |

**Step 11 is new (2026-08-10) and it exists because every other step validates INPUTS.**
Nothing asked whether what we were about to SAY was true. A hand-back went out for review
carrying 24 deadline disputes; a customer spot-checked two by hand and both were wrong. A full
re-audit put 22 of the 24 in the same bucket. See "The outbound standard" below.

The method escalation, which recurs at steps 6, 7, 9 and 11:

```
grounding -> crawl4ai (headless) -> Playwright (headed) -> real Chrome via CDP -> manual -> unresolved
```

Each rung is slower and more capable. `unresolved` is a recorded outcome, never a disproof.

---

## The outbound standard - what may leave the building

We require upstream to cite the exact page carrying a sentence and to quote it. **Until
2026-08-10 we did not hold ourselves to the same rule**, and disputed their claims using our
own cached crawls - 15 of 24 disputes were decided by L0/L0s, which fetch nothing at all. One
rested on a record that said "closed" while holding a close date six months in the future.
Another named a page we had never opened; it is a soft 404.

A finding may be sent to another party only when **all five** hold:

1. **We fetched the CITED page** - not a fallback, not our cache
2. **Through the ladder, until it loaded** - escalate rather than substitute a different page
3. **The page is real content** - soft-404 detection; "page not found" is not a source
4. **We can quote the sentence and name the URL** - no quote, no dispute
5. **The finding is internally consistent** - a closed call cannot have a future deadline

Two further rules, both earned the same day:

- **The quote must say WHICH call it refers to** (R10). One event runs abstracts, full papers,
  case studies, posters and workshops with different deadlines. `"July 6, 2026"` settles
  nothing; `"Case study deadline: July 6, 2026"` settles it and names the call.
- **A shared submission platform cannot source an event-specific claim** unless the quote
  names the event. `ras.papercept.net` hosts many IEEE conferences on one page - we read
  TMECH/AIM's deadline and attributed it to IROS.

Anything failing the standard is not discarded; it becomes **unverified**, which is honest and
costs upstream nothing. A verdict says what the page said; **exportable** says whether we may
put it in front of someone. Conflating those two is how 24 disputes were assembled from what
were, mostly, regex hits.

```bash
# step 11, before generating anything that leaves
./venv/Scripts/python.exe scripts/build_evidence.py --db cfp_monitor.db --delivery <markets dir>
./venv/Scripts/python.exe scripts/audit_evidence.py --db cfp_monitor.db
./venv/Scripts/python.exe scripts/make_handback.py --db cfp_monitor.db --replacements <csv> --out <md>
```

`make_handback.py` reads the gate. If no audited evidence exists it says so loudly and falls
back to `verify_state` - which is the unsafe path, and the warning is the point.

---

## 0. Where things live

| | |
|---|---|
| **Dev repo** | `C:\Users\matts\cfp-monitor` — source of truth, git, tests |
| **Live build** | `C:\Users\matts\AppData\Local\CFP-Monitor` — what the customer runs; has its own `venv\` |
| Live database | `<live>\cfp_monitor.db` |
| Seed CSVs | `<live>\market_sheets\<market>_seed.csv` |
| Deliveries | `C:\Users\matts\Downloads\` |

**Two Pythons, and it matters.** The dev repo uses `uv` (`uv run --with pypdf --with pytest …`);
the live build uses its own interpreter (`./venv/Scripts/python.exe`). Never run `uv` from
inside the live build — it creates a stray `.venv\` there that shadows nothing but wastes a
gigabyte and has to be deleted. **Always `cd` explicitly before running anything**; the shell's
working directory persists between commands and this has bitten twice.

Code changes go in the dev repo, get tested, get committed, and are then copied across:

```bash
cp src/cfp_monitor/<file>.py "/c/Users/matts/AppData/Local/CFP-Monitor/src/cfp_monitor/"
```

---

## 1. Gate the delivery *before* loading it

```bash
cd /c/Users/matts/cfp-monitor
uv run --with pypdf python scripts/accept_delivery.py "/c/Users/matts/Downloads/<market>.csv"
```

Exits non-zero on failure, so it can gate an automated step. Add `--no-network` for a fast
structural pass (skips the citation fetches, which take a few minutes).

**Read check 1 first.** If rows do not parse to 38 fields, every later check is measuring
shifted columns and its output is meaningless.

**Check 3 distinguishes two very different faults:**

- `paraphrase, date IS on page` — the deadline really is there, only the wording was rewritten. Minor.
- `quote and date both absent` — the citation supports nothing. Send back.

Do not report these as one number. That distinction cost us a wrong accusation once.

### If check 1 fails

The delivery is malformed, not wrong. Repair locally so it does not block you, and send it back
anyway:

```bash
uv run python scripts/repair_delivery.py "/c/Users/matts/Downloads/<market>.csv" \
    --out "/c/Users/matts/Downloads/<market>_REPAIRED.csv"
```

It refuses to write unless every rebuilt row validates on six independently-shaped fields, so a
successful repair is trustworthy. **A repaired file still fails the gate.** Upstream must fix
its writer, or we absorb the defect forever.

---

## 2. Back up, then import

```bash
cd "/c/Users/matts/AppData/Local/CFP-Monitor"
cp cfp_monitor.db "cfp_monitor.backup-pre-<market>-$(date +%Y%m%d-%H%M%S).db"
```

### Do NOT clear before importing. Import first, reconcile after.

**Superseded 2026-08-08 - the old instruction is kept below only so nobody reinvents it.**

The old step deleted rows before importing. It does not do what it claims: it deletes rows
whose `event_id` is in the NEW seed, but a renamed or re-keyed event has a DIFFERENT id, so
the stale row survives anyway. Import is an upsert, so the deletion buys nothing.

Worse, the obvious "improvement" - scoping the delete by market membership - actively
destroys data. `conference_markets` holds the PREVIOUS cycle's memberships, so processing
market 5 deletes rows that markets 1-4 just imported, and market 5's CSV has nothing to put
back. That silently lost 4 rows on 2026-08-08 and nothing complained.

**Do this instead:**

1. Import every market (below). It upserts; nothing needs clearing.
2. Reconcile: list DB rows that are not in any current seed.
3. Classify each one. Same name present under a corrected key, or a rename declared in the
   manifest, means superseded - delete it. **No counterpart and no declared reason means
   KEEP it** (contract 2.1) and add it to `market_sheets/held_rows.txt` with the reason.
4. Run `scripts/check_invariants.py`. It fails if a delivered row is missing or an extra row
   is undeclared, which is the check that would have caught the 4 lost rows immediately.

<details>
<summary>The superseded pre-import delete (do not use)</summary>

```bash
./venv/Scripts/python.exe -c "
import csv
from src.cfp_monitor.storage import Store
s = Store('cfp_monitor.db')
old = {(r['EVENT_ID_CANON'] or '').strip()
       for r in csv.DictReader(open('market_sheets/<market>_seed.csv', encoding='utf-8'))}
cur = s.db.execute('delete from grounding_facts where event_id in (%s)' % ','.join('?'*len(old)),
                   tuple(old))
s.db.commit(); print('removed', cur.rowcount)"
```

</details>

Then import:

```bash
./venv/Scripts/python.exe scripts/import_grounding.py \
    "/c/Users/matts/Downloads/<market>.csv" \
    --out market_sheets/<market>_seed.csv --seed cfp_monitor.db
```

**What to check in the output:**

| Line | Good | Investigate if |
|---|---|---|
| `exact duplicates` | 0 | non-zero — two rows share a key |
| `CITY repaired` | low | high — upstream regressed on R8 |
| `CFP model normalized` | 0 | non-zero — vocabulary drifting |
| `markets` | exactly one | more than one — wrong file |
| `UNMAPPED market labels` | absent | present — decide, then add to `markets.ALIASES` |

`NO_SUBMISSION_URL` in the issues block is **expected and good** — it is upstream leaving an
honest blank rather than inventing a path.

---

## 3. Verify

```bash
./venv/Scripts/python.exe scripts/verify_grounding.py --db cfp_monitor.db \
    --market <MarketLabel> --seed-csv market_sheets/<market>_seed.csv --layers 012 --apply
```

`--market` takes upstream's spelling from the file (`ConsumerElectronics`), **not** our
canonical name (`Consumer Electronics`) — it filters via the seed CSV.

Run without `--apply` first to preview. `--layers 0` alone is free and instant; `012` fetches
pages and takes several minutes for ~50 rows.

**Expect `not_found` to dominate.** That is the contract working: unverifiable claims stand and
are labelled `Unconfirmed`. A market where everything verifies would be the surprising result.

---

## 3b. Reconcile the database - do not skip this

```bash
./venv/Scripts/python.exe scripts/check_invariants.py --db cfp_monitor.db
```

Six invariants: every delivered row present, no undeclared extra rows, no venue or postcode
in a canonical key, nothing left unverified, `event_id` unique, link results populated.
Exits non-zero on any violation.

**This asks a different question from the gate.** `accept_delivery.py` judges a DELIVERY
against the contract; this judges the DATABASE against the delivery. A file can be perfectly
acceptable and still be imported into a database that quietly lost four rows.

Rows kept deliberately but absent from the delivery go in `market_sheets/held_rows.txt` with
a reason. An undeclared extra row is a violation - that is the point of the file.

---

## 4. Gate again, now including the loaded criteria

```bash
./venv/Scripts/python.exe scripts/accept_delivery.py \
    "/c/Users/matts/Downloads/<market>.csv" --no-network \
    --db cfp_monitor.db --market "<Canonical Market>"
```

Here `--market` **is** our canonical name, because it queries `conference_markets`. Adds
criteria 7 (no row wearing another event's evidence) and 8 (open rows always labelled).

---

## 5. Read the customer view

```bash
./venv/Scripts/python.exe -c "
from collections import Counter
from src.cfp_monitor.storage import Store
from src.cfp_monitor.customer_format import to_customer_row
s = Store('cfp_monitor.db')
recs = s.export_dicts()
keys = {r[0] for r in s.db.execute(
    \"select conference_key from conference_markets where market='<Canonical Market>'\")}
rows = [to_customer_row(r) for r in recs if r['key'] in keys]
print(len(rows), dict(Counter(r['CONFIDENCE'] for r in rows)))"
```

Sanity checks: no `Confirmed` row should be a projection; `Check link` means a dead submission
URL; blank `CONFIDENCE` should appear only on rows nobody can act on.

### The HTML page the customer actually reads

Built in the upstream working area, not this repo. **All three inputs are required** - the two
evidence flags were optional until 2026-08-11 and omitting them produced a page reading
"Deadline confirmed 0 / Need to Verify 0 / Submit Link Missing 0". That is not an obviously
broken page; it is a confident claim that nothing was verified and nothing is broken. The
builder now refuses rather than allowing it.

```bash
python build_review_page.py -i ALL_MARKETS_AUDITED_<date>.csv \
  --dead-links ../handoff-files/dead_submission_links_<date>.csv \
  --checks deadline_checks_<date>.csv \
  -o Conference_Review_<date>.html
```

Expected on the 2026-08-07 delivery: `406 rows; 41 dead links; 74 deadlines confirmed`. If any
of those three is zero, an input is missing - check before reading anything into the numbers.
`--no-evidence` exists for layout work only and its output must never be sent.

**The view counts do not sum to the row count, and should not.** They are overlapping lenses,
not buckets: "Closing this week" is inside "Closing this month" is inside "All open calls",
while "Deadline confirmed" and "Need to Verify" sit on a different axis entirely. On the
2026-08-07 delivery 242 of 406 rows match more than one view and one matches six. Every row
matches at least "Everything", so a row in NO view would be the real defect.

---

## 6. Send the result back

Write findings as **defend-or-correct** (contract §9) and save to the Desktop for the operator
to forward. Every finding offers three acceptable answers: defend with the exact URL, correct
with a working citation, or withdraw (blank citation and quote, keep the deadline, set
`IS_PROJECTED = true`).

**Verify their corrections as rigorously as their original claims.** Every cycle so far has
contained at least one problem introduced by a fix.

---

## Failure modes seen in the wild

| Symptom | Cause | Fix |
|---|---|---|
| Rows silently missing after a multi-market import | cleared by market membership; `conference_markets` held LAST cycle's memberships | never clear before import; `check_invariants.py` catches it |
| A canonical key contains a venue or postcode | `clean_city` overrode a correct `CITY` (fixed 2026-08-08) | re-import, remove the old-key rows, `check_invariants.py` |
| Two rows for one conference across cycles | its key changed, usually via the city | compare keys, not names; the golden master shows key churn as a diff |
| A count in a report never changes | it was hard-coded in a string (`make_handback`, fixed 2026-08-08) | derive every reported number at render time |
| Dead-link count lower than expected | reading `verify_state`, which only sees links layer 1 reached | use `link_checks`, populated by `weekly_verify.py` |
| `Market` column holds dates; `OPPORTUNITY_TYPE` holds `PASSED_DEADLINE (…)` | unquoted comma split the row | `repair_delivery.py`; upstream must fix its writer |
| `database is locked` | a verify sweep holds the DB | wait for it; do not open a second connection |
| Streamlit shows no change | it runs the **live build**, not the dev repo | copy the file across |
| A stray `.venv\` appears in the live build | `uv` was run from that directory | `rm -rf`; always `cd` first |
| Import reports unmapped market labels | upstream used a new spelling | map in `markets.ALIASES` — never auto-register |
| Everything verifies | almost certainly a bug | check the guards in `verify.py` |
| Many rows verify against a *different* edition | claim matching regressed | `tests/test_claim_match.py` |

---

## What a healthy result looks like

Measured on the two markets loaded 2026-08-01:

| | Consumer Electronics | Bioeconomy |
|---|---|---|
| Grounding claims | 50 | 58 |
| Verified | 3 | 6 |
| Contradicted | 2 | 4 |
| Not found (claims stand) | 45 | 48 |
| Customer rows | 45 | 53 |
| Confirmed / Unconfirmed | 7 / 24 | 6 / 29 |

**Verified counts are low by design and must never become a target** (contract §8, criterion 9).
Semiconductor reached 15 of 44 because semiconductor conferences publish dated calls early;
Consumer Electronics is mostly forecast-stage events with nothing yet citable. The rate is a
property of the market, not a score.

---

## Full cycle, condensed

```bash
# 1  gate
cd /c/Users/matts/cfp-monitor
uv run --with pypdf python scripts/accept_delivery.py "/c/Users/matts/Downloads/M.csv"

# 2  repair only if check 1 failed
uv run python scripts/repair_delivery.py "/c/Users/matts/Downloads/M.csv" --out ".../M_REPAIRED.csv"

# 3  back up + import + verify
cd "/c/Users/matts/AppData/Local/CFP-Monitor"
cp cfp_monitor.db "cfp_monitor.backup-pre-M-$(date +%Y%m%d-%H%M%S).db"
./venv/Scripts/python.exe scripts/import_grounding.py ".../M.csv" --out market_sheets/m_seed.csv --seed cfp_monitor.db
./venv/Scripts/python.exe scripts/verify_grounding.py --db cfp_monitor.db --market <UpstreamLabel> --seed-csv market_sheets/m_seed.csv --layers 012 --apply

# 4  gate again with the loaded criteria
./venv/Scripts/python.exe scripts/accept_delivery.py ".../M.csv" --no-network --db cfp_monitor.db --market "<Canonical>"

# 5  reconcile the DB against the delivery - catches rows lost during import
./venv/Scripts/python.exe scripts/check_invariants.py --db cfp_monitor.db
```

---

## What runs on a schedule (nobody has to remember these)

| Job | When | What it does | Cost |
|---|---|---|---|
| **CFP Weekly Verification** | Sunday 01:00 | `run_weekly.bat` -> `weekly_verify.py`: layers 0/1/2 across every market, browser recheck, invariants, digest of what CHANGED. Starts CDP Chrome first. | none |
| **CFP Monthly Re-Research** | 1st, 02:00 | `run_monthly.ps1` in the upstream area: archives the previous cycle, then a fresh grounded audit of all 8 markets | ~400 grounded requests |

Weekly finds links that died and deadlines that moved. **Only the monthly run finds
conferences we do not track**, which is why the split exists - weekly re-research would be
~400 requests a week and that is what exhausted quota on 2026-08-04.

Digest lands in `runs_out\weekly_verify_<stamp>.md`. Email only happens if `CFP_SMTP_*` and
`CFP_ALERT_TO` are set; otherwise it is written to disk and nothing is lost.

Both tasks have `StartWhenAvailable` and `AllowStartIfOnBatteries` set. Without those a
01:00 job on a sleeping or unplugged machine silently never runs.

---

## Reading a page: which rung, and why it matters

Measured across 4,021 claims on 2026-08-10/11:

| Rung | Pages read | When it earns its place |
|---|---|---|
| plain HTTP | 1,063 | the cheap default; resolves most claims in seconds |
| crawl4ai | 2,163 | JS-rendered content plain HTTP returns without |
| playwright-fallback | 742 | headless gets 403'd; a headed render gets through |
| cdp | 53 | hard anti-bot sites, via a REAL Chrome on 9222 |

**A page that LOADS is not a page that was READ.** The first escalation only retried pages
that failed outright, so 1,145 pages that returned HTTP 200 without their date were never
re-read. Escalating those recovered 2,313 claims. If a claimed value is absent, escalate
before concluding it is not there.

**Without CDP running, hard anti-bot sites are SKIPPED, not failed.** That is deliberate -
hammering them from a residential IP gets it flagged. It also means an unattended run without
Chrome silently under-reports. `run_weekly.bat` now starts one.

**Sample rates do not extrapolate.** A 6-page pilot rescued 2 (33%); across 1,145 pages the
verified yield was 11%. Use a pilot to prove a method works, never to forecast a number.

---

## Where an LLM is safe, and where it is not

This is the rule that came out of five rounds of citation pilots, and it generalises past
citations. The question is never "is the model good enough". It is **can we check the answer
without trusting the answerer.**

| | Safe | Not safe |
|---|---|---|
| What we ask for | a POINTER into text we already hold | a REPORT about something we did not read |
| Why | the answer is checkable against the source | nothing to check it against |
| Failure mode | rejected at the gate | reaches the customer looking correct |

Upstream was asked to read a page and report the sentence on it. Ten rows across two pilots
produced two usable ones - and the bad ones were not obviously bad: real URLs, fluent
sentences, right dates, on pages that never contained them. Two rounds of prompt tightening
moved nothing, because the prompt cannot reach the seam. The model knew the fact and was
guessing where it lived.

The fix was not a better prompt. It was moving the question:

- **We** fetch the page, through the full ladder. That text is real by construction.
- **The model** is given that text and asked which sentence answers the question.
- **The code** checks the answer is a literal substring of what we supplied, and re-cuts the
  quote from the page so what we store is the source's own characters, not the model's echo.

Fabrication stops being something we detect and becomes something that cannot survive.
`scripts/extract_citations.py:llm_pick_sentence` is the reference implementation;
`tests/test_llm_selector.py` proves each rejection path by triggering it.

**Three rules that travel with the pattern:**

1. **Verify the whole answer, not the convenient part.** The quote was substring-checked from
   the start; the CALL label that came back beside it was not, and a wrong label is worse than
   none because it looks like precision. Anything the model returns that the check does not
   cover needs its own check - `verify_call_label` requires the page nearby to actually use
   those words. Where no check is possible, do not ask for the field.
2. **Distinguish "answered no" from "did not answer".** A considered blank is a result and must
   stand; falling back to string matching there silently overrules the judgement you paid for.
   Fall back only on an outage.
3. **Report the rejection counts every run.** `not-on-page` is the direct measure of whether
   the guard is earning its place. A number nobody prints is a number nobody notices moving.

**Where this should go next.** These are all semantic judgements currently done with regex, and
each one has the same shape - we hold the text, so a selection can be checked:

| Now | What it actually needs to decide |
|---|---|
| `audit_evidence.call_label()` | which call a quote belongs to |
| `audit_evidence.page_status()` | whether a page says open, closed, or neither |
| `verify.other_deadline_dates()` | whether a rival date contradicts ours or is unrelated |

Do not convert these speculatively. Convert one when its error rate is measured and the check
is written first.

---

## Before you change anything that DERIVES a value

`clean_city`, `event_id`, `gated_status`, `confidence`, `normalize_cfp_model` - a change here
rewrites stored values across every row, and the suite will not necessarily notice. On
2026-08-08 a tidy-up corrupted 26 cities and 24 canonical keys with all tests passing.

```bash
# 1. before the change - confirm the baseline is clean
uv run python scripts/snapshot_delivery.py --delivery <upstream Markets dir> \
    --exclude "test_,single_,_Conf_,backup" --snapshot <private repo>/derivation_snapshot.json

# 2. make the change, then run it again. Non-zero means derivation moved.
# 3. read EVERY line of the diff. Only then:
uv run python tests/test_golden_derivation.py --bless   # synthetic fixture
#    and re-run step 1 with --bless                     # real delivery
```

**Never bless without reading the diff.** Blessing a corruption is how it becomes permanent.

### Identity is frozen. Facts are derived.

`event_id` is on that list, and there is a rule about it that is easy to get backwards.

A canonical key must be **stable and unique. It does not have to be true.** When a value baked
into a key turns out to be wrong, the fix is *not* to correct the key - that is a rename, and a
rename breaks every reference at once. The fix is to stop reading meaning out of the key.

That is why `key_year` and `EDITION` are two fields and not one:

| `key_year` | frozen when the row is minted, never recomputed | keeps every key byte-identical |
| `EDITION` | derived from the conference's `START DATE` | what the customer sees, what L0 compares |

Concretely: 67 rows carry a key year that disagrees with their own start date, and `AWE USA
2027` will keep the key `2026-awe-usa-long-beach` forever. That is correct and intended.
`check_invariants.py` check 7 asserts no key has drifted from its `key_year`; check 8 watches
(without failing) for editions that disagree with the event's name.

Before deciding to "fix" a derived value, ask whether the thing built on it is a fact or an
identifier. Correct facts. Freeze identifiers and route around them. Amendment v1.4 and
JUDGEMENT 14 have the full case.

Tests, before any commit:

```bash
cd /c/Users/matts/cfp-monitor && uv run --with pypdf --with pytest python -m pytest tests/ -q
```

`tests/run_all.py` delegates to pytest. It used to run each file as a script, which silently
skipped the 9 files without a `__main__` block — 112 tests reported as passing without ever
executing. Do not reintroduce that pattern.
