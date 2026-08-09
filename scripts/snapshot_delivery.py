"""Golden master over a REAL delivery, stored outside this public repo.

`tests/test_golden_derivation.py` runs a golden master over a synthetic fixture: one row per
documented ruling, committed here and run by the suite. It is the durable regression net, but
it only covers the cases somebody thought to write down.

This covers the other half - every row of an actual delivery, where the surprises live. The
snapshot lands wherever you point `--snapshot`, which should be the PRIVATE upstream repo:
the delivery is the customer's asset and `cfp-monitor` is public.

    # first time, or after an intended change
    python scripts/snapshot_delivery.py --delivery <dir> --snapshot <private>/derivation_snapshot.json --bless

    # any time after: prints a diff and exits non-zero if derivation moved
    python scripts/snapshot_delivery.py --delivery <dir> --snapshot <private>/derivation_snapshot.json

Run it before and after any change to grounding.py. On 2026-08-08 a change that looked like a
tidy-up rewrote 26 cities and 24 canonical keys; against a snapshot that would have been 50
lines of diff instead of a discovery three cycles later.

Exit 0 = derivation unchanged. 1 = it moved (read the diff). 2 = could not run.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cfp_monitor.grounding import load_master_csv          # noqa: E402

# Pinned. A snapshot that changes with the calendar cannot distinguish "the code changed"
# from "it is Tuesday", which is the only question this tool exists to answer.
TODAY = date(2026, 8, 8)


def derive_dir(delivery: Path, pattern: str, exclude: list[str]) -> dict:
    """Derive every row across the delivery's market files.

    `exclude` has NO default on purpose. The working area accumulates scratch files
    (test_audited.csv, single_audited.csv, an old *_Conf_Audited.csv) and a blanket glob
    swept up 3 of them for 19 extra rows on the first run. A silent default would have
    hidden that; making it explicit means the file list is a decision, and the list is
    recorded in the snapshot so a change to it shows up as a diff.
    """
    files = sorted(f for f in delivery.glob(pattern)
                   if not any(x.lower() in f.name.lower() for x in exclude))
    if not files:
        raise SystemExit(f"ERROR: no files matching {pattern!r} in {delivery}")
    out: dict[str, dict] = {}
    for f in files:
        rows, _ = load_master_csv(str(f), TODAY)
        for r in rows:
            # Keyed on the SOURCE name + market, never the derived id - a key that changes
            # is exactly what we are trying to detect, so it cannot also be the index.
            out[f"{r.name}||{r.market}"] = {
                "event_id": r.event_id,
                "city": r.city,
                "cfp_model": r.cfp_model,
                "deadline": r.deadline,
                "is_projected": r.is_projected,
                "issues": sorted(r.issues),
            }
    return {"files": [f.name for f in files], "rows": out}


def diff(expected: dict, actual: dict) -> list[str]:
    e, a = expected["rows"], actual["rows"]
    out = [f"ROW DISAPPEARED: {k}" for k in sorted(set(e) - set(a))]
    out += [f"ROW APPEARED:    {k}" for k in sorted(set(a) - set(e))]
    for k in sorted(set(e) & set(a)):
        for fld in e[k]:
            if e[k][fld] != a[k].get(fld):
                out.append(f"{k} . {fld}\n    was: {e[k][fld]!r}\n    now: {a[k].get(fld)!r}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Golden master over a real delivery.")
    ap.add_argument("--delivery", required=True, help="directory holding the market CSVs")
    ap.add_argument("--pattern", default="*_audited.csv")
    ap.add_argument("--exclude", default="", help="comma-separated substrings to skip (scratch files)")
    ap.add_argument("--snapshot", required=True, help="snapshot JSON (keep it OUT of this repo)")
    ap.add_argument("--bless", action="store_true", help="write the current state as the baseline")
    a = ap.parse_args()

    excl = [x.strip() for x in a.exclude.split(",") if x.strip()]
    actual = derive_dir(Path(a.delivery), a.pattern, excl)
    snap = Path(a.snapshot)
    print(f"{len(actual['rows'])} row(s) derived from {len(actual['files'])} file(s)")

    if not snap.exists():
        if not a.bless:
            print(f"No snapshot at {snap}. Create the baseline with --bless.")
            return 2
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(json.dumps(actual, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Blessed baseline -> {snap}")
        return 0

    d = diff(json.loads(snap.read_text(encoding="utf-8")), actual)
    if not d:
        print("Derivation unchanged.")
        return 0

    print(f"\nDERIVATION CHANGED - {len(d)} difference(s):\n")
    print("\n".join(d[:80]))
    if len(d) > 80:
        print(f"\n... and {len(d) - 80} more")
    if a.bless:
        snap.write_text(json.dumps(actual, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nBlessed -> {snap}")
        return 0
    print("\nIf every line is intended, re-run with --bless. If any line is a surprise, it is\n"
          "a regression - read it before blessing anything.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
