"""Apply docs/operations/pinned_rows.json to what is LIVE right now: both approved files and the database.

    python scripts/apply_pins_live.py            # report: which cells would change, nothing written
    python scripts/apply_pins_live.py --apply    # write (backups first), prove only the pinned cells changed

WHY. The Saturday load applies pins to the next research; a fact you verify TODAY must hold today too (Monday's pages are built from the approved files, the customer reads the
database). Run this after adding a pin (QA-REGISTER.md C14). It:
  1 applies every live pin to `Markets/<Market>_audited.final.csv` for both markets (rows found through the seed map), proving only the pinned cells changed;
  2 writes the same facts to the matching database columns (start date, city, state, country, deadline and its evidence, submission link, main page) and clears a pinned blank start date;
  3 prints the next step: an approved file that was edited has to be re-gated with the network and re-promoted (market-runbook 7.5) or Monday's page will refuse to publish.
Backups: `*.pre-pins-<stamp>.bak.csv` beside each file and `cfp_monitor.pre-pins-<stamp>.db`. Cells with no database column (dates text, location, opens date) are file-only."""
from __future__ import annotations

import csv
import os
import shutil
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.pinned_rows import apply_pins, clear_pinned_blank_starts, load_pins        # noqa: E402
from src.cfp_monitor.identity import seed_map, to_canonical                              # noqa: E402

LIVE = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor")
MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
DBCOL = {"SUBMISSION DEADLINE": "deadline", "DEADLINE_EVIDENCE_URL": "deadline_evidence_url", "DEADLINE_QUOTE": "deadline_quote", "IS_PROJECTED": "is_projected",
         "CFP_SUBMISSION_URL": "submission_url", "START DATE": "start_date", "CITY": "city", "STATE_PROVINCE": "state_province", "COUNTRY": "country",
         "MAIN_INFO_URL": "main_info_url"}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    apply = "--apply" in sys.argv
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    pins = load_pins()
    db_path = LIVE / "cfp_monitor.db"
    up_to_canon, _ = seed_map(str(db_path))
    edited = []
    plans = []
    for market in ("Cybersecurity", "Utility"):
        path = MARKETS / f"{market}_audited.final.csv"
        raw = path.read_bytes()
        bom, crlf = raw.startswith(b"\xef\xbb\xbf"), b"\r\n" in raw
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rd = csv.DictReader(fh)
            cols, rows = list(rd.fieldnames), list(rd)
        before = [dict(r) for r in rows]
        rows, rep = apply_pins(rows, up_to_canon, to_canonical, pins, date.today())
        changed = {(i, c) for i, (a, b) in enumerate(zip(before, rows)) for c in a if a[c] != b[c]}
        print(f"{market} approved file: {len(changed)} cell(s) change on {len({i for i, _ in changed})} row(s)")
        for i, c in sorted(changed):
            print(f"   {rows[i]['CONFERENCE'][:40]:40s} {c:20s} {before[i][c][:38]!r} -> {rows[i][c][:38]!r}")
        plans.append((path, cols, rows, before, changed, bom, crlf))
    if rep["lapsed"]:
        print("lapsed pins (not applied):", rep["lapsed"])

    con = sqlite3.connect(str(db_path))
    dbplan = []
    for p in pins:
        if p.get("until") and date.fromisoformat(p["until"]) < date.today():
            continue
        cur = con.execute("select event_id," + ",".join(DBCOL.values()) + " from grounding_facts where event_id=?", (p["canonical"],)).fetchone()
        if cur is None:
            print(f"DATABASE {p['event']}: no row with id {p['canonical']} (pin waits for the row)")
            continue
        have = dict(zip(DBCOL.values(), cur[1:]))
        diff = {DBCOL[k]: (have[DBCOL[k]], v) for k, v in p["set"].items() if k in DBCOL and k != "START DATE" or (k == "START DATE" and v)
                if k in DBCOL and (have[DBCOL[k]] or "") != v}
        dbplan.append((p["canonical"], diff))
        if diff:
            print(f"DATABASE {p['event']}: " + ", ".join(f"{k} {str(a or '-')[:24]!r}->{str(b)[:24]!r}" for k, (a, b) in diff.items()))
    blank_starts = [p["event"] for p in pins if p.get("set", {}).get("START DATE") == "" and not (p.get("until") and date.fromisoformat(p["until"]) < date.today())]
    if blank_starts:
        print("pinned blank start dates (database cleared if set):", "; ".join(blank_starts))
    if not apply:
        print("\nreport only; add --apply to write")
        return 0

    for path, cols, rows, before, changed, bom, crlf in plans:
        if not changed:
            continue
        shutil.copy(path, str(path).replace(".csv", f".pre-pins-{stamp}.bak.csv"))
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL, lineterminator="\r\n" if crlf else "\n")
            w.writeheader()
            w.writerows(rows)
        with open(tmp, encoding="utf-8-sig", newline="") as fh:
            aft = list(csv.DictReader(fh))
        d2 = {(i, c) for i, (a, b) in enumerate(zip(before, aft)) for c in a if a[c] != b.get(c)}
        assert len(aft) == len(before) and d2 == changed, f"unexpected change in {path.name}"
        os.replace(tmp, path)
        edited.append(path.name)
        print(f"{path.name} written; proved only the pinned cells changed")
    con.close()
    shutil.copy(db_path, LIVE / f"cfp_monitor.pre-pins-{stamp}.db")
    con = sqlite3.connect(str(db_path))
    n = 0
    for cid, diff in dbplan:
        if diff:
            con.execute(f"update grounding_facts set {','.join(k + '=?' for k in diff)} where event_id=?", (*[b for _, b in diff.values()], cid))
            n += 1
    con.commit()
    con.close()
    cleared = clear_pinned_blank_starts(db_path, pins)
    print(f"database written: {n} row(s) updated, blank start dates cleared: {cleared}")
    if edited:
        print("\nNEXT (required): re-gate with the network and re-promote " + ", ".join(edited) + " (market-runbook 7.5), or Monday's page will not publish.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
