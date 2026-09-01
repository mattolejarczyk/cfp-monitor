"""One place that knows an upstream EVENT_ID is not ours, and translates between them.

THE CLASS OF ERROR THIS EXISTS TO REMOVE
Two id namespaces run through this system and look identical - both are lowercase slugs like
`2027-ces-las-vegas`. Nothing about a string says which space it belongs to, so a join across
the boundary compiles, runs, and returns a confident empty answer. It has now cost:

  2026-08-29  a delivery edit keyed on EVENT_ID reported success and corrected 0 of 406 rows
  2026-09-01  a client-sheet join scored 43 of 111, was written up as a measured finding that
              the matcher's own key was the WORST of three options, and recommended replacing
              it. The correct join - through the seed map - scores 87 of 87.
  JUDGEMENT rule 17 exists for it, and was still repeated twice on the day it was written.

Documenting it has not worked. `docs/operations/customer-sheet-matching.md` has said "the
delivery's EVENT_ID column is UPSTREAM's, not ours - never copy that column straight across"
since 2026-08-13, and the error above happened anyway, by someone who had the file open.

So the translation lives in ONE function with ONE name, in `src` where the rules layer lives
rather than inside a script, and `tests/test_identity_join.py` fails the build when a script
compares ids without it.

    upstream EVENT_ID   what a delivery CSV carries. Upstream's key, echoed back to us.
    canonical id        what WE compute on import (grounding.event_id, contract 5.4).
                        What the database, the client matcher and every internal join use.

    to_canonical(delivery_row_id, seed_map)   the only sanctioned crossing.
"""
from __future__ import annotations

import csv
from pathlib import Path


def seed_roots(db_path: str) -> list[Path]:
    """Where the seed files live: beside the DATABASE first, then the working directory.

    The order matters and is not cosmetic. Seeds live in the live build's data root while these
    scripts are usually run from the repo. A bare relative path found nothing there, the map
    came back empty, every row failed to resolve, and the run reported five per-row DATA
    rejections for what was purely a path problem.

    **A config fault must not be able to impersonate a data fault.**
    """
    roots: list[Path] = []
    seen: set[Path] = set()
    for cand in (Path(db_path or ".").resolve().parent, Path.cwd()):
        d = cand / "market_sheets"
        if d.is_dir() and d not in seen:
            seen.add(d)
            roots.append(d)
    return roots


def seed_map(db_path: str) -> tuple[dict[str, str], list[Path]]:
    """upstream EVENT_ID -> our canonical id, and the directories it was read from.

    The roots come back so a caller can say WHERE it looked when the map is empty. An empty map
    is nearly always a path problem, and reporting it as a data problem is the failure above.
    """
    roots = seed_roots(db_path)
    up_to_canon: dict[str, str] = {}
    for root in roots:
        for seed in sorted(root.glob("*_seed.csv")):
            if seed.name == "grounding_seed.csv":
                continue
            with open(seed, encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    up = (row.get("EVENT_ID") or "").strip()
                    canon = (row.get("EVENT_ID_CANON") or "").strip()
                    if up and canon:
                        up_to_canon.setdefault(up, canon)
    return up_to_canon, roots


def to_canonical(event_id: str, up_to_canon: dict[str, str]) -> str:
    """Translate one delivery id into ours. Unknown ids pass through unchanged.

    PASSING THROUGH IS DELIBERATE, and it is the one judgement call in this module. A delivery
    can legitimately carry a row the seed map has not seen - a conference added since the last
    import - and dropping those would silently shrink every join that uses this. So an unmapped
    id is returned as-is and matches only something that already shares its spelling.

    The cost of that choice is that a WHOLLY empty map degrades to the old broken behaviour
    rather than failing loudly. `assert_mapped` is how a caller refuses that.
    """
    e = (event_id or "").strip()
    return up_to_canon.get(e, e)


def assert_mapped(up_to_canon: dict[str, str], roots, minimum: int = 1) -> None:
    """Refuse to run on an empty or implausible seed map.

    Call this before any join that matters. Without it a path problem produces a map of zero
    entries, every row falls through `to_canonical` unchanged, and the join returns nothing -
    which reads exactly like a customer who tracks nothing, or a delivery with no matches.
    """
    if len(up_to_canon) < minimum:
        where = ", ".join(str(r) for r in roots) or "(no market_sheets directory found)"
        raise SystemExit(
            f"ERROR: the EVENT_ID seed map has {len(up_to_canon)} entries, expected at least "
            f"{minimum}. Looked in: {where}\n"
            f"This is a PATH problem, not a data problem - every join through it would return "
            f"nothing and look like an empty result.")


def index_by_canonical(rows, up_to_canon: dict[str, str], id_col: str = "EVENT_ID") -> dict:
    """Delivery rows keyed by OUR canonical id, ready to join against the database or a client.

    First row wins. A delivery legitimately repeats one EVENT_ID across markets (contract 10 -
    one event, several market rows), and those copies carry the same evidence, so collapsing
    them is correct here. A caller that needs every market row must not use this.
    """
    out: dict[str, dict] = {}
    for r in rows:
        out.setdefault(to_canonical(r.get(id_col, ""), up_to_canon), r)
    return out
