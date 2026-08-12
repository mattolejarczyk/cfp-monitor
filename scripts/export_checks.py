"""Write the deadline-verification CSV the customer page reads.

THE STEP THAT WAS MISSING
`build_review_page.py --checks` drives "Deadline confirmed", "Need to Verify" and its three
sub-buckets. Nothing in this repo produced that file - the one in use was made by hand on
2026-08-11 at 06:20. So `audit_evidence.py` could re-read every cited page and the page would
still show the morning's numbers, because the audit writes to the database and the page reads
a spreadsheet nobody regenerated.

Same disconnect as the delivery CSV, one layer over. Measured the evening it was found: 43 of
the 96 rows the page still called "Need to Verify" had been verified hours earlier.

VERDICTS, AND WHY THEY ARE PER-EVENT NOT PER-CLAIM
`evidence` holds one row per claim, so an event can carry several deadline claims from
different origins - upstream's and our own crawl. The page needs one answer per event, so they
are collapsed worst-first: a contradiction outranks a missing quote, which outranks an
unreadable page, which outranks a pass. Reporting the friendliest verdict of several would
quietly hide the disagreement that matters.

IDS ARE UPSTREAM'S HERE. The page matches on the delivery's EVENT_ID, so canonical ids are
mapped back through the seeds on the way out. Emitting canonical ids produces a file that
matches nothing and a page that reports zero of everything - a missing input reading as a
finding, again.

    python scripts/export_checks.py --db <live.db> -o deadline_checks_<date>.csv
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Worst first. The page shows one badge per row, so the badge must be the least reassuring
# thing we know, not the most.
PRECEDENCE = ("contradicted", "no_quote", "unreadable", "verified")
COLUMNS = ("EVENT_ID", "CHECK", "CHECK_URL", "CHECK_QUOTE", "CHECK_DETAIL")


def main() -> int:
    ap = argparse.ArgumentParser(description="Export deadline verdicts for the customer page.")
    ap.add_argument("--db", required=True)
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--origin", default="grounding", choices=["grounding", "crawl"],
                    help="whose claim is being checked. 'grounding' is upstream's cited page, "
                         "which is what the page reports on. Changing this changes what the "
                         "customer is told.")
    a = ap.parse_args()

    con = sqlite3.connect(a.db)
    con.row_factory = sqlite3.Row
    # TWO FILTERS, AND BOTH CHANGE WHAT THE CUSTOMER IS TOLD.
    #
    # origin='grounding' - the page's question is "did we open THEIR cited page and find the
    # deadline on it". Our own crawl verdicts answer a different question and mixing them in
    # would relabel rows nobody disputed.
    #
    # deadline must be non-blank - "not on page" is meaningless when there is no date to look
    # for. Without this the export covered 370 events instead of 158 and reported 308 rows
    # needing verification instead of 96, almost all of them rows with nothing to verify. It
    # would have tripled the alarm on the customer's page using rows that carry no claim.
    rows = list(con.execute(
        "select e.event_id, e.verdict, e.source_url, e.found_quote, e.quote, e.detail, "
        "       e.fetched_at "
        "from evidence e join grounding_facts g on g.event_id = e.event_id "
        "where e.field='deadline' and coalesce(e.verdict,'') <> '' "
        f"  and e.origin = ? "
        "  and coalesce(g.deadline,'') <> '' "
        "order by e.fetched_at", (a.origin,)))
    if not rows:
        print(f"REFUSING: no {a.origin} deadline verdicts on rows that have a deadline. "
              "Run build_evidence.py then "
              "audit_evidence.py first - writing an empty file here would make the page "
              "report 0 confirmed, which reads as a finding rather than a missing input.")
        return 2

    best: dict[str, sqlite3.Row] = {}
    for r in rows:
        cur = best.get(r["event_id"])
        if cur is None:
            best[r["event_id"]] = r
            continue
        def rank(x):
            v = (x["verdict"] or "")
            return PRECEDENCE.index(v) if v in PRECEDENCE else len(PRECEDENCE)
        # Worse wins; on a tie the more recent reading wins.
        if rank(r) < rank(cur) or (rank(r) == rank(cur)
                                   and (r["fetched_at"] or "") > (cur["fetched_at"] or "")):
            best[r["event_id"]] = r

    # canonical -> upstream, the reverse of the merge direction
    _s = importlib.util.spec_from_file_location("_ar", ROOT / "scripts" / "apply_resolutions.py")
    _ar = importlib.util.module_from_spec(_s)
    _s.loader.exec_module(_ar)

    class _S:
        path = a.db
    up_to_canon, _roots = _ar._seed_map(_S())
    canon_to_up: dict[str, str] = {}
    for up, canon in up_to_canon.items():
        canon_to_up.setdefault(canon, up)
    if not canon_to_up:
        print("REFUSING: no EVENT_ID map beside the database. The page matches on upstream "
              "ids; emitting canonical ones gives a file that matches nothing.")
        return 2

    out, unmapped = [], 0
    for eid, r in sorted(best.items()):
        up = canon_to_up.get(eid)
        if not up:
            unmapped += 1
            continue
        out.append({"EVENT_ID": up, "CHECK": r["verdict"],
                    "CHECK_URL": r["source_url"] or "",
                    "CHECK_QUOTE": (r["found_quote"] or r["quote"] or "")[:400],
                    "CHECK_DETAIL": (r["detail"] or "")[:300]})

    with open(a.output, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS))
        w.writeheader()
        w.writerows(out)

    from collections import Counter
    c = Counter(r["CHECK"] for r in out)
    need = c["contradicted"] + c["no_quote"] + c["unreadable"]
    print(f"{len(rows)} deadline claim(s) -> {len(best)} event(s) -> {len(out)} written")
    if unmapped:
        print(f"  {unmapped} event(s) had no upstream id and were skipped")
    print(f"\n  confirmed       {c['verified']}")
    print(f"  need to verify  {need}")
    print(f"     disputed         {c['contradicted']}")
    print(f"     not on page      {c['no_quote']}")
    print(f"     could not check  {c['unreadable']}")
    print(f"\nwrote {a.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
