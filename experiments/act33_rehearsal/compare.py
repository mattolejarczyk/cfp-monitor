"""ACT-33 rehearsal, step 3: compare the full-research sandbox load with the skipped-research sandbox load (both made by weekend_import.py --sandbox; see prepare.py).

    python experiments/act33_rehearsal/compare.py > experiments/act33_rehearsal/COMPARE.txt

Prints: the import report numbers side by side, the skipped rows (carried exactly as last week's approved row?), the shipped rows that differ between the two runs (only the skipped ones may),
the database rows that differ for the skipped events, the invariants of each sandbox database and the load QA flags (post_load_qa.py) of each. Reads only files under this folder."""
import csv
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from src.cfp_monitor.identity import seed_map, to_canonical   # noqa: E402

MARKETS = ("Cybersecurity", "Utility")


def rows(p: Path) -> list[dict]:
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    rep = {k: json.loads((HERE / f"import_{k}.json").read_text(encoding="utf-8")) for k in ("full", "skip")}
    print("== weekend_import report")
    for k in ("full", "skip"):
        print(f"{k}: status {rep[k]['status']}, database {rep[k].get('database')}")
        for m in rep[k]["markets"]:
            print(f"   {m['market']}: {m['status']} shipped {m.get('shipped')}, this week {m.get('from_this_week')}, kept from last week {m.get('from_last_week')}, held back {m.get('held_back')}, "
                  f"carried-over {m.get('carried_over')}, new events {len(m.get('new_events', []))}, research rows {m.get('rows')}")
    up_to_canon, _ = seed_map(str(HERE / "live_pre" / "cfp_monitor.db"))
    for m in MARKETS:
        print(f"\n== {m}")
        inp = rows(HERE / "skip" / f"{m}_input.csv")
        skipped = {r["EVENT_ID_CANON"] for r in inp if (r.get("REFRESH_SKIP") or "").strip()}
        prior = {to_canonical(r["EVENT_ID"], up_to_canon): r for r in rows(HERE / "full" / f"{m}_audited.final.csv")}
        fin = {k: {to_canonical(r["EVENT_ID"], up_to_canon): r for r in rows(HERE / f"sbx_{k}" / f"{m}_audited.final.csv")} for k in ("full", "skip")}
        print(f"marked REFRESH_SKIP in the input: {len(skipped)}; shipped rows full {len(fin['full'])}, skip {len(fin['skip'])}; same ids: {set(fin['full']) == set(fin['skip'])}")
        carried_exact = [c for c in skipped if c in fin["skip"] and c in prior and fin["skip"][c] == prior[c]]
        print(f"skipped events shipped unchanged from last week's approved row (all columns equal): {len(carried_exact)} of {len(skipped)}")
        missing = sorted(c for c in skipped if c not in fin["skip"])
        print(f"skipped events MISSING from the skipped run's shipped file: {len(missing)} {missing[:5]}")
        no_prior = sorted(c for c in skipped if c not in prior)
        print(f"skipped events with no prior row (cannot happen: the planner never skips them): {no_prior}")
        diff_other = [c for c in fin["full"] if c not in skipped and c in fin["skip"] and fin["full"][c] != fin["skip"][c]]
        print(f"NOT-skipped events whose shipped row differs between the two runs: {len(diff_other)} {diff_other[:5]}")
        diff_skip_cols = {}
        for c in skipped:
            if c in fin["full"] and c in fin["skip"]:
                for col in fin["full"][c]:
                    if fin["full"][c][col] != fin["skip"][c].get(col):
                        diff_skip_cols[col] = diff_skip_cols.get(col, 0) + 1
        n_changed = sum(1 for c in skipped if c in fin["full"] and c in fin["skip"] and fin["full"][c] != fin["skip"][c])
        print(f"skipped events whose row differs from the FULL run (what a fresh research would have changed): {n_changed} of {len(skipped)}; by column: {dict(sorted(diff_skip_cols.items(), key=lambda x: -x[1]))}")
        # database rows of the skipped events: skip run vs the pre-load database
        con = {k: sqlite3.connect(f"file:{(HERE / ('sbx_' + k) / 'cfp_monitor.db').as_posix()}?mode=ro", uri=True) for k in ("full", "skip")}
        pre = sqlite3.connect(f"file:{(HERE / 'live_pre' / 'cfp_monitor.db').as_posix()}?mode=ro", uri=True)
        for c in (con["full"], con["skip"], pre):
            c.row_factory = sqlite3.Row
        cols = [r[1] for r in pre.execute("pragma table_info(grounding_facts)") if r[1] not in ("imported_at", "verify_state", "verify_detail", "verify_basis")]
        sel = f"select {','.join(cols)} from grounding_facts where event_id = ?"
        same_as_pre = changed_vs_pre = 0
        for e in skipped:
            a, b = pre.execute(sel, (e,)).fetchone(), con["skip"].execute(sel, (e,)).fetchone()
            if a is None or b is None:
                continue
            if tuple(a) == tuple(b):
                same_as_pre += 1
            else:
                changed_vs_pre += 1
        print(f"database rows of the skipped events (all columns but imported_at / verify_*): unchanged by the skipped load {same_as_pre}, changed {changed_vs_pre}")
    print("\n== invariants (check_invariants.py on each sandbox database)")
    for k in ("full", "skip"):
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_invariants.py"), "--db", str(HERE / f"sbx_{k}" / "cfp_monitor.db"), "--seed-dir", str(HERE / f"sbx_{k}" / "market_sheets")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        lines = (p.stdout + p.stderr).strip().splitlines()
        print(f"{k}: exit {p.returncode}; " + " | ".join(l.strip() for l in lines[-4:]))
    print("\n== load QA (post_load_qa.py) flags")
    for k in ("full", "skip"):
        out = HERE / f"qa_{k}"
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / "post_load_qa.py"), "--previous-db", str(HERE / "live_pre" / "cfp_monitor.db"), "--db", str(HERE / f"sbx_{k}" / "cfp_monitor.db"),
                            "--import-json", str(HERE / f"import_{k}.json"), "--markets-dir", str(HERE / f"sbx_{k}"), "--today", "2026-10-11", "--out", str(out)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(f"--- {k} (exit {p.returncode})")
        for l in (p.stdout + p.stderr).strip().splitlines():
            print("   " + l[:300])


if __name__ == "__main__":
    main()
