"""ACT-58 remainder: ledger hygiene, the draft note to upstream, and the Monday build QA section. Fixtures only (no live files, nothing sent)."""
import csv
import importlib.util
import sqlite3
import sys
from datetime import date
from pathlib import Path

from scripts import check_commitments as cc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
_spec = importlib.util.spec_from_file_location("qb_followup", ROOT / "scripts" / "qa_build.py")
qb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qb)

LCOLS = ["id", "promised_on", "note", "market", "event_id", "column", "op", "expected", "due", "what"]


def _led(**kw):
    base = {"id": "C1", "promised_on": "2026-10-06", "note": "33", "market": "Utility", "event_id": "ev-a", "column": "STATUS", "op": "equals", "expected": "Upcoming", "due": "2026-10-10", "what": "w"}
    base.update(kw)
    return base


def _write(path, rows, cols):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)


def test_a_clean_line_has_no_problem_and_each_defect_is_named():
    ids = {"ev-a"}
    assert cc.lint_ledger([_led()], {}, ids) == {}
    cases = {
        "no due date": _led(due=""), "not YYYY-MM-DD": _led(due="10/10/2026"), "unknown op": _led(op="eqals"), "is not one of": _led(market="Robotics"),
        "not a delivery field": _led(column="STATUZ"), "needs an expected value": _led(expected=""), "only for not_contains": _led(event_id="*"),
        "no event id": _led(event_id=""), "not one we hold": _led(event_id="ev-zzz"),
    }
    for want, line in cases.items():
        got = cc.lint_ledger([line], {}, ids)
        assert want in " ".join(got.get("C1", [])), (want, got)


def test_an_upstream_id_is_named_as_such_and_duplicate_ids_are_caught():
    got = cc.lint_ledger([_led(event_id="up-1")], {"up-1": "ev-a"}, {"ev-a"})
    assert "upstream's, ours is 'ev-a'" in got["C1"][0]
    assert "duplicate id" in " ".join(cc.lint_ledger([_led(), _led()], {}, {"ev-a"})["C1"])


def test_without_any_id_source_the_id_check_is_skipped_not_failed():
    assert cc.lint_ledger([_led(event_id="anything")], {}, set()) == {}


def test_run_never_reports_a_malformed_promise_as_kept_or_not_yet(tmp_path):
    db = tmp_path / "t.db"
    sqlite3.connect(db).close()
    f = tmp_path / "d.csv"
    _write(f, [{"EVENT_ID": "ev-a", "STATUS": "Upcoming"}], ["EVENT_ID", "STATUS"])
    led = tmp_path / "l.csv"
    # would be KEPT on the data (ev-a is Upcoming) except that its due date is missing; the other line is fine
    _write(led, [_led(id="C1", due=""), _led(id="C2")], LCOLS)
    res = {r["id"]: r for r in cc.run(led, {"*": f}, db, "2026-10-11")}
    assert res["C1"]["state"] == "BAD LEDGER LINE" and "no due date" in res["C1"]["detail"]
    assert res["C2"]["state"] == "KEPT"


def test_lint_flag_prints_only_the_hygiene_result(tmp_path, monkeypatch, capsys):
    db = tmp_path / "t.db"
    sqlite3.connect(db).close()
    f = tmp_path / "d.csv"
    _write(f, [{"EVENT_ID": "ev-a", "STATUS": "x"}], ["EVENT_ID", "STATUS"])
    led = tmp_path / "l.csv"
    _write(led, [_led(op="nope")], LCOLS)
    monkeypatch.setattr(sys, "argv", ["x", "--ledger", str(led), "--file", str(f), "--db", str(db), "--lint"])
    assert cc.main() == 0
    out = capsys.readouterr().out
    assert "LEDGER: 1 malformed line(s) of 1" in out and "LEDGER BAD: C1" in out and "COMMITMENTS:" not in out


