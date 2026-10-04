"""scripts/board_metrics.py: the customer-agreement number is a defined, reproducible query (2026-10-02)."""
from __future__ import annotations

import csv
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("bm", ROOT / "scripts" / "board_metrics.py")
bm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bm)


def _db(path: Path, client_rows: list[tuple], conf: dict[str, str], awards: dict[str, str] | None = None) -> str:
    con = sqlite3.connect(path)
    con.execute("create table client_conferences (client_key text, their_name text, event_id text, their_deadline text, "
                "submission_date_verified text, withdrawn_by_customer integer)")
    con.execute("create table grounding_facts (event_id text, deadline text)")
    con.execute("create table award_grounding_facts (event_id text, deadline text)")
    con.executemany("insert into client_conferences values (?,?,?,?,?,?)", client_rows)
    con.executemany("insert into grounding_facts values (?,?)", list(conf.items()))
    con.executemany("insert into award_grounding_facts values (?,?)", list((awards or {}).items()))
    con.commit()
    con.close()
    return str(path)


def test_their_date_parsing():
    assert bm.parse_their_date("07/15/2026") == "2026-07-15"
    assert bm.parse_their_date(" 2026-07-15 ") == "2026-07-15"
    assert bm.parse_their_date("TBD") is None and bm.parse_their_date("") is None
    assert bm.parse_their_date("15/07/2026") is None                   # day-first is not guessed


def test_the_four_classes(tmp_path):
    rows = [("a", "Same", "e1", "10/15/2026", "Verified", 0),
            ("a", "Blank", "e2", "10/16/2026", "verified", 0),
            ("a", "Differ", "e3", "10/17/2026", "Verified", 0),
            ("a", "Garbage", "e4", "TBD", "Verified", 0)]
    db = _db(tmp_path / "x.db", rows, {"e1": "2026-10-15", "e2": "", "e3": "2026-12-01", "e4": "2026-10-01"})
    r = bm.customer_agreement(db)
    assert r["counts"] == {"agree": 1, "blank": 1, "differ": 1, "unreadable": 1} and r["rows"] == 4


def test_withdrawn_unverified_and_dateless_rows_are_not_in_the_population(tmp_path):
    rows = [("a", "Withdrawn", "e1", "10/15/2026", "Verified", 1),
            ("a", "Estimate", "e2", "10/15/2026", "Internal Estimate", 0),
            ("a", "No date", "e3", "", "Verified", 0),
            ("a", "Counted", "e4", "10/15/2026", "Verified", 0)]
    db = _db(tmp_path / "x.db", rows, {f"e{i}": "2026-10-15" for i in range(1, 5)})
    r = bm.customer_agreement(db)
    assert r["rows"] == 1 and r["counts"]["agree"] == 1


def test_awards_are_looked_up_in_their_own_table(tmp_path):
    db = _db(tmp_path / "x.db", [("a", "Award", "aw1", "10/06/2026", "Verified", 0)], {}, awards={"aw1": "2026-10-06"})
    assert bm.customer_agreement(db, kind="award")["counts"]["agree"] == 1          # a customer line linked to an award row is read against the award table
    assert bm.customer_agreement(db)["counts"]["agree"] == 0                         # and never against the conference table


def test_a_row_not_in_our_database_is_reported_not_counted(tmp_path):
    db = _db(tmp_path / "x.db", [("a", "Ghost", "nope", "10/06/2026", "Verified", 0)], {})
    r = bm.customer_agreement(db)
    assert r["rows"] == 0 and r["unmatched_to_our_db"] == 1


