"""docs/qa/trap-cases.json: the cases that have fooled us must keep passing in the code we run; known gaps stay recorded as gaps."""
from scripts.trap_cases import load_cases, run_all, score_method


def test_no_trap_case_fails_in_the_code_we_run():
    res = run_all(load_cases())
    failed = [(r["id"], r["details"]) for r in res if r["result"] == "FAIL"]
    assert not failed, failed
    assert len(res) >= 12


def test_the_three_former_gaps_are_closed_and_stay_closed():
    res = {r["id"]: r["result"] for r in run_all(load_cases())}
    assert res["T04"] == "PASS"      # ACT-13: the earliest open deadline is the default, the other recorded
    assert res["T05"] == "PASS"      # ACT-14: an aggregator citation is flagged (offline host rule; and by page when the page is read)
    assert res["T02"] == "PASS"      # ACT-15: a header prints the dates bare beside the place; the year check is intact


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


# ---- ACT-13 / ACT-14 / ACT-15: the rules behind the three closed gaps, and what they must NOT accept -----------------------
from datetime import date as _date


def test_earliest_deadline_picks_the_earliest_open_round_and_records_the_other():
    from src.cfp_monitor.verify import earliest_deadline
    t = "Abstract submission deadline: November 16, 2026. Research paper submission deadline: November 23, 2026."
    assert earliest_deadline(t, _date(2026, 10, 3)) == {"date": "2026-11-16", "others": ["2026-11-23"], "passed": []}
    # the first round has closed: the next OPEN one is the default, the closed one is listed as passed
    assert earliest_deadline(t, _date(2026, 11, 20)) == {"date": "2026-11-23", "others": [], "passed": ["2026-11-16"]}
    assert earliest_deadline(t, _date(2026, 12, 1))["date"] == ""                       # nothing open: honest blank
    # a conference date or a price date is not a deadline
    assert earliest_deadline("The conference takes place June 8, 2027. Early bird ends April 1, 2027.", _date(2026, 10, 3))["date"] == ""


def test_aggregator_flag_by_host_and_by_page():
    from src.cfp_monitor.rules import aggregator_citation_flag, is_aggregator_url
    assert is_aggregator_url("https://www.cfptime.org/x") and is_aggregator_url("https://sub.confs.tech/")
    assert not is_aggregator_url("https://sessionize.com/apres-cyber/") and not is_aggregator_url("https://notcfptime.org.evil.example/")
    assert not aggregator_citation_flag("https://sessionize.com/apres-cyber/")                   # the organizer's platform is fine
    assert "does not name the event" in aggregator_citation_flag("https://cfptime.org/", "CFP Time. BSides Boston", "Apres-Cyber Slopes Summit")
    assert "third-party listing" in aggregator_citation_flag("https://cfptime.org/")


def test_the_gate_notes_an_aggregator_citation_but_does_not_reject(tmp_path):
    from scripts.accept_delivery import Gate
    g = Gate(str(tmp_path / "x.csv"), network=False)
    g.rows = [{"CONFERENCE": "Apres-Cyber", "DEADLINE_EVIDENCE_URL": "https://cfptime.org/"}]
    import inspect
    from scripts import accept_delivery
    assert "R22a" in inspect.getsource(accept_delivery.Gate.check_schema_rules)
    from scripts.post_load_qa import aggregator_citations
    out = aggregator_citations("Cybersecurity", g.rows)
    assert len(out) == 1 and "cfptime.org" in out[0]
    assert aggregator_citations("Cybersecurity", [{"CONFERENCE": "x", "DEADLINE_EVIDENCE_URL": "https://example.org/cfp"}]) == []


def test_header_date_rule_accepts_a_place_beside_the_date_and_nothing_looser():
    from src.cfp_monitor.self_heal import find_conference_dates_sentence as f
    hdr = "Menino Convention and Exhibition Center, Boston, MA | May 10, 2027 - May 12, 2027 REGISTER NOW"
    assert f(hdr, "2027-05-10")[0]
    assert f("May 10, 2027 - May 12, 2027 | Boston, MA REGISTER", "2027-05-10")[0]               # the reverse order
    assert not f(hdr, "2026-05-10")[0]                                                           # the year stays bound to the date asked for
    assert not f("Early bird ends May 10, 2027 | Register now", "2027-05-10")[0]                 # a date by a pipe is not a header
    assert not f("Sale | May 10, 2027 | Terms apply", "2027-05-10")[0]
    assert not f("Posted in Boston, MA on May 10, 2027 by the editor", "2027-05-10")[0]          # no separator
