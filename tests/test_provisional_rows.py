"""Provisional rows (ACT-68): researched rows the approved file does not carry yet.

The decisions pinned here: a row the approved file already has is NEVER provisional (by the permanent id through identity.to_canonical, or by name / deep URL when the research row has no id yet);
a stub, a nameless row and a second row for the same award are left out and counted; an Open row never survives its deadline; no confidence badge travels with a provisional row; and the research file
of a previous cycle is not used at all."""
from __future__ import annotations

import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import provisional_rows as pr                                  # noqa: E402

ON = date(2026, 10, 12)


def row(name, eid, market="Utility", **kw):
    r = {"EVENT_ID": eid, "CONFERENCE": name, "Market": market, "OPPORTUNITY_TYPE": "Awards", "STATUS": "Open", "SUBMISSION DEADLINE": "2026-12-01", "CITY": "", "STATE_PROVINCE": "",
         "COUNTRY": "", "FORMAT": "", "GROUNDING_CONFIDENCE": "Verified (2026)", "IS_PROJECTED": "false", "STATUS DETAILS": "", "SUBMISSION URL": "", "CONFERENCE URL": "",
         "DEADLINE_QUOTE": "", "ORGANIZER": "", "TRACK": ""}
    r.update(kw)
    return r


def test_a_row_the_approved_file_has_by_permanent_id_is_not_provisional():
    approved = [row("Grist 50", "2027-grist-50-nan-awards")]
    raw = [row("Grist 50 (renamed by upstream)", "2027-grist-50-tbd-awards")]
    # upstream renamed its output id; the permanent id of the input row (identity file) and the lookup say it is the approved row
    res = pr.candidates(raw, {"2027-grist-50-tbd-awards": "grist-50-perm"}, approved, {"2027-grist-50-nan-awards": "grist-50-perm"})
    assert res["rows"] == []


def test_the_same_permanent_id_in_the_OTHER_market_does_not_hide_it():
    approved = [row("Fast Company MIC", "2027-fc-mic", market="Cybersecurity")]
    raw = [row("Fast Company MIC", "2027-fc-mic-u", market="Utility")]
    res = pr.candidates(raw, {"2027-fc-mic-u": "fc-mic-perm"}, approved, {"2027-fc-mic": "fc-mic-perm"})
    assert [c["name"] for c in res["rows"]] == ["Fast Company MIC"] and res["rows"][0]["category"] == "not_loaded"


def test_an_id_given_but_not_loaded_is_not_loaded_and_a_blank_id_is_waiting():
    raw = [row("New Award A", "2027-a", ), row("New Award B", "2027-b")]
    res = pr.candidates(raw, {"2027-a": "perm-a", "2027-b": ""}, [], {})
    cat = {c["name"]: c["category"] for c in res["rows"]}
    assert cat == {"New Award A": "not_loaded", "New Award B": "waiting_for_id"}


def test_no_id_yet_is_recognised_by_name_without_year_or_brackets_like_the_customer_sheets():
    approved = [row("Computing Security Awards", "2026-computing-security-awards")]
    raw = [row("Computing Security Awards (computingsecurityawards.co.uk)", "2026-csa-x")]
    assert pr.candidates(raw, {"2026-csa-x": ""}, approved, {})["rows"] == []


def test_no_id_yet_is_recognised_by_a_deep_submission_url_but_not_a_bare_website():
    approved = [row("Alpha Awards", "2026-alpha", **{"SUBMISSION URL": "https://x.org/awards/alpha"}),
                row("Beta Awards", "2026-beta", **{"SUBMISSION URL": "https://bare.org/"})]
    raw = [row("Alpha Prize Programme", "2026-a2", **{"SUBMISSION URL": "https://www.x.org/awards/alpha/"}),
           row("Gamma Prize", "2026-g", **{"SUBMISSION URL": "https://bare.org/"})]
    res = pr.candidates(raw, {"2026-a2": "", "2026-g": ""}, approved, {})
    assert [c["name"] for c in res["rows"]] == ["Gamma Prize"], "a deep URL matches; the bare website of another award does not"


