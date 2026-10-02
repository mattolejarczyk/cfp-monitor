"""scripts/sponsor_carry.py: option A, never lose a known sponsorship answer (2026-10-02). One test per rule."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("sc", ROOT / "scripts" / "sponsor_carry.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


def to_canon(eid, lookup):
    return lookup.get(eid, eid)


def row(eid="E1", edition="2026", req="Unknown", url="", cost="", quote="", name="Conf"):
    return {"EVENT_ID": eid, "CONFERENCE": name, "EDITION": edition, "SPONSOR_REQUIRED": req, "SPONSOR_URL": url,
            "SPONSOR_COST": cost, "SPONSOR_QUOTE": quote, "SOURCE_AS_OF": "2026-10-03", "OVERVIEW": "x"}


PRIOR = row(req="Yes", url="https://c.org/sponsor", cost="Gold $10k", quote="Gold sponsors pay $10,000")


def run(rows, prior=PRIOR, sources=None, lookup=None):
    return sc.carry_sponsorship(rows, sources or ["new"] * len(rows), {"E1": prior}, lookup or {}, to_canon)


def test_unknown_this_week_carries_the_whole_unit():
    rows, rep = run([row(req="Unknown")])
    r = rows[0]
    assert (r["SPONSOR_REQUIRED"], r["SPONSOR_URL"], r["SPONSOR_COST"], r["SPONSOR_QUOTE"]) == \
        ("Yes", "https://c.org/sponsor", "Gold $10k", "Gold sponsors pay $10,000")
    assert len(rep["carried"]) == 1 and "Unknown" in rep["carried"][0]["why"]


def test_blank_this_week_also_carries():
    rows, _ = run([row(req="")])
    assert rows[0]["SPONSOR_REQUIRED"] == "Yes" and rows[0]["SPONSOR_URL"]


def test_the_answer_is_never_carried_without_its_page():
    # even if this week returned a stray URL with Unknown, the unit comes from last week as a whole
    rows, _ = run([row(req="Unknown", url="https://other.example/")])
    assert rows[0]["SPONSOR_URL"] == "https://c.org/sponsor" and rows[0]["SPONSOR_REQUIRED"] == "Yes"


def test_same_answer_fills_only_blank_cells_and_never_overwrites():
    rows, rep = run([row(req="Yes", url="https://c.org/new-page", cost="", quote="")])
    r = rows[0]
    assert r["SPONSOR_URL"] == "https://c.org/new-page"                     # fresh value stands
    assert r["SPONSOR_COST"] == "Gold $10k" and r["SPONSOR_QUOTE"] == "Gold sponsors pay $10,000"
    assert rep["carried"][0]["fields"] == ["SPONSOR_COST", "SPONSOR_QUOTE"]


def test_a_fresh_reworded_cost_is_not_replaced():
    rows, rep = run([row(req="Yes", url="u", cost="Tiers available on request", quote="q")])
    assert rows[0]["SPONSOR_COST"] == "Tiers available on request" and rep["carried"] == []


def test_a_different_answer_is_reported_not_carried():
    rows, rep = run([row(req="No", url="", cost="", quote="")])
    assert rows[0]["SPONSOR_REQUIRED"] == "No" and rows[0]["SPONSOR_URL"] == ""
    assert rep["disagreements"] == [{"conference": "Conf", "canonical": "E1", "last_week": "yes", "this_week": "no"}]


def test_a_new_edition_starts_fresh():
    rows, rep = run([row(edition="2027", req="Unknown")])
    assert rows[0]["SPONSOR_REQUIRED"] == "Unknown" and rep["skipped_new_edition"] == 1


def test_a_blank_edition_never_carries():
    rows, rep = run([row(edition="", req="Unknown")])
    assert rows[0]["SPONSOR_REQUIRED"] == "Unknown"


def test_an_unresolved_prior_is_not_an_answer():
    for bad in ("Unknown", ""):
        rows, rep = run([row(req="Unknown")], prior=row(req=bad, url="u", cost="c"))
        assert rows[0]["SPONSOR_URL"] == "" and rep["carried"] == []


def test_only_this_weeks_research_is_touched():
    rows, rep = run([row(req="Unknown")], sources=["prior"])
    assert rows[0]["SPONSOR_REQUIRED"] == "Unknown" and rep["carried"] == []


def test_no_prior_row_means_nothing_to_carry():
    rows, rep = sc.carry_sponsorship([row(eid="NEW", req="Unknown")], ["new"], {"E1": PRIOR}, {}, to_canon)
    assert rows[0]["SPONSOR_REQUIRED"] == "Unknown" and rep["carried"] == []


def test_identity_goes_through_the_lookup_not_the_raw_event_id():
    # this week's id differs from the canonical one; the lookup maps it (contract 5.4)
    rows, rep = run([row(eid="UPSTREAM-ID", req="Unknown")], lookup={"UPSTREAM-ID": "E1"})
    assert rows[0]["SPONSOR_REQUIRED"] == "Yes" and rep["carried"][0]["canonical"] == "E1"


def test_no_other_column_is_touched():
    rows, _ = run([row(req="Unknown")])
    assert rows[0]["SOURCE_AS_OF"] == "2026-10-03" and rows[0]["OVERVIEW"] == "x" and rows[0]["EDITION"] == "2026"


def test_a_file_without_the_sponsor_columns_is_left_alone():
    plain = {"EVENT_ID": "E1", "CONFERENCE": "C", "EDITION": "2026"}
    rows, rep = sc.carry_sponsorship([plain], ["new"], {"E1": PRIOR}, {}, to_canon)
    assert rows[0] == {"EVENT_ID": "E1", "CONFERENCE": "C", "EDITION": "2026"} and rep["carried"] == []
