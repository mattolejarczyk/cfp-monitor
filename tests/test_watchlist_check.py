"""scripts/watchlist_check.py: named-row expectations and the deadline-movement diff (2026-10-02)."""
from __future__ import annotations

import csv
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("wc", ROOT / "scripts" / "watchlist_check.py")
wc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wc)

COLS = "event_id, name, deadline, is_projected, deadline_evidence_url, submission_url"


def _db(path: Path, rows: list[tuple], awards: list[tuple] | None = None) -> str:
    con = sqlite3.connect(path)
    for t in wc.TABLES:
        con.execute(f"create table {t} (event_id text, name text, deadline text, is_projected text, "
                    f"deadline_evidence_url text, submission_url text)")
    con.executemany("insert into grounding_facts values (?,?,?,?,?,?)", rows)
    con.executemany("insert into award_grounding_facts values (?,?,?,?,?,?)", awards or [])
    con.commit()
    con.close()
    return str(path)


def test_judge_values():
    assert wc.judge("2026-10-15", "2026-10-15", "2026-10-05")
    assert wc.judge(" FALSE ", "false", "2026-10-05")
    assert wc.judge("x", "NONBLANK", "2026-10-05") and not wc.judge("", "NONBLANK", "2026-10-05")
    assert wc.judge("", "BLANK", "2026-10-05") and not wc.judge("x", "BLANK", "2026-10-05")
    assert wc.judge("2026-10-05", "NOT_PASSED", "2026-10-05")          # today is not passed
    assert not wc.judge("2026-10-04", "NOT_PASSED", "2026-10-05")
    assert not wc.judge("", "NOT_PASSED", "2026-10-05")                # a blank date is not "still open"


def test_ok_changed_and_missing(tmp_path):
    db = _db(tmp_path / "a.db", [("e1", "One", "2026-10-15", "false", "http://x", ""),
                                 ("e2", "Two", "2026-09-30", "true", "", "")])
    tables = {t: wc._rows(db, t) for t in wc.TABLES}
    ok = wc.check_item({"label": "l", "table": "grounding_facts", "event_id": "e1",
                        "expect": {"deadline": "2026-10-15", "deadline_evidence_url": "NONBLANK"}}, tables, {}, "2026-10-05")
    assert ok["result"] == "OK"
    moved = wc.check_item({"label": "l", "table": "grounding_facts", "event_id": "e2",
                           "expect": {"deadline": "2026-10-15"}}, tables, {}, "2026-10-05")
    assert moved["result"] == "CHANGED" and "2026-09-30" in moved["problems"][0]
    gone = wc.check_item({"label": "l", "table": "grounding_facts", "event_id": "nope", "expect": {}}, tables, {}, "2026-10-05")
    assert gone["result"] == "MISSING"


def test_info_items_never_count_against_the_run(tmp_path):
    db = _db(tmp_path / "a.db", [("dup", "Dup", "2026-09-30", "true", "", "")])
    tables = {t: wc._rows(db, t) for t in wc.TABLES}
    r = wc.check_item({"label": "dup", "kind": "info", "table": "grounding_facts", "event_id": "dup",
                       "expect": {"deadline": "2027-01-01"}}, tables, {}, "2026-10-05")
    assert r["result"] == "INFO"


def test_expect_absent(tmp_path):
    db = _db(tmp_path / "a.db", [("dup", "Dup", "x", "", "", "")])
    tables = {t: wc._rows(db, t) for t in wc.TABLES}
    still = wc.check_item({"label": "l", "table": "grounding_facts", "event_id": "dup", "expect_absent": True}, tables, {}, "d")
    gone = wc.check_item({"label": "l", "table": "grounding_facts", "event_id": "zzz", "expect_absent": True}, tables, {}, "d")
    assert still["result"] == "CHANGED" and gone["result"] == "OK"


def test_award_table_is_read_separately(tmp_path):
    db = _db(tmp_path / "a.db", [], awards=[("a1", "Award", "2026-10-06", "false", "http://y", "")])
    tables = {t: wc._rows(db, t) for t in wc.TABLES}
    r = wc.check_item({"label": "l", "table": "award_grounding_facts", "event_id": "a1", "expect": {"deadline": "2026-10-06"}},
                      tables, {}, "2026-10-05")
    assert r["result"] == "OK"


def test_movement_lists_new_removed_and_moved(tmp_path):
    prev = _db(tmp_path / "p.db", [("keep", "Keep", "2026-10-01", "true", "", ""), ("drop", "Drop", "2026-11-01", "false", "", ""),
                                   ("same", "Same", "2026-12-01", "false", "http://z", "")])
    cur = _db(tmp_path / "c.db", [("keep", "Keep", "2026-10-15", "false", "http://q", ""), ("same", "Same", "2026-12-01", "false", "http://z", ""),
                                  ("add", "Add", "2027-01-01", "false", "", "")])
    m = wc.movement(prev, cur)["grounding_facts"]
    assert m["new"] == ["add"] and m["removed"] == ["drop"] and (m["before"], m["after"]) == (3, 3)
    assert [x[0] for x in m["moved"]] == ["keep"]
    fields = [f for f, _, _ in m["moved"][0][2]]
    assert fields == ["deadline", "is_projected", "deadline_evidence_url"]


def test_csv_source_and_exit_codes(tmp_path):
    db = _db(tmp_path / "a.db", [("e1", "One", "2026-10-15", "false", "http://x", "")])
    md = tmp_path / "Markets"
    md.mkdir()
    with open(md / "F.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["EVENT_ID", "SUBMISSION DEADLINE"])
        w.writeheader()
        w.writerow({"EVENT_ID": "up1", "SUBMISSION DEADLINE": "2026-10-30"})
    wl = tmp_path / "w.json"
    wl.write_text(json.dumps({"items": [
        {"label": "db", "table": "grounding_facts", "event_id": "e1", "expect": {"deadline": "2026-10-15"}},
        {"label": "csv", "file": "F.csv", "event_id": "up1", "expect": {"SUBMISSION DEADLINE": "2026-10-30"}}]}), encoding="utf-8")
    argv = ["--db", db, "--markets-dir", str(md), "--watchlist", str(wl), "--today", "2026-10-05"]
    assert wc.main(argv) == 0
    wl.write_text(json.dumps({"items": [{"label": "csv", "file": "F.csv", "event_id": "up1",
                                         "expect": {"SUBMISSION DEADLINE": "2099-01-01"}}]}), encoding="utf-8")
    assert wc.main(argv) == 1
    assert wc.main(["--db", db, "--watchlist", str(tmp_path / "missing.json")]) == 2


def test_a_missing_csv_file_is_reported_not_crashed(tmp_path):
    db = _db(tmp_path / "a.db", [])
    r = wc.check_item({"label": "l", "file": "Nope.csv", "event_id": "x", "expect": {}}, {t: {} for t in wc.TABLES}, {}, "d")
    assert r["result"] == "MISSING" and "not readable" in r["problems"][0]
