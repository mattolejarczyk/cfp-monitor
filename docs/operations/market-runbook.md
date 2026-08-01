# Market runbook — processing a delivery end to end

**Audience:** whoever is operating the pipeline, including a session starting cold.
**Read `pipeline-contract.md` first** — it says *why*. This says *how*.
**Last executed:** 2026-08-01 (Consumer Electronics v4.3, Bioeconomy v4.3).

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

**Read check 1 first.** If rows do not parse to 35 fields, every later check is measuring
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

**If this market was loaded before, clear the superseded grounding rows first.** Upstream
renames events between deliveries, so a re-import otherwise leaves the old rows behind as
duplicates:

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
```

Tests, before any commit:

```bash
cd /c/Users/matts/cfp-monitor && uv run --with pypdf --with pytest python -m pytest tests/ -q
```

`tests/run_all.py` delegates to pytest. It used to run each file as a script, which silently
skipped the 9 files without a `__main__` block — 112 tests reported as passing without ever
executing. Do not reintroduce that pattern.
