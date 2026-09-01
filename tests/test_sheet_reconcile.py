"""Reconciliation between our record and the customer's sheet.

The framing is load-bearing. On 2026-09-01 a first pass called these "sheet errors" and counted
74 across six categories. Under scrutiny four categories were ours, one was a bug in the
heuristic, and of the deadline disagreements that survived, WE were the wrong side twice. A
customer handed 74 of their own mistakes, most of which are not, stops reading the report.
"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import sheet_reconcile as sr  # noqa: E402

TODAY = date(2026, 9, 1)


def test_the_global_energy_show_case():
    """Their sheet points at the 2026 call; the live one is 2027."""
    why = sr.url_year_conflict(
        "https://www.globalenergyshow.com/conferences/2026-call-for-submissions/", "2027")
    assert why and "2026" in why and "2027" in why


def test_a_matching_year_is_not_a_conflict():
    assert sr.url_year_conflict(
        "https://www.globalenergyshow.com/conferences/2027-call-for-submissions/", "2027") == ""


def test_only_the_last_year_in_the_path_counts():
    """A host or campaign id can carry a number that is not the edition. Reading the first one
    would invent conflicts on rows that are fine."""
    assert sr.url_year_conflict("https://ev2020.example/cfp/2027-call/", "2027") == ""


def test_no_edition_means_no_verdict():
    """2.5 - decline rather than guess. Without an edition there is nothing to compare."""
    assert sr.url_year_conflict("https://x.example/2026-cfp", "") == ""
    assert sr.url_year_conflict("", "2027") == ""


def test_ours_is_named_as_the_likely_wrong_side_when_it_has_expired():
    """Troopers: we hold a passed 2026 date, they hold 2027. Reporting that as THEIR problem
    would be wrong on the facts."""
    ours = {"SUBMISSION DEADLINE": "2026-03-31", "EDITION": "2027"}
    got = sr.reconcile([{"client_key": "arnica", "their_name": "Troopers", "event_id": "e1",
                         "their_deadline": "03/31/2027", "status": ""}],
                       {"e1": ours}, TODAY)
    dl = [g for g in got if g["cat"] == "deadline conflict"]
    assert len(dl) == 1
    assert dl[0]["ours_wrong"] is True
    assert "likely ours" in dl[0]["detail"]


def test_a_live_disagreement_blames_neither_side():
    ours = {"SUBMISSION DEADLINE": "2026-12-04", "EDITION": "2027"}
    got = sr.reconcile([{"client_key": "u", "their_name": "GES", "event_id": "e1",
                         "their_deadline": "12/05/2026", "status": ""}], {"e1": ours}, TODAY)
    dl = [g for g in got if g["cat"] == "deadline conflict"][0]
    assert dl["ours_wrong"] is False
    assert "neither is proven wrong" in dl["detail"]


def test_unmatched_rows_are_split_by_WHY_not_lumped_together():
    """The three causes need different actions, and only the last means 'not in our database'.
    A name-prefix join reported 27 'we do not track' rows including ESF MENA, which we track."""
    rows = [
        {"client_key": "u", "their_name": "High", "event_id": "", "match_confidence": 90.0},
        {"client_key": "u", "their_name": "Mid", "event_id": "", "match_confidence": 46.0},
        {"client_key": "u", "their_name": "None", "event_id": "", "match_confidence": 0.0},
    ]
    got = {g["name"]: g["cat"] for g in sr.reconcile(rows, {}, TODAY)}
    assert got["High"] == "match not promoted"
    assert got["Mid"] == "ambiguous match"
    assert got["None"] == "no candidate found"


def test_a_settled_row_is_still_reported_but_marked():
    """A conflict on a row they have already submitted is worth seeing and is not urgent.
    Hiding it would lose the audit trail; ranking it equally would bury the live ones."""
    ours = {"SUBMISSION DEADLINE": "2026-05-15", "EDITION": "2026"}
    got = sr.reconcile([{"client_key": "u", "their_name": "ADIPEC", "event_id": "e1",
                         "their_deadline": "05/31/2026", "status": "Client Declined"}],
                       {"e1": ours}, TODAY)
    assert got and got[0]["acted"] is True


def test_agreement_produces_nothing():
    ours = {"SUBMISSION DEADLINE": "2026-09-09", "EDITION": "2027",
            "CFP_SUBMISSION_URL": "https://x.example/2027-cfp"}
    got = sr.reconcile([{"client_key": "u", "their_name": "CES", "event_id": "e1",
                         "their_deadline": "09/09/2026", "status": "Info Needed",
                         "their_submission_url": "https://x.example/2027-cfp"}],
                       {"e1": ours}, TODAY)
    assert got == []


def test_a_bad_date_does_not_crash_the_report():
    ours = {"SUBMISSION DEADLINE": "2026-13-45", "EDITION": "2027"}
    sr.reconcile([{"client_key": "u", "their_name": "X", "event_id": "e1",
                   "their_deadline": "99/99/2026", "status": ""}], {"e1": ours}, TODAY)
