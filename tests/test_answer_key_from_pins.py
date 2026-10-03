"""The confirmed answer key is generated from the pins: every verified fact is a line, a pinned blank is recorded as 'the page states nothing'."""
from scripts.answer_key_from_pins import key_rows
from scripts.pinned_rows import load_pins


def test_every_pinned_fact_becomes_a_confirmed_line():
    pins = [{"canonical": "c1", "event": "E", "by": "operator", "ruled_on": "2026-10-03", "links": ["https://x"], "why": "w",
             "set": {"START DATE": "2027-01-26", "CONFERENCE DATES": "", "DEADLINE_QUOTE": "q", "IS_PROJECTED": "false"}}]
    rows = key_rows(pins)
    assert [(r["field"], r["confirmed_value"], r["page_states_nothing"]) for r in rows] == [("START DATE", "2027-01-26", ""), ("CONFERENCE DATES", "", "yes")]
    assert rows[0]["confirmed_by"] == "operator" and rows[0]["pages"] == "https://x"


def test_the_real_ledger_produces_a_key_with_provenance_on_every_line():
    rows = key_rows(load_pins())
    assert len(rows) >= 20
    assert all(r["confirmed_by"] and r["confirmed_on"] and r["pages"].startswith("https://") for r in rows)
