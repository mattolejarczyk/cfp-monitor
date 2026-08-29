"""R8c must not fire on a multi-market event, and must still catch a real duplicate.

On 2026-08-27 the check compared EVENT_ID globally and flagged 12 rows of perfectly correct
data in a combined all-markets file. We reported it to upstream as R9 name-drift and told them
to MERGE the rows. All 11 duplicated IDs were one event legitimately belonging to several
markets - same name, distinct markets, same deadline, and zero duplicates inside any per-market
delivery. Merging would have deleted real market memberships; upstream had it queued before the
retraction arrived.

Contract section 10: "Membership is many-to-many in its own table; market is excluded from the
key so one event is one record."
"""
import csv
import importlib.util
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("_ad", ROOT / "scripts" / "accept_delivery.py")
ad = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ad)

HDR = ["EVENT_ID", "CONFERENCE", "CONFERENCE URL", "LOCATION", "CONFERENCE DATES",
       "LATEST UPDATE", "SUBMISSION DEADLINE", "SUBMISSION DATE VERIFIED", "PRIORITY",
       "STATUS", "STATUS DETAILS", "CFP MODEL TYPE", "SUBMISSION URL", "COORDINATOR EMAIL",
       "OVERVIEW", "CATEGORIES", "NOTES", "TRACK", "GROUNDING_CONFIDENCE", "EDITION",
       "START DATE", "Market", "CITY", "STATE_PROVINCE", "COUNTRY", "MAIN_INFO_URL",
       "CFP_SUBMISSION_URL", "DEADLINE_EVIDENCE_URL", "VENUE_EVIDENCE_URL", "DEADLINE_QUOTE",
       "IS_PROJECTED", "SOURCE_AS_OF", "GATED_STATUS", "ISSUES", "OPPORTUNITY_TYPE", "FORMAT",
       "LIFECYCLE_EVIDENCE_URL", "LIFECYCLE_QUOTE", "ORGANIZER", "SPONSOR_REQUIRED",
       "SPONSOR_URL", "SPONSOR_COST", "SPONSOR_QUOTE"]


def _csv(tmp_path, rows):
    p = tmp_path / "d.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_ALL)
        w.writerow(HDR)
        for eid, name, market in rows:
            r = {c: "" for c in HDR}
            r.update({"EVENT_ID": eid, "CONFERENCE": name, "Market": market,
                      "OPPORTUNITY_TYPE": "Speaking", "IS_PROJECTED": "true",
                      "SPONSOR_REQUIRED": "Unknown", "SOURCE_AS_OF": "2026-08-01"})
            w.writerow([r[c] for c in HDR])
    return str(p)


def _r8c(path):
    g = ad.Gate(path)
    g.run(date(2026, 9, 1))
    return [x for x in g.results if x[0] == "R8c"]


def test_one_event_in_three_markets_is_not_a_duplicate(tmp_path):
    """The CES 2027 case: one record, three market labels, exactly as section 10 prescribes."""
    path = _csv(tmp_path, [("2027-ces-2027-las-vegas-speaking", "CES 2027", "ConsumerElectronics"),
                           ("2027-ces-2027-las-vegas-speaking", "CES 2027", "Robotics"),
                           ("2027-ces-2027-las-vegas-speaking", "CES 2027", "Semiconductor")])
    failures = [r for r in _r8c(path) if r[-1]]
    assert not failures, f"multi-market event wrongly flagged: {failures}"


def test_a_real_duplicate_within_one_market_still_fails(tmp_path):
    """GOOD INPUT SURVIVES is only half of it - the check must still catch the real thing."""
    path = _csv(tmp_path, [("2027-dupe-event-city-speaking", "Dupe Event", "Utility"),
                           ("2027-dupe-event-city-speaking", "Dupe Event", "Utility")])
    failures = [r for r in _r8c(path) if r[-1]]
    assert failures, "a genuine duplicate inside one market must still be reported"


def test_distinct_events_in_one_market_are_fine(tmp_path):
    path = _csv(tmp_path, [("2027-event-a-city-speaking", "Event A", "Utility"),
                           ("2027-event-b-city-speaking", "Event B", "Utility")])
    assert not [r for r in _r8c(path) if r[-1]]
