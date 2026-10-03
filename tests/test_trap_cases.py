"""docs/qa/trap-cases.json: the cases that have fooled us must keep passing in the code we run; known gaps stay recorded as gaps."""
from scripts.trap_cases import load_cases, run_all, score_method


def test_no_trap_case_fails_in_the_code_we_run():
    res = run_all(load_cases())
    failed = [(r["id"], r["details"]) for r in res if r["result"] == "FAIL"]
    assert not failed, failed
    assert len(res) >= 12


def test_the_two_known_gaps_are_recorded_not_hidden():
    res = {r["id"]: r["result"] for r in run_all(load_cases())}
    assert res["T04"] == "GAP" and res["T05"] == "GAP"      # earliest-of-two-deadlines; aggregator that does not list the event
    assert res["T02"] == "GAP"                              # the date prover needs an event word beside the date; a header prints it bare


def test_every_case_has_a_fixture_a_wrong_and_a_right_answer_and_checks():
    for c in load_cases():
        for k in ("id", "name", "event", "read_on", "went_wrong", "fixture", "wrong", "right", "checks"):
            assert c.get(k), (c.get("id"), k)


def test_a_method_is_scored_on_the_right_and_wrong_answers():
    cases = load_cases()
    good = lambda c: {"answer": c["right"]} if c["id"] == "T09" else None
    bad = lambda c: {"answer": c["wrong"]} if c["id"] == "T09" else None
    assert [r["result"] for r in score_method(cases, good) if r["id"] == "T09"] == ["PASS"]
    assert [r["result"] for r in score_method(cases, bad) if r["id"] == "T09"] == ["FAIL"]
