"""The awards importer's guards.

Two of these are load-bearing beyond this file. The gate check is the runbook's "the gate
decides" made enforceable rather than remembered, and the id-minting test is contract 5.4 -
the boundary that has cost three separate incidents on the conference side.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("ia", ROOT / "scripts" / "import_awards.py")
ia = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ia)

from src.cfp_monitor.storage import Store            # noqa: E402

COLS = ["EVENT_ID", "CONFERENCE", "CONFERENCE URL", "LOCATION", "SUBMISSION DEADLINE",
        "STATUS", "SUBMISSION URL", "CATEGORIES", "EDITION", "Market", "CITY",
        "STATE_PROVINCE", "COUNTRY", "MAIN_INFO_URL", "DEADLINE_EVIDENCE_URL",
        "DEADLINE_QUOTE", "IS_PROJECTED", "SOURCE_AS_OF", "OPPORTUNITY_TYPE", "ORGANIZER",
        "SPONSOR_REQUIRED", "SUBMISSION_OPENS", "ANNOUNCEMENT_DATE", "CFP MODEL TYPE",
        "OVERVIEW", "COORDINATOR EMAIL", "SPONSOR_URL", "SPONSOR_COST", "SPONSOR_QUOTE"]


def _row(**kw):
    base = {c: "" for c in COLS}
    base.update({"OPPORTUNITY_TYPE": "Awards", "Market": "Cybersecurity"})
    base.update(kw)
    return base


def _delivery(tmp_path, rows, name="Awards_out.csv"):
    p = tmp_path / name
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    return p


def _gate(tmp_path, delivery, passed=True):
    p = tmp_path / "gate.json"
    checks = [{"check": "1", "name": "structure", "passed": True, "failures": []},
              {"check": "3", "name": "quote", "passed": passed,
               "failures": [] if passed else ["a row"]}]
    p.write_text(json.dumps({delivery.name: checks}), encoding="utf-8")
    return p


def _db(tmp_path):
    p = tmp_path / "t.db"
    Store(str(p)).db.close()
    return str(p)


# ---- the gate decides ------------------------------------------------------------------
def test_refuses_when_a_gate_check_failed(tmp_path):
    d = _delivery(tmp_path, [_row(EVENT_ID="up-1", CONFERENCE="A", EDITION="2027")])
    ok, why = ia.gate_says_accepted(_gate(tmp_path, d, passed=False), d)
    assert not ok and "never imported" in why


def test_refuses_a_gate_run_on_a_different_file(tmp_path):
    """The subtle one: a real ACCEPTED json, for something else."""
    d = _delivery(tmp_path, [_row(EVENT_ID="up-1", CONFERENCE="A", EDITION="2027")])
    other = _delivery(tmp_path, [_row(EVENT_ID="up-1", CONFERENCE="A")], name="Other.csv")
    ok, why = ia.gate_says_accepted(_gate(tmp_path, other), d)
    assert not ok and "proves nothing" in why


def test_accepts_a_clean_gate_for_this_file(tmp_path):
    d = _delivery(tmp_path, [_row(EVENT_ID="up-1", CONFERENCE="A", EDITION="2027")])
    ok, _ = ia.gate_says_accepted(_gate(tmp_path, d), d)
    assert ok


# ---- 5.4: upstream's id is not ours ----------------------------------------------------
def test_mints_our_own_id_and_keeps_upstreams(tmp_path):
    d = _delivery(tmp_path, [_row(EVENT_ID="2026-time-worlds-top-nan-awards",
                                  CONFERENCE="TIME World's Top GreenTech Companies",
                                  EDITION="2026")])
    planned, problems, _skip = ia.plan(d, _db(tmp_path))
    assert not problems
    rec = planned[0]
    assert rec["upstream_event_id"] == "2026-time-worlds-top-nan-awards"
    assert "nan" not in rec["event_id"], "minting is the moment the artefact stops travelling"
    assert rec["event_id"].startswith("2026-") and rec["event_id"].endswith("-awards")


def test_a_row_with_no_city_keys_on_tbd_rather_than_inventing_one(tmp_path):
    d = _delivery(tmp_path, [_row(EVENT_ID="u", CONFERENCE="Some Prize", EDITION="2027")])
    planned, _p, _s = ia.plan(d, _db(tmp_path))
    assert planned[0]["event_id"] == "2027-some-prize-tbd-awards"


def test_two_rows_minting_one_id_is_refused_not_silently_merged(tmp_path):
    d = _delivery(tmp_path, [
        _row(EVENT_ID="u1", CONFERENCE="Same Award", EDITION="2027"),
        _row(EVENT_ID="u2", CONFERENCE="Same Award", EDITION="2027"),
    ])
    _planned, problems, _skip = ia.plan(d, _db(tmp_path))
    assert problems and "mint the same id" in problems[0]


# ---- separation ------------------------------------------------------------------------
def test_a_non_awards_row_is_excluded_and_named(tmp_path):
    """The awards market file really does carry a few Speaking and Registration rows.

    Coercing one into the award tables is the mixing the two pipelines are kept apart to
    prevent; dropping it silently is indistinguishable from a bug. So it is excluded, and
    named in the report.
    """
    d = _delivery(tmp_path, [_row(EVENT_ID="u", CONFERENCE="A Conference",
                                  EDITION="2027", OPPORTUNITY_TYPE="Speaking")])
    planned, problems, skipped = ia.plan(d, _db(tmp_path))
    assert planned == [] and problems == []
    assert len(skipped) == 1 and "not an award" in skipped[0]


# ---- the duplicate labelling is load-bearing -------------------------------------------
def _seed(tmp_path, pairs):
    p = tmp_path / "seed.csv"
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["CONFERENCE", "DUP_OF"])
        w.writeheader()
        for mark, survivor in pairs:
            w.writerow({"CONFERENCE": mark, "DUP_OF": survivor})
    return p


def test_a_labelled_duplicate_is_collapsed_onto_its_survivor(tmp_path):
    """slug() drops parentheticals, so these two mint one id - the same conclusion the
    duplicate pass reached from the other direction."""
    rows = [_row(EVENT_ID="u1", CONFERENCE="Fortress Cybersecurity Award", EDITION="2027"),
            _row(EVENT_ID="u2", EDITION="2027",
                 CONFERENCE="Fortress Cybersecurity Award (Business Intelligence Group)")]
    d = _delivery(tmp_path, rows)
    seed = _seed(tmp_path, [("Fortress Cybersecurity Award (Business Intelligence Group)",
                             "Fortress Cybersecurity Award")])
    planned, problems, skipped = ia.plan(d, _db(tmp_path), seed)
    assert problems == [], "a labelled duplicate must not still collide"
    assert len(planned) == 1 and planned[0]["upstream_event_id"] == "u1"
    assert len(skipped) == 1 and "DUP_OF" in skipped[0]


def test_an_unexplained_collision_is_still_refused(tmp_path):
    """The distinction that matters: a duplicate we DECIDED about may collapse; two rows that
    merely happen to collide may not."""
    rows = [_row(EVENT_ID="u1", CONFERENCE="Fortress Cybersecurity Award", EDITION="2027"),
            _row(EVENT_ID="u2", EDITION="2027",
                 CONFERENCE="Fortress Cybersecurity Award (Business Intelligence Group)")]
    d = _delivery(tmp_path, rows)
    empty = _seed(tmp_path, [])
    _planned, problems, _skipped = ia.plan(d, _db(tmp_path), empty)
    assert problems and "label one DUP_OF" in problems[0]


def test_import_never_touches_the_conference_tables(tmp_path):
    db = _db(tmp_path)
    con = sqlite3.connect(db)
    con.execute("insert into grounding_facts (event_id, name) values ('c-1', 'A Conference')")
    con.commit()
    con.close()

    d = _delivery(tmp_path, [_row(EVENT_ID="u", CONFERENCE="An Award", EDITION="2027")])
    planned, _p, _s = ia.plan(d, db)
    ia.apply(db, planned, "test")

    con = sqlite3.connect(db)
    assert con.execute("select count(*) from grounding_facts").fetchone()[0] == 1
    assert con.execute("select count(*) from conference_markets").fetchone()[0] == 0
    assert con.execute("select count(*) from award_grounding_facts").fetchone()[0] == 1
    con.close()


# ---- write, membership, reconcile ------------------------------------------------------
def test_market_membership_is_keyed_by_programme_not_host(tmp_path):
    """cloud-awards.com runs several programmes; a host key cannot tell them apart."""
    db = _db(tmp_path)
    d = _delivery(tmp_path, [
        _row(EVENT_ID="u1", CONFERENCE="The Security Awards", EDITION="2027",
             MAIN_INFO_URL="https://www.cloud-awards.com/programs/", Market="Cybersecurity"),
        _row(EVENT_ID="u2", CONFERENCE="The SaaS Awards", EDITION="2027",
             MAIN_INFO_URL="https://www.cloud-awards.com/programs/", Market="Utility"),
    ])
    planned, _p, _s = ia.plan(d, db)
    ia.apply(db, planned, "test")
    con = sqlite3.connect(db)
    rows = sorted(con.execute("select award_key, market from award_markets"))
    con.close()
    assert len(rows) == 2, "two programmes on one host must be two memberships"
    assert rows[0][0] != rows[1][0]
    assert {r[1] for r in rows} == {"Cybersecurity", "Utility"}


def test_reimport_updates_and_preserves_verify_state(tmp_path):
    db = _db(tmp_path)
    d = _delivery(tmp_path, [_row(EVENT_ID="u", CONFERENCE="An Award", EDITION="2027",
                                  **{"SUBMISSION DEADLINE": "2027-01-01"})])
    planned, _p, _s = ia.plan(d, db)
    ia.apply(db, planned, "test")

    con = sqlite3.connect(db)
    con.execute("update award_grounding_facts set verify_state='verified', "
                "verify_detail='checked by hand'")
    con.commit()
    con.close()

    d2 = _delivery(tmp_path, [_row(EVENT_ID="u", CONFERENCE="An Award", EDITION="2027",
                                   **{"SUBMISSION DEADLINE": "2027-02-02"})],
                   name="Awards_out2.csv")
    planned2, _p2, _s2 = ia.plan(d2, db)
    assert planned2[0]["_new"] is False
    ia.apply(db, planned2, "test")

    con = sqlite3.connect(db)
    row = con.execute("select deadline, verify_state, verify_detail "
                      "from award_grounding_facts").fetchone()
    n = con.execute("select count(*) from award_grounding_facts").fetchone()[0]
    con.close()
    assert n == 1, "a re-import updates, it never duplicates"
    assert row[0] == "2027-02-02", "the new deadline landed"
    assert row[1] == "verified" and row[2] == "checked by hand", \
        "an import must not tell the system a verified row became unverified again"


def test_reconcile_notices_a_missing_row(tmp_path):
    db = _db(tmp_path)
    d = _delivery(tmp_path, [_row(EVENT_ID="u", CONFERENCE="An Award", EDITION="2027")])
    planned, _p, _s = ia.plan(d, db)
    assert ia.reconcile(db, planned), "nothing written yet, so reconciliation must complain"
    ia.apply(db, planned, "test")
    assert ia.reconcile(db, planned) == []


def test_a_dup_of_pointing_at_a_customer_sheet_coordinate_is_not_a_deletion(tmp_path):
    """The eight pre-existing labels read like `Utility Global:23`.

    They say the customer already lists this award - a cross-reference, not an instruction to
    drop the row. One of them is Goldman Environmental Prize, whose citation was withdrawn by
    agreement on 2026-09-08; excluding it would have silently discarded that work.
    """
    d = _delivery(tmp_path, [_row(EVENT_ID="u", CONFERENCE="Goldman Environmental Prize 2026",
                                  EDITION="2026")])
    seed = _seed(tmp_path, [("Goldman Environmental Prize 2026", "Utility Global:46")])
    planned, problems, skipped = ia.plan(d, _db(tmp_path), seed)
    assert problems == [] and skipped == []
    assert len(planned) == 1, "a customer-sheet cross-reference must not drop the row"
