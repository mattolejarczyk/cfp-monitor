"""Guarded FIRST LOAD of a brand-new event inside the weekend import (ACT-63, 2026-10-10).

WHY. weekend_import.resolve_market held back every researched row whose permanent id was not already in
the database, labelled 'no permanent id'. A brand-new event could therefore never be loaded by the Saturday
job even when upstream HAD given its id (docs/operations/given_ids.csv, stamped on our input row): 82
customer events were held on 2026-10-10. The only route was runbook 7.1 step 4 by hand.

THE RULE (pure functions, no I/O except reading two small CSVs; weekend_import.py calls them):
a researched row is let through as a NEW event only when ALL of these hold
  1. the switch is on (weekend_import.py --new-events; default OFF);
  2. its permanent id (carried through <Market>_audited.identity.csv from OUR input row, never derived
     from a name) is in the given_ids ledger for THIS market, exactly as written there;
  3. that same id is stamped as EVENT_ID_CANON on a row of <Market>_input.csv (the id on the research
     row and the id on our input row agree);
  4. identity.to_canonical maps it to itself (it is not an upstream alias of an event we already hold)
     and it is not in the database;
  5. this run has not already let `cap` new events through (default 100).
The row then goes through the gate like every other row. An id the ledger does not hold is never loaded.
Nothing here mints, derives or normalises an id.
"""
from __future__ import annotations

import csv
from pathlib import Path

DEFAULT_CAP = 100


def read_ledger(path: Path, market: str) -> set[str]:
    """Ids upstream gave us for `market` (same reading as stamp_input_ids.load_given)."""
    if not path or not Path(path).exists():
        return set()
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return {r["event_id"].strip() for r in csv.DictReader(fh)
                if (r.get("market") or "").strip() == market and (r.get("event_id") or "").strip()}


def input_canons(input_csv: Path) -> set[str]:
    """Every EVENT_ID_CANON stamped on the research input list."""
    if not input_csv or not Path(input_csv).exists():
        return set()
    with open(input_csv, encoding="utf-8-sig", newline="") as fh:
        return {(r.get("EVENT_ID_CANON") or "").strip() for r in csv.DictReader(fh)} - {""}


def decide(canon: str, *, enabled: bool, ledger: set[str], input_ids: set[str], known: set[str],
           up_to_canon: dict, to_canonical, taken: int, cap: int) -> tuple[bool, str]:
    """(load it as a new event?, the plain reason it is held when not)."""
    if not canon:
        return False, ("no permanent id on our input row (EVENT_ID_CANON is blank), so it is not "
                       "loaded - we never derive an id from a name; upstream must give one")
    if canon in known:
        return False, "already in the database"                       # not a first load; caller never asks
    if canon not in ledger:
        return False, (f"id {canon} is not in the given_ids ledger and not in the database, so we "
                       "cannot tell for certain which event this is; not loaded (we never take an id "
                       "upstream has not given us)")
    # from here the id IS upstream's, recorded as given
    held = f"id {canon} was given by upstream (given_ids ledger) but the event is not in the database yet; "
    if canon not in input_ids:
        return False, held + "it is not stamped on our input row, so the two do not agree; not loaded"
    if to_canonical(canon, up_to_canon) != canon:
        return False, held + "it is an alias of an event we already hold; not loaded as new"
    if not enabled:
        return False, held + "the first-load path is OFF (weekend_import.py --new-events), so it waits"
    if taken >= cap:
        return False, held + f"this run's cap of {cap} new events was reached, so it waits for next week"
    return True, ""
