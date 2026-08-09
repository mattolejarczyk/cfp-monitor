# Market runbook — processing a delivery end to end

**Audience:** whoever is operating the pipeline, including a session starting cold.
**Read `pipeline-contract.md` first** — it says *why*. This says *how*.
**Last executed:** 2026-08-08 (all 8 markets, 406 rows, first full downstream verification).

> **Schema is 38 columns, not the 35 the contract still says.** `FORMAT` was added as 36 and
> `LIFECYCLE_EVIDENCE_URL` / `LIFECYCLE_QUOTE` as 37-38. `EXPECTED_COLS` in
> `accept_delivery.py` is already 38. The contract text lags because it is a JOINT document
> and amendments **v1.2 and v1.3 are still drafted-but-unsent** in `handoff-files`. Do not
> edit the contract unilaterally to close the gap - send the amendments.

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
| **CFP Weekly Verification** | Sunday 01:00 | `run_weekly.bat` -> `weekly_verify.py`: layers 0/1/2 across every market, browser recheck, invariants, digest of what CHANGED | none |
| **CFP Monthly Re-Research** | 1st, 02:00 | `run_monthly.ps1` in the upstream area: archives the previous cycle, then a fresh grounded audit of all 8 markets | ~400 grounded requests |

Weekly finds links that died and deadlines that moved. **Only the monthly run finds
conferences we do not track**, which is why the split exists - weekly re-research would be
~400 requests a week and that is what exhausted quota on 2026-08-04.

Digest lands in `runs_out\weekly_verify_<stamp>.md`. Email only happens if `CFP_SMTP_*` and
`CFP_ALERT_TO` are set; otherwise it is written to disk and nothing is lost.

Both tasks have `StartWhenAvailable` and `AllowStartIfOnBatteries` set. Without those a
01:00 job on a sleeping or unplugged machine silently never runs.

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

Tests, before any commit:

```bash
cd /c/Users/matts/cfp-monitor && uv run --with pypdf --with pytest python -m pytest tests/ -q
```

`tests/run_all.py` delegates to pytest. It used to run each file as a script, which silently
skipped the 9 files without a `__main__` block — 112 tests reported as passing without ever
executing. Do not reintroduce that pattern.
