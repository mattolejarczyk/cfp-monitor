"""SOURCE_AS_OF became load-bearing on 2026-08-27; the gate should notice if it is flattened.

Upstream emits SPONSOR_REQUIRED as a blanket "Unknown" on the first 43-column delivery, so the
only thing separating "inspected, no sponsorship found" from "nobody has looked yet" is whether
that row's SOURCE_AS_OF advanced. They agreed to advance it strictly on rows actually fetched.

If it is stamped wholesale at export the file still looks perfect and we silently lose the
ability to measure coverage. This is an ADVISORY, not a rejection, because a genuine single-pass
re-research of one market really would share one date.
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


def _csv(tmp_path, stamps):
    p = tmp_path / "d.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_ALL)
        w.writerow(HDR)
        for i, s in enumerate(stamps):
            row = {c: "" for c in HDR}
            row.update({"EVENT_ID": f"e{i}", "CONFERENCE": f"Conf {i}", "Market": "Utility",
                        "OPPORTUNITY_TYPE": "Speaking", "SOURCE_AS_OF": s,
                        "SPONSOR_REQUIRED": "Unknown", "IS_PROJECTED": "true"})
            w.writerow([row[c] for c in HDR])
    return str(p)


def _gate(path):
    g = ad.Gate(path)
    g.run(date(2026, 9, 2))
    return g


def _notes(path):
    return {n[0] for n in _gate(path).notes}


def test_a_uniform_source_as_of_raises_an_advisory(tmp_path):
    """The wholesale-stamp case we asked upstream not to do."""
    notes = _notes(_csv(tmp_path, ["2026-09-02"] * 25))
    assert "R19b" in notes


def test_varied_source_as_of_is_silent(tmp_path):
    """GOOD INPUT SURVIVES: per-row advancement is exactly what we asked for."""
    stamps = [f"2026-08-{(i % 7) + 1:02d}" for i in range(25)]
    notes = _notes(_csv(tmp_path, stamps))
    assert "R19b" not in notes


def test_a_small_file_is_not_flagged(tmp_path):
    """A handful of rows sharing a date proves nothing - don't cry wolf on a correction pass."""
    notes = _notes(_csv(tmp_path, ["2026-09-02"] * 5))
    assert "R19b" not in notes


def test_blank_stamps_are_not_treated_as_uniform(tmp_path):
    """Blank is 'we do not know', not 'all the same'. Counting it would fire on empty data."""
    notes = _notes(_csv(tmp_path, [""] * 25))
    assert "R19b" not in notes


def test_the_advisory_never_rejects(tmp_path):
    """It asks a question. A legitimate single-pass re-research shares one date."""
    g = _gate(_csv(tmp_path, ["2026-09-02"] * 25))
    assert "R19b" in {n[0] for n in g.notes}, "should be raised as a note"
    hard = " ".join(str(x) for x in getattr(g, "results", []) or [])
    assert "R19b" not in hard or "FAIL" not in hard, "R19b must never reject a delivery"