def test_a_url_used_by_two_different_awards_names_nothing():
    approved = [row("Family One", "2026-f1", **{"SUBMISSION URL": "https://x.org/family"}), row("Family Two", "2026-f2", **{"SUBMISSION URL": "https://x.org/family"})]
    raw = [row("Family Three", "2026-f3", **{"SUBMISSION URL": "https://x.org/family"})]
    assert len(pr.candidates(raw, {"2026-f3": ""}, approved, {})["rows"]) == 1


def test_a_row_with_an_id_is_not_hidden_by_a_look_alike_name():
    """ACT-66's cause: a stale 2026 row and a researched 2027 row share a name key. A row WITH a permanent id is judged by the id alone."""
    approved = [row("Fast Company Most Innovative Companies 2026", "2026-fc-mic")]
    raw = [row("Fast Company Most Innovative Companies 2027", "2027-fc-mic")]
    res = pr.candidates(raw, {"2027-fc-mic": "perm-2027"}, approved, {"2026-fc-mic": "perm-2026"})
    assert len(res["rows"]) == 1


def test_stubs_nameless_and_second_rows_are_left_out_and_counted():
    raw = [row("Real Award", "2027-r"), row("Stub Award", "2027-s", **{"STATUS DETAILS": "Audit Exception: every attempt failed"}), row("--", "2027-n"), row("Real Award", "2027-r2")]
    res = pr.candidates(raw, {"2027-r": "p1", "2027-r2": "p1", "2027-s": "p2", "2027-n": "p3"}, [], {})
    assert [c["name"] for c in res["rows"]] == ["Real Award"]
    assert sum(res["excluded"].values()) == 3 and "a stub: not researched this week" in res["excluded"]


def test_conferences_need_the_exact_name_because_the_year_is_the_edition():
    approved = [row("Black Hat USA 2026", "2026-bh", market="Cybersecurity")]
    raw = [row("Black Hat USA 2027", "2027-bh", market="Cybersecurity")]
    assert len(pr.candidates(raw, {"2027-bh": ""}, approved, {}, kind="conference")["rows"]) == 1
    assert pr.candidates([row("Black Hat USA 2026", "x", market="Cybersecurity")], {"x": ""}, approved, {}, kind="conference")["rows"] == []


def test_the_status_is_never_open_after_its_deadline():
    assert pr.derive_status(row("A", "a", **{"SUBMISSION DEADLINE": "2026-10-09"}), ON)["STATUS"] == "Closed"
    assert pr.derive_status(row("A", "a", STATUS="Upcoming", **{"SUBMISSION DEADLINE": "2026-10-11"}), ON)["STATUS"] == "Closed"
    assert pr.derive_status(row("A", "a", **{"SUBMISSION DEADLINE": "2026-10-12"}), ON)["STATUS"] == "Open", "today is not past"
    assert pr.derive_status(row("A", "a", **{"SUBMISSION DEADLINE": ""}), ON)["STATUS"] == "Open"
    assert pr.derive_status(row("A", "a", STATUS="Needs Verification", **{"SUBMISSION DEADLINE": "2026-01-01"}), ON)["STATUS"] == "Needs Verification"


def test_page_rows_carry_no_confidence_and_no_placeholder_places_and_are_tagged():
    cands = [{"row": row("Award" + chr(0xFFFD) + "s Show", "x", CITY="nan", COUNTRY="TBD"), "canon": "", "category": "waiting_for_id", "name": "n", "market": "Utility"}]
    out = pr.to_page_rows(cands, ON)[0]
    assert out["_PROVISIONAL"] == "1" and out["GROUNDING_CONFIDENCE"] == "" and out["IS_PROJECTED"] == ""
    assert out["CITY"] == "" and out["COUNTRY"] == "" and out["CONFERENCE"] == "Award's Show"
    assert cands[0]["row"]["CITY"] == "nan", "the candidate itself is not edited"


