"""QA report for the INTAKE step: their sheet, last week vs this week, and what our database holds.

    python scripts/qa_intake.py                    # both clients, today's snapshots
    python scripts/qa_intake.py --client utility

Run by `weekly_intake.py` after loading. Writes, per run:

    runs_out/qa/<YYYY-MM-DD>/intake.json   machine-readable - what a dashboard drill-down reads
    runs_out/qa/<YYYY-MM-DD>/intake.md     the same tables, for a person

WHY IT EXISTS
Asked for by the operator on 2026-09-16, after the first column-by-column comparison of both
customer sheets against the database. Two questions a person reviewing the week should be able to
answer without running anything:

    did the load faithfully copy their sheet?    this week's sheet vs our DB, column by column
    what did THEY change this week?              last week's sheet vs this week's

Counts, not values. A count per column shows a dropped column, a half-loaded field or a sudden
emptying without putting the customer's text into another file.

THE SHARED SHAPE - intended for every step's QA report, not just this one:

    {"step", "week_of", "ran_at", "status": PASS | FLAG, "summary",
     "sections": [{"title", "scope", "columns": [...], "rows": [[...]], "flags": [...]}]}

A FLAG is something a person should look at, never a failure of the run: this report is read,
not enforced. It changes nothing and writes only under runs_out/qa.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import clients                                  # noqa: E402

LIVE_DB = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor\cfp_monitor.db")
SNAPSHOTS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets\customer_snapshots")
QA_OUT = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor\runs_out\qa")

# snapshot folder -> the client key the database uses (same table as weekly_intake.CLIENTS)
CLIENTS = {"utility": ("utility-global", "Utility Global"), "arnica": ("arnica", "Arnica")}


def _taken(p: Path) -> date | None:
    m = re.search(r"_(\d{8})-", p.name)
    return datetime.strptime(m.group(1), "%Y%m%d").date() if m else None


def this_and_last(folder: str, snapshots: Path, today: date) -> tuple[Path | None, Path | None]:
    """Newest snapshot on or before today, and the newest from an EARLIER DAY.

    An earlier day, not the previous file: intake can run twice in a morning, and comparing two
    copies taken an hour apart would report a week with no changes.
    """
    files = sorted((p for p in (snapshots / folder).glob(f"{folder}_*.csv")
                    if _taken(p) and _taken(p) <= today), key=lambda p: p.name)
    if not files:
        return None, None
    cur = files[-1]
    earlier = [p for p in files if _taken(p) < _taken(cur)]
    return cur, (earlier[-1] if earlier else None)


def _read(path: Path | None) -> tuple[list[str], list[list[str]]]:
    if path is None:
        return [], []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        raw = list(csv.reader(fh))
    return (raw[0], raw[1:]) if raw else ([], [])


def _filled(header: list[str], body: list[list[str]], norm: str) -> int | None:
    idx = next((i for i, h in enumerate(header) if clients.norm_header(h) == norm), None)
    if idx is None:
        return None
    return sum(1 for r in body if idx < len(r) and r[idx].strip())


def report_client(con: sqlite3.Connection, folder: str, snapshots: Path, today: date) -> dict:
    key, label = CLIENTS[folder]
    cur, prev = this_and_last(folder, snapshots, today)
    head, body = _read(cur)
    phead, pbody = _read(prev)
    q = "from client_conferences where client_key=? and withdrawn_by_customer=0"
    db_rows = con.execute(f"select count(*) {q}", (key,)).fetchone()[0]
    db_withdrawn = con.execute("select count(*) from client_conferences where client_key=? "
                               "and withdrawn_by_customer=1", (key,)).fetchone()[0]

    flags: list[str] = []
    rows = []
    for i, h in enumerate(head, start=1):
        n = clients.norm_header(h)
        field = clients.COLUMN_MAP.get(n)
        now = _filled(head, body, n)
        before = _filled(phead, pbody, n) if prev else None
        if field:
            db = con.execute(f"select count(*) {q} and trim(coalesce({field},''))<>''",
                             (key,)).fetchone()[0]
            check = "match" if db == now else "MISMATCH"
            if db != now:
                flags.append(f"{h}: sheet has {now} filled, database has {db}")
        else:
            db, field = None, "never stored" if n in clients.NEVER_LOAD else "NOT MAPPED"
            check = "by design" if n in clients.NEVER_LOAD else "NOT LOADED"
            if n not in clients.NEVER_LOAD:
                flags.append(f"{h}: a column we do not load")
            elif now:
                flags.append(f"{h}: {now} row(s) hold a credential in their sheet (never stored)")
        change = None if before is None or now is None else now - before
        rows.append([i, h, field, before, now, change, db, check])
    if prev and [clients.norm_header(h) for h in phead] != [clients.norm_header(h) for h in head]:
        gone = [h for h in phead if clients.norm_header(h) not in map(clients.norm_header, head)]
        new = [h for h in head if clients.norm_header(h) not in map(clients.norm_header, phead)]
        flags.append(f"columns changed since the previous copy - removed {gone}, added {new}")

    # Rows: who came and went. A rename looks like one out and one in, and it matters because our
    # link to the conference is keyed by name - so likely renames are named separately.
    names = [r[0].strip() for r in body if r and r[0].strip()]
    pnames = [r[0].strip() for r in pbody if r and r[0].strip()]
    out_ = [n for n in pnames if n not in names]
    in_ = [n for n in names if n not in pnames]
    renamed = [(o, m[0]) for o in out_ for m in [difflib.get_close_matches(o, in_, 1, 0.6)] if m]
    if db_rows != len(names):
        flags.append(f"sheet has {len(names)} rows, database holds {db_rows} current")
    if prev and renamed:
        flags.append(f"{len(renamed)} likely rename(s) - each loses its link to our conference "
                     f"until re-matched")

    row_rows = [
        ["Rows", len(pnames) if prev else None, len(names), db_rows],
        ["Added since previous", None, len(in_) - len(renamed) if prev else None, None],
        ["Removed since previous", None, len(out_) - len(renamed) if prev else None,
         f"{db_withdrawn} kept, marked withdrawn"],
        ["Likely renamed", None, len(renamed) if prev else None, None],
    ]
    was = _taken(prev).isoformat() if prev else "none"
    now_d = _taken(cur).isoformat() if cur else "none"
    return {
        "client": label, "client_key": key,
        "this_week": cur.name if cur else None, "last_week": prev.name if prev else None,
        "sections": [
            {"title": f"{label} - rows", "scope": label,
             "columns": ["", f"Previous sheet ({was})", f"This sheet ({now_d})", "Database now"],
             "rows": row_rows, "flags": []},
            {"title": f"{label} - columns", "scope": label,
             "columns": ["#", "Google Sheet column", "Database column", f"Filled {was}",
                         f"Filled {now_d}", "Change", "Filled in DB", "Check"],
             "rows": rows, "flags": flags},
        ],
        "renamed": [{"from": a, "to": b} for a, b in renamed],
        "flags": flags,
    }


def build(db: Path, snapshots: Path, folders: list[str], today: date) -> dict:
    con = sqlite3.connect(db)
    per = [report_client(con, f, snapshots, today) for f in folders]
    con.close()
    flags = [f"{p['client']}: {x}" for p in per for x in p["flags"]]
    # A credential in their own sheet is worth seeing but is not a defect in OUR step.
    ours = [x for x in flags if "credential" not in x and "likely rename" not in x]
    return {
        "step": "intake", "week_of": today.isoformat(),
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "status": "FLAG" if ours else "PASS",
        "summary": ("every column in both sheets matches the database" if not ours
                    else f"{len(ours)} thing(s) to look at"),
        "clients": per,
        "sections": [s for p in per for s in p["sections"]],
        "flags": flags,
    }


def _cell(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, int) and not isinstance(v, bool):
        return str(v)
    return str(v)


def to_markdown(r: dict) -> str:
    out = [f"# Intake QA - week of {r['week_of']}", "",
           f"**{r['status']}** - {r['summary']}  ", f"ran {r['ran_at']}", ""]
    for p in r["clients"]:
        out += [f"## {p['client']}", "",
                f"This copy: `{p['this_week']}`  ", f"Compared with: `{p['last_week'] or 'none - first copy'}`", ""]
        for s in p["sections"]:
            out += ["| " + " | ".join(s["columns"]) + " |",
                    "|" + "---|" * len(s["columns"])]
            for row in s["rows"]:
                cells = [_cell(c) for c in row]
                if s["columns"][0] == "#" and row[5] not in (None, 0):
                    cells[5] = f"{row[5]:+d}"
                out.append("| " + " | ".join(cells) + " |")
            out.append("")
        if p["renamed"]:
            out += ["Likely renamed:", ""] + [f"- {x['from']} -> {x['to']}" for x in p["renamed"]]
            out.append("")
        if p["flags"]:
            out += ["Look at:", ""] + [f"- {x}" for x in p["flags"]] + [""]
    return "\n".join(out)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--snapshots", default=str(SNAPSHOTS))
    ap.add_argument("--client", choices=[*CLIENTS, "all"], default="all")
    ap.add_argument("--out", default=str(QA_OUT))
    ap.add_argument("--today", default=date.today().isoformat())
    a = ap.parse_args()

    today = date.fromisoformat(a.today)
    folders = list(CLIENTS) if a.client == "all" else [a.client]
    r = build(Path(a.db), Path(a.snapshots), folders, today)
    md = to_markdown(r)
    print(md)
    d = Path(a.out) / today.isoformat()
    try:
        d.mkdir(parents=True, exist_ok=True)
        (d / "intake.json").write_text(json.dumps(r, indent=2), encoding="utf-8")
        (d / "intake.md").write_text(md, encoding="utf-8")
        print(f"wrote {d / 'intake.json'} and intake.md")
    except OSError as exc:
        print(f"could not write QA report: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
