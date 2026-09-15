"""Find records that are one event held twice, and say WHY the key split.

    python scripts/find_duplicate_events.py --db DB [--kind conference|awards|both] [--csv OUT]

WHY THIS EXISTS
`event_id()` builds the canonical key from three inputs - `<year>-<name>-<city>[-<opportunity>]`
- and a key is minted once, at import. So when any one of those three changes between cycles,
the next import cannot find the row it should update and INSERTS a second one instead. Both
copies then live in the database: one carrying August's evidence, one carrying September's.

That is not a hypothetical. `fix_edition.py` was written for exactly this failure on the year
component and froze `key_year` so no canonical key could move again - but it could not undo the
rows already split, and it does not cover the other two components at all.

WHAT IT DOES NOT DO
It does not merge and it does not delete. Contract 2.1: discovery is innocent until proven
guilty, and a row with no counterpart and no declared reason is KEPT and declared. The upstream
sibling `label_seed_duplicates.py` settled the same question the same way - it labels, and both
members stay. Deciding which of two evidenced rows survives is a judgement about evidence, and
this is a report that lets a person make it.

THE FIVE CLASSES, and why they are not one problem

    SAME_TODAY  the strongest signal, and the easiest to misread. Recomputed from the rows'
              CURRENT fields, both mint the same key: same name, same city, same edition. They
              differ only in the key each was minted with. That is `fix_edition.py` working as
              designed - it froze `key_year` so a key could never move again, which is right
              ("a key is a name, not a fact") - but it leaves the pair provably one event.

    YEAR      the editions genuinely differ, name and place identical. May be two real
              editions of a series rather than a split record. Read the dates before merging.

    PLACE     the city changed, usually to or from `tbd` when upstream stopped supplying it,
              or to a suburb (St. Louis -> Clayton, the clean_city hazard in the runbook).
              Almost always one event.

    NON_OPPORTUNITY  the suffix is a label for ATTENDING, not for anything the customer can
              submit to. One event, split by a label that should never have made a key.
              Decided 2026-09-14 - see NOT_AN_OPPORTUNITY below.

    OPPORTUNITY  one key carries a suffix naming a REAL second thing to act on
              (`-exhibiting`). event_id() includes OPPORTUNITY deliberately, because one event
              can run several calls with different deadlines and collapsing them loses one.
              Surfaced for a person; never merged on assumption.

    MIXED     more than one component moved, or the group holds more than two rows. Read it.

CONFLICT is reported separately from class, because it is the one that can reach a customer:
both rows carry a deadline and the deadlines disagree. Whichever row a join happens to pick,
somebody is being told the wrong date.
"""
from __future__ import annotations

import argparse
import collections
import csv
import importlib.util
import itertools
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor.grounding import slug                          # noqa: E402

TABLES = {"conference": "grounding_facts", "awards": "award_grounding_facts"}

# OPPORTUNITY earns a place in the key when it names a SECOND THING THE CUSTOMER CAN ACT ON -
# a call for speakers and an awards entry are two submissions with two deadlines, and one key
# would lose one of them. Attending is not that. Buying a ticket is not a submission, it has no
# deadline to beat, and Nicolia's product is speaking placement.
#
# The data said so before the rule did: of the seven suffix-split pairs found on 2026-09-14,
# NOT ONE had a deadline on either row - and distinguishing two deadlines is the entire
# justification for the suffix. Three were pure noise (SANS: both rows empty and contradicted).
#
# Decided by the operator 2026-09-14: speaking is the primary opportunity; registration is not
# an opportunity at all. EXHIBITING STAYS A REAL ONE - a stand is a commercial opportunity the
# pipeline already tracks through sponsorship, it is what a customer looks at when speaking is
# unavailable, and a company sending a speaker often exhibits too.
NOT_AN_OPPORTUNITY = frozenset({"registration", "register", "attending", "attendance", "tickets"})
OUT_COLUMNS = ["KIND", "CLASS", "CONFLICT", "GROUP", "EVENT_ID", "NAME", "CITY", "EDITION",
               "DEADLINE", "VERIFY_STATE", "SOURCE_AS_OF", "NEWER"]


def parts(row: sqlite3.Row) -> tuple[str, str, str, str]:
    """The three key components as event_id() would compute them now, plus any suffix.

    Recomputed from the row's own fields rather than parsed back out of the stored key: a
    name-slug contains hyphens, so the key cannot be split on them without guessing.
    """
    year = (row["edition"] or "").strip()[:4]
    year = year if year.isdigit() else "tbd"
    name = slug(row["name"], strip_years=True)
    place = slug(row["city"] or "", 28) or "tbd"
    base = f"{year}-{name}-{place}".strip("-")
    stored = row["event_id"] or ""
    suffix = stored[len(base) + 1:] if stored.startswith(base + "-") else ""
    return year, name, place, suffix