def test_a_research_file_from_a_previous_cycle_is_not_used(tmp_path):
    p = tmp_path / "Awards_audited.csv"
    p.write_text("EVENT_ID\n", encoding="utf-8")
    assert pr.find_raw(tmp_path, "Awards", ON)[0] == p
    old = time.time() - 12 * 86400
    os.utime(p, (old, old))
    path, note = pr.find_raw(tmp_path, "Awards", ON)
    assert path is None and "no research this cycle" in note
    assert pr.find_raw(tmp_path / "nowhere", "Awards", ON)[0] is None


def test_awards_candidates_end_to_end(tmp_path):
    import csv
    cols = list(row("x", "x").keys())

    def write(path, rows, cols_=cols):
        with open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols_)
            w.writeheader()
            w.writerows(rows)
    write(tmp_path / "Awards_audited.csv", [row("Held Award", "2027-held"), row("Loaded Award", "2027-loaded-new")])
    write(tmp_path / "Awards_audited.identity.csv", [{"OUTPUT_EVENT_ID": "2027-held", "OUTPUT_CONFERENCE": "Held Award", "INPUT_CONFERENCE": "Held Award", "EVENT_ID_CANON": ""},
                                                  {"OUTPUT_EVENT_ID": "2027-loaded-new", "OUTPUT_CONFERENCE": "Loaded Award", "INPUT_CONFERENCE": "Loaded Award", "EVENT_ID_CANON": "perm-loaded"}],
          ["OUTPUT_EVENT_ID", "OUTPUT_CONFERENCE", "INPUT_CONFERENCE", "EVENT_ID_CANON"])
    approved = [row("Loaded Award", "2027-loaded-old")]
    res, note, raw = pr.awards_candidates(tmp_path, approved, None, ON, lookup={"2027-loaded-old": "perm-loaded"})
    assert raw == tmp_path / "Awards_audited.csv" and note == ""
    assert [c["name"] for c in res["rows"]] == ["Held Award"], "the approved row is tied to its permanent id through the lookup; the unmatched blank-id row is provisional"
    res, note, _raw = pr.awards_candidates(tmp_path, approved, tmp_path / "no-such.db", ON)
    assert res["rows"] == [] and "lookup could not be read" in note, "no lookup: nothing is guessed, and the page is built without provisional rows"


def test_a_market_sibling_row_shows_the_provisional_award_to_the_other_customer_too():
    raw = [row("Fast Company MIC 2027", "2027-fc", market="Utility")]
    sibs = pr.awards_siblings([{"CONFERENCE": "Fast Company MIC 2027", "Market": "Cybersecurity", "DUP_OF": "MARKET_SIBLING", "EVENT_ID_CANON": ""},
                               {"CONFERENCE": "Fast Company MIC 2027", "Market": "Utility", "DUP_OF": "", "EVENT_ID_CANON": "perm-fc"}])
    assert sibs == [{"name": "Fast Company MIC 2027", "market": "Cybersecurity", "canon": "perm-fc"}]
    res = pr.candidates(raw, {"2027-fc": "perm-fc"}, [], {}, siblings=sibs)
    assert sorted((c["market"], bool(c.get("sibling"))) for c in res["rows"]) == [("Cybersecurity", True), ("Utility", False)]
    assert [c["row"]["Market"] for c in res["rows"]] == ["Utility", "Cybersecurity"], "the copy carries the sibling's market; the primary row is not edited"
    # already approved for the sibling's market: no second provisional row
    done = pr.candidates(raw, {"2027-fc": "perm-fc"}, [row("Fast Company MIC 2027", "2027-fc-old", market="Cybersecurity")], {"2027-fc-old": "perm-fc"}, siblings=sibs)
    assert [c["market"] for c in done["rows"]] == ["Utility"]
