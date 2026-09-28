"""Give every row of the research INPUT list the permanent id of the event it asks about.

    python scripts/stamp_input_ids.py [--markets Cybersecurity Utility] [--db <live db>] [--apply]

WHY (2026-09-27). The research input (Markets\\<Market>_input.csv) carried no id. The research
minted a fresh EVENT_ID from whatever name it wrote back, and import derived our canonical id
from that name too - so every rename made a second record for one event. One weekend's research
would have created 24 duplicates; check_invariants caught it and the load rolled back.

The fix is to pass identity THROUGH the research rather than rebuild it afterwards: this stamps
an EVENT_ID_CANON column on the input, run_market_audit writes a <output>.identity.csv linking
each output row to the input row it answers, and weekend_import.py loads each row onto that id.

HOW AN ID IS CHOSEN - exact names only, never a guess (the matcher rule: only 100% sets an id)
  0. an id already stamped and still in the database is KEPT. Identity is frozen.
  1. last week's approved file (<Market>_audited.final.csv), same name exactly
  2. the seed sheets, same CONFERENCE exactly
  3. the database, same name exactly
The first source that names a candidate decides. Several candidates are narrowed by the year
in the row's own name ("... 2027" -> a 2027- id). Still several, or none: left BLANK and
reported. A blank-id row is never loaded as a new event; weekend_import holds it back and last
week's version stays on the page.

Reports by default. --apply writes the column in place, after a timestamped backup.
"""
from __future__ import annotations

import argparse
import csv
import glob
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.cfp_monitor.identity import (assert_mapped, seed_map, seed_names,     # noqa: E402
                                      to_canonical)

import os                                                                    # noqa: E402
MARKETS_DIR = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
LIVE_DB = Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor" / "cfp_monitor.db"
COL = "EVENT_ID_CANON"


def norm(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def by_year(name: str, cands: set[str]) -> set[str]:
    """Break a tie using the one year the row's own name states. A tie-breaker ONLY.

    A canonical id keeps the year it was MINTED with (key_year is frozen), so a 2027 edition
    can correctly live under a 2026- id; a lone candidate is never rejected for its year. The
    stale-twin case ('India Energy Week 2027' -> an old 2026 record) is stopped by the
    last-week's-page rule in resolve(), not here."""
    years = set(re.findall(r"\b(20\d\d)\b", name or ""))
    if len(cands) > 1 and len(years) == 1:
        y = years.pop()
        hit = {c for c in cands if c.startswith(y + "-")}
        if hit:
            return hit
    return cands


def resolve(name: str, current: str, known: set[str], sources: list[dict[str, set[str]]],
            published: set[str] | None = None) -> tuple[str, str]:
    """(id, how). id is "" when it cannot be decided exactly.

    `published` is last week's approved file, as canonical ids. An id found through the seed
    sheets or the database must ALSO be on it: those sources remember superseded duplicates
    (Hack In The Box has two records, and the old seed name points at the stale one), and
    loading onto a stale twin would show one event twice on the customer's page. Without a
    published file (a first run) any known id is allowed.
    """
    if current and current in known:
        return current, "kept"
    k = norm(name)
    for i, (label, src) in enumerate(zip(("last week's file", "seed sheets", "database"), sources)):
        allowed = known if (i == 0 or not published) else (known & published)
        cands = by_year(name, {c for c in src.get(k, set()) if c in allowed})
        if not cands:
            continue
        if len(cands) == 1:
            return next(iter(cands)), label
        return "", f"ambiguous in {label}: {', '.join(sorted(cands))}"
    return "", "no exact match to an event on last week's page"


def published_awards(markets_dir: Path) -> Path | None:
    """The awards file the customer page was last built from: the promoted final if there is
    one, else the newest dated research output (how Monday picked it before 2026-09-28)."""
    final = markets_dir / "Awards_audited.final.csv"
    if final.exists():
        return final
    dated = sorted(markets_dir.glob("Awards_2*_out.csv"))
    return dated[-1] if dated else None


def build_award_sources(markets_dir: Path, db: Path) -> tuple[set[str], list[dict]]:
    """Awards live in award_grounding_facts, which keeps upstream's id beside ours
    (upstream_event_id), so that column - not the conference seed sheets - is the crossing."""
    con = sqlite3.connect(str(db))
    try:
        rows = list(con.execute("select event_id, upstream_event_id, name from award_grounding_facts"))
    finally:
        con.close()
    known = {r[0] for r in rows}
    up = {(r[1] or "").strip(): r[0] for r in rows if r[1]}
    final, dbn = {}, {}
    pub = published_awards(markets_dir)
    if pub:
        with open(pub, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                c = up.get((r.get("EVENT_ID") or "").strip())
                if c:
                    final.setdefault(norm(r.get("CONFERENCE", "")), set()).add(c)
    for eid, _up, name in rows:
        dbn.setdefault(norm(name), set()).add(eid)
    return known, [final, {}, dbn]


def build_sources(market: str, markets_dir: Path, db: Path) -> tuple[set[str], list[dict]]:
    if market == "Awards":
        return build_award_sources(markets_dir, db)
    up_to_canon, roots = seed_map(str(db))
    assert_mapped(up_to_canon, roots, minimum=50)
    con = sqlite3.connect(str(db))
    try:
        rows = list(con.execute("select event_id, name from grounding_facts"))
    finally:
        con.close()
    known = {r[0] for r in rows}
    final, seeds, dbn = {}, {}, {}
    fp = markets_dir / f"{market}_audited.final.csv"
    if fp.exists():
        with open(fp, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                final.setdefault(norm(r["CONFERENCE"]), set()).add(to_canonical(r["EVENT_ID"], up_to_canon))
    seeds = seed_names(str(db))
    for eid, name in rows:
        dbn.setdefault(norm(name), set()).add(eid)
    return known, [final, seeds, dbn]


def main() -> int:
    ap = argparse.ArgumentParser(description="Stamp permanent event ids on the research input list.")
    ap.add_argument("--markets", nargs="+", default=["Cybersecurity", "Utility"])
    ap.add_argument("--markets-dir", default=str(MARKETS_DIR))
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    md, db = Path(a.markets_dir), Path(a.db)
    unresolved_total = 0
    for m in a.markets:
        path = md / f"{m}_input.csv"
        if not path.exists():
            print(f"{m}: no input file - skipped")
            continue
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rd = csv.DictReader(fh)
            cols, rows = list(rd.fieldnames or []), list(rd)
        known, sources = build_sources(m, md, db)
        published = set().union(*sources[0].values()) if sources[0] else None
        counts: dict[str, int] = {}
        unresolved = []
        for r in rows:
            cid, how = resolve(r.get("CONFERENCE", ""), (r.get(COL) or "").strip(), known,
                               sources, published)
            r[COL] = cid
            key = how if cid else "UNRESOLVED"
            counts[key] = counts.get(key, 0) + 1
            if not cid:
                unresolved.append(f"{r.get('CONFERENCE', '')} - {how}")
        unresolved_total += len(unresolved)
        print(f"{m}: {len(rows)} rows | " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        for u in unresolved:
            print(f"   no id (held back until linked): {u}")
        if a.apply:
            if COL not in cols:
                cols.append(COL)
            shutil.copy2(path, path.with_name(f"{path.stem}.pre-ids-{datetime.now():%Y%m%d-%H%M%S}.csv"))
            with open(path, "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL)
                w.writeheader()
                w.writerows(rows)
            print(f"   wrote {COL} into {path.name}")
    if not a.apply:
        print("\nReport only - add --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
