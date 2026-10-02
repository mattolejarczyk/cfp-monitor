"""Numbers for the CFP Status Board that can be computed from the database alone.

    python scripts/board_metrics.py [--db <live db>] [--previous-db <backup>] [--examples N] [--update-status]

WHY (2026-10-02). The board's "agreement with customer-verified dates" (20 of 40 on 2026-10-01) was computed once, by
hand, and could not be reproduced: the query was not kept. A headline number that nobody can re-run is a rumour. This
script is that query, with its definition written down, so the board can refresh the number the same way every time.

DEFINITION - customer agreement
  Population: rows in `client_conferences` where the customer's team marked the date `Verified`
              (submission_date_verified = 'Verified', case-insensitive), the customer has a date, and the customer has NOT
              withdrawn the row (withdrawn_by_customer = 0: a row they no longer track is not a promise to them).
  Our side:   the stored `deadline` of the same canonical event_id, in `grounding_facts` or `award_grounding_facts`.
  Unmatched:  rows whose customer line has no counterpart in our database are NOT in the population above; they are reported
              as the coverage gap (2026-10-02: 41 of 75, mostly older or out-of-scope events).
  Classes:    agree      the two dates are the same day
              blank      the customer has a date and ours is blank (we have nothing to offer)
              differ     both have a date and they are different days
              unreadable the customer's date cell is not a date we can read (reported, never counted as agree or differ)
  Not cleaned for editions or passed rows: a customer date of 2026-07-15 against our 2027 edition counts as `differ`.
  That is a rough reading on purpose; it is what the customer would feel on opening the sheet beside the page.

--update-status rewrites `headline.customer` in docs/design/status.json (levels, row count, source line) and nothing else.
Read-only otherwise. The 2026-10-01 figure (40 rows) also counted rows the customer had withdrawn; excluding them gives the
34 this script reports for the same database.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE_DB = Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor" / "cfp_monitor.db"
STATUS_JSON = ROOT / "docs" / "design" / "status.json"
CLASSES = ("agree", "blank", "differ", "unreadable")


def parse_their_date(s: str) -> str | None:
    """The customer's sheet writes MM/DD/YYYY; ISO is accepted too. Anything else is unreadable, not guessed."""
    s = (s or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _our_deadlines(con: sqlite3.Connection) -> dict[str, str]:
    ours: dict[str, str] = {}
    for table in ("grounding_facts", "award_grounding_facts"):
        try:
            for eid, dl in con.execute(f"select event_id, deadline from {table}"):
                ours[eid] = (dl or "").strip()
        except sqlite3.OperationalError:
            continue
    return ours


def customer_agreement(db: str) -> dict:
    con = sqlite3.connect(db)
    try:
        ours = _our_deadlines(con)
        rows = con.execute(
            "select client_key, their_name, event_id, their_deadline from client_conferences "
            "where lower(trim(submission_date_verified)) = 'verified' and trim(their_deadline) != '' "
            "and coalesce(withdrawn_by_customer, 0) = 0").fetchall()
    finally:
        con.close()
    counts = {k: 0 for k in CLASSES}
    detail = []
    unmatched = 0
    for client, name, eid, theirs in rows:
        if eid not in ours:
            unmatched += 1
            continue
        t, o = parse_their_date(theirs), ours[eid]
        if t is None:
            cls = "unreadable"
        elif not o:
            cls = "blank"
        elif t == o:
            cls = "agree"
        else:
            cls = "differ"
        counts[cls] += 1
        detail.append({"client": client, "name": name, "event_id": eid, "theirs": theirs.strip(), "ours": o, "class": cls})
    return {"rows": sum(counts.values()), "counts": counts, "unmatched_to_our_db": unmatched, "detail": detail}


def render(cur: dict, prev: dict | None, examples: int) -> str:
    c = cur["counts"]
    readable = c["agree"] + c["blank"] + c["differ"]
    pct = f"{100 * c['agree'] / readable:.0f}%" if readable else "n/a"
    lines = [f"Customer agreement: {c['agree']} of {readable} readable rows agree ({pct})",
             f"  agree {c['agree']} | our deadline blank {c['blank']} | different date {c['differ']} | unreadable customer date {c['unreadable']}",
             f"  coverage gap: {cur['unmatched_to_our_db']} more customer-verified, dated rows have NO matching event of ours "
             f"(they track it, we do not research it)"]
    if prev:
        p = prev["counts"]
        lines.append("  since the backup: " + ", ".join(f"{k} {p[k]} -> {c[k]}" for k in CLASSES))
    for cls in ("differ", "blank"):
        shown = [d for d in cur["detail"] if d["class"] == cls][:examples]
        if shown:
            lines.append(f"  {cls}:")
            lines += [f"    - [{d['client']}] {d['name'][:48]}: customer {d['theirs']} / ours {d['ours'] or '(blank)'}" for d in shown]
    return "\n".join(lines)


def update_status(cur: dict, today: str, path: Path = STATUS_JSON) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    c = cur["counts"]
    h = data["headline"]["customer"]
    h["rows"] = cur["rows"]
    h["levels"] = [{"key": "agree", "label": "Same date", "n": c["agree"], "tone": "good"},
                   {"key": "blank", "label": "Our deadline blank", "n": c["blank"], "tone": "warn"},
                   {"key": "differ", "label": "Different date", "n": c["differ"], "tone": "bad"}]
    if c["unreadable"]:
        h["levels"].append({"key": "unreadable", "label": "Customer date unreadable", "n": c["unreadable"], "tone": "none"})
    h["source"] = f"scripts/board_metrics.py, client_conferences joined to our deadlines, {today}; customer-withdrawn rows excluded"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--previous-db")
    ap.add_argument("--examples", type=int, default=6)
    ap.add_argument("--update-status", action="store_true")
    ap.add_argument("--today", default=date.today().isoformat())
    a = ap.parse_args(argv)
    cur = customer_agreement(a.db)
    prev = customer_agreement(a.previous_db) if a.previous_db else None
    print(render(cur, prev, a.examples))
    if a.update_status:
        update_status(cur, a.today)
        print(f"updated headline.customer in {STATUS_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
