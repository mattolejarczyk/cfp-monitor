"""Put every conference back on its market's list, from the sources that decided it.

    python scripts/rebuild_market_membership.py --db DB [--delivery CSV ...] [--apply]

THE DRIFT, AND WHY IT IS INVISIBLE
`conference_markets` answers "which market does this belong to", and it identifies a conference
by its WEBSITE ADDRESS (`conference_key`), not by our canonical id. A website address is not a
stable thing: an event moves host, or we record it under a deeper path, and the membership row
still points at the old address. The conference stays in the database and silently falls off
every market's list.

Measured 2026-09-15: **115 of 401 conferences were on no market list at all**, including all
thirteen SecureWorld events, and ~98 membership rows pointed at addresses no conference uses
any more.

Nothing reports it, because nothing is missing. But a great deal of our tooling asks "show me
the Cybersecurity conferences", and that question is answered from this list rather than from
the conferences themselves - so a row that has drifted off is invisible to those tools while
sitting in plain sight in the database. `resolve_client_matches.py` reported events we plainly
hold as "not in our industry list" for exactly this reason, and the customer's rows went
unmatched as a result.

WHERE THE ANSWER COMES FROM, in order of authority

    1. THE CUSTOMER'S OWN SHEET. It is how these conferences were identified in the first
       place: the Utility sheet defines the Utility market and the Arnica sheet defines
       Cybersecurity. If a conference is on their sheet, it belongs to that market, and no
       derivation of ours outranks that.
    2. The delivery's `Market` column - upstream's own statement of what it researched under
       which market. This covers all eight markets, including the six with no customer.

ADDITIVE, LIKE THE TABLE IT WRITES TO
`Store._add_market` is additive by design: an event on several market lists keeps every one,
and a failed crawl never strips a membership. This honours that. It ADDS what the sources
assert and never removes a membership, so a market list that is merely absent today cannot
delete history. Entries pointing at addresses no conference uses are REPORTED, not deleted -
they cost nothing, and deleting on the strength of today's data is how the 2026-08-08 silent
deletion happened.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor.identity import seed_map, to_canonical           # noqa: E402

MARKETS_DIR = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
DEFAULTS = ["ALL_MARKETS_REFRESHED_20260812.csv",
            "Cybersecurity_audited.final.csv", "Utility_audited.final.csv"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--delivery", nargs="*")
    ap.add_argument("--apply", action="store_true", help="write (default: report only)")
    a = ap.parse_args()

    con = sqlite3.connect(a.db)
    con.row_factory = sqlite3.Row
    key_of = {r["event_id"]: r["conference_key"] for r in
              con.execute("SELECT event_id, conference_key FROM grounding_facts")}
    name_of = {r["event_id"]: r["name"] for r in
               con.execute("SELECT event_id, name FROM grounding_facts")}
    existing = {(r["conference_key"], r["market"]) for r in
                con.execute("SELECT conference_key, market FROM conference_markets")}
    live_keys = set(key_of.values())

    # 1. THE CUSTOMER'S SHEET - the highest authority, because it is how these conferences were
    #    identified in the first place.
    asserted: dict[tuple[str, str], str] = {}
    for r in con.execute("""select cc.event_id, cl.industry from client_conferences cc
                            join clients cl on cl.client_key = cc.client_key
                            where coalesce(cc.event_id,'') <> ''"""):
        k = key_of.get(r["event_id"])
        if k and (r["industry"] or "").strip():
            asserted[(k, r["industry"].strip())] = "customer sheet"
    from_sheet = len(asserted)

    # 2. The delivery's own Market column, covering the six markets with no customer.
    up2c, _ = seed_map(a.db)
    files = [Path(p) for p in (a.delivery or [str(MARKETS_DIR / f) for f in DEFAULTS])]
    for f in files:
        if not f.exists():
            print(f"  (skipped, not found) {f.name}")
            continue
        n = 0
        with open(f, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                mk = (row.get("Market") or row.get("MARKET") or "").strip()
                eid = to_canonical((row.get("EVENT_ID") or "").strip(), up2c)
                k = key_of.get(eid)
                if mk and k:
                    asserted.setdefault((k, mk), f.name)
                    n += 1
        print(f"  {f.name}: {n} market assertion(s)")

    add = {km: src for km, src in asserted.items() if km not in existing}
    stale = [(k, m) for (k, m) in existing if k not in live_keys]

    con2 = sqlite3.connect(a.db)
    before = con2.execute("""select count(*) from grounding_facts g where not exists
        (select 1 from conference_markets cm where cm.conference_key = g.conference_key)""").fetchone()[0]
    after_keys = {k for k, _ in existing | set(add)}
    after = sum(1 for e, k in key_of.items() if k not in after_keys)

    print(f"\n{len(key_of)} conference(s); {len(existing)} membership row(s) today")
    print(f"  the customer's sheets assert     : {from_sheet}")
    print(f"  all sources assert               : {len(asserted)}")
    print(f"  NEW memberships to add           : {len(add)}")
    print(f"  on NO market list before         : {before}")
    print(f"  on no market list after          : {after}")
    print(f"  entries pointing at an address no conference uses: {len(stale)} (reported, never deleted)")

    if add:
        print("\n  a sample of what gets its market back:")
        seen = set()
        for (k, m), src in list(add.items()):
            eid = next((e for e, kk in key_of.items() if kk == k), None)
            if eid and eid not in seen and len(seen) < 10:
                seen.add(eid)
                print(f"     {name_of.get(eid, eid)[:48]:50} -> {m:20} ({src})")

    if not a.apply:
        print("\nREPORT ONLY - re-run with --apply to write.")
        return 0

    today = date.today().isoformat()
    for (k, m), src in add.items():
        con.execute("INSERT OR IGNORE INTO conference_markets"
                    " (conference_key, market, source_list, first_seen) VALUES (?,?,?,?)",
                    (k, m, f"rebuild: {src}", today))
    con.commit()
    left = con.execute("""select count(*) from grounding_facts g where not exists
        (select 1 from conference_markets cm where cm.conference_key = g.conference_key)""").fetchone()[0]
    con.close()
    print(f"\nadded {len(add)} membership(s); {left} conference(s) still on no market list")
    print("A mutation needs a reconciliation - run scripts/check_invariants.py next.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
