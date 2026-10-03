"""scripts/failure_steps.py: the reasons the weekly load records, classified by the step that failed. The strings are the real ones from the 2026-10-03 live load."""
import json

from scripts.failure_steps import STEPS, append_history, classify, counts, line, load_history, rises, summarize


def test_real_reasons_from_the_2026_10_03_load_are_classified_by_step():
    assert classify(["no permanent id - cannot tell for certain which event this is, so it is not loaded (a rename would otherwise create a duplicate)"], "held-back") == "IDENTITY"
    assert classify(["[2] Gartner Identity & Access Mana: HTTP 404 https://infosec-conferences.com/cybersecurity-events-usa/"], "kept-last-week") == "FIND"
    assert classify(["[2] Black Hat Asia 2027: HTTP 404 (plain fetch said 403; a browser says 404) https://www.blackhat.com/x"], "held-back") == "FIND"
    assert classify(["[3] SecureWorld: paraphrase, date IS on page - \"Government & Critical Infrastructure. October 28, 20\""], "kept-last-week") == "PROVE"
    assert classify(["[3] Industrial Net Zero: quote and date both absent - \"Sale ends on 16-10-2026.\""], "kept-last-week") == "PROVE"
    assert classify(["[4] CarbonZero: The event is confirmed for October 27-29, 2026, in Brussels"], "kept-last-week") == "READ"
    assert classify(["year check: Y1 START DATE 2027-06-08 is not in edition 2026; Y2 CONFERENCE DATES year 2026 differs"], "kept-last-week") == "READ"
    assert classify(["not researched this week (every search attempt failed)"], "held-back") == "FIND"
    assert classify(["a second row for the same event (2026-x)"], "held-back") == "IDENTITY"
    assert classify(["not covered by this week's research"], "carried-over") == "COVERAGE"
    assert classify(["[1] line 2: 47 fields"], "held-back") == "FORMAT"


def test_summary_counts_each_decision_once_and_ignores_other_actions():
    dec = [{"action": "held-back", "conference": "A", "reasons": ["no permanent id - x"]},
           {"action": "kept-last-week", "conference": "B", "reasons": ["[2] B: HTTP 404 https://x"]},
           {"action": "kept-last-week", "conference": "C", "reasons": ["[3] C: paraphrase, date IS on page"]},
           {"action": "carried-over", "conference": "D", "reasons": ["not covered by this week's research"]},
           {"action": "shipped", "conference": "E", "reasons": []}]
    s = summarize(dec)
    assert counts(s) == {"IDENTITY": 1, "FIND": 1, "PROVE": 1, "READ": 0, "FORMAT": 0, "COVERAGE": 1}
    assert s["FIND"]["examples"] == ["B"] and set(counts(s)) == set(STEPS)
    assert line(counts(s)) == "FIND 1, PROVE 1, IDENTITY 1"


def test_history_is_appended_once_per_load_and_a_rise_is_reported(tmp_path):
    h = tmp_path / "step_failures.jsonl"
    r1 = {"stamp": "20261003-074945", "market": "Cybersecurity", "counts": {"FIND": 4, "PROVE": 2, "READ": 0, "IDENTITY": 3, "FORMAT": 0, "COVERAGE": 2}}
    append_history(h, r1)
    append_history(h, r1)                                                   # re-running the report must not double count
    r2 = {"stamp": "20261010-074000", "market": "Cybersecurity", "counts": {"FIND": 11, "PROVE": 2, "READ": 0, "IDENTITY": 3, "FORMAT": 0, "COVERAGE": 2}}
    append_history(h, r2)
    assert len(h.read_text(encoding="utf-8").strip().splitlines()) == 2
    hist = load_history(h, "Cybersecurity")
    assert [x["stamp"] for x in hist] == ["20261003-074945", "20261010-074000"]
    assert rises(hist[-1]["counts"], hist[-2]["counts"]) == ["FIND 4 -> 11"]
    assert rises(hist[-1]["counts"], None) == [] and load_history(h, "Utility") == []
    json.loads(h.read_text(encoding="utf-8").splitlines()[0])