def test_update_status_changes_only_the_customer_headline(tmp_path):
    sj = tmp_path / "status.json"
    sj.write_text(json.dumps({"headline": {"customer": {"label": "L", "rows": 40, "levels": [], "note": "keep me", "source": "old"},
                                           "provable": {"rows": 39}}, "other": [1, 2]}), encoding="utf-8")
    cur = {"rows": 5, "counts": {"agree": 3, "blank": 1, "differ": 1, "unreadable": 0}}
    bm.update_status(cur, "2026-10-05", sj)
    d = json.loads(sj.read_text(encoding="utf-8"))
    assert d["headline"]["customer"]["rows"] == 5 and [l["n"] for l in d["headline"]["customer"]["levels"]] == [3, 1, 1]
    assert d["headline"]["customer"]["note"] == "keep me" and "2026-10-05" in d["headline"]["customer"]["source"]
    assert d["headline"]["provable"] == {"rows": 39} and d["other"] == [1, 2]


def test_render_mentions_the_change_when_a_backup_is_given(tmp_path):
    a = _db(tmp_path / "a.db", [("a", "X", "e1", "10/15/2026", "Verified", 0)], {"e1": ""})
    b = _db(tmp_path / "b.db", [("a", "X", "e1", "10/15/2026", "Verified", 0)], {"e1": "2026-10-15"})
    text = bm.render(bm.customer_agreement(b), bm.customer_agreement(a), 3)
    assert "agree 0 -> 1" in text and "blank 1 -> 0" in text


# ---- live vs all (2026-10-02) ------------------------------------------------------------------------
def _live_db(tmp_path):
    db = tmp_path / "live.db"
    con = sqlite3.connect(db)
    con.execute("create table grounding_facts (event_id text, name text, deadline text, verify_state text, verify_detail text, deadline_evidence_url text)")
    con.executemany("insert into grounding_facts values (?,?,?,?,?,?)", [
        ("ok", "Proven", "2026-12-01", "verified", "[L2] page states 2026-12-01", "http://p"),
        ("blocked", "Blocked", "2026-12-02", "not_found", "[L2] the cited page could not be read - grounding stands", "http://b"),
        ("nocite", "Withdrawn", "2026-12-03", "not_found", "", ""),
        ("miss", "Absent", "2026-12-04", "not_found", "[L2] page read, date not found", "http://m"),
        ("diff", "Different", "2026-12-05", "contradicted", "[L2] page states another date", "http://d"),
        ("past", "Past", "2026-01-01", "verified", "", "http://q"),
        ("offlist", "Not on a seed sheet", "2026-12-06", "verified", "", "http://o")])
    con.commit()
    con.close()
    sd = tmp_path / "market_sheets"
    sd.mkdir()
    for name, ids in (("cyber_seed.csv", ["ok", "blocked", "past"]), ("utility_seed.csv", ["nocite", "miss", "diff"])):
        with open(sd / name, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["EVENT_ID", "EVENT_ID_CANON"])
            for i in ids:
                w.writerow(["u-" + i, i])
    return str(db)


def test_provable_live_classes_and_scope(tmp_path):
    r = bm.provable_live(_live_db(tmp_path), "2026-10-02")
    assert r["rows"] == 5                                              # past and off-list rows are not scored
    assert r["counts"] == {"verified": 1, "withdrawn": 1, "unreadable": 1, "notfound": 1, "contradicted": 1, "unchecked": 0}


def test_a_deadline_equal_to_today_is_live(tmp_path):
    assert bm.provable_live(_live_db(tmp_path), "2026-12-01")["counts"]["verified"] == 1


def test_customer_live_split(tmp_path):
    rows = [("a", "Both past", "e1", "01/15/2026", "Verified", 0), ("a", "Live agree", "e2", "12/01/2026", "Verified", 0),
            ("a", "Live blank", "e3", "12/02/2026", "Verified", 0), ("a", "Customer old round", "e4", "06/19/2026", "Verified", 0)]
    db = _db(tmp_path / "x.db", rows, {"e1": "2026-02-01", "e2": "2026-12-01", "e3": "", "e4": "2026-10-19"})
    r = bm.customer_agreement(db, "2026-10-02")
    assert r["live_counts"] == {"agree": 1, "blank": 1, "differ": 0, "unreadable": 0} and r["live_rows"] == 2
    assert r["live_side"]["edition"] == 1                              # the customer's earlier round is reported beside the figure, not as a different date
    assert r["counts"]["differ"] == 1                                  # the all-rows view still counts the past one


