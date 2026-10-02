"""Named-row expectations after a load, plus a deadline-movement diff against a backup.

    python scripts/watchlist_check.py [--db <live db>] [--previous-db <backup>] [--markets-dir <Markets>]
        [--watchlist docs/operations/watchlist.json] [--out report.md]

WHY (2026-10-02). After a weekend load the question is never "did something change" (qa_import.py answers that)
but "did the rows we corrected by hand still hold, did the rows we added arrive, and did anything we did NOT
touch move". Doing that by hand on a Saturday morning is how a corrected row goes unnoticed until the customer
sees it. This script holds the expectations in a data file (`docs/operations/watchlist.json`, edit it, not the code),
reads the live database and the approved CSV files, and prints one plain-English page.

WHAT IT DOES NOT DO. It never writes to the database or to a delivery. It does not decide whether a change is
right: a Saturday re-research can legitimately move a date. A CHANGED row is "look at this", not "this is wrong".

RESULT WORDS
  OK       the row exists and every expected field holds
  CHANGED  the row exists but a field differs from the expectation (shown, expected vs actual)
  MISSING  the row is not there at all
  INFO     an informational item (a known duplicate, say): shown, never counted against the run

EXPECTATION VALUES   an exact string | "NONBLANK" | "BLANK" | "NOT_PASSED" (a deadline on or after --today)
EXIT CODE  0 when every non-INFO item is OK, 1 otherwise (so it can gate a step), 2 on a usage error.

The movement diff compares the two databases by event_id (our canonical id; contract 5.4 - no upstream-id joins)
and lists new rows, removed rows and rows whose deadline, is_projected or evidence URL changed.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE_DB = Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor" / "cfp_monitor.db"
MARKETS_DIR = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
TABLES = ("grounding_facts", "award_grounding_facts")
MOVE_FIELDS = ("deadline", "is_projected", "deadline_evidence_url")


def _rows(db: str, table: str) -> dict[str, dict]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        return {r["event_id"]: dict(r) for r in con.execute(f"select * from {table}")}
    except sqlite3.OperationalError:
        return {}
    finally:
        con.close()


def _norm(v) -> str:
    return ("" if v is None else str(v)).strip()


def judge(actual: str, expected: str, today: str) -> bool:
    """Does one actual value meet one expectation?"""
    a = _norm(actual)
    if expected == "NONBLANK":
        return a != ""
    if expected == "BLANK":
        return a == ""
    if expected == "NOT_PASSED":
        return len(a) == 10 and a >= today
    return a.lower() == _norm(expected).lower()


def check_item(item: dict, tables: dict[str, dict[str, dict]], csvs: dict[str, dict[str, dict]], today: str) -> dict:
    """One watch-list item -> {label, result, problems[]}."""
    label = item["label"]
    kind = item.get("kind", "expect")
    if "file" in item:
        source = csvs.get(item["file"])
        if source is None:
            return {"label": label, "result": "MISSING", "problems": [f"file {item['file']} not readable"]}
        row = source.get(item["event_id"])
    else:
        row = tables.get(item.get("table", "grounding_facts"), {}).get(item["event_id"])
    if item.get("expect_absent"):
        ok = row is None
        return {"label": label, "result": "OK" if ok else ("INFO" if kind == "info" else "CHANGED"),
                "problems": [] if ok else ["expected to be gone but is still present"]}
    if row is None:
        return {"label": label, "result": "INFO" if kind == "info" else "MISSING", "problems": ["row not found"]}
    problems = []
    for field, expected in item.get("expect", {}).items():
        actual = row.get(field, "")
        if not judge(actual, expected, today):
            shown = _norm(actual) if len(_norm(actual)) < 70 else _norm(actual)[:67] + "..."
            problems.append(f"{field}: expected {expected!r}, found {shown!r}")
    if kind == "info":
        return {"label": label, "result": "INFO", "problems": problems}
    return {"label": label, "result": "OK" if not problems else "CHANGED", "problems": problems}


def movement(prev_db: str, cur_db: str) -> dict:
    """Deadline-level movement between two databases, per table, joined on canonical event_id."""
    out = {}
    for t in TABLES:
        a, b = _rows(prev_db, t), _rows(cur_db, t)
        moved = []
        for eid in sorted(set(a) & set(b)):
            diffs = [(f, _norm(a[eid].get(f)), _norm(b[eid].get(f))) for f in MOVE_FIELDS
                     if _norm(a[eid].get(f)) != _norm(b[eid].get(f))]
            if diffs:
                moved.append((eid, b[eid].get("name", ""), diffs))
        out[t] = {"new": sorted(set(b) - set(a)), "removed": sorted(set(a) - set(b)), "moved": moved,
                  "before": len(a), "after": len(b)}
    return out


def read_csv_by_id(path: Path) -> dict[str, dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return {r["EVENT_ID"]: r for r in csv.DictReader(fh)}


def render(results: list[dict], mv: dict | None, today: str, db: str, prev: str | None) -> str:
    counted = [r for r in results if r["result"] != "INFO"]
    bad = [r for r in counted if r["result"] != "OK"]
    lines = [f"# Watch-list check - {today}", "",
             f"Database: `{db}`" + (f"  |  compared with: `{prev}`" if prev else ""), "",
             f"**{'ALL OK' if not bad else str(len(bad)) + ' of ' + str(len(counted)) + ' need a look'}** "
             f"({len(counted) - len(bad)} of {len(counted)} expectations hold)", ""]
    for word in ("MISSING", "CHANGED", "OK", "INFO"):
        group = [r for r in results if r["result"] == word]
        if not group:
            continue
        lines.append(f"## {word} ({len(group)})")
        for r in group:
            lines.append(f"- **{r['label']}**" + ("" if not r["problems"] else ": " + "; ".join(r["problems"])))
        lines.append("")
    if mv:
        lines.append("## Movement since the backup")
        for t, m in mv.items():
            lines.append(f"- `{t}`: {m['before']} -> {m['after']} rows; {len(m['new'])} new, "
                         f"{len(m['removed'])} removed, {len(m['moved'])} with a moved deadline / projection / evidence")
            for eid in m["new"][:15]:
                lines.append(f"    - new: {eid}")
            for eid in m["removed"][:15]:
                lines.append(f"    - REMOVED: {eid}")
            for eid, name, diffs in m["moved"][:25]:
                lines.append(f"    - moved: {name or eid} - " + "; ".join(f"{f} {o!r} -> {n!r}" for f, o, n in diffs))
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--previous-db", help="a backup to diff deadlines against")
    ap.add_argument("--markets-dir", default=str(MARKETS_DIR))
    ap.add_argument("--watchlist", default=str(ROOT / "docs" / "operations" / "watchlist.json"))
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--out", help="write the report here as well as printing it")
    a = ap.parse_args(argv)
    try:
        items = json.load(open(a.watchlist, encoding="utf-8"))["items"]
    except (OSError, ValueError, KeyError) as e:
        print(f"cannot read the watch-list: {e}", file=sys.stderr)
        return 2
    tables = {t: _rows(a.db, t) for t in TABLES}
    csvs: dict[str, dict] = {}
    for f in sorted({i["file"] for i in items if "file" in i}):
        p = Path(a.markets_dir) / f
        if p.exists():
            csvs[f] = read_csv_by_id(p)
    results = [check_item(i, tables, csvs, a.today) for i in items]
    mv = movement(a.previous_db, a.db) if a.previous_db else None
    text = render(results, mv, a.today, a.db, a.previous_db)
    print(text)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    return 0 if all(r["result"] in ("OK", "INFO") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
