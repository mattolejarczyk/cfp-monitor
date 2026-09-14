"""Draft - and on --apply, perform - the merge of one event that is held as two records.

    python scripts/merge_duplicate_events.py --db DB [--class SAME_TODAY] [--apply]

Reads the classes `find_duplicate_events.py` produces. Reports by default. Nothing here runs
unattended: a merge destroys a row, and 2.1 permits that only for a row positively identified
as superseded, with the reason recorded.

WHICH ROW SURVIVES, and why it is not the newest one
The obvious rule - keep the row with the freshest research - is wrong here, and measurably so.
On 2026-09-14 all seven SAME_TODAY groups carried a `client_conferences` link, and SIX of the
seven pointed at the OLDER row. Keeping the newest would have orphaned Nicolia's own matches,
including ACT Expo (`Drafting Abstract`, priority Urgent) and World Future Energy Summit
(`Submitted`, with their own note about chasing the deadline). `match_customer_sheet` already
knew: two of its stored justifications read "We hold 2 editions of this conference; chose...".

So the SURVIVOR IS THE ROW THE CUSTOMER IS JOINED TO. That costs nothing, because a key is a
name, not a fact - `2026-act-expo-las-vegas` holding a 2027 edition is ugly and harmless, and
fix_edition.py already established that keys do not move. The FACTS then move onto it.

WHICH FACTS WIN
The newer row's, field by field, with the merge guard `apply_resolutions.py --citations`
already uses: a blank NEVER overwrites a populated field. So the survivor keeps everything it
has that the newer row lacks, and gains everything the newer row learned. A citation travels
as a unit - URL, quote and the date they support - because splitting them is how a quote ends
up attached to a date it never proved (R1, from the other direction).

WHAT IS NEVER TOUCHED
`client_conferences` is the customer's layer - their status, priority and notes (contract 3).
The merge re-points nothing there and rewrites nothing in it, which is the whole reason the
survivor is chosen the way it is.
"""
from __future__ import annotations

import argparse
import collections
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import importlib.util                                                # noqa: E402

_spec = importlib.util.spec_from_file_location("fde", ROOT / "scripts" / "find_duplicate_events.py")
fde = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fde)

# The citation travels as a unit: a URL without its quote proves nothing, and a quote attached
# to a date it did not prove is the defect R1 exists to stop.
FACT_FIELDS = ("deadline", "deadline_quote", "deadline_evidence_url", "verify_state",
               "verify_detail", "source_as_of", "submission_url", "main_info_url", "status",
               "cfp_model", "overview", "categories", "organizer", "coordinator_email",
               "sponsor_required", "sponsor_url", "sponsor_cost", "sponsor_quote", "is_projected")
# Everything that describes A SUBMISSION. These must never travel off a row that was only ever
# about attending, however fresh it is.
#
# The draft caught itself doing it on 2026-09-14: merging SIEW's registration row would have
# put `deadline_quote = "Registration is now open for the 1..."` and status Open onto the
# speaking row - the same mistake as the CES stale crawl, where "Registration is now open" was
# read as an open call for speakers and produced a false contradiction. A registration page can
# still tell us who organises the event and what it is about; it can never tell us when an
# abstract is due.
SUBMISSION_FIELDS = frozenset({"deadline", "deadline_quote", "deadline_evidence_url",
                               "verify_state", "verify_detail", "submission_url", "cfp_model",
                               "status", "is_projected"})

# Tables that point at an event by id and must follow the row that survives.
ATTACHED = (("evidence", "event_id"), ("conferences", "event_id"))
# Read to warn, never written: contract 3.
CUSTOMER_ACTIVE = ("Drafting Abstract", "Info Needed", "Submitted", "Accepted")


def blank(v) -> bool:
    return v is None or str(v).strip() == ""


def survivor(rows: list[sqlite3.Row], linked: dict[str, dict]) -> tuple[sqlite3.Row, str]:
    """The row the customer is joined to, if any. Otherwise the one with the most evidence."""
    joined = [r for r in rows if r["event_id"] in linked]
    if len(joined) == 1:
        return joined[0], "the customer's sheet is matched to this row"
    if len(joined) > 1:
        return None, f"AMBIGUOUS: {len(joined)} rows carry a customer link - decide by hand"
    best = max(rows, key=lambda r: (sum(not blank(r[f]) for f in FACT_FIELDS if f in r.keys()),
                                    r["source_as_of"] or ""))
    return best, "no customer link; kept the row carrying more evidence"


def about_attending_only(row: sqlite3.Row) -> bool:
    """True when this row's key was minted under a label for attending rather than submitting."""
    return fde.parts(row)[3] in fde.NOT_AN_OPPORTUNITY


