"""Step 4a guard: the build refuses a final.csv that is not a fresh, ACCEPTED, untampered
promotion. Replays 2026-09-14, when a cycle nobody promoted published last week's file with
every other check green.
"""
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import publish_guard as pg  # noqa: E402


# --- acceptance verdict, recomputed from the gate's own --json ----------------

def _accept_json(tmp_path, name, checks):
    p = tmp_path / "accept.json"
    p.write_text(json.dumps({name: checks}), encoding="utf-8")
    return p


def _chk(passed, failures=None):
    return {"check": "R1", "name": "x", "passed": passed, "failures": failures or []}


def test_verdict_accepted_when_all_pass(tmp_path):
    j = _accept_json(tmp_path, "d.csv", [_chk(True), _chk(True)])
    assert pg.acceptance_verdict(j, "d.csv")[0] == "ACCEPTED"


def test_verdict_rejected_on_a_real_failure(tmp_path):
    j = _accept_json(tmp_path, "d.csv", [_chk(True), _chk(False, ["quote not on page"])])
    assert pg.acceptance_verdict(j, "d.csv")[0] == "REJECTED"


def test_verdict_incomplete_when_a_check_was_skipped(tmp_path):
    j = _accept_json(tmp_path, "d.csv", [_chk(True), _chk(False, ["SKIPPED (--no-network)"])])
    assert pg.acceptance_verdict(j, "d.csv")[0] == "INCOMPLETE"


def test_verdict_not_found_for_a_different_file(tmp_path):
    j = _accept_json(tmp_path, "d.csv", [_chk(True)])
    assert pg.acceptance_verdict(j, "other.csv")[0] == "NOT_FOUND"


def test_verdict_unreadable_when_json_missing(tmp_path):
    assert pg.acceptance_verdict(tmp_path / "nope.json", "d.csv")[0] == "UNREADABLE"


# --- promote + freshness ------------------------------------------------------

def _promote(tmp_path, verdict="ACCEPTED", body="a,b\n1,2\n", when=None):
    final = tmp_path / "Cybersecurity_audited.final.csv"
    final.write_text(body, encoding="utf-8")
    pg.write_manifest(final, "Cybersecurity", tmp_path / "d.csv", tmp_path / "accept.json",
                      verdict, promoted_at=when or datetime.now())
    return final


def test_a_fresh_accepted_promotion_passes(tmp_path):
    final = _promote(tmp_path)
    ok, reason = pg.check_publish_fresh(final)
    assert ok, reason


def test_missing_manifest_is_refused(tmp_path):
    final = tmp_path / "Cybersecurity_audited.final.csv"
    final.write_text("a,b\n1,2\n", encoding="utf-8")
    ok, reason = pg.check_publish_fresh(final)
    assert not ok and "no promotion manifest" in reason


def test_non_accepted_promotion_is_refused(tmp_path):
    final = _promote(tmp_path, verdict="INCOMPLETE")
    ok, reason = pg.check_publish_fresh(final)
    assert not ok and "not an ACCEPTED" in reason


def test_edit_after_promote_is_caught_by_hash(tmp_path):
    final = _promote(tmp_path)
    final.write_text("a,b\n9,9\n", encoding="utf-8")   # tamper after the manifest was written
    ok, reason = pg.check_publish_fresh(final)
    assert not ok and "hash mismatch" in reason


def test_last_cycle_file_is_caught_as_stale(tmp_path):
    """The 2026-09-14 incident: a promotion from a week ago is stale for this build."""
    final = _promote(tmp_path, when=datetime.now() - timedelta(days=7))
    ok, reason = pg.check_publish_fresh(final)
    assert not ok and "stale" in reason


def test_freshness_window_is_configurable(tmp_path):
    final = _promote(tmp_path, when=datetime.now() - timedelta(days=3))
    assert pg.check_publish_fresh(final, max_age_days=4)[0] is True
    assert pg.check_publish_fresh(final, max_age_days=2)[0] is False


def test_missing_file_is_refused(tmp_path):
    ok, reason = pg.check_publish_fresh(tmp_path / "nope.final.csv")
    assert not ok and "does not exist" in reason
