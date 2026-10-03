"""scripts/answer_key_prefill.py: the draft states what a page says; it never confirms anything."""
from scripts.answer_key_prefill import best_row, field_proof, other_dates_for_year

PAGE = "6th European Carbon Capture 2027. The conference takes place 26 - 27 January 2027 | Amsterdam. Organised by Acme Events. " + "padding " * 60
ROW = {"CONFERENCE": "European Carbon Capture, Utilization & Storage Conference 2027"}


def test_matches_the_benchmark_event_to_its_approved_row_or_none():
    rows = [ROW, {"CONFERENCE": "Totally Different Summit"}]
    assert best_row("European Carbon Capture, Utilization & Storage Conference 2027", rows) is ROW
    assert best_row("Some Event That Is Not There 2026", rows) is None


def test_start_date_states_differs_unproven_and_unreadable():
    pages = [("u", PAGE)]
    assert field_proof("START DATE", "2027-01-26", pages, ROW)["status"] == "page-states"
    d = field_proof("START DATE", "2027-03-09", pages, ROW)
    assert d["status"] in ("page-differs", "unproven") and "2027" in d["note"]
    assert field_proof("START DATE", "2027-01-26", [("u", "short")], ROW)["status"] == "unreadable"
    assert field_proof("START DATE", "", pages, ROW)["status"] == "no claim"


def test_city_and_organizer_must_be_named_on_the_page_and_year_is_specific():
    pages = [("u", PAGE)]
    assert field_proof("CITY", "Amsterdam, Netherlands", pages, ROW)["status"] == "page-states"
    assert field_proof("CITY", "Rotterdam", pages, ROW)["status"] == "unproven"
    assert field_proof("ORGANIZER", "Acme Events", pages, ROW)["status"] == "page-states"
    assert field_proof("EDITION", "2027", pages, ROW)["status"] == "page-states"
    assert field_proof("EDITION", "2026", pages, ROW)["status"] == "unproven"


def test_dates_of_another_year_never_count():
    assert other_dates_for_year([("u", PAGE)], "2026", require_context=False) == []
