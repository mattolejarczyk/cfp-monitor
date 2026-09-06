"""The v2.1 transition: 45 columns, and the v1.5 block stops being last.

Contract v2.1 (R26) appends SUBMISSION_OPENS and ANNOUNCEMENT_DATE after the five v1.5
sponsorship columns. That moves the sponsorship block off the end of the row.

THE BUG THIS PINS. check_structure used to verify the sponsorship block with
`header[-5:]`. On a 45-column file that reads SPONSOR_URL..ANNOUNCEMENT_DATE and rejects a
correct delivery. The check is now BY POSITION - 39-43 for v1.5, 44-45 for v2.1 - so
appending again later cannot break it the same way.

Both shapes pass while the change lands, exactly as in the v1.5 transition: Bioeconomy
Batch 1 was cleared under 43 and may arrive mid-change.
"""
from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("ad", ROOT / "scripts" / "accept_delivery.py")
ad = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ad)

V13 = ["EVENT_ID", "CONFERENCE", "CONFERENCE URL", "LOCATION", "CONFERENCE DATES",
       "LATEST UPDATE", "SUBMISSION DEADLINE", "SUBMISSION DATE VERIFIED", "PRIORITY", "STATUS",
       "STATUS DETAILS", "CFP MODEL TYPE", "SUBMISSION URL", "COORDINATOR EMAIL", "OVERVIEW",
       "CATEGORIES", "NOTES", "TRACK", "GROUNDING_CONFIDENCE", "EDITION", "START DATE", "Market",
       "CITY", "STATE_PROVINCE", "COUNTRY", "MAIN_INFO_URL", "CFP_SUBMISSION_URL",
       "DEADLINE_EVIDENCE_URL", "VENUE_EVIDENCE_URL", "DEADLINE_QUOTE", "IS_PROJECTED",
       "SOURCE_AS_OF", "GATED_STATUS", "ISSUES", "OPPORTUNITY_TYPE", "FORMAT",
       "LIFECYCLE_EVIDENCE_URL", "LIFECYCLE_QUOTE"]

V43 = V13 + ad.V15_COLS
V45 = V43 + ad.V21_COLS


def write(tmp_path, header):
    p = tmp_path / "d.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow(header)
    return str(p)


def check1(path):
    g = ad.Gate(path, network=False)
    g.check_structure()
    num, name, passed, failures = next(r for r in g.results if r[0] == "1")
    return failures


def test_the_schema_constants_are_the_agreed_ones():
    assert ad.ACCEPTED_COLS == {43, 45}
    assert ad.V21_COLS == ["SUBMISSION_OPENS", "ANNOUNCEMENT_DATE"]
    assert len(V45) == 45


def test_a_45_column_delivery_passes(tmp_path):
    assert check1(write(tmp_path, V45)) == []


def test_a_43_column_delivery_still_passes(tmp_path):
    """Bioeconomy Batch 1 was cleared under 43 and may land mid-change."""
    assert check1(write(tmp_path, V43)) == []


def test_the_sponsorship_block_is_checked_by_position_not_by_being_last(tmp_path):
    """The regression that motivated this file.

    On a correct 45-column header the last five are SPONSOR_URL, SPONSOR_COST,
    SPONSOR_QUOTE, SUBMISSION_OPENS, ANNOUNCEMENT_DATE - which is NOT V15_COLS. A
    last-five check rejects this valid delivery.
    """
    assert [c for c in V45[-5:]] != ad.V15_COLS, "premise: the v1.5 block is no longer last"
    assert V45[38:43] == ad.V15_COLS, "premise: it sits at positions 39-43"
    assert check1(write(tmp_path, V45)) == [], "a valid 45-column header must pass"


def test_45_columns_with_the_new_pair_in_the_wrong_order_fails(tmp_path):
    bad = V43 + ["ANNOUNCEMENT_DATE", "SUBMISSION_OPENS"]
    offenders = check1(write(tmp_path, bad))
    assert offenders, "reversed v2.1 columns must fail"
    assert any("44-45" in o for o in offenders), offenders


def test_45_columns_with_a_disturbed_sponsorship_block_fails(tmp_path):
    bad = V13 + ["ORGANIZER", "SPONSOR_REQUIRED", "SPONSOR_URL", "SPONSOR_COST",
                 "SPONSOR_NOTE"] + ad.V21_COLS
    offenders = check1(write(tmp_path, bad))
    assert offenders, "a wrong name at position 43 must fail"
    assert any("39-43" in o for o in offenders), offenders


def test_a_44_column_delivery_fails(tmp_path):
    """Half an amendment is not a shape."""
    offenders = check1(write(tmp_path, V43 + ["SUBMISSION_OPENS"]))
    assert offenders
    assert any("44 columns" in o for o in offenders), offenders


def test_a_count_is_still_not_a_schema(tmp_path):
    """45 columns of the wrong names must not sail through on length alone."""
    offenders = check1(write(tmp_path, [f"COL{i}" for i in range(45)]))
    assert offenders, "45 arbitrary names must fail"
