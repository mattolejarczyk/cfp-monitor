# Restore point - 2026-08-10

Taken before the evidence-table work, because that changes the shape of the data and the
database is the one asset that is NOT in version control.

## What "good" looks like here

| | |
|---|---|
| grounding_facts rows | 392 (391 delivered + AES Convention, held) |
| verify_state | 91 verified / 61 contradicted / 240 not_found |
| Tests | 286 passing |
| Invariants | all six hold |
| Golden master | blessed on 406 rows |

## Restoring

**Code** - tagged `known-good-20260810` in both repos, pushed to their remotes.

```bash
cd /c/Users/matts/cfp-monitor && git checkout known-good-20260810
cd "/c/Users/matts/Desktop/Nicolia-PR-Prime/Markets" && git checkout known-good-20260810
```

A tag is used rather than a branch name because branches move and tags do not.

**Database** - not in git (13 MB binary, and it holds customer data). Copy it back:

```bash
cd "/c/Users/matts/AppData/Local/CFP-Monitor"
cp cfp_monitor.KNOWN-GOOD-20260810.db cfp_monitor.db
```

Verified at capture time: `pragma integrity_check` = ok on both, identical sha256, same row
and verify_state counts.

**Confirm the restore worked** - do not trust the copy, check it:

```bash
./venv/Scripts/python.exe scripts/check_invariants.py --db cfp_monitor.db
cd /c/Users/matts/cfp-monitor && uv run --with pypdf --with pytest python -m pytest tests/ -q
```

Six invariants holding and 286 tests passing means you are back.

## What is NOT covered

- The **live build's** `src/` and `scripts/` are copies. Restoring the repo does not restore
  them; re-copy per the runbook.
- `runs_out/` digests accumulate and are not restored. They are history, not state.
- Scheduled tasks are registered in Windows, not in git. `schtasks /query /tn "CFP Weekly
  Verification"` to confirm they survive.

## Why a restore point at all

The database is the only place the verification work exists. On 2026-08-08 an import silently
deleted four rows and a city repair corrupted 24 canonical keys; both were recoverable only
because a backup had been taken first. The next change alters the data model, which is a
larger blast radius than either.
