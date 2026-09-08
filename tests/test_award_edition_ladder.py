"""Amendment v2.3 - the awards EDITION anchor ladder.

Every case here is a real row from the 2026-09-05 awards delivery, because the ladder's shape
came from measuring that file rather than from reasoning about it. Two of the cases exist only
because the measurement contradicted the obvious rule.
"""
from __future__ import annotations

from datetime import date

from cfp_monitor.rules import award_edition, is_awards_row

TODAY = date(2026, 9, 8)


def _row(**kw):
    base = {"OPPORTUNITY_TYPE": "Awards", "SUBMISSION DEADLINE": "", "ANNOUNCEMENT_DATE": "",
            "START DATE": "", "EDITION": ""}
    base.update(kw)
    return base


# ---- rung 2 ---------------------------------------------------------------------------
def test_announcement_after_the_deadline_anchors_the_edition():
    """Globee Awards for Cybersecurity: EDITION read 2026 against a 2027-02-04 deadline."""
    year, why = award_edition(_row(**{"SUBMISSION DEADLINE": "2027-02-04",
                                      "ANNOUNCEMENT_DATE": "2027-06-15"}))
    assert year == "2027"
    assert "rung 2" in why


def test_announcement_on_the_deadline_still_anchors():
    """The guard is `not earlier than`, not `strictly after` - a same-day pair is not stale."""
    year, why = award_edition(_row(**{"SUBMISSION DEADLINE": "2027-02-04",
                                      "ANNOUNCEMENT_DATE": "2027-02-04"}))
    assert year == "2027" and "rung 2" in why


# ---- rung 2's guard, which the measurement forced -------------------------------------
def test_an_announcement_before_its_own_deadline_is_history_and_does_not_anchor():
    """The Earthshot Prize: deadline 2024-12-11, announcement earlier still.

    Without the guard this row's edition moves 2026 -> 2025, backwards into a cycle that has
    already happened. Two of the ten rows the ladder would move failed exactly this way.
    """
    row = _row(**{"SUBMISSION DEADLINE": "2024-12-11", "ANNOUNCEMENT_DATE": "2025-11-03",
                  "EDITION": "2026"})
    # announcement is AFTER this deadline, so it does anchor - the stale case is the next one
    year, _ = award_edition(row)
    assert year == "2025"

    stale = _row(**{"SUBMISSION DEADLINE": "2025-03-14", "ANNOUNCEMENT_DATE": "2024-06-01",
                    "EDITION": "2026"})
    year, why = award_edition(stale)
    assert year is None, "a pre-deadline announcement must not anchor"
    assert "rung 4" in why


def test_the_guard_falls_THROUGH_rather_than_returning_the_stale_year():
    """It must reach rung 3 if a START DATE is there, not stop at rung 2 with nothing."""
    year, why = award_edition(_row(**{"SUBMISSION DEADLINE": "2025-03-14",
                                      "ANNOUNCEMENT_DATE": "2024-06-01",
                                      "START DATE": "2026-05-19"}))
    assert year == "2026" and "rung 3" in why


# ---- rung 3 ---------------------------------------------------------------------------
def test_start_date_anchors_when_there_is_no_announcement():
    year, why = award_edition(_row(**{"START DATE": "2027-04-17"}))
    assert year == "2027" and "rung 3" in why


def test_announcement_outranks_start_date():
    year, why = award_edition(_row(**{"SUBMISSION DEADLINE": "2026-01-01",
                                      "ANNOUNCEMENT_DATE": "2027-09-24",
                                      "START DATE": "2026-05-19"}))
    assert year == "2027" and "rung 2" in why


# ---- rung 4, and the thing it must never do -------------------------------------------
def test_no_anchor_returns_None_so_the_caller_keeps_what_was_delivered():
    """41 of 127 rows land here. Blanking them would empty a third of the delivery."""
    year, why = award_edition(_row(EDITION="2026"))
    assert year is None
    assert "keep the delivered value" in why and "projected" in why


def test_the_deadline_is_never_an_anchor():
    """The one field the ladder exists to stop being used."""
    year, _ = award_edition(_row(**{"SUBMISSION DEADLINE": "2026-11-27"}))
    assert year is None, "a deadline alone must not produce an edition"


def test_a_blank_row_produces_no_edition_rather_than_todays_year():
    year, _ = award_edition(_row(), TODAY)
    assert year is None


# ---- scoping --------------------------------------------------------------------------
def test_only_awards_rows_consult_the_ladder():
    assert is_awards_row({"OPPORTUNITY_TYPE": "Awards"})
    assert not is_awards_row({"OPPORTUNITY_TYPE": "Speaking"})
    assert not is_awards_row({})


def test_garbage_dates_are_ignored_not_guessed_at():
    year, why = award_edition(_row(**{"ANNOUNCEMENT_DATE": "TBD", "START DATE": "Anticipated"}))
    assert year is None and "rung 4" in why
