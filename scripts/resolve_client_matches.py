"""Settle the matcher's middle band by evidence, and say plainly what evidence cannot settle.

    python scripts/resolve_client_matches.py --db <db> --client arnica [--apply]

THE PROBLEM
`match_customer_sheet.py` returns 100% only for its three CERTAIN tests. Everything else is a
weighted vote, and a vote is a suggestion (2.5). On 2026-08-31 that left 21 rows across two
clients sitting unmatched - too uncertain to join, too plausible to ignore.

Leaving them costs the customer twice: the row shows no verification, and it never enters the
weekly sweep. Guessing costs more - a wrong join puts another conference's deadline in front of
a client. So this settles only what the evidence settles.

THE RULE, AND WHY IT IS SAFE
Resolve when EXACTLY ONE row in that client's industry has both:

    the client's full conference name inside ours, ignoring edition years, and
    the same city

That is not a new test. It is the matcher's own certain test "name + city + date agreeing is
not a coincidence" with the date requirement dropped - and the date is precisely what was
silent on these rows, because a customer tracks the edition they care about while we have moved
to the next. Requiring EXACTLY ONE candidate is what keeps it safe: two plausible rows is
ambiguity, and ambiguity goes to a human.

WHAT IT REFUSES
Anything with zero candidates or more than one. Those two outcomes mean different things and are
reported separately:

    zero      the conference is not in our industry list at all - usually a REGIONAL edition we
              do not carry. On 2026-08-31 that was MENA, Asia-Pacific, Italy and Singapore
              editions of series where we hold only the North America and Europe ones. It is a
              gap in coverage, not a matching failure, and it becomes a promotion candidate.
    several   two of our rows are both plausible. Only the customer can say which they mean.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import clients          # noqa: E402

PROTECTED = ("conferences", "grounding_facts", "conference_markets", "evidence")
# Dropped before comparing names. An edition year is the thing that legitimately differs
# between what the customer tracks and what we have moved on to.
YEAR = re.compile(r"\b(19|20)\d{2}\b")


def norm_name(s: str) -> str:
    s = YEAR.sub(" ", (s or "").lower())
    s = re.sub(r"\(.*?\)", " ", s)                  # "(Black Hat Canada / SecTor)"
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def norm_city(s: str) -> str:
    """Their LOCATION is a venue string - 'Marina Bay Sands, Singapore'. Ours is a bare city.
    Compare on the words, so a venue prefix cannot prevent a match."""
    return {w for w in re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split() if len(w) > 3}


def main() -> int:
    ap = argparse.ArgumentParser(description="Resolve tentative client matches by evidence.")
    ap.add_argument("--db", required=True)
    ap.add_argument("--client", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    db = Path(a.db)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    industry = con.execute("select industry from clients where client_key = ?",
                           (a.client,)).fetchone()
    if not industry:
        print(f"ERROR: no client {a.client!r}")
        return 2
    industry = industry["industry"]

    ours = con.execute("""
        select g.event_id, g.name, g.city, g.country, g.deadline, g.status
        from grounding_facts g join conference_markets m on m.conference_key = g.conference_key
        where m.market = ?""", (industry,)).fetchall()

    pending = con.execute("""
        select their_name, location, match_confidence
        from client_conferences
        where client_key = ? and (event_id is null or trim(event_id) = '')
          and withdrawn_by_customer = 0 and coalesce(match_confidence,0) >= ?
        order by their_name""", (a.client, clients.NO_MATCH)).fetchall()

    resolved, none_found, ambiguous = [], [], []
    for p in pending:
        tn, tc = norm_name(p["their_name"]), norm_city(p["location"])
        cands = []
        for o in ours:
            on = norm_name(o["name"])
            if tn and tn in on and tc and tc & norm_city(f"{o['city']} {o['country']}"):
                cands.append(o)
        # Same EVENT_ID in two markets is ONE edition, not two candidates (section 10).
        uniq = {c["event_id"]: c for c in cands}
        if len(uniq) == 1:
            resolved.append((p, list(uniq.values())[0]))
        elif not uniq:
            none_found.append(p)
        else:
            ambiguous.append((p, list(uniq.values())))

    print(f"{a.client} ({industry}) - {len(pending)} row(s) in the matcher's middle band\n")
    print(f"  RESOLVED by name+city, exactly one candidate : {len(resolved)}")
    for p, o in resolved:
        print(f"      {p['their_name'][:42]:<44} -> {o['name'][:44]}")
        print(f"          {o['event_id']}")
    print(f"\n  NOT IN OUR INDUSTRY LIST (a coverage gap)    : {len(none_found)}")
    for p in none_found:
        print(f"      {p['their_name'][:42]:<44} {(p['location'] or '')[:38]}")
    print(f"\n  AMBIGUOUS - only the customer can say        : {len(ambiguous)}")
    for p, os_ in ambiguous:
        print(f"      {p['their_name'][:42]}")
        for o in os_:
            print(f"          could be: {o['name'][:50]}  ({o['city']})")

    if not a.apply:
        print("\nDRY RUN - nothing written. Re-run with --apply")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(db, db.with_name(f"{db.stem}.backup-pre-resolve-{stamp}.db"))
    before = {t: con.execute(f"select count(*) from [{t}]").fetchone()[0] for t in PROTECTED}
    for p, o in resolved:
        con.execute("""update client_conferences
                         set event_id = ?, match_method = 'resolve_client_matches: name+city,
                             exactly one candidate', matched_at = ?
                       where client_key = ? and their_name = ?""",
                    (o["event_id"], datetime.now().date().isoformat(), a.client,
                     p["their_name"]))
    con.commit()
    r = clients.refresh_candidates(con, a.client, industry)
    after = {t: con.execute(f"select count(*) from [{t}]").fetchone()[0] for t in PROTECTED}

    print(f"\n  joined            {len(resolved)}")
    print(f"  candidates raised {r['raised']}, pending {r['pending']}")
    drift = {t: (before[t], after[t]) for t in PROTECTED if before[t] != after[t]}
    print("  shared tables " + ("UNCHANGED" if not drift else f"MOVED: {drift}"))
    con.close()
    return 4 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
