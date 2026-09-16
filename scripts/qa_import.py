"""QA report for the IMPORT step: did the delivery land faithfully, and how did the database move?

    python scripts/qa_import.py                          # compares with last cycle's report
    python scripts/qa_import.py --previous-db <backup.db> --previous-label "Sep 14 backup"

Run by `weekly_deliverable.py` FIRST, before anything it does writes to the database - so it
describes exactly what Step 4 (promote, import, reconcile) left behind. Writes
`runs_out/qa/<cycle>/import.md` and `.json` (shared shape: src/cfp_monitor/qa_report.py).

WHY THIS STEP. WEEKLY-CYCLE calls import "the step most easily forgotten, and the one that fails
invisibly": if the delivery is accepted but not imported, Monday publishes last week's rows with
this week's badges and reports HEALTHY. Three questions a person should be able to answer without
running anything:

    did it land?          each live market's delivery against the database, field by field
    how did we move?      database totals this cycle against last cycle's
    can we see them?      how many of each customer's rows link to a conference we research

THE DATABASE HAS NO HISTORY TABLE, so this report keeps its own: the numbers it measures are saved
in the JSON, and next cycle's report reads them back as "previous". The first run can be given a
backup database instead.

Joins a delivery to the database through `identity` (contract 5.4 - their EVENT_ID is not ours).
Counts and names only. It changes nothing.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import qa_report                                # noqa: E402
from src.cfp_monitor.grounding import parse_loose_date               # noqa: E402
from src.cfp_monitor.identity import seed_map, to_canonical          # noqa: E402

LIVE_DB = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor\cfp_monitor.db")
MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
LIVE_DELIVERIES = {"Cybersecurity": "Cybersecurity_audited.final.csv",
                   "Utility": "Utility_audited.final.csv"}

# delivery column -> database column, and how to compare. The database may legitimately differ
# from a delivery - a merge moves facts, a resolution edits a deadline - so a difference is a
# COUNT to read, not a failure. What IS a flag is a delivered row the database does not hold.
FIELDS = [
    ("SUBMISSION DEADLINE", "deadline", "date"),
    ("DEADLINE_EVIDENCE_URL", "deadline_evidence_url", "text"),
    ("DEADLINE_QUOTE", "deadline_quote", "text"),
    ("IS_PROJECTED", "is_projected", "bool"),
    ("CITY", "city", "text"),
    ("START DATE", "start_date", "date"),
    ("LIFECYCLE_QUOTE", "lifecycle_quote", "text"),
    ("SPONSOR_REQUIRED", "sponsor_required", "text"),
]


def _cols(con, table: str) -> set[str]:
    return {r[1] for r in con.execute(f"pragma table_info({table})")}           # noqa: S608


def _count(con, sql: str, *args) -> int | None:
    try:
        return con.execute(sql, args).fetchone()[0]
    except sqlite3.Error:
        return None


def held_ids(db: Path) -> list[str]:
    """Rows declared held in market_sheets/held_rows.txt beside the database - the same file and
    format check_invariants.py reads."""
    p = Path(db).parent / "market_sheets" / "held_rows.txt"
    if not p.exists():
        return []
    return [ln.partition("#")[0].strip() for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def db_metrics(db: Path) -> dict[str, int | None]:
    """The numbers that describe the database after import. Tolerates an older schema, so a backup
    from before a column existed reports '-' for it rather than failing."""
    con = sqlite3.connect(str(db))
    m: dict[str, int | None] = collections.OrderedDict()
    gf = _cols(con, "grounding_facts")
    nb = "trim(coalesce({},'')) <> ''"
    m["Conferences"] = _count(con, "select count(*) from grounding_facts")
    for state in ("verified", "contradicted", "not_found", "unverified"):
        m[f"  verify: {state}"] = _count(con, "select count(*) from grounding_facts "
                                              "where verify_state = ?", state)
    m["  with a deadline"] = _count(con, f"select count(*) from grounding_facts where {nb.format('deadline')}")
    m["  with a cited page"] = _count(con, f"select count(*) from grounding_facts where {nb.format('deadline_evidence_url')}")
    m["  projected"] = _count(con, "select count(*) from grounding_facts where lower(is_projected)='true'")
    m["  with a start date"] = (_count(con, f"select count(*) from grounding_facts where {nb.format('start_date')}")
                                if "start_date" in gf else None)
    m["  with a lifecycle claim"] = (_count(con, f"select count(*) from grounding_facts where {nb.format('lifecycle_quote')}")
                                     if "lifecycle_quote" in gf else None)
    # A row held on purpose (held_rows.txt, contract 2.1) is on no market list BY DECISION - the
    # AES New York hold on 2026-09-16 - so it is counted apart and never warned about.
    held = set(held_ids(db))
    try:
        unlisted = [r[0] for r in con.execute(
            "select event_id from grounding_facts g where not exists "
            "(select 1 from conference_markets c where c.conference_key = g.conference_key)")]
        m["  on no market list"] = sum(1 for e in unlisted if e not in held)
        m["  on no market list, held by decision"] = sum(1 for e in unlisted if e in held)
    except sqlite3.Error:
        m["  on no market list"] = m["  on no market list, held by decision"] = None
    m["Awards"] = _count(con, "select count(*) from award_grounding_facts")
    m["  awards verified"] = _count(con, "select count(*) from award_grounding_facts where verify_state='verified'")
    try:
        keys = [r[0] for r in con.execute("select distinct client_key from client_conferences order by 1")]
    except sqlite3.Error:
        keys = []
    for k in keys:
        cur = _count(con, "select count(*) from client_conferences where client_key=? and withdrawn_by_customer=0", k)
        linked = _count(con, "select count(*) from client_conferences where client_key=? and withdrawn_by_customer=0 "
                             f"and {nb.format('event_id')}", k)
        m[f"Customer {k}: rows on their sheet"] = cur
        m[f"  {k}: linked to our conference"] = linked
        m[f"  {k}: NOT linked"] = None if cur is None or linked is None else cur - linked
        m[f"  {k}: withdrawn, kept"] = _count(con, "select count(*) from client_conferences where client_key=? "
                                                   "and withdrawn_by_customer=1", k)
    con.close()
    return m


def _norm(v: str, how: str):
    v = (v or "").strip()
    if how == "date":
        d = parse_loose_date(v)
        return d.isoformat() if d else v.lower()
    if how == "bool":
        return v.lower() in ("true", "yes", "1")
    return re.sub(r"\s+", " ", v).rstrip("/").lower()


def delivery_vs_db(db: Path, market: str, delivery: Path) -> dict:
    """One market's delivery against the database, joined the governed way."""
    up2c, _roots = seed_map(str(db))
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    gf = _cols(con, "grounding_facts")
    facts = {r["event_id"]: dict(r) for r in con.execute("select * from grounding_facts")}
    con.close()
    with open(delivery, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    missing, agree, differ, examples = [], collections.Counter(), collections.Counter(), collections.defaultdict(list)
    for r in rows:
        eid = to_canonical((r.get("EVENT_ID") or "").strip(), up2c)
        f = facts.get(eid)
        if f is None:
            missing.append((r.get("CONFERENCE") or eid)[:60])
            continue
        for dcol, fcol, how in FIELDS:
            if fcol not in gf or dcol not in r:
                continue
            if _norm(r.get(dcol), how) == _norm(f.get(fcol) or "", how):
                agree[dcol] += 1
            else:
                differ[dcol] += 1
                if len(examples[dcol]) < 3:
                    examples[dcol].append(f"{(r.get('CONFERENCE') or eid)[:40]}: delivery "
                                          f"'{(r.get(dcol) or '')[:30]}' / database '{(f.get(fcol) or '')[:30]}'")
    return {"market": market, "file": delivery.name, "delivered": len(rows),
            "in_db": len(rows) - len(missing), "missing": missing,
            "agree": dict(agree), "differ": dict(differ), "examples": dict(examples)}


def invariants(db: Path) -> tuple[str, list[str]]:
    try:
        p = subprocess.run([sys.executable, str(ROOT / "scripts/check_invariants.py"), "--db", str(db)],
                           capture_output=True, text=True, timeout=600)
    except Exception as exc:                                         # noqa: BLE001
        return f"did not run ({type(exc).__name__})", []
    out = p.stdout + p.stderr
    result = next((ln.strip() for ln in out.splitlines() if ln.startswith("RESULT")), "no RESULT line")
    fails = [ln.strip() for ln in out.splitlines() if "[FAIL]" in ln]
    return result, fails


def previous_metrics(out_root: Path, cycle: str) -> tuple[dict | None, str, str | None]:
    """The metrics saved by the most recent EARLIER cycle's import report, and the day they
    were measured (so merges since then can be counted)."""
    earlier = sorted(p for p in Path(out_root).glob("*/import.json") if p.parent.name < cycle)
    if not earlier:
        return None, "none - this is the first import report", None
    data = json.loads(earlier[-1].read_text(encoding="utf-8"))
    return (data.get("metrics"), f"cycle {earlier[-1].parent.name} (measured {data.get('ran_on')})",
            data.get("ran_on"))


MERGED_ROWS = ROOT / "docs" / "operations" / "merged_rows.txt"


def merges_recorded_since(since: str, path: Path | None = None) -> int:
    """Merges recorded on or after `since` (YYYY-MM-DD). Each merge is one dated header line.
    The file is looked up at CALL time: a default bound at definition time ignored any other path."""
    path = Path(path) if path else MERGED_ROWS
    if not path.exists():
        return 0
    pat = re.compile(r"^(\d{4}-\d{2}-\d{2}) \S+ -> \S+")
    return sum(1 for ln in path.read_text(encoding="utf-8").splitlines()
               if (m := pat.match(ln)) and m.group(1) >= since)


def build(db: Path, on: date, deliveries: dict[str, Path], prev: dict | None, prev_label: str,
          run_invariants: bool = True, prev_since: str | None = None) -> dict:
    rep = qa_report.new_report("import", on)
    rep["notes"] = []
    now = db_metrics(db)
    rep["metrics"] = now

    # 1. Did each delivery land?
    land_rows = []
    for market, path in deliveries.items():
        if not path.exists():
            rep["flags"].append(f"{market}: no promoted delivery at {path.name} - nothing to import")
            continue
        d = delivery_vs_db(db, market, path)
        if d["missing"]:
            rep["flags"].append(f"{market}: {len(d['missing'])} delivered row(s) are NOT in the database "
                                f"- import did not run or did not finish: {', '.join(d['missing'][:5])}")
        for dcol, _f, _h in FIELDS:
            a, x = d["agree"].get(dcol), d["differ"].get(dcol)
            if a is None and x is None:
                continue
            land_rows.append([market, dcol, d["in_db"], a or 0, x or 0,
                              "; ".join(d["examples"].get(dcol, [])[:2])])
        rep["sections"].append({
            "title": f"{market} delivery -> database",
            "note": f"`{d['file']}`: {d['delivered']} delivered, {d['in_db']} found in the database",
            "columns": [], "rows": []})
    rep["sections"].append({
        "title": "Did the delivery land? Field by field",
        "note": ("A difference is not automatically wrong - a merge or a resolution can "
                 "legitimately change the database after import. A delivered row that is MISSING is."),
        "columns": ["Market", "Delivery field", "Rows compared", "Agree", "Differ", "Examples"],
        "rows": land_rows})

    # 2. How did the database move?
    keys = list(now) + [k for k in (prev or {}) if k not in now]
    rep["sections"].append({
        "title": "How the database moved",
        "note": f"Previous: {prev_label}",
        "columns": ["", "Previous", "Now", "Change"],
        "rows": [[k, (prev or {}).get(k), now.get(k),
                  qa_report.change((prev or {}).get(k), now.get(k))] for k in keys]})

    # What deserves a look, from the numbers themselves.
    for k, v in now.items():
        if k.endswith("NOT linked") and v:
            total = now.get(k.replace("  ", "Customer ").replace(": NOT linked", ": rows on their sheet"))
            rep["flags"].append(f"{k.strip()}: {v} of their rows link to no conference we research"
                                + (f" (of {total})" if total else ""))
        if k == "  on no market list" and v:
            rep["flags"].append(f"{v} conference(s) on no market list - invisible to every market view")
        if prev and k == "Conferences" and prev.get(k) is not None and v is not None and v < prev[k]:
            # A fall is explained only by merges someone RECORDED. On 2026-09-16 the database was
            # 26 rows smaller than the Sep 14 backup and merged_rows.txt recorded exactly 26 merges
            # in between - a deliberate tidy, not a loss. Rows gone beyond what was recorded are.
            merged = merges_recorded_since(prev_since) if prev_since else None
            lost = prev[k] - v
            if merged is None or lost > merged:
                rep["flags"].append(
                    f"conference rows fell from {prev[k]} to {v}"
                    + (f" - only {merged} merge(s) recorded since {prev_since}, so {lost - merged} "
                       f"row(s) are unaccounted for" if merged is not None else ""))
            else:
                rep["notes"].append(f"conference rows fell by {lost}, fully accounted for by {merged} "
                                    f"merge(s) recorded in merged_rows.txt since {prev_since}")

    if rep["notes"]:
        rep["sections"].insert(0, {"title": "Explained", "note": "\n".join(f"- {n}" for n in rep["notes"]),
                                   "columns": [], "rows": []})

    # 3. The reconciliation, recorded rather than re-derived.
    if run_invariants:
        result, fails = invariants(db)
        rep["invariants"] = {"result": result, "failures": fails}
        rep["sections"].append({"title": "Reconciliation (check_invariants.py)",
                                "note": result, "columns": ["Failed check"],
                                "rows": [[f] for f in fails]})
        if "VIOLATED" in result or "did not run" in result:
            rep["flags"].append(f"invariants: {result}")
    return qa_report.finish(rep, "the deliveries are in the database and nothing moved unexpectedly")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--previous-db", help="a backup to compare with, when no earlier report exists")
    ap.add_argument("--previous-label", default="")
    ap.add_argument("--on", default=date.today().isoformat())
    ap.add_argument("--out", default=str(qa_report.QA_ROOT))
    ap.add_argument("--no-invariants", action="store_true")
    a = ap.parse_args()

    on = date.fromisoformat(a.on)
    cycle = qa_report.cycle_of(on).isoformat()
    if a.previous_db:
        pdb = Path(a.previous_db)
        prev, label = db_metrics(pdb), a.previous_label or pdb.name
        since = date.fromtimestamp(pdb.stat().st_mtime).isoformat()
    else:
        prev, label, since = previous_metrics(Path(a.out), cycle)
    deliveries = {m: Path(a.markets_dir) / f for m, f in LIVE_DELIVERIES.items()}
    rep = build(Path(a.db), on, deliveries, prev, label, run_invariants=not a.no_invariants,
                prev_since=since)
    md = qa_report.to_markdown(rep, "Import QA - did the delivery land, and how did we move")
    print(md)
    try:
        print(f"wrote {qa_report.write(rep, md, Path(a.out))}")
    except OSError as exc:
        print(f"could not write QA report: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
