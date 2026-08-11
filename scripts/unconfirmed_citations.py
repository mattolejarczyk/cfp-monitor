"""List the rows whose deadline we could NOT confirm against the page they cite.

THE ASK THIS SUPPORTS
Not "your date is wrong" - for most of these we have no opinion on the date. It is "the page
you cited does not carry this deadline, so nothing can confirm it, now or in future sweeps."

That distinction matters. 42% of DEADLINE_EVIDENCE_URL values are the row's own MAIN_INFO_URL
copied across - placeholders, not readings. A homepage can never confirm a deadline: we fetch
it, the sentence is not there, and a CORRECT date is labelled unverified forever.

WHY THIS GOES TO UPSTREAM RATHER THAN BEING FIXED HERE
Finding the page that states a deadline is discovery, which is upstream's side of the contract
(section 3). We could ground-search these ourselves, and it would work - but every row we
quietly repair is a row they never learn to cite properly, and the placeholder habit survives
into the next delivery. Handing back a bounded, specific list fixes the cause.

WHAT WE ARE NOT DOING
Not asserting the dates are wrong. Not asking them to re-research the event. The date can
stay exactly as it is; we want the URL that carries it and the sentence on it.

    python scripts/unconfirmed_citations.py --db cfp_monitor.db --out unconfirmed.csv
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# What we want back, per reason we could not confirm it.
ASK = {
    "no_quote": "Send the URL that states this deadline, and the sentence. "
                "The page you cited opened fine but never mentions it.",
    "unreadable": "We could not open the page you cited. Confirm it is right, "
                  "or send a page we can read.",
    "contradicted": "The page you cited states a different date. Defend it with a quote, "
                    "or correct it.",
}
WHY = {
    "no_quote": "cited page opened, deadline not on it",
    "unreadable": "cited page would not load for us",
    "contradicted": "cited page states a different date",
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Rows whose deadline we could not confirm.")
    ap.add_argument("--db", default="cfp_monitor.db")
    ap.add_argument("--seed-dir", default="market_sheets")
    ap.add_argument("--out", default="unconfirmed_citations.csv")
    a = ap.parse_args()

    market_of: dict[str, set] = {}
    upstream_id: dict[str, str] = {}
    for seed in sorted(Path(a.seed_dir).glob("*_seed.csv")):
        if seed.name == "grounding_seed.csv":
            continue
        with open(seed, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                c = (r.get("EVENT_ID_CANON") or "").strip()
                if not c:
                    continue
                if (r.get("Market") or "").strip():
                    market_of.setdefault(c, set()).add(r["Market"].strip())
                if (r.get("EVENT_ID") or "").strip():
                    upstream_id.setdefault(c, r["EVENT_ID"].strip())

    con = sqlite3.connect(a.db)
    con.row_factory = sqlite3.Row
    rows = list(con.execute("""
        select e.event_id, f.name, f.deadline, e.source_url, e.verdict, e.detail,
               e.exportable, f.main_info_url
        from evidence e join grounding_facts f on f.event_id = e.event_id
        where e.field='deadline' and e.origin='grounding'
          and coalesce(e.value_claimed,'') <> ''
          and e.verdict in ('no_quote','unreadable','contradicted')
        order by f.name"""))

    out, seen = [], set()
    for r in rows:
        if r["event_id"] in seen:
            continue
        seen.add(r["event_id"])
        cited = r["source_url"] or ""
        main = r["main_info_url"] or ""
        placeholder = bool(cited) and cited.rstrip("/").lower() == main.rstrip("/").lower()
        out.append({
            "CONFERENCE": r["name"],
            "EVENT_ID": upstream_id.get(r["event_id"], r["event_id"]),
            "MARKET": ", ".join(sorted(market_of.get(r["event_id"], {"?"}))),
            "DEADLINE YOU SENT": r["deadline"] or "",
            "URL YOU CITED": cited,
            "CITATION IS THE MAIN URL": "yes" if placeholder else "",
            "WHAT HAPPENED": WHY.get(r["verdict"], r["verdict"]),
            "DETAIL": (r["detail"] or "")[:120],
            "WHAT WE NEED": ASK.get(r["verdict"], ""),
            # The two that clear our outbound gate are ALSO raised as formal disputes in the
            # hand-back. Flagged so nobody answers the same row twice.
            "ALSO IN HANDBACK": "yes - Section B" if r["exportable"] else "",
        })

    if not out:
        print("Nothing unconfirmed. Has audit_evidence.py run?")
        return 0

    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    counts = Counter(r["WHAT HAPPENED"] for r in out)
    ph = sum(1 for r in out if r["CITATION IS THE MAIN URL"])
    print(f"{len(out)} row(s) we could not confirm\n")
    for k, n in counts.most_common():
        print(f"  {n:>3}  {k}")
    print(f"\n  {ph} of {len(out)} cite the row's own main URL - the placeholder pattern")
    print(f"\nwrote {a.out}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