def _broken(**kw):
    r = {"id": "C9", "event_id": "ev-b", "what": "STATUS must read Open", "note": "43", "due": "2026-10-10", "state": "NOT KEPT", "detail": "STATUS is 'Closed', expected equals 'Open'",
         "promised_on": "2026-10-06", "column": "STATUS", "op": "equals", "expected": "Open"}
    r.update(kw)
    return r


def test_the_draft_note_names_event_field_found_and_promised_and_is_ascii():
    note = cc.draft_note([_broken(), _broken(id="C10", state="KEPT"), _broken(id="C11", event_id="*", column="STATUS DETAILS", op="not_contains", expected="typically", detail="2 row(s) contain 'typically'")], "2026-10-11")
    assert note.startswith("DRAFT") and "Nothing has been sent" in note
    assert "1. ev-b, field STATUS." in note and "Found: STATUS is 'Closed'" in note and "Expected: the value 'Open'" in note and "your answer to note 43" in note
    assert "2. every row, field STATUS DETAILS." in note and "no value containing 'typically'" in note
    assert "C10" not in note and "3." not in note                              # a kept promise is not in the note
    note.encode("ascii")
    assert cc.draft_note([_broken(state="KEPT")], "2026-10-11") == ""          # nothing unmet: no note


def test_main_files_the_draft_only_when_something_is_not_kept(tmp_path, monkeypatch, capsys):
    db = tmp_path / "t.db"
    sqlite3.connect(db).close()
    f = tmp_path / "d.csv"
    _write(f, [{"EVENT_ID": "ev-a", "STATUS": "Closed"}], ["EVENT_ID", "STATUS"])
    led = tmp_path / "l.csv"
    _write(led, [_led()], LCOLS)
    monkeypatch.setattr(sys, "argv", ["x", "--ledger", str(led), "--file", str(f), "--db", str(db), "--today", "2026-10-11", "--out-dir", str(tmp_path / "o")])
    assert cc.main() == 0
    assert "1 NOT kept" in capsys.readouterr().out
    text = (tmp_path / "o" / cc.DRAFT_NAME).read_text(encoding="utf-8")
    assert "ev-a, field STATUS" in text and "Closed" in text and "Upcoming" in text
    _write(f, [{"EVENT_ID": "ev-a", "STATUS": "Upcoming"}], ["EVENT_ID", "STATUS"])
    monkeypatch.setattr(sys, "argv", ["x", "--ledger", str(led), "--file", str(f), "--db", str(db), "--today", "2026-10-11", "--out-dir", str(tmp_path / "o2")])
    assert cc.main() == 0
    assert not (tmp_path / "o2" / cc.DRAFT_NAME).exists()


def test_the_monday_build_qa_lists_not_kept_promises_and_files_the_draft(tmp_path):
    rep = qb.qa_report.new_report("build", date(2026, 10, 12))
    qb.commitments_section(rep, [_broken(), _broken(id="C2", state="KEPT"), _broken(id="C3", state="BAD LEDGER LINE", detail="no due date")], date(2026, 10, 12), tmp_path)
    assert len(rep["flags"]) == 2 and "NOT KEPT: C9" in rep["flags"][0] and "STATUS is 'Closed'" in rep["flags"][0] and "BAD LEDGER LINE: C3" in rep["flags"][1]
    sec = rep["sections"][-1]
    assert sec["title"] == "Upstream's promises" and "1 kept, 1 NOT kept" in sec["note"] and len(sec["rows"]) == 2
    assert (tmp_path / rep["cycle"] / cc.DRAFT_NAME).exists()
    md = qb.qa_report.to_markdown(qb.qa_report.finish(rep, "ok"), "Build QA")
    assert "FLAG" in md and "C9" in md


def test_build_is_unchanged_without_commitments_and_a_failed_checker_is_only_a_note(tmp_path):
    rep = qb.build([], date(2026, 10, 12), True)                                  # default: promises not checked, no section
    assert rep["sections"] == [] and rep["status"] == "PASS"
    rep = qb.build([], date(2026, 10, 12), True, None, tmp_path)                  # checker could not run: a note, never a flag
    assert rep["status"] == "PASS" and "did not run" in rep["sections"][-1]["note"]
