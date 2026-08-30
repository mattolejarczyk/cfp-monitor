"""Apply `match_customer_sheet.py` output to the client layer, then raise promotion candidates.

    python scripts/apply_client_match.py --db <db> --client arnica \
        --matches <match_out.csv> --industry Cybersecurity [--dry-run]

Only CERTAIN matches (100%) set an `event_id`. The matcher's three certain tests - exact URL, a
domain resolving to exactly one row in the whole database, and name+city+date agreeing - are
each definitive alone. Everything below that is a weighted vote, and a vote is a suggestion:
contract 2.5 is decline rather than guess.

Three outcomes, deliberately kept apart:

    100        joined to the industry list
    40 to 99   recorded and sent to a human. NOT joined, and NOT proposed for promotion.
    under 40   the matcher found nothing - these become promotion candidates

The middle band is the one that matters. Treated as matched it invents a join; treated as
absent it asks Nicolia's team to add a conference we already hold.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import clients          # noqa: E402

PROTECTED = ("conferences", "grounding_facts", "conference_markets", "evidence")


def read_matches(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        conf = (r.get("Index_Confidence") or "").strip().rstrip("%")
        try:
            conf = float(conf) if conf else 0.0
        except ValueError:
            conf = 0.0
        out.append({"their_name": (r.get("CONFERENCE") or "").strip(),
                    "event_id": (r.get("EVENT_ID") or "").strip(),
                    "confidence": conf,
                    "justification": (r.get("Index_Justification") or "").strip()})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply matcher output to the client layer.")
    ap.add_argument("--db", required=True)
    ap.add_argument("--client", required=True)
    ap.add_argument("--matches", required=True, help="output of match_customer_sheet.py")
    ap.add_argument("--industry", required=True)
    ap.add_argument("--subindustry", default="")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    db, src = Path(a.db), Path(a.matches)
    for p in (db, src):
        if not p.exists():
            print(f"ERROR: no such file: {p}")
            return 2

    matches = read_matches(src)
    certain = [m for m in matches if m["confidence"] >= clients.CERTAIN and m["event_id"]]
    review = [m for m in matches
              if clients.NO_MATCH <= m["confidence"] < clients.CERTAIN or
              (m["confidence"] >= clients.CERTAIN and not m["event_id"])]
    absent = [m for m in matches if m["confidence"] < clients.NO_MATCH]

    print(f"{a.client}  -  {len(matches)} row(s) from the matcher")
    print(f"  certain (100%)        {len(certain)}  -> event_id applied")
    print(f"  needs review (40-99)  {len(review)}  -> left unmatched, for a person")
    print(f"  no match (<40)        {len(absent)}  -> promotion candidates")

    if a.dry_run:
        print("\nDRY RUN - nothing written")
        for m in review[:10]:
            print(f"    review  {m['confidence']:>5.0f}%  {m['their_name'][:52]}")
        for m in absent[:14]:
            print(f"    absent  {m['confidence']:>5.0f}%  {m['their_name'][:52]}")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = db.with_name(f"{db.stem}.backup-pre-clientmatch-{stamp}.db")
    shutil.copy2(db, backup)

    con = sqlite3.connect(db)
    before = {t: con.execute(f"select count(*) from [{t}]").fetchone()[0] for t in PROTECTED}
    clients.ensure_schema(con)
    r = clients.apply_matches(con, a.client, matches)
    c = clients.refresh_candidates(con, a.client, a.industry, a.subindustry)
    after = {t: con.execute(f"select count(*) from [{t}]").fetchone()[0] for t in PROTECTED}

    print(f"\n  applied      {r['applied']}")
    print(f"  needs review {r['needs_review']}")
    print(f"  no match     {r['no_match']}")
    print(f"  candidates raised {c['raised']}, pending {c['pending']}"
          "  (undecided - nothing joins an industry list on its own)")

    drift = {t: (before[t], after[t]) for t in PROTECTED if before[t] != after[t]}
    if drift:
        print(f"\n  *** SHARED TABLES MOVED: {drift} - restore {backup.name}")
        con.close()
        return 4
    print(f"  shared tables unchanged: " + ", ".join(f"{t}={after[t]}" for t in PROTECTED))
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
