# Matching a customer sheet to our rows - operational steps

**What this is for.** The customer's sheets carry no key of ours, so nothing they populate -
corrected dates, confirmed deadlines, notes - can be attributed to the right conference. This
process puts our `EVENT_ID` into their sheet once, per market. After that the key is the join
and this is never run again for those rows.

The reasoning behind the method is in `MATCHING-METHODOLOGY.md`. This page is how to run it.

Measured on Utility Global, 2026-08-13: **50 of 57 rows at 100%**, 2 at 90%, 2 at 70%, 3
correctly blank.

---

## 0. Before you start

| You need | Notes |
|---|---|
| Their sheet, exported as CSV | see step 1 |
| Which of our markets those rows belong to | `Utility`, `Bioeconomy`, `Semiconductor`, ... |
| The current delivery CSV | supplies `START DATE`, and the row order used for alignment |
| The live database | supplies our canonical ids, names and cities |

**One market at a time.** The sequence-alignment signal only works when the two lists cover the
same population. Running a Utility sheet against all eight markets weakens it for no gain.

---

## 1. Export their sheet

Their sheets live in Google Sheets. The CSV export endpoint works through an authenticated
browser session:

```
https://docs.google.com/spreadsheets/d/<SHEET_ID>/export?format=csv&gid=<TAB_GID>
```

Both ids are in the URL when the tab is open: `/spreadsheets/d/<SHEET_ID>/edit?gid=<TAB_GID>`.
Navigating to the export URL downloads the CSV to `Downloads`.

**Do not use `/gviz/tq?tqx=out:csv`** - it redirects back to the editor. **Do not fetch the
export URL with JavaScript from the page** - Google's CSP blocks it. Navigation is what works.

Check what you got before using it:

```bash
python -c "import csv,sys; r=list(csv.reader(open(sys.argv[1],encoding='utf-8-sig'))); print(len(r)-1,'rows',len(r[0]),'cols'); print([repr(h) for h in r[0]])" "<downloaded>.csv"
```

**Expect trailing whitespace in their headers.** `'CONFERENCE '` is real and has bitten us: read
without stripping, every name comes back empty and the matcher reports a confident, entirely
wrong 0%. The script strips keys and refuses to run if the name column is empty across every
row, but know that this is why.

---

## 2. Run the matcher

```bash
uv run python scripts/match_customer_sheet.py \
  --sheet    "<their export>.csv" \
  --market   Utility \
  --db       "C:/Users/matts/AppData/Local/CFP-Monitor/cfp_monitor.db" \
  --delivery "C:/Users/matts/Desktop/Nicolia-PR-Prime/Markets/ALL_MARKETS_REFRESHED_<date>.csv" \
  -o         "<market> - EVENT_ID matched.csv"
```

`--name-col` defaults to `CONFERENCE`; pass it if a sheet names that column differently. The
awards sheets use `AWARD`.

It prints the calibration table and the confidence bands. Read the calibration table - a test
scoring poorly against the anchors is a signal about that market's data, not a reason to
proceed regardless.

---

## 3. Read the output

Three columns are appended. **Everything else is byte-identical to their export, in the same
row order**, so the new columns paste straight back.

| Column | Contents |
|---|---|
| `EVENT_ID` | our canonical id, or blank |
| `Index_Confidence` | `100%` down to `0%` |
| `Index_Justification` | the verdict, which tests agreed, which dissented and where they pointed, which were silent |

A justification reads:

```
CERTAIN via unique domain: the domain ceraweek.com resolves to exactly one conference in our
database, so no other row could claim it. 8 of 9 tests agree: domain+city, domain+date,
domain+name, domain+position, exact name, name+city, name+city+date, unique domain.
Silent (1): exact URL.
```

### What to do with each band

| Band | Meaning | Action |
|---|---|---|
| **100%** | A Tier-1 test proved it: exact URL, a domain unique to one conference, or name+city+date agreeing | Accept without review |
| **90-99%** | Several tests agree, none conclusive alone | Skim; accept unless something looks odd |
| **40-89%** | Thin evidence, often one test | Read the justification and decide |
| **0%, blank** | Every test abstained | **Do not invent a match.** Usually an event they track and we do not - a question for the customer |

**A dissent naming a sibling of the winner is a duplicate on our side, not a matching failure.**
`Disagreeing: exact name -> 2027-decarb-connect-europe-vienna` means we hold two rows for one
conference. Worth collecting as you go.

---

## 4. Verify before it goes anywhere

Never paste without checking the file is faithful:

```bash
python -c "
import csv,sys
a=list(csv.reader(open(sys.argv[1],encoding='utf-8-sig')))
b=list(csv.reader(open(sys.argv[2],encoding='utf-8-sig')))
n=len(a[0])-(1 if 'EVENT_ID' in [c.strip() for c in a[0]] else 0)
print('rows      ', len(a)==len(b))
print('order     ', all(a[i][0]==b[i][0] for i in range(1,len(a))))
print('cells kept', all(a[i][:n]==b[i][:n] for i in range(1,len(a))))
" "<their export>.csv" "<output>.csv"
```

All three must be `True`. Then confirm every filled id exists in the database - the script only
emits canonical ids, but a reconciliation file that quietly reorders or invents a key is worse
than none.

---

## 5. Give it back

1. Add an `EVENT_ID` column to their sheet if it has none. It is theirs to add.
2. Paste the three columns. `EVENT_ID` is permanent; the other two are working columns the
   customer can delete once satisfied.
3. **Archive the output CSV in `handoff-files`.** It is the record of how each key was assigned
   and at what confidence. If a mismatch surfaces later, you want to know whether that row was
   a certainty or a judgement call. CSVs are gitignored there, so keep it on disk deliberately.

---

## 6. After alignment

**This does not run again for those rows.** The key is the join. The recurring work becomes:

- **Their sheet gains a row we have never seen.** Run the matcher on that row alone. It decides
  whether the conference is new to us or an edition of a series we hold.
- **A new conference year comes round.** That is *not* this tool. A new edition getting a new
  key is series-successor logic - contract amendment v1.3 R14, with the 25-day floor and no
  assumed cadence.

---

## Gotchas, all of them learned the hard way

- **Their headers carry trailing whitespace.** Strip keys before anything else.
- **The delivery's `EVENT_ID` column is UPSTREAM's, not ours** (contract 5.4). The matcher maps
  through the seed map to our canonical id. Never copy that column straight across.
- **One market per run.** Alignment needs matching populations.
- **A stale sheet is normal.** Their row may track a concluded edition while we hold the next.
  The matcher collapses editions and picks by date; do not "fix" this by filtering on year.
- **`domain+position` cannot validate itself** - it defines the anchors, so its 100% precision
  is tautological. Rows resting on it alone score lower on purpose.
- **Awards sheets need both `--name-col` and `--url-col`, and are weaker.** Checked 2026-08-13:
  they carry `AWARD` and `SUBMISSION URL` and have **no `CONFERENCE URL` and no `LOCATION`**.
  So:

  ```bash
  --name-col AWARD --url-col "SUBMISSION URL"
  ```

  Tests needing a city abstain, which is correct behaviour and simply lowers coverage. But treat
  the domain tests with suspicion here: a submission URL often points at a third-party
  platform - Awardforce, Submittable - shared by dozens of unrelated awards. **"Unique domain"
  is only proof when the domain belongs to the event.** Expect lower confidence and review the
  90-99% band rather than accepting it, until we have run one and measured it.
