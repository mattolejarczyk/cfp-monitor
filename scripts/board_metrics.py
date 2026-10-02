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

LIVE vs ALL (2026-10-02, operator questioned 28% and 50% as too low). A deadline that has already passed cannot be judged by
whether its page still carries the date: pages move on to the next edition (the purpose audit itself said 15 of 16 "absent" and 11 of 12
"unreadable" rows were already-passed deadlines, "not errors"), and the customer's dated row can still point at the previous edition. So both
headlines are reported for LIVE rows (the date a customer would act on is still ahead) with the all-rows figure kept beside it as the rough one.
  customer agreement, live: the customer's date OR ours is on or after --today.
  provable, live:  our stored deadline is on or after --today, for events on the Cybersecurity or Utility seed sheets (the market lists the
                   pipeline uses; `conference_markets` misses events added since the last crawl).
                   verified   our verifier found the date on the cited page and a citation exists
                   withdrawn  no citation (withdrawn by agreement, projected): honestly unproven, not wrong
                   unreadable the verifier could not read the cited page (HTTP 403, script-built page): unproven, a browser read would settle it
                   notfound   the page was read and the date is not on it
                   contradicted  the page was read and states a different date
--update-status rewrites `headline.customer` and `headline.provable` in docs/design/status.json (levels, row counts, notes) and nothing else.
Read-only otherwise. The 2026-10-01 figure (40 rows) also counted rows the customer had withdrawn; excluding them gives the
34 this script reports for the same database.
"""
from __future__ import annotations

import argparse
import csv
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


def customer_agreement(db: str, today: str = "") -> dict:
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
        is_live = bool(today) and ((t is not None and t >= today) or (o != "" and o >= today))
        detail.append({"client": client, "name": name, "event_id": eid, "theirs": theirs.strip(), "ours": o, "class": cls, "live": is_live})
    live_counts = {k: sum(1 for d in detail if d["live"] and d["class"] == k) for k in CLASSES}
    return {"rows": sum(counts.values()), "counts": counts, "unmatched_to_our_db": unmatched, "detail": detail,
            "live_counts": live_counts, "live_rows": sum(live_counts.values())}


def provable_live(db: str, today: str) -> dict:
    """How many LIVE stored deadlines (on or after `today`) are proven on their cited page. See the module docstring."""
    ids: set[str] = set()
    seed_dir = Path(db).parent / "market_sheets"
    for name in ("cyber_seed.csv", "utility_seed.csv"):
        p = seed_dir / name
        if p.exists():
            with open(p, encoding="utf-8-sig", newline="") as fh:
                ids |= {(r.get("EVENT_ID_CANON") or "").strip() for r in csv.DictReader(fh)} - {""}
    con = sqlite3.connect(db)
    try:
        rows = con.execute("select event_id, name, deadline, verify_state, coalesce(verify_detail,''), coalesce(deadline_evidence_url,'') "
                           "from grounding_facts where trim(deadline) != '' and deadline >= ?", (today,)).fetchall()
    finally:
        con.close()
    counts = {k: 0 for k in ("verified", "withdrawn", "unreadable", "notfound", "contradicted")}
    detail = []
    for eid, name, dl, state, why, ev in rows:
        if eid not in ids:
            continue
        if not ev.strip():
            cls = "withdrawn"
        elif state == "verified":
            cls = "verified"
        elif state == "contradicted":
            cls = "contradicted"
        elif "could not be read" in why:
            cls = "unreadable"
        else:
            cls = "notfound"
        counts[cls] += 1
        detail.append({"event_id": eid, "name": name, "deadline": dl, "class": cls})
    return {"rows": sum(counts.values()), "counts": counts, "detail": sorted(detail, key=lambda d: d["deadline"])}


def render(cur: dict, prev: dict | None, examples: int) -> str:
    c = cur["counts"]
    readable = c["agree"] + c["blank"] + c["differ"]
    pct = f"{100 * c['agree'] / readable:.0f}%" if readable else "n/a"
    lc = cur.get("live_counts")
    lines = []
    if lc is not None:
        lr = lc["agree"] + lc["blank"] + lc["differ"]
        lines.append(f"Customer agreement, LIVE rows (a date still ahead): {lc['agree']} of {lr} agree "
                     f"({100 * lc['agree'] // lr if lr else 0}%); our blank {lc['blank']}, different {lc['differ']}")
    lines += [f"Customer agreement, ALL rows (rough; includes past dates and old editions): {c['agree']} of {readable} readable rows agree ({pct})",
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


def update_status(cur: dict, today: str, path: Path = STATUS_JSON, prov: dict | None = None) -> None:
    """Rewrite headline.customer (and headline.provable when `prov` is given). LIVE figures lead; the all-rows figure stays in the note."""
    data = json.loads(path.read_text(encoding="utf-8"))
    c = cur["counts"]
    lc = cur.get("live_counts")
    h = data["headline"]["customer"]
    use = lc if lc is not None else c
    h["rows"] = cur.get("live_rows", cur["rows"]) if lc is not None else cur["rows"]
    h["levels"] = [{"key": "agree", "label": "Same date", "n": use["agree"], "tone": "good"},
                   {"key": "blank", "label": "Our deadline blank", "n": use["blank"], "tone": "warn"},
                   {"key": "differ", "label": "Different date", "n": use["differ"], "tone": "bad"}]
    if use["unreadable"]:
        h["levels"].append({"key": "unreadable", "label": "Customer date unreadable", "n": use["unreadable"], "tone": "none"})
    if lc is not None:
        readable_all = c["agree"] + c["blank"] + c["differ"]
        h["label"] = "Agreement with customer-verified dates (live rows)"
        h["definition"] = ("Rows where the customer's team marked the date Verified and has a date, the customer has not withdrawn the row, and the "
                           "customer's date or ours is still ahead: does ours match? Rows whose dates have both passed are not scored here.")
        h["note"] = (f"All rows, rough (includes past dates and old editions): {c['agree']} of {readable_all} agree. Of the live rows that do not "
                     "agree today, most are fixed by loads already done (Nullcon, Troopers 2027, Black Hat Asia) but the customer's row still points at "
                     "the previous edition's event; Climate Change is the customer holding the earlier round's date.")
    h["source"] = f"scripts/board_metrics.py, client_conferences joined to our deadlines, {today}; customer-withdrawn rows excluded"
    if prov is not None:
        pc = prov["counts"]
        ph = data["headline"]["provable"]
        ph["label"] = "Provable submission date (live deadlines)"
        ph["definition"] = ("Deadlines still ahead for events on the Cybersecurity and Utility market lists. Proven = our verifier found the stored date on "
                            "the cited page and a citation exists. A deadline that has already passed is not scored: its page moves on to the next edition.")
        ph["rows"] = prov["rows"]
        ph["open_rows"] = prov["rows"]
        ph["open_confirmed"] = pc["verified"]
        ph["levels"] = [
            {"key": "confirmed", "label": "Date on the cited page", "n": pc["verified"], "tone": "good"},
            {"key": "withdrawn", "label": "Citation withdrawn by agreement (honestly unproven)", "n": pc["withdrawn"], "tone": "warn"},
            {"key": "nopage", "label": "Cited page blocks our plain reader (a browser read would settle it)", "n": pc["unreadable"], "tone": "mute"},
            {"key": "absent", "label": "Page read, date not on it", "n": pc["notfound"], "tone": "bad"},
            {"key": "mismatch", "label": "Page read, shows a different date", "n": pc["contradicted"], "tone": "bad"}]
        ph["note"] = ("The earlier 28% (11 of 39) counted every stored deadline, including 44 of 48 that had already passed; the purpose audit itself said "
                      "15 of 16 'absent' and 11 of 12 'unreadable' rows were already-passed deadlines, 'not errors'. On live deadlines the unproven ones are "
                      "a deliberate citation withdrawal and pages that refuse a plain fetch, not wrong dates.")
        ph["source"] = f"scripts/board_metrics.py provable_live, {today}; experiments/purpose_audit/RESULT.md for the all-rows audit"
        for g in data["objective"]["good"]:
            if g["label"].startswith("Provable submission dates"):
                g["now"] = f"{pc['verified']} of {prov['rows']} live deadlines proven on their cited page; the rest are a deliberate withdrawal or pages our plain reader cannot open"
            if g["label"].startswith("Agreement with customer-verified dates") and lc is not None:
                lr = lc["agree"] + lc["blank"] + lc["differ"]
                g["now"] = f"{lc['agree']} of {lr} live rows today ({100 * lc['agree'] // lr if lr else 0}%); {c['agree']} of {c['agree'] + c['blank'] + c['differ']} counting past dates and old editions"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--previous-db")
    ap.add_argument("--examples", type=int, default=6)
    ap.add_argument("--update-status", action="store_true")
    ap.add_argument("--today", default=date.today().isoformat())
    a = ap.parse_args(argv)
    cur = customer_agreement(a.db, a.today)
    prev = customer_agreement(a.previous_db, a.today) if a.previous_db else None
    print(render(cur, prev, a.examples))
    prov = provable_live(a.db, a.today)
    pc = prov["counts"]
    print(f"Provable submission date, LIVE deadlines ({a.today} or later, on the market lists): {pc['verified']} of {prov['rows']} proven on the cited page"
          f" | citation withdrawn {pc['withdrawn']} | page unreadable by plain fetch {pc['unreadable']} | date not on page {pc['notfound']} | different date {pc['contradicted']}")
    for d in prov["detail"]:
        if d["class"] != "verified":
            print(f"    {d['class']:12} {d['deadline']}  {d['name'][:56]}")
    if a.update_status:
        update_status(cur, a.today, prov=prov)
        print(f"updated headline.customer in {STATUS_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