def classify(rows: list[sqlite3.Row]) -> str:
    """Which component moved. Named for the CAUSE, because the causes want different fixes."""
    if len(rows) > 2:
        return "MIXED"
    (y1, _n1, p1, s1), (y2, _n2, p2, s2) = (parts(r) for r in rows)
    moved = [lbl for lbl, a, b in
             (("YEAR", y1, y2), ("PLACE", p1, p2), ("OPPORTUNITY", s1, s2)) if a != b]
    if moved == ["OPPORTUNITY"] and {s1, s2} <= NOT_AN_OPPORTUNITY | {""}:
        # The only thing separating these two rows is a label for attending. That is one event.
        return "NON_OPPORTUNITY"
    if len(moved) == 1:
        return moved[0]
    # Nothing moved, yet the stored keys differ: the pair agrees on every field event_id()
    # reads, so only the moment of minting separates them.
    return "MIXED" if moved else "SAME_TODAY"


def conflicting(rows: list[sqlite3.Row]) -> bool:
    """Both sides claim a deadline and they disagree - the case that can reach a customer."""
    seen = {(r["deadline"] or "").strip() for r in rows if (r["deadline"] or "").strip()}
    return len(seen) > 1


def groups(con: sqlite3.Connection, table: str) -> dict[str, list[sqlite3.Row]]:
    """Group on the name slug alone - the one key component that has never been observed to
    drift, and so the only safe thing to group by when the others are what moved."""
    by: dict[str, list[sqlite3.Row]] = collections.defaultdict(list)
    for r in con.execute(f"SELECT * FROM {table}"):                  # noqa: S608 - fixed set
        by[slug(r["name"], strip_years=True)].append(r)
    return {k: v for k, v in by.items() if len(v) > 1}


# The matcher's own threshold for "these names describe the same event", reused rather than
# invented so one number governs both. `sim` is imported, never reimplemented.
NAME_FLOOR = 0.7
SAME_DAYS = 1


