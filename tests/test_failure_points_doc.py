"""scripts/failure_points_doc.py: the root-cause register is valid, ordered and in step with the document on disk."""
import json
from pathlib import Path

from scripts.failure_points_doc import DATA, OUT, counts, ordered, render, score, validate

D = json.loads(Path(DATA).read_text(encoding="utf-8"))


def test_the_data_is_valid_and_every_step_has_failure_points():
    assert validate(D) == []
    assert {i["step"] for i in D["items"]} == set(D["steps"])
    assert len({i["id"] for i in D["items"]}) == len(D["items"])


def test_each_step_is_ordered_by_score_then_impact():
    for sid in D["steps"]:
        its = ordered([i for i in D["items"] if i["step"] == sid])
        keys = [(-score(i), -i["impact"], -i["freq"]) for i in its]
        assert keys == sorted(keys)


def test_a_bad_row_is_reported_not_rendered():
    bad = {"steps": {"A": "x"}, "items": [{"id": "A1", "step": "A", "freq": 4, "impact": 3, "status": "DONE", "cause": "c", "evidence": "e", "controls": "k", "remains": "r"},
                                         {"id": "A1", "step": "B", "freq": 1, "impact": 1, "status": "PENDING", "cause": "", "evidence": "e", "controls": "k", "remains": "r"}]}
    errs = validate(bad)
    assert any("freq and impact" in e for e in errs) and any("unknown status" in e for e in errs) and any("duplicate id" in e for e in errs) and any("missing cause" in e for e in errs)


def test_the_document_on_disk_is_what_the_data_produces_and_counts_add_up():
    assert Path(OUT).read_text(encoding="utf-8") == render(D)          # regenerate with: python scripts/failure_points_doc.py
    c = counts(D["items"])
    assert sum(c.values()) == len(D["items"])
    assert "Scoreboard" in render(D) and "The highest remaining risks" in render(D)