def plan_one(rows: list[sqlite3.Row], linked: dict[str, dict]) -> dict | None:
    keep, why = survivor(rows, linked)
    if keep is None:
        return {"error": why, "rows": rows}
    losers = [r for r in rows if r["event_id"] != keep["event_id"]]
    newest = max(rows, key=lambda r: r["source_as_of"] or "")
    changes = {}
    for f in FACT_FIELDS:
        if f not in keep.keys():
            continue
        for src in sorted(losers, key=lambda r: r["source_as_of"] or "", reverse=True):
            if f in SUBMISSION_FIELDS and about_attending_only(src):
                continue                        # a ticket page cannot date an abstract
            if not blank(src[f]) and str(src[f]) != str(keep[f] or ""):
                # The guard: a blank never overwrites a populated field. A populated value is
                # replaced only by the row that saw the page more recently.
                if blank(keep[f]) or (src["source_as_of"] or "") > (keep["source_as_of"] or ""):
                    changes[f] = (keep[f], src[f], src["event_id"])
                break
    return {"keep": keep, "why": why, "losers": losers, "newest": newest, "changes": changes,
            "client": linked.get(keep["event_id"])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--class", dest="cls", default="SAME_TODAY",
                    help="which duplicate class to merge (default: SAME_TODAY)")
    ap.add_argument("--apply", action="store_true", help="write the merge (backs up the DB first)")
    a = ap.parse_args()

    con = sqlite3.connect(a.db)
    con.row_factory = sqlite3.Row
    linked: dict[str, dict] = {}
    for r in con.execute("SELECT * FROM client_conferences"):
        linked.setdefault(r["event_id"], dict(r))

    plans, blocked = [], []
    for _gkey, rows in sorted(fde.groups(con, "grounding_facts").items()):
        if fde.classify(rows) != a.cls:
            continue
        p = plan_one(rows, linked)
        (blocked if p.get("error") else plans).append(p)

    print(f"MERGE DRAFT - class {a.cls} - {len(plans)} group(s)"
          f"{f', {len(blocked)} blocked' if blocked else ''}\n")
    warn = 0
    for p in plans:
        keep, cl = p["keep"], p["client"]
        print("=" * 78)
        print(f"KEEP    {keep['event_id']}")
        print(f"        {keep['name'][:66]}")
        print(f"        ({p['why']})")
        for lo in p["losers"]:
            print(f"DELETE  {lo['event_id']}   (seen {lo['source_as_of'] or '-'},"
                  f" {lo['verify_state']})")
            for t, col in ATTACHED:
                n = con.execute(f"SELECT COUNT(*) FROM {t} WHERE {col}=?",  # noqa: S608
                                (lo["event_id"],)).fetchone()[0]
                if n:
                    print(f"          re-point {n} {t} row(s) to the survivor")
        if p["changes"]:
            print("        facts moved onto the survivor:")
            for f, (old, new, src) in sorted(p["changes"].items()):
                print(f"          {f:24} {str(old or '(blank)')[:28]:30} -> {str(new)[:34]}")
        else:
            print("        no fact changes - the survivor already holds everything")
        if cl and (cl.get("status") or "") in CUSTOMER_ACTIVE:
            warn += 1
            print(f"        *** CUSTOMER IS WORKING THIS ROW: status={cl['status']!r}"
                  f" priority={cl.get('priority') or '-'!r} - read before applying")
    for b in blocked:
        print("=" * 78)
        print(f"BLOCKED {b['error']}")
        for r in b["rows"]:
            print(f"        {r['event_id']}")

    print("\n" + "=" * 78)
    print(f"{len(plans)} merge(s) drafted; {warn} touch a row the customer is actively working.")
    if not a.apply:
        print("\nDRY RUN - nothing was changed. Re-run with --apply to write it.")
        con.close()
        return 0

    backup = Path(a.db).with_suffix(f".before-merge-{datetime.now():%Y%m%d-%H%M%S}.db")
    shutil.copy2(a.db, backup)
    print(f"\nbacked up -> {backup.name}")
    ledger = ROOT / "docs" / "operations" / "merged_rows.txt"
    lines = []
    for p in plans:
        keep = p["keep"]
        for f, (_old, new, _src) in p["changes"].items():
            con.execute(f"UPDATE grounding_facts SET {f}=? WHERE event_id=?",  # noqa: S608
                        (new, keep["event_id"]))
        for lo in p["losers"]:
            for t, col in ATTACHED:
                con.execute(f"UPDATE OR IGNORE {t} SET {col}=? WHERE {col}=?",  # noqa: S608
                            (keep["event_id"], lo["event_id"]))
                con.execute(f"DELETE FROM {t} WHERE {col}=?", (lo["event_id"],))  # noqa: S608
            con.execute("DELETE FROM grounding_facts WHERE event_id=?", (lo["event_id"],))
            lines.append(f"{datetime.now():%Y-%m-%d} {lo['event_id']} -> {keep['event_id']}"
                         f"  (duplicate of the same event; {p['why']})")
    con.commit()
    con.close()
    with open(ledger, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"merged {len(plans)} group(s); recorded in {ledger.name}")
    print("Now run scripts/check_invariants.py - a mutation needs a reconciliation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
