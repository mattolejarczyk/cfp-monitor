"""experiments/finder_reader_test/side_by_side.py: how the grounded and real-URL answers relate."""
from experiments.finder_reader_test.side_by_side import outcome, policy


def test_outcome_and_policy():
    assert outcome("2026-11-16", "2026-11-16") == "exact" and outcome("2026-11-23", "2026-11-16") == "different" and outcome("", "2026-11-16") == "blank"
    assert policy("exact", "exact") == "both right (agree)"
    assert policy("different", "exact") == "disagree: the real-URL path was right"
    assert policy("exact", "different") == "disagree: the grounded path was right"
    assert policy("blank", "exact") == "only real-URL right" and policy("exact", "blank") == "only grounded right"
    assert policy("blank", "blank") == "neither right" and policy("not researched", "exact") == "only real-URL right"
