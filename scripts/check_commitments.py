"""Did upstream do what it said it would? A ledger of concrete promises, checked against the data (ACT-58). READ-ONLY, always exits 0.

    python scripts/check_commitments.py                          # against the PUBLISHED files Markets/<Market>_audited.final.csv (what the customer pages are built from)
    python scripts/check_commitments.py --file delivery.csv      # against ANY delivery CSV, today (an upstream row they send now can be checked now)
    python scripts/check_commitments.py --today 2026-10-11 --out-dir <dir>

WHY. Across notes 33 to 38 (2026-10-06) upstream answered 'we will do X in Saturday's research' several times and nothing proved it was done. Each promise is one line of `docs/operations/upstream_commitments.csv`: which event
(OUR canonical id, or `*` for every row), which column, what it must be, and the date it is due. This reads the rows and says per promise: KEPT, NOT KEPT (due date reached and the value is wrong: it names what was found),
NOT YET (before the due date, or the event's row is not in the file yet), per the ops:
    equals        the cell equals the expected text (case and spacing ignored)
    blank         the cell is empty
    contains      the cell contains the text (case ignored)
    not_contains  the cell does NOT contain the text (for `*`: no row in the file may)
    absent        the event is NOT in the file (a promise to drop or keep out a row)
A row is paired to an event by its canonical id (`identity.to_canonical` on the file's EVENT_ID; never by joining on an upstream id). Output: one summary line `COMMITMENTS: <k> kept, <n> NOT kept, <y> not yet`,
a line per NOT KEPT, and a report `<out-dir>/commitments.md/.json` (default %LOCALAPPDATA%\\CFP-Monitor\\runs_out\\qa\\<date>\\). Nothing is written to the data; a bad ledger line is reported, not fatal."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.cfp_monitor.identity import seed_map, to_canonical      # noqa: E402

LEDGER = ROOT / "docs" / "operations" / "upstream_commitments.csv"
MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
LIVE_DB = Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor" / "cfp_monitor.db"
OPS = ("equals", "blank", "contains", "not_contains", "absent")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def read_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def judge(c: dict, rows_by_canon: dict[str, dict], all_rows: list[dict], today: str, have_file: bool) -> tuple[str, str]:
    """(KEPT | NOT KEPT | NOT YET | BAD LEDGER LINE, detail)."""
    op, col, exp, ev = c["op"].strip(), c["column"].strip(), c["expected"], c["event_id"].strip()
    if op not in OPS:
        return "BAD LEDGER LINE", f"unknown op {op!r}"
    due = (c.get("due") or "").strip()
    pending = bool(due) and today < due
    if not have_file:
        return "NOT YET", "no file to check"
    if ev == "*":
        if op != "not_contains":
            return "BAD LEDGER LINE", "'*' is only for not_contains"
        hits = [r.get("CONFERENCE", "")[:40] for r in all_rows if norm(exp) in norm(r.get(col, ""))]
        if not hits:
            return "KEPT", "no row contains it"
        return ("NOT YET", f"{len(hits)} row(s) still contain {exp!r} (due {due})") if pending else ("NOT KEPT", f"{len(hits)} row(s) contain {exp!r}: {', '.join(hits[:3])}")
    row = rows_by_canon.get(ev)
    if op == "absent":
        if row is None:
            return "KEPT", "not in the file"
        return ("NOT YET", f"still in the file (due {due})") if pending else ("NOT KEPT", "the row is in the file")
    if row is None:
        return "NOT YET", "the event's row is not in the file yet"
    if col not in row:
        return "BAD LEDGER LINE", f"no column {col!r}"
    val = row.get(col, "")
    ok = {"equals": norm(val) == norm(exp), "blank": not (val or "").strip(), "contains": norm(exp) in norm(val), "not_contains": norm(exp) not in norm(val)}[op]
    if ok:
        return "KEPT", f"{col} = {val!r}"
    return ("NOT YET", f"{col} is {val!r}, due {due}") if pending else ("NOT KEPT", f"{col} is {val!r}, expected {op} {exp!r}")


def run(ledger: Path, files: dict[str, Path], db: Path, today: str) -> list[dict]:
    up_to_canon, _ = seed_map(str(db)) if Path(db).exists() else ({}, [])
    loaded: dict[str, tuple[list[dict], dict[str, dict]]] = {}
    for market, p in files.items():
        if Path(p).exists():
            rows = read_rows(Path(p))
            loaded[market] = (rows, {to_canonical((r.get("EVENT_ID") or "").strip(), up_to_canon): r for r in rows})
    out = []
    for c in read_rows(ledger):
        market = c["market"].strip()
        if "*" in files:
            rows, by = loaded.get("*", ([], {}))
            have = "*" in loaded
        else:
            rows, by = loaded.get(market, ([], {}))
            have = market in loaded
        state, detail = judge(c, by, rows, today, have)
        out.append({"id": c["id"], "event_id": c["event_id"], "what": c["what"], "note": c["note"], "due": c["due"], "state": state, "detail": detail})
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger", default=str(LEDGER))
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--file", help="check a delivery CSV instead of the published files")
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--out-dir")
    a = ap.parse_args()
    try:
        files = {"*": Path(a.file)} if a.file else {m: Path(a.markets_dir) / f"{m}_audited.final.csv" for m in ("Cybersecurity", "Utility")}
        res = run(Path(a.ledger), files, Path(a.db), a.today)
    except Exception as e:                                   # a checker must never stop the job
        print(f"COMMITMENTS: UNKNOWN - {type(e).__name__}: {e}")
        return 0
    n = {s: sum(1 for r in res if r["state"] == s) for s in ("KEPT", "NOT KEPT", "NOT YET", "BAD LEDGER LINE")}
    print(f"COMMITMENTS: {n['KEPT']} kept, {n['NOT KEPT']} NOT kept, {n['NOT YET']} not yet" + (f", {n['BAD LEDGER LINE']} bad ledger line(s)" if n["BAD LEDGER LINE"] else "") + f" (of {len(res)}, as of {a.today})")
    for r in res:
        if r["state"] in ("NOT KEPT", "BAD LEDGER LINE"):
            print(f"COMMITMENT {r['state']}: {r['id']} (note {r['note']}) {r['what']} - {r['detail']}")
    out_dir = Path(a.out_dir) if a.out_dir else Path(os.environ.get("LOCALAPPDATA", ".")) / "CFP-Monitor" / "runs_out" / "qa" / a.today
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "commitments.json").write_text(json.dumps({"today": a.today, "summary": n, "results": res}, indent=1, ensure_ascii=False), encoding="utf-8")
        lines = [f"# Upstream commitments - {a.today}", "", f"{n['KEPT']} kept, {n['NOT KEPT']} NOT kept, {n['NOT YET']} not yet, of {len(res)}", "", "| id | note | state | what | detail |", "|---|---|---|---|---|"]
        lines += [f"| {r['id']} | {r['note']} | {r['state']} | {r['what']} | {r['detail']} |" for r in res]
        (out_dir / "commitments.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as e:
        print(f"COMMITMENTS: report not written ({e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
