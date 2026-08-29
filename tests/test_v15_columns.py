"""The v1.5 transition: two column shapes are valid, and a count is not a schema.

Upstream agreed v1.5 on 2026-08-14 and gave no date for the first delivery carrying it. Until
one arrives both shapes must pass, or every delivery between the agreement and their next run
would be rejected by check 1 - the check the runbook says to read first, because if rows do not
parse then every later check is measuring shifted fields.
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


def write(tmp_path, header, rows=()):
    p = tmp_path / "d.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            w.writerow(list(r) + [""] * (len(header) - len(r)))
    return str(p)


def check1(path):
    """Run only structural check 1 and return its offender list.

    results rows are (num, name, passed, failures) - the offenders are the LAST element.
    """
    g = ad.Gate(path, network=False)
    g.check_structure()
    num, name, passed, failures = next(r for r in g.results if r[0] == "1")
    return failures


# --------------------------------------------------------- both shapes are valid --
def test_the_38_column_delivery_is_now_rejected(tmp_path):
    """WINDOW CLOSED 2026-08-29. This test previously asserted the opposite.

    38 was accepted alongside 43 from 2026-08-20 so nothing broke while upstream implemented
    v1.5. That was explicitly temporary - a gate accepting two shapes indefinitely lets a silent
    regression to the old shape through. The first 43-column delivery was accepted with zero
    failures on 2026-08-29 and upstream authorised the close, so a 38-column file must now fail
    at check 1 rather than import and store nothing in columns 39-43.
    """
    assert check1(write(tmp_path, V13, [["x"] * 38])), "38 columns must now be rejected"


def test_the_43_column_v15_delivery_passes(tmp_path):
    assert check1(write(tmp_path, V13 + ad.V15_COLS, [["x"] * 43])) == []


def test_any_other_width_is_rejected(tmp_path):
    """35 predates v1.2. 39 is someone appending a column nobody agreed to."""
    for n in (35, 37, 39, 44):
        hdr = (V13 + ad.V15_COLS + [f"X{i}" for i in range(9)])[:n]
        assert check1(write(tmp_path, hdr, [["x"] * n])), f"{n} columns should be rejected"


# ------------------------------------------------------ a count is not a schema --
def test_43_columns_with_the_wrong_names_is_rejected(tmp_path):
    """The failure this guards: 43 columns of the wrong names sail through a length check,
    and every later check then reads shifted fields."""
    wrong = V13 + ["ORGANISER", "SPONSOR_NEEDED", "SPONSOR_LINK", "COST", "QUOTE"]
    bad = check1(write(tmp_path, wrong, [["x"] * 43]))
    assert bad and "expected" in bad[0].lower()


def test_43_columns_in_the_wrong_order_is_rejected(tmp_path):
    shuffled = V13 + ["SPONSOR_REQUIRED", "ORGANIZER", "SPONSOR_URL", "SPONSOR_COST",
                      "SPONSOR_QUOTE"]
    assert check1(write(tmp_path, shuffled, [["x"] * 43]))


def test_ragged_rows_are_caught_against_the_headers_own_width(tmp_path):
    """Rows are measured against the HEADER's width, not a hardcoded constant - otherwise the
    transition would only catch ragged rows in one of the two valid shapes."""
    p = tmp_path / "ragged.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(V13 + ad.V15_COLS)      # 43
        w.writerow(["x"] * 43)             # fine
        w.writerow(["y"] * 41)             # two fields short - line 3
    bad = check1(str(p))
    assert any("line 3" in b for b in bad), bad


# ----------------------------------------------------------- the R18 rules --
def test_sponsor_required_accepts_only_the_agreed_vocabulary():
    assert "yes" in ad.SPONSOR_VALUES and "unknown" in ad.SPONSOR_VALUES
    assert "" in ad.SPONSOR_VALUES, "a blank must be readable as Unknown (R18.1)"
    assert "maybe" not in ad.SPONSOR_VALUES


def test_the_v15_column_names_are_pinned():
    """If these drift from the amendment, the delivery and the contract disagree silently."""
    assert ad.V15_COLS == ["ORGANIZER", "SPONSOR_REQUIRED", "SPONSOR_URL", "SPONSOR_COST",
                           "SPONSOR_QUOTE"]


def test_only_the_v15_width_is_accepted():
    """43 is the single accepted shape as of 2026-08-29. If a future change re-opens this to
    two widths, that should be a deliberate amendment with an end date, not a convenience."""
    assert ad.ACCEPTED_COLS == {43}


# ------------------------------------------ ownership: the quote is OURS, not theirs --
def test_a_sponsor_yes_needs_only_the_URL_from_upstream(tmp_path):
    """R20a: SPONSOR_QUOTE is extracted by us from the page upstream supplies, exactly as with
    DEADLINE_QUOTE. Demanding it of upstream would reject a delivery for a column we told them
    to leave blank - which is how a contract and its gate quietly disagree."""
    hdr = V13 + ad.V15_COLS
    row = ["x"] * 38 + ["Reuters Events", "Yes", "https://x.com/sponsorship", "Gold $25,000", ""]
    row[1] = "Some Conference"
    g = ad.Gate(write(tmp_path, hdr, [row]), network=False)
    g.check_structure()
    g.check_schema_rules()
    r18b = [r for r in g.results if r[0] == "R18b"]
    assert r18b, "R18b did not run on a v1.5 delivery"
    assert r18b[0][3] == [], f"a blank SPONSOR_QUOTE was rejected: {r18b[0][3]}"


def test_a_sponsor_yes_without_a_url_is_still_rejected(tmp_path):
    hdr = V13 + ad.V15_COLS
    row = ["x"] * 38 + ["", "Yes", "", "", ""]
    row[1] = "Some Conference"
    g = ad.Gate(write(tmp_path, hdr, [row]), network=False)
    g.check_structure()
    g.check_schema_rules()
    assert [r for r in g.results if r[0] == "R18b"][0][3], "a Yes with no page should fail"
