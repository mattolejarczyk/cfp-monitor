"""ACT-21: the answer key has a confidence tier; the reader is scored only on person-confirmed facts, the grounded call may use both (decision ACT-04)."""
import csv

import pytest

from experiments.read_the_page_pass import pass_lib as L
from scripts.answer_key import GROUNDED_TIERS, PAGE, PERSON, READER_TIERS, assert_reader_tier, grounded_key, load_key, page_proven_rows, reader_key, tier_counts
from scripts.answer_key_from_pins import key_rows
from scripts.answer_key import COLS

CANDS = [
    {"id": "B1", "market": "Cybersecurity", "event": "Alpha Con 2027", "field": "CITY", "claimed": "Paris", "reader_value": "Paris", "status": "agree", "quote": "held in Paris", "why": "ok", "pages": "https://a"},
    {"id": "B1", "market": "Cybersecurity", "event": "Alpha Con 2027", "field": "COUNTRY", "claimed": "France", "reader_value": "France", "status": "agree", "quote": "", "why": "ok", "pages": "https://a"},
    {"id": "B2", "market": "Utility", "event": "Beta Expo", "field": "CITY", "claimed": "Rome", "reader_value": "Milan", "status": "differs", "quote": "in Milan", "why": "ok", "pages": "https://b"},
    {"id": "B3", "market": "Utility", "event": "Gamma Summit", "field": "CITY", "claimed": "Oslo", "reader_value": "Oslo", "status": "agree", "quote": "Oslo", "why": "ok", "pages": "https://g"},
    {"id": "B4", "market": "Utility", "event": "Unmapped Event", "field": "START DATE", "claimed": "2027-01-02", "reader_value": "2027-01-02", "status": "agree", "quote": "2 January 2027", "why": "ok", "pages": "https://u"},
]
PERSON_ROWS = [{"event": "Gamma Summit", "canonical": "2027-gamma-oslo-speaking", "field": "CITY", "confirmed_value": "Oslo", "tier": PERSON}]
NAMES = {"alpha con 2027": "2027-alpha-paris-speaking", "gamma summit": "2027-gamma-oslo-speaking", "beta expo": "2027-beta-rome-speaking"}


def _write(tmp_path, rows):
    p = tmp_path / "key.csv"
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    return p


def test_pins_become_person_confirmed_lines():
    rows = key_rows([{"canonical": "c1", "event": "E", "by": "operator", "ruled_on": "2026-10-03", "links": ["https://x"], "why": "w", "set": {"CITY": "Oslo"}}])
    assert rows[0]["tier"] == PERSON and rows[0]["quote"] == ""


def test_only_an_agreeing_candidate_with_a_quote_becomes_a_page_proven_line():
    rows = page_proven_rows(CANDS, NAMES, PERSON_ROWS)
    assert [(r["event"], r["field"]) for r in rows] == [("Alpha Con 2027", "CITY"), ("Unmapped Event", "START DATE")]   # no quote, differs and already-person-confirmed are all out
    assert all(r["tier"] == PAGE and r["confirmed_by"] == "" and r["quote"] for r in rows)
    assert rows[0]["canonical"] == "2027-alpha-paris-speaking" and rows[1]["canonical"] == ""      # an unmapped event is kept, with a blank id, not dropped


def test_reader_key_is_person_confirmed_only_and_grounded_key_has_both(tmp_path):
    p = _write(tmp_path, PERSON_ROWS + page_proven_rows(CANDS, NAMES, PERSON_ROWS))
    assert {r["tier"] for r in reader_key(p)} == {PERSON}
    assert {r["tier"] for r in grounded_key(p)} == {PERSON, PAGE}
    assert len(grounded_key(p)) == len(reader_key(p)) + 2
    assert READER_TIERS == (PERSON,) and set(GROUNDED_TIERS) == {PERSON, PAGE}


def test_an_old_key_file_without_a_tier_column_is_all_person_confirmed(tmp_path):
    p = tmp_path / "old.csv"
    p.write_text('"event","canonical","field","confirmed_value"\n"E","c","CITY","Oslo"\n', encoding="utf-8")
    assert [r["tier"] for r in load_key(p)] == [PERSON]


def test_an_unknown_tier_is_refused_not_skipped(tmp_path):
    p = _write(tmp_path, [{"event": "E", "canonical": "c", "field": "CITY", "confirmed_value": "x", "tier": "probably-right"}])
    with pytest.raises(ValueError):
        load_key(p)


def test_the_reader_score_refuses_a_page_proven_fact():
    ok = [{"event": "E", "field": "city", "gold": "Oslo", "accepted": "Oslo", "tier": PERSON}]
    assert L.score(ok)["correct"] == 1
    bad = ok + [{"event": "F", "field": "city", "gold": "Rome", "accepted": "Rome", "tier": PAGE}]
    with pytest.raises(ValueError):
        L.score(bad)
    with pytest.raises(ValueError):
        assert_reader_tier(bad)


def test_the_readers_gold_comes_from_pins_and_is_person_confirmed():
    gold = L.gold_facts([{"canonical": "c", "event": "E", "links": [], "set": {"CITY": "Oslo", "START DATE": "2027-01-02"}}])
    assert gold and all(g["tier"] == PERSON for g in gold)


def test_the_real_key_file_has_a_tier_on_every_line_and_the_reader_part_is_the_pins():
    rows = load_key()
    assert rows and all(r["tier"] in (PERSON, PAGE) for r in rows)
    counts = tier_counts(rows)
    from scripts.pinned_rows import load_pins
    assert counts[PERSON] == len(key_rows(load_pins()))
