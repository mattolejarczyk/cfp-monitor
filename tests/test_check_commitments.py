"""scripts/check_commitments.py: did upstream do what it promised? (ACT-58). Fixtures only."""
import csv
import sqlite3
import sys
from pathlib import Path

from scripts import check_commitments as cc

COLS = ["EVENT_ID", "CONFERENCE", "STATUS", "START DATE", "CITY", "STATUS DETAILS"]
LCOLS = ["id", "promised_on", "note", "market", "event_id", "column", "op", "expected", "due", "what"]


def _write(path, rows, cols):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)


def _led(**kw):
    base = {"id": "C1", "promised_on": "2026-10-06", "note": "33", "market": "Utility", "event_id": "ev-a", "column": "STATUS", "op": "equals", "expected": "Upcoming", "due": "2026-10-10", "what": "w"}
    base.update(kw)
    return base


def _by(rows):
    return {r["EVENT_ID"]: r for r in rows}


ROWS = [{"EVENT_ID": "ev-a", "CONFERENCE": "A", "STATUS": " upcoming ", "START DATE": "", "CITY": "Houston", "STATUS DETAILS": "Postponed"},
        {"EVENT_ID": "ev-b", "CONFERENCE": "B", "STATUS": "Closed", "START DATE": "2027-01-01", "CITY": "Milan", "STATUS DETAILS": "It typically runs in August"}]


def test_equals_blank_contains_pass_and_ignore_case_and_spacing():
    f = lambda c: cc.judge(c, _by(ROWS), ROWS, "2026-10-11", True)[0]
    assert f(_led()) == "KEPT"                                                       # ' upcoming ' equals 'Upcoming'
    assert f(_led(column="START DATE", op="blank", expected="")) == "KEPT"
    assert f(_led(column="CITY", op="contains", expected="HOUS")) == "KEPT"
    assert f(_led(event_id="ev-b", column="CITY", op="not_contains", expected="Houston")) == "KEPT"


def test_a_wrong_value_after_the_due_date_is_not_kept_and_before_it_is_not_yet():
    c = _led(event_id="ev-b", column="STATUS", expected="Upcoming")
    state, detail = cc.judge(c, _by(ROWS), ROWS, "2026-10-11", True)
    assert state == "NOT KEPT" and "Closed" in detail and "Upcoming" in detail
    assert cc.judge(c, _by(ROWS), ROWS, "2026-10-09", True)[0] == "NOT YET"


def test_absent_and_a_missing_row():
    assert cc.judge(_led(event_id="gone", column="EVENT_ID", op="absent", expected=""), _by(ROWS), ROWS, "2026-10-11", True)[0] == "KEPT"
    assert cc.judge(_led(event_id="ev-b", column="EVENT_ID", op="absent", expected=""), _by(ROWS), ROWS, "2026-10-11", True)[0] == "NOT KEPT"
    assert cc.judge(_led(event_id="not-loaded-yet"), _by(ROWS), ROWS, "2026-10-11", True)[0] == "NOT YET"      # nothing to judge until the row exists


def test_a_star_line_checks_every_row():
    c = _led(event_id="*", column="STATUS DETAILS", op="not_contains", expected="typically")
    state, detail = cc.judge(c, _by(ROWS), ROWS, "2026-10-11", True)
    assert state == "NOT KEPT" and "B" in detail
    assert cc.judge(c, _by(ROWS[:1]), ROWS[:1], "2026-10-11", True)[0] == "KEPT"


def test_bad_ledger_lines_are_reported_not_raised():
    assert cc.judge(_led(op="nonsense"), _by(ROWS), ROWS, "2026-10-11", True)[0] == "BAD LEDGER LINE"
    assert cc.judge(_led(column="NO SUCH"), _by(ROWS), ROWS, "2026-10-11", True)[0] == "BAD LEDGER LINE"
    assert cc.judge(_led(event_id="*", op="equals"), _by(ROWS), ROWS, "2026-10-11", True)[0] == "BAD LEDGER LINE"


def test_run_pairs_by_the_canonical_id_and_main_never_fails(tmp_path, monkeypatch, capsys):
    db = tmp_path / "t.db"
    sqlite3.connect(db).close()
    f = tmp_path / "delivery.csv"
    _write(f, [{**ROWS[0], "EVENT_ID": "ev-a"}], COLS)
    led = tmp_path / "ledger.csv"
    _write(led, [_led()], LCOLS)
    res = cc.run(led, {"*": f}, db, "2026-10-11")
    assert [r["state"] for r in res] == ["KEPT"]
    monkeypatch.setattr(sys, "argv", ["x", "--ledger", str(led), "--file", str(f), "--db", str(db), "--today", "2026-10-11", "--out-dir", str(tmp_path / "out")])
    assert cc.main() == 0
    assert "COMMITMENTS: 1 kept, 0 NOT kept, 0 not yet" in capsys.readouterr().out
    assert (tmp_path / "out" / "commitments.md").exists()
    monkeypatch.setattr(sys, "argv", ["x", "--ledger", str(tmp_path / "missing.csv"), "--file", str(f), "--db", str(db)])
    assert cc.main() == 0 and "COMMITMENTS: UNKNOWN" in capsys.readouterr().out                 # a checker never stops the job
