"""Move a customer row's link to another event we hold, on a person's ruling. Report-only unless --apply.

    python scripts/relink_client_rows.py --db <db> --plan docs/operations/relink_plan_20261108.csv --reason "D2 on Daily Review, decided 2026-11-09" [--apply]

WHY. `apply_client_match.py` never rewrites a link we hold (two locks, 2026-09-16): when the weekly matcher is certain of a DIFFERENT event it reports a CONFLICT and a person decides
between the two links. Until now the person's decision was written by hand (ACT-55, 2026-10-06, one row). This is that hand, with the guards a hand edit lacks, for the case the
customer sheets keep producing: the customer moved their row on to the NEXT edition (date a year later) while our link still points at the edition we matched first.

THE PLAN FILE names each move: client, their_name, from_event_id, to_event_id (other columns are notes for the reader). It is committed to the repo as the record of the ruling.

GUARDS, all or nothing (one refusal and nothing is written):
  * the row exists for that client and holds exactly from_event_id: a link that moved since the plan was written is not re-linked blind;
  * to_event_id is an event we hold (grounding_facts);
  * the new link AGREES ON DATE with the customer's own row (src/cfp_monitor/link_agreement.py, the one rule, 30 days). A place disagreement is allowed and REPORTED: the customer's
    place often names a venue or a region, not the city, and the date is what tells editions apart;
  * the customer has not withdrawn the row.

--apply: a timestamped backup <db>.backup-pre-relink-<stamp>.db is written first; the shared tables (conferences, grounding_facts, conference_markets, evidence) are counted before and
after and the run exits 4 naming the backup if any moved; every row is read back and proved to hold to_event_id. The row records how it was linked: match_method
'operator re-link <date> (<reason>)', match_justification 'was <from_event_id>; <note>', matched_at today. Exit 0 (applied, or dry run), 2 (refused: nothing written), 4 (shared tables moved)."""
from __future__ import annotations

import argparse
import csv
import shutil
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.cfp_monitor.link_agreement import DATE_TOLERANCE_DAYS, full_date, link_disagreement   # noqa: E402

PROTECTED = ("conferences", "grounding_facts", "conference_markets", "evidence")
NEEDED = ("client", "their_name", "from_event_id", "to_event_id")


def read_plan(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for i, r in enumerate(rows, 2):
        missing = [c for c in NEEDED if not (r.get(c) or "").strip()]
        if missing:
            raise ValueError(f"plan line {i}: blank {', '.join(missing)}")
    return [{k: (v or "").strip() for k, v in r.items()} for r in rows]


def check(con: sqlite3.Connection, plan: list[dict]) -> tuple[list[dict], list[str]]:
    """-> (moves that pass every guard, with both sides, [refusal reasons]). Reads only."""
    ok: list[dict] = []
    refused: list[str] = []
    for p in plan:
        tag = f"{p['client']} / {p['their_name']}"
        held = con.execute("select event_id, location, event_start_date, coalesce(withdrawn_by_customer,0) from client_conferences where client_key = ? and their_name = ?",
                           (p["client"], p["their_name"])).fetchone()
        if held is None:
            refused.append(f"{tag}: no such customer row")
            continue
        if (held[0] or "").strip() != p["from_event_id"]:
            refused.append(f"{tag}: holds {held[0] or '(no link)'}, not {p['from_event_id']}: the link moved since the plan was written")
            continue
        if held[3]:
            refused.append(f"{tag}: withdrawn by the customer; nothing to re-link")
            continue
        new = con.execute("select name, city, start_date from grounding_facts where event_id = ?", (p["to_event_id"],)).fetchone()
        if new is None:
            refused.append(f"{tag}: {p['to_event_id']} is not an event we hold")
            continue
        t, o = full_date(held[2] or ""), full_date(new[2] or "")
        if not (t and o):
            refused.append(f"{tag}: cannot judge the date (customer {held[2] or 'none'}, event {new[2] or 'none'})")
            continue
        gap = abs((t - o).days)
        if gap > DATE_TOLERANCE_DAYS:
            refused.append(f"{tag}: {p['to_event_id']} starts {o.isoformat()}, {gap} days from the customer's {t.isoformat()}: not the edition the customer tracks")
            continue
        ok.append({**p, "customer_start": t.isoformat(), "customer_place": held[1] or "", "to_name": new[0] or "", "to_city": new[1] or "", "to_start": o.isoformat(),
                   "gap_days": gap, "place_note": link_disagreement(held[1] or "", held[2] or "", new[1] or "", new[2] or "")})
    return ok, refused


def apply(con: sqlite3.Connection, moves: list[dict], reason: str, today: str) -> int:
    method = f"operator re-link {today} ({reason})"
    for m in moves:
        why = f"was {m['from_event_id']}; " + (m.get("note") or f"the customer's row ({m['customer_start']}) is this edition ({m['to_start']})")
        con.execute("update client_conferences set event_id = ?, match_method = ?, match_justification = ?, matched_at = ? where client_key = ? and their_name = ?",
                    (m["to_event_id"], method, why[:400], today, m["client"], m["their_name"]))
    con.commit()
    for m in moves:
        now = con.execute("select event_id from client_conferences where client_key = ? and their_name = ?", (m["client"], m["their_name"])).fetchone()
        if not now or now[0] != m["to_event_id"]:
            raise AssertionError(f"{m['client']} / {m['their_name']}: read-back holds {now[0] if now else 'nothing'}, not {m['to_event_id']}")
    return len(moves)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--plan", required=True, help="CSV: client, their_name, from_event_id, to_event_id [, note]")
    ap.add_argument("--reason", required=True, help="the ruling, e.g. 'D2 on Daily Review, decided 2026-11-09'")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    db = Path(a.db)
    if not db.exists():
        print(f"ERROR: no such database: {db}")
        return 2
    plan = read_plan(Path(a.plan))
    con = sqlite3.connect(db)
    ok, refused = check(con, plan)
    print(f"{len(plan)} move(s) in the plan: {len(ok)} pass every guard, {len(refused)} refused")
    for m in ok:
        print(f"  MOVE {m['client']} / {m['their_name']}\n       {m['from_event_id']} -> {m['to_event_id']} ({m['to_name']}, {m['to_city']}, starts {m['to_start']}; customer {m['customer_start']}, {m['gap_days']} day(s) apart)")
        if m["place_note"]:
            print(f"       place still differs, allowed: {m['place_note']}")
    for r in refused:
        print(f"  REFUSED {r}")
    if refused:
        print("\nNOTHING WRITTEN: every move must pass (all or nothing). Fix the plan or the ruling.")
        con.close()
        return 2
    if not a.apply:
        print("\nreport only; add --apply to write (backup first)")
        con.close()
        return 0
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = db.with_name(f"{db.stem}.backup-pre-relink-{stamp}.db")
    con.close()
    shutil.copy2(db, backup)
    con = sqlite3.connect(db)
    before = {t: con.execute(f"select count(*) from [{t}]").fetchone()[0] for t in PROTECTED}
    n = apply(con, ok, a.reason, date.today().isoformat())
    after = {t: con.execute(f"select count(*) from [{t}]").fetchone()[0] for t in PROTECTED}
    con.close()
    drift = {t: (before[t], after[t]) for t in PROTECTED if before[t] != after[t]}
    if drift:
        print(f"\n*** SHARED TABLES MOVED: {drift} - restore {backup.name}")
        return 4
    print(f"\napplied {n} move(s); read back and proved; shared tables unchanged ({', '.join(f'{t}={after[t]}' for t in PROTECTED)}); backup {backup.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
