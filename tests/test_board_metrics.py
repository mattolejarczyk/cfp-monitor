"""scripts/board_metrics.py: the customer-agreement number is a defined, reproducible query (2026-10-02)."""
from __future__ import annotations

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
    assert bm.customer_agreement(db)["counts"]["agree"] == 1


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