def test_update_status_writes_both_headlines_live_first(tmp_path):
    sj = tmp_path / "status.json"
    sj.write_text(json.dumps({"headline": {"customer": {"label": "x"}, "provable": {"label": "y"}},
                              "objective": {"good": [{"label": "Provable submission dates", "now": "old", "target": "t"},
                                                     {"label": "Agreement with customer-verified dates", "now": "old", "target": "t"}]}}), encoding="utf-8")
    cur = {"rows": 33, "counts": {"agree": 17, "blank": 9, "differ": 7, "unreadable": 0},
           "live_counts": {"agree": 4, "blank": 3, "differ": 2, "unreadable": 0}, "live_rows": 9}
    prov = {"rows": 10, "counts": {"verified": 6, "withdrawn": 1, "unreadable": 3, "notfound": 0, "contradicted": 0}}
    bm.update_status(cur, "2026-10-02", sj, prov=prov)
    d = json.loads(sj.read_text(encoding="utf-8"))
    assert d["headline"]["customer"]["rows"] == 9 and d["headline"]["customer"]["levels"][0]["n"] == 4
    assert d["headline"]["provable"]["rows"] == 10 and d["headline"]["provable"]["levels"][0]["n"] == 6
    assert "17 of 33" in d["headline"]["customer"]["note"]
    assert d["objective"]["good"][0]["now"].startswith("6 of 10") and d["objective"]["good"][1]["now"].startswith("4 of 9")


