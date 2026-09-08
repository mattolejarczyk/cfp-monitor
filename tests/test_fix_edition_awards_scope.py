"""fix_edition.py must not apply the conference rule to an awards row, and must write nothing.

Amendment v2.3 section 4.1 is non-retroactive: the ladder governs future research, and a rule
adopted today does not rewrite rows the customer has already read. That is enforced here by
the shape of what plan() emits - only entries marked "change" are ever written, so an awards
row that never carries that marker cannot be applied by accident.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("fe", ROOT / "scripts" / "fix_edition.py")
fe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fe)

DELIVERY_COLS = ["EVENT_ID", "CONFERENCE", "OPPORTUNITY_TYPE", "SUBMISSION DEADLINE",
                 "ANNOUNCEMENT_DATE", "START DATE", "CONFERENCE DATES", "EDITION"]


def _db(tmp_path, rows):
    p = tmp_path / "t.db"
    con = sqlite3.connect(p)
    con.execute("create table grounding_facts (event_id text, name text, edition text)")
    con.executemany("insert into grounding_facts values (?,?,?)", rows)
    con.commit()
    con.close()
    return str(p)


def _csv(tmp_path, rows):
    import csv
    p = tmp_path / "d.csv"
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=DELIVERY_COLS)
        w.writeheader()
        w.writerows(rows)
    return p


def _plan(tmp_path, monkeypatch, db_rows, csv_rows):
    monkeypatch.setattr(fe, "_seed_map", lambda db: {})
    return fe.plan(_db(tmp_path, db_rows), _csv(tmp_path, csv_rows))


def test_an_awards_row_with_no_anchor_is_kept_not_changed(tmp_path, monkeypatch):
    out, tally = _plan(tmp_path, monkeypatch,
                       [("e1", "Some Award", "2026")],
                       [{"EVENT_ID": "e1", "CONFERENCE": "Some Award",
                         "OPPORTUNITY_TYPE": "Awards", "SUBMISSION DEADLINE": "2026-11-27",
                         "ANNOUNCEMENT_DATE": "", "START DATE": "", "CONFERENCE DATES": "",
                         "EDITION": "2026"}])
    assert tally["awards - no anchor, kept"] == 1
    assert out[0][3] is None, "rung 4 proposes no new year"
    assert out[0][4] != "change", "and must never be marked applicable"


def test_a_derived_disagreement_is_reported_never_applied(tmp_path, monkeypatch):
    """Rung 1 is upstream's and invisible here, so a derived answer never overwrites."""
    out, tally = _plan(tmp_path, monkeypatch,
                       [("e2", "Globee Awards", "2026")],
                       [{"EVENT_ID": "e2", "CONFERENCE": "Globee Awards",
                         "OPPORTUNITY_TYPE": "Awards", "SUBMISSION DEADLINE": "2027-02-04",
                         "ANNOUNCEMENT_DATE": "2027-06-15", "START DATE": "",
                         "CONFERENCE DATES": "", "EDITION": "2026"}])
    assert tally["awards - derived disagrees, REPORTED"] == 1
    assert out[0][3] is None and out[0][4].startswith("REPORT ONLY")
    assert "2027" in out[0][4] and "2026" in out[0][4], "both answers must be visible"


def test_an_awards_row_already_agreeing_is_silent(tmp_path, monkeypatch):
    _out, tally = _plan(tmp_path, monkeypatch,
                        [("e3", "Award", "2027")],
                        [{"EVENT_ID": "e3", "CONFERENCE": "Award",
                          "OPPORTUNITY_TYPE": "Awards", "SUBMISSION DEADLINE": "2027-02-04",
                          "ANNOUNCEMENT_DATE": "2027-06-15", "START DATE": "",
                          "CONFERENCE DATES": "", "EDITION": "2027"}])
    assert tally["already right"] == 1


def test_a_conference_row_is_untouched_by_v23(tmp_path, monkeypatch):
    """Rung 3 is R19.1, and a conference never enters the ladder at all."""
    out, tally = _plan(tmp_path, monkeypatch,
                       [("e4", "AWE USA 2027", "2026")],
                       [{"EVENT_ID": "e4", "CONFERENCE": "AWE USA 2027",
                         "OPPORTUNITY_TYPE": "Speaking", "SUBMISSION DEADLINE": "2027-01-01",
                         "ANNOUNCEMENT_DATE": "", "START DATE": "2027-06-01",
                         "CONFERENCE DATES": "", "EDITION": "2026"}])
    assert tally["would change"] == 1
    assert out[0][3] == "2027" and out[0][4] == "change"


def test_apply_writes_nothing_for_awards_rows(tmp_path, monkeypatch):
    """The load-bearing assertion of 4.1: no awards entry can reach the update statement."""
    db_rows = [("e1", "No Anchor Award", "2026"), ("e2", "Disagreeing Award", "2026")]
    csv_rows = [
        {"EVENT_ID": "e1", "CONFERENCE": "No Anchor Award", "OPPORTUNITY_TYPE": "Awards",
         "SUBMISSION DEADLINE": "2026-11-27", "ANNOUNCEMENT_DATE": "", "START DATE": "",
         "CONFERENCE DATES": "", "EDITION": "2026"},
        {"EVENT_ID": "e2", "CONFERENCE": "Disagreeing Award", "OPPORTUNITY_TYPE": "Awards",
         "SUBMISSION DEADLINE": "2027-02-04", "ANNOUNCEMENT_DATE": "2027-06-15",
         "START DATE": "", "CONFERENCE DATES": "", "EDITION": "2026"},
    ]
    monkeypatch.setattr(fe, "_seed_map", lambda db: {})
    db = _db(tmp_path, db_rows)
    out, _tally = fe.plan(db, _csv(tmp_path, csv_rows))
    fe.apply(db, out)
    con = sqlite3.connect(db)
    editions = dict(con.execute("select event_id, edition from grounding_facts"))
    keys = dict(con.execute("select event_id, key_year from grounding_facts"))
    assert editions == {"e1": "2026", "e2": "2026"}, "v2.3 is not retroactive"
    assert keys == {"e1": "2026", "e2": "2026"}, "4.2: key_year frozen, never recomputed"
