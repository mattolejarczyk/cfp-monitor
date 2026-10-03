"""scripts/pinned_rows.py: a person's ruling holds over the research, lapses after the call closes, and only touches the cells a ruling may set."""
from datetime import date

import pytest

from scripts.pinned_rows import ALLOWED, apply_pins, load_pins

T = date(2026, 10, 3)
CANON = lambda eid, lookup: lookup.get(eid, eid)
PIN = {"canonical": "c1", "event": "Conf", "ruled_on": "2026-10-03", "why": "operator read the page", "until": "2026-11-17",
       "set": {"SUBMISSION DEADLINE": "2026-11-16", "DEADLINE_QUOTE": "Abstract submission deadline: November 16, 2026", "IS_PROJECTED": "false"}}


def _row(**kw):
    base = {"EVENT_ID": "up-1", "CONFERENCE": "Conf", "EDITION": "2027", "SUBMISSION DEADLINE": "2026-11-23", "DEADLINE_QUOTE": "Research paper submission deadline: November 23, 2026",
            "IS_PROJECTED": "true", "GROUNDING_CONFIDENCE": "Projected (2027)", "STATUS DETAILS": "x"}
    base.update(kw)
    return base


def test_a_pin_overrides_the_research_and_reports_what_the_research_said():
    rows, rep = apply_pins([_row()], {"up-1": "c1"}, CANON, [PIN], T)
    r = rows[0]
    assert r["SUBMISSION DEADLINE"] == "2026-11-16" and r["DEADLINE_QUOTE"].startswith("Abstract") and r["IS_PROJECTED"] == "false"
    assert r["GROUNDING_CONFIDENCE"] == "Verified (2027)"                      # R11 stays bound to IS_PROJECTED
    ch = rep["applied"][0]["changed"]
    assert ch["SUBMISSION DEADLINE"] == {"research": "2026-11-23", "pinned": "2026-11-16"}


def test_a_row_that_already_agrees_is_unchanged_and_other_rows_are_untouched():
    rows, rep = apply_pins([_row(**{"SUBMISSION DEADLINE": "2026-11-16", "DEADLINE_QUOTE": PIN["set"]["DEADLINE_QUOTE"], "IS_PROJECTED": "false",
                                    "GROUNDING_CONFIDENCE": "Verified (2027)"}), _row(EVENT_ID="other")], {"up-1": "c1"}, CANON, [PIN], T)
    assert rep["applied"] == [] and rep["unchanged"] == 1 and rows[1]["SUBMISSION DEADLINE"] == "2026-11-23"


def test_a_pin_lapses_after_its_until_date():
    rows, rep = apply_pins([_row()], {"up-1": "c1"}, CANON, [PIN], date(2026, 11, 18))
    assert rows[0]["SUBMISSION DEADLINE"] == "2026-11-23" and rep["lapsed"] == ["Conf"] and not rep["applied"]


def test_a_pin_may_not_set_identity_or_customer_columns():
    for col in ("EVENT_ID", "CONFERENCE", "EDITION", "STATUS", "NOTES", "PRIORITY", "SUBMISSION URL"):
        assert col not in ALLOWED
        with pytest.raises(ValueError):
            apply_pins([_row()], {}, CANON, [{**PIN, "set": {col: "x"}}], T)


def test_the_real_pin_file_is_valid_and_each_pin_names_why_and_until():
    pins = load_pins()
    assert len(pins) >= 2
    for p in pins:
        assert p["canonical"] and p["until"] and p["why"] and p["ruled_on"] and set(p["set"]) <= set(ALLOWED)
        assert p["set"].get("DEADLINE_EVIDENCE_URL", "").startswith("https://")