# ---- conference and award indexes are separate (2026-10-02) ---------------------------------------------------
def _split_db(tmp_path):
    db = tmp_path / "split.db"
    con = sqlite3.connect(db)
    con.execute("create table grounding_facts (event_id text, conference_key text, name text, deadline text, verify_state text, verify_detail text, "
                "deadline_evidence_url text, url text)")
    con.execute("create table award_grounding_facts (event_id text, conference_key text, name text, deadline text, verify_state text, verify_detail text, "
                "deadline_evidence_url text, url text)")
    con.execute("create table award_markets (award_key text, market text, source_list text, first_seen text)")
    con.execute("create table client_conferences (client_key text, their_name text, event_id text, their_deadline text, submission_date_verified text, "
                "withdrawn_by_customer integer, their_url text)")
    con.executemany("insert into grounding_facts values (?,?,?,?,?,?,?,?)", [("c1", "c.org", "Conf", "2026-12-01", "verified", "", "http://c", "http://c.org")])
    con.executemany("insert into award_grounding_facts values (?,?,?,?,?,?,?,?)", [
        ("a1", "a.org", "Award ok", "2026-12-02", "verified", "verified 2026-09-28 x", "http://a", "http://a.org"),
        ("a2", "b.org", "Award unchecked", "2026-12-03", "unverified", None, "http://b", "http://b.org"),
        ("a3", "c.org", "Award unreadable", "2026-12-04", "unverified", "unreadable 2026-09-28 http://u", "http://u", "http://c.org"),
        ("a4", "d.org", "Award off list", "2026-12-05", "verified", "", "http://d", "http://d.org")])
    con.executemany("insert into award_markets values (?,?,?,?)", [("a1", "Utility", "", ""), ("a2", "Cybersecurity", "", ""), ("a3", "Utility", "", "")])
    con.executemany("insert into client_conferences values (?,?,?,?,?,?,?)", [("x", "Conf", "c1", "12/01/2026", "Verified", 0, "http://c.org")])
    con.commit()
    con.close()
    sd = tmp_path / "market_sheets"
    sd.mkdir()
    with open(sd / "cyber_seed.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["EVENT_ID", "EVENT_ID_CANON"])
        w.writerow(["u-c1", "c1"])
    return str(db)


def test_award_proof_uses_the_award_table_and_the_award_market_list(tmp_path):
    db = _split_db(tmp_path)
    r = bm.provable_live(db, "2026-10-02", "award")
    assert r["rows"] == 3                                              # a4 is on no award list
    assert r["counts"]["verified"] == 1 and r["counts"]["unchecked"] == 1 and r["counts"]["unreadable"] == 1
    assert bm.provable_live(db, "2026-10-02", "conference")["rows"] == 1   # never mixes


def test_customer_agreement_and_coverage_never_cross_kinds(tmp_path):
    db = _split_db(tmp_path)
    assert bm.customer_agreement(db, "2026-10-02", "conference")["live_rows"] == 1
    assert bm.customer_agreement(db, "2026-10-02", "award")["live_rows"] == 0
    assert bm.coverage_live(db, "2026-10-02", "conference")["rows"] == 1 and bm.coverage_live(db, "2026-10-02", "award")["rows"] == 0


def test_award_process_driver_names_the_disabled_job(tmp_path):
    d = bm.process_drivers(str(tmp_path), "2026-10-02", "award")
    assert any("disabled" in x for x in d)


def test_award_freshness_reads_the_awards_file_and_ignores_stale_and_stub_rows(tmp_path):
    md = tmp_path / "Markets"
    md.mkdir()
    with open(md / "Awards_20261002_out.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["EVENT_ID", "SOURCE_AS_OF", "STATUS DETAILS"])
        w.writeheader()
        w.writerows([{"EVENT_ID": "a", "SOURCE_AS_OF": "2026-10-01", "STATUS DETAILS": ""},
                     {"EVENT_ID": "b", "SOURCE_AS_OF": "2026-09-05", "STATUS DETAILS": ""},
                     {"EVENT_ID": "c", "SOURCE_AS_OF": "2026-10-01", "STATUS DETAILS": "Audit Exception: failed"}])
    assert bm.freshness_last_run(str(md), "2026-10-02", "award") == {"rows": 3, "researched": 1, "stubs": 1}


def test_spotchecks_are_filtered_by_kind(tmp_path):
    sp = tmp_path / "s.json"
    sp.write_text(json.dumps({"checks": [{"rows": 7, "rows_with_error": 3}, {"kind": "award", "rows": 4, "rows_with_error": 0}]}), encoding="utf-8")
    assert bm.spotcheck_summary(sp, "conference") == {"rows": 7, "bad": 3, "checks": 1}
    assert bm.spotcheck_summary(sp, "award") == {"rows": 4, "bad": 0, "checks": 1}


def test_market_canonical_ids_reads_only_the_customer_market_seed_sheets(tmp_path):
    from src.cfp_monitor.identity import market_canonical_ids
    (tmp_path / "x.db").write_bytes(b"")
    sd = tmp_path / "market_sheets"
    sd.mkdir()
    for name, ids in (("cyber_seed.csv", ["c1", "c2"]), ("utility_seed.csv", ["u1"]), ("robotics_seed.csv", ["r1"])):
        with open(sd / name, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["EVENT_ID", "EVENT_ID_CANON"])
            for i in ids:
                w.writerow(["up-" + i, i])
    ids = market_canonical_ids(str(tmp_path / "x.db"))     # seed_roots also searches the working directory second, by design
    assert {"c1", "c2", "u1"} <= ids and "r1" not in ids   # a prospect market's seed sheet is not a customer market


# --- Complete % and Accurate % (operator's definitions, 2026-10-03) ---
from scripts.board_metrics import expected_fields, far_future, split_scores   # noqa: E402

TODAY = "2026-10-03"


def _row(**k):
    base = {"event_id": "e", "name": "E", "edition": "2027", "start_date": "", "city": "X", "country": "Y", "main_info_url": "http://x",
            "deadline": "", "submission_url": "", "deadline_evidence_url": "", "deadline_quote": "", "status": "", "is_projected": 0, "verify_state": ""}
    base.update(k)
    return base


def test_far_future_event_without_an_open_call_is_not_penalised_for_missing_call_fields():
    r = _row(start_date="2027-06-08")                                   # 248 days out, nothing published
    exp, excused = expected_fields(r, TODAY)
    assert "deadline" in excused and "deadline" not in exp
    assert split_scores([r], TODAY, "conference")["complete"] == 100


def test_the_90_day_edge_and_an_open_call_lift_the_grace():
    assert far_future(_row(start_date="2027-01-02"), TODAY) is True      # 91 days
    assert far_future(_row(start_date="2027-01-01"), TODAY) is False     # 90 days: call fields are expected
    assert far_future(_row(start_date="2027-06-08", status="Open"), TODAY) is False
    assert far_future(_row(start_date="2027-06-08", deadline="2026-12-04"), TODAY) is False
    assert far_future(_row(start_date="2027-06-08", deadline="2026-12-04", is_projected=1), TODAY) is True


def test_a_blank_close_to_the_event_is_a_miss_but_a_pinned_honest_blank_is_not():
    r = _row(start_date="2026-12-01")
    assert split_scores([r], TODAY, "conference")["complete"] < 100
    pin = [{"canonical": "e", "set": {"DEADLINE": "", "CFP_SUBMISSION_URL": ""}}]
    s = split_scores([_row(start_date="2026-12-01", deadline_evidence_url="x", deadline_quote="x")], TODAY, "conference", pin)
    assert s["missing_by_field"] == {}


def test_accuracy_never_counts_unproven_as_wrong_but_a_contradiction_is_not_excused_by_the_grace():
    far = _row(start_date="2027-06-08", deadline="2027-01-10", is_projected=1)             # far-future, unproven
    near = _row(event_id="n", edition="2026", start_date="2026-12-01", deadline="2026-11-01", verify_state="contradicted", deadline_evidence_url="u")
    ok = _row(event_id="o", edition="2026", start_date="2026-12-01", deadline="2026-11-01", verify_state="verified", deadline_evidence_url="u")
    s = split_scores([far, near, ok], TODAY, "conference")
    assert (s["proven"], s["contradicted"], s["unproven_excused"], s["unproven"]) == (1, 1, 1, 0) and s["accurate"] == 50
    far2 = _row(event_id="f", start_date="2027-06-08", deadline="2027-01-10", is_projected=1, verify_state="contradicted")
    assert split_scores([far2], TODAY, "conference")["contradicted"] == 1


def test_year_rule_and_pins_feed_accuracy_and_passed_rows_are_out_of_scope():
    wrong_year = _row(start_date="2026-06-08", edition="2027")
    assert split_scores([wrong_year], TODAY, "conference")["rows_scored"] == 0          # passed: not scored
    r = _row(start_date="2027-06-08", edition="2026")
    assert split_scores([r], TODAY, "conference")["contradicted"] == 1
    p = [{"canonical": "e", "set": {"START DATE": "2027-06-08"}}]
    assert split_scores([_row(start_date="2027-06-08")], TODAY, "conference", p)["proven"] == 1
    assert split_scores([_row(start_date="2027-06-09")], TODAY, "conference", p)["contradicted"] == 1


# --- the three fixes (2026-10-03): operator pins prove a deadline, 90-day rule in both metrics, other-edition class ---
def _mini_db(tmp_path, grounding, client):
    import sqlite3
    db = str(tmp_path / "m.db")
    con = sqlite3.connect(db)
    con.execute("create table grounding_facts (event_id, name, deadline, verify_state, verify_detail, deadline_evidence_url, start_date, status, is_projected)")
    con.execute("create table client_conferences (client_key, their_name, event_id, their_deadline, submission_date_verified, withdrawn_by_customer, their_url)")
    con.executemany("insert into grounding_facts values (?,?,?,?,?,?,?,?,?)", grounding)
    con.executemany("insert into client_conferences values (?,?,?,?,?,?,?)", client)
    con.commit()
    con.close()
    return db


def test_customer_agreement_separates_other_edition_and_far_blank_from_a_real_difference(tmp_path):
    cl = [("c", "Same", "a", "11/01/2026", "Verified", 0, ""), ("c", "Older edition", "b", "03/31/2027", "Verified", 0, ""),
          ("c", "Earlier round", "d", "06/19/2026", "Verified", 0, ""), ("c", "Real diff", "e", "11/05/2026", "Verified", 0, ""),
          ("c", "Far blank", "f", "03/01/2027", "Verified", 0, ""), ("c", "Near blank", "g", "10/20/2026", "Verified", 0, "")]
    g = [("a", "A", "2026-11-01", "", "", "", "", "", 0), ("b", "B", "2026-03-31", "", "", "", "", "", 0), ("d", "D", "2026-10-19", "", "", "", "", "", 0),
         ("e", "E", "2026-11-09", "", "", "", "", "", 0), ("f", "F", "", "", "", "", "", "", 0), ("g", "G", "", "", "", "", "", "", 0)]
    r = bm.customer_agreement(_mini_db(tmp_path, g, cl), "2026-10-03")
    assert r["live_counts"] == {"agree": 1, "blank": 1, "differ": 1, "unreadable": 0}
    assert r["live_side"] == {"edition": 2, "excused": 1}


def test_provable_live_counts_operator_pins_as_proven_and_excuses_far_future_without_a_call(tmp_path, monkeypatch):
    import scripts.pinned_rows as pr
    monkeypatch.setattr(pr, "load_pins", lambda *a, **k: [{"canonical": "pin", "until": "2027-12-31", "set": {"SUBMISSION DEADLINE": "2026-12-04"}}])
    import src.cfp_monitor.identity as idn
    monkeypatch.setattr(idn, "market_canonical_ids", lambda db: {"pin", "far", "firm", "near"})
    g = [("pin", "Pinned", "2026-12-04", "not_found", "", "u", "2027-06-01", "Open", 0),         # operator read it: proven
         ("far", "Far", "2027-01-10", "unverified", "", "", "2027-06-01", "Upcoming", 1),         # far off, projected: excused
         ("firm", "Firm", "2026-12-10", "not_found", "", "u", "2027-06-01", "Upcoming", 0),       # firm call: still scored
         ("near", "Near", "2026-11-01", "unverified", "", "", "2026-12-01", "Upcoming", 1)]
    r = bm.provable_live(_mini_db(tmp_path, g, []), "2026-10-03")
    assert (r["rows"], r["counts"]["verified"], r["operator_verified"], r["excused_far_future"]) == (3, 1, 1, 1)


# --- awards grace (2026-10-04): a Closed award with no new cycle announced is not expected to carry a deadline, link or evidence ---
def _award(**k):
    base = {"event_id": "a", "name": "A", "edition": "2026", "status": "Closed", "deadline": "", "submission_opens": "", "main_info_url": "http://a", "submission_url": "",
            "deadline_evidence_url": "", "deadline_quote": "", "is_projected": 0, "verify_state": ""}
    base.update(k)
    return base


def test_a_closed_award_with_no_new_cycle_is_not_penalised_for_a_blank_call():
    r = _award()
    exp, excused = expected_fields(r, TODAY, "award")
    assert "deadline" in excused and exp == ["main_info_url"]
    assert split_scores([r], TODAY, "award")["complete"] == 100


def test_an_award_with_a_date_ahead_or_an_open_call_is_expected_to_be_complete():
    for r in (_award(status="Open"), _award(status="Upcoming"), _award(deadline="2026-12-01"), _award(submission_opens="2026-11-01"), _award(status="Needs Verification")):
        exp, excused = expected_fields(r, TODAY, "award")
        assert "deadline" in exp and not excused, r


def test_an_award_whose_dates_are_not_announced_or_that_has_no_deadline_by_design_is_not_expected_to_carry_one():
    for model in ("Not Announced", "Invitation Only", "Rolling Form"):
        exp, excused = expected_fields(_award(status="Upcoming", cfp_model=model), TODAY, "award")
        assert set(excused) == {"deadline", "deadline_evidence_url", "deadline_quote"} and "submission_url" in exp
    exp, excused = expected_fields(_award(status="Upcoming", cfp_model="Fixed Deadline"), TODAY, "award")
    assert "deadline" in exp and not excused