def _sim():
    spec = importlib.util.spec_from_file_location(
        "mcs", Path(__file__).resolve().parent / "match_customer_sheet.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.sim


def city_date_pairs(con: sqlite3.Connection, table: str,
                    seen_together: set[frozenset]) -> list[tuple[sqlite3.Row, sqlite3.Row]]:
    """Two rows for one event always share its city and its dates, whatever they call it.

    THE CLASS THE NAME DETECTOR CANNOT SEE. Grouping by name slug misses every duplicate whose
    two names differ in wording rather than in edition or place - `&` against `and`, Summit
    against Expo, an ordinal prefix, a "Virtual" qualifier. Measured 2026-09-15, this finds
    seven such pairs the slug grouping had never grouped, among them
    "IEEE Symposium on Security & Privacy" beside "IEEE Symposium on Security and Privacy".

    A NAME SIGNAL IS STILL REQUIRED, and this is the whole reason city+date is a duplicate test
    and not a matching rule. 50 pairs in our own data share a city and start within a day, and
    the collisions are structural: satellite events inside big shows (AppSec Village at DEF CON,
    four IFA events in Berlin on one morning), industry weeks (three healthcare conferences in
    San Francisco on 2027-01-11), and co-located sister expos from one organiser. Requiring the
    names to agree at the matcher's own floor drops those and keeps the real duplicates.

    Pairs the name grouping already reported are skipped - one finding, once.
    """
    sim = _sim()
    cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}  # noqa: S608
    if "start_date" not in cols:
        return []                                    # awards carry no event date to compare
    rows = [r for r in con.execute(                                   # noqa: S608
        f"SELECT * FROM {table} WHERE COALESCE(start_date,'') <> '' AND COALESCE(city,'') <> ''")]
    by_city: dict[str, list[sqlite3.Row]] = collections.defaultdict(list)
    for r in rows:
        by_city[(r["city"] or "").strip().lower()].append(r)

    out = []
    for group in by_city.values():
        for a, b in itertools.combinations(group, 2):
            if frozenset((a["event_id"], b["event_id"])) in seen_together:
                continue
            try:
                delta = abs((date.fromisoformat(a["start_date"])
                             - date.fromisoformat(b["start_date"])).days)
            except ValueError:
                continue
            if delta <= SAME_DAYS and sim(a["name"], b["name"]) >= NAME_FLOOR:
                out.append((a, b))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--kind", choices=[*TABLES, "both"], default="both")
    ap.add_argument("--csv", help="also write the findings as a CSV")
    a = ap.parse_args()

    con = sqlite3.connect(a.db)
    con.row_factory = sqlite3.Row
    kinds = list(TABLES) if a.kind == "both" else [a.kind]

    out: list[dict] = []
    tally: collections.Counter = collections.Counter()
    conflicts = 0
    for kind in kinds:
        found = groups(con, TABLES[kind])
        print(f"\n{'=' * 78}\n{kind.upper()}: {len(found)} group(s), "
              f"{sum(len(v) for v in found.values())} row(s)\n{'=' * 78}")
        for gkey, rows in sorted(found.items()):
            cls = classify(rows)
            clash = conflicting(rows)
            tally[f"{kind}/{cls}"] += 1
            conflicts += clash
            newest = max((r["source_as_of"] or "") for r in rows)
            flag = "  <<< DEADLINES DISAGREE" if clash else ""
            print(f"\n  [{cls}]{flag}")
            for r in sorted(rows, key=lambda r: (r["source_as_of"] or "")):
                newer = (r["source_as_of"] or "") == newest
                print(f"    {'newer' if newer else 'older'}  {r['event_id']}")
                print(f"           {r['name'][:56]:58} city={r['city'] or '-':12}"
                      f" ed={r['edition'] or '-':5} dl={r['deadline'] or '-':11}"
                      f" {r['verify_state']:12} seen={r['source_as_of'] or '-'}")
                out.append({"KIND": kind, "CLASS": cls, "CONFLICT": "yes" if clash else "",
                            "GROUP": gkey, "EVENT_ID": r["event_id"], "NAME": r["name"],
                            "CITY": r["city"], "EDITION": r["edition"],
                            "DEADLINE": r["deadline"], "VERIFY_STATE": r["verify_state"],
                            "SOURCE_AS_OF": r["source_as_of"],
                            "NEWER": "yes" if newer else ""})

    # THE SECOND DETECTOR. Everything above groups by name; this finds the pairs whose names
    # never grouped, by the two facts two rows for one event always share.
    seen_together = set()
    for kind2 in kinds:
        for _g, rs in groups(con, TABLES[kind2]).items():
            for x in rs:
                for y in rs:
                    if x["event_id"] != y["event_id"]:
                        seen_together.add(frozenset((x["event_id"], y["event_id"])))
    for kind2 in kinds:
        pairs = city_date_pairs(con, TABLES[kind2], seen_together)
        if not pairs:
            continue
        print(f"\n{'=' * 78}\n{kind2.upper()}: {len(pairs)} pair(s) sharing a city and dates, "
              f"which the name grouping cannot see\n{'=' * 78}")
        for a, b in pairs:
            tally[f"{kind2}/SAME_CITY_DATE"] += 1
            clash2 = conflicting([a, b])
            conflicts += clash2
            flag = "  <<< DEADLINES DISAGREE" if clash2 else ""
            print(f"\n  [SAME_CITY_DATE]{flag}   {a['city']}, {a['start_date']}")
            for r in (a, b):
                print(f"    {r['event_id']}")
                print(f"           {r['name'][:58]:60} dl={r['deadline'] or '-':11}"
                      f" {r['verify_state']}")
                out.append({"KIND": kind2, "CLASS": "SAME_CITY_DATE",
                            "CONFLICT": "yes" if clash2 else "",
                            "GROUP": f"{a['city']}|{a['start_date']}",
                            "EVENT_ID": r["event_id"], "NAME": r["name"], "CITY": r["city"],
                            "EDITION": r["edition"], "DEADLINE": r["deadline"],
                            "VERIFY_STATE": r["verify_state"],
                            "SOURCE_AS_OF": r["source_as_of"], "NEWER": ""})
    con.close()

    print(f"\n{'=' * 78}\nBY CAUSE\n{'=' * 78}")
    for k, n in sorted(tally.items()):
        print(f"  {k:34}{n:>4}")
    print(f"\n  groups whose two rows claim DIFFERENT deadlines: {conflicts}")
    print("\nNothing was changed. 2.1 - a row is kept and declared, never deleted on suspicion;")
    print("choosing between two evidenced rows is a judgement about evidence, not a script.")

    if a.csv:
        with open(a.csv, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=OUT_COLUMNS, quoting=csv.QUOTE_ALL)
            w.writeheader()
            w.writerows(out)
        print(f"\nwrote {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
