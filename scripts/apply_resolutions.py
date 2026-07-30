"""Apply the upstream defend-or-correct resolutions to the discovery layer.

    python scripts/apply_resolutions.py --db cfp_monitor.db [--apply]

Three resolution types, each landing differently:
  CORRECTED  upstream accepted our evidence -> take the corrected deadline, mark verified
             (our own crawl already read that date off the page, so it is evidence-backed).
  DEFENDED   upstream produced a verbatim quote + deep link -> keep THEIR value and store the
             evidence, so the next pass can confirm it automatically instead of re-arguing.
  UNCERTAIN  neither side can establish it -> blank the deadline, Not Announced. Better an
             admitted gap than a confident wrong date.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cfp_monitor.storage import Store          # noqa: E402

# name fragment -> (resolution, deadline, note/evidence)
RESOLUTIONS = [
    ("ASCO Annual Meeting 2027",      "CORRECTED", "1/26/2027", ""),
    ("AVS 72nd International",        "CORRECTED", "5/18/2026", "main abstract deadline"),
    ("AppSec Israel 2026",            "CORRECTED", "10/6/2026", ""),
    ("Area41 Security",               "CORRECTED", "3/1/2026",  "primary CFP close"),
    ("FIRST 38th Annual",             "CORRECTED", "10/24/2025", ""),
    ("Electron Devices Meeting",      "CORRECTED", "8/3/2026",  ""),
    ("NAB Show 2027",                 "CORRECTED", "12/1/2026", "main call for speakers close"),
    ("SEMICON Japan 2026",            "CORRECTED", "8/21/2026", "main tech session paper deadline"),
    ("MedTech Conference 2026",       "CORRECTED", "8/19/2026", ""),
    ("WFCC 2026",                     "CORRECTED", "7/8/2026",  ""),
    ("LOPEC 2027", "DEFENDED", "12/4/2026",
     "OE-A Competition & LOPEC Call for Papers submission deadline: December 4, 2026"
     "||https://oe-a.org/topics/oe-a-working-groups/oe-a-competition/||2026-07-30"),
    ("OWASP Global AppSec EU 2026",   "UNCERTAIN", "", "site-wide placeholder date"),
    ("OWASP Global AppSec Europe 2026", "UNCERTAIN", "", "site-wide placeholder date"),
    ("OWASP Global AppSec USA 2026",  "UNCERTAIN", "", "site-wide placeholder date"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply upstream dispute resolutions.")
    ap.add_argument("--db", default="cfp_monitor.db")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    store = Store(a.db)
    db = store.db
    db.row_factory = __import__("sqlite3").Row
    counts = {"CORRECTED": 0, "DEFENDED": 0, "UNCERTAIN": 0, "not matched": 0}

    for frag, kind, deadline, note in RESOLUTIONS:
        rows = [dict(r) for r in db.execute(
            "SELECT * FROM grounding_facts WHERE name LIKE ?", ("%" + frag + "%",))]
        rows = [r for r in rows if r["verify_state"] == "contradicted"] or rows
        if not rows:
            print("  NOT MATCHED: {!r}".format(frag))
            counts["not matched"] += 1
            continue
        for r in rows:
            old = r["deadline"] or "(none)"
            print("  {:<10} {:<42} {:>11} -> {:>11}".format(
                kind, (r["name"] or "")[:40], old, deadline or "(blank)"))
            if not a.apply:
                continue
            if kind == "CORRECTED":
                db.execute(
                    "UPDATE grounding_facts SET deadline=?, verify_state='verified',"
                    " verify_detail=? WHERE event_id=?",
                    (deadline,
                     "[upstream] corrected to match our page evidence"
                     + (f" ({note})" if note else ""), r["event_id"]))
            elif kind == "DEFENDED":
                quote, url, as_of = note.split("||")
                db.execute(
                    "UPDATE grounding_facts SET deadline=?, deadline_quote=?,"
                    " deadline_evidence_url=?, source_as_of=?, verify_state='verified',"
                    " verify_detail=? WHERE event_id=?",
                    (deadline, quote, url, as_of,
                     "[upstream] defended with a labelled quote + deep link; our checker had"
                     " missed the zero-padded date on the page", r["event_id"]))
            else:  # UNCERTAIN
                db.execute(
                    "UPDATE grounding_facts SET deadline='', cfp_model='Not Announced',"
                    " verify_state='not_found', verify_detail=? WHERE event_id=?",
                    ("[upstream] neither side could establish a deadline"
                     + (f" ({note})" if note else ""), r["event_id"]))
            counts[kind] += 1

    if a.apply:
        db.commit()
        print("\nAPPLIED:", {k: v for k, v in counts.items() if v})
        states = dict(db.execute(
            "SELECT verify_state, COUNT(*) FROM grounding_facts GROUP BY verify_state").fetchall())
        print("verification states now:", states)
    else:
        print("\nDry run. Re-run with --apply to write.")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
