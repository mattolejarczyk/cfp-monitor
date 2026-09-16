"""The import step's QA report: did the delivery land, and is every movement in the database explained?

Its first live run warned "conference rows fell from 419 to 393" - and merged_rows.txt recorded
exactly 26 merges in between. A warning a person has to explain away every week is one they stop
reading, so a fall is now compared with the merges someone recorded. The same run warned about one
conference on no market list: the AES New York row, held on purpose and declared.
"""
from __future__ import annotations

import csv
import importlib.util
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor.storage import Store                            # noqa: E402

_spec = importlib.util.spec_from_file_location("qi", ROOT / "scripts" / "qa_import.py")
qi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qi)

ON = date(2026, 9, 21)


def _db(tmp_path, ids=("2027-alpha-houston", "2027-beta-boston"), markets=True, held=()):
    db = tmp_path / "cfp_monitor.db"
    Store(str(db)).db.close()
    con = sqlite3.connect(db)
    for e in ids:
        con.execute("insert into grounding_facts (event_id, conference_key, name, deadline, "
                    "verify_state) values (?,?,?,?,?)", (e, e, e, "2026-11-01", "verified"))
        if markets:
            con.execute("insert into conference_markets (conference_key, market) values (?,?)",
                        (e, "Utility"))
    con.commit()
    con.close()
    seeds = tmp_path / "market_sheets"
    seeds.mkdir(exist_ok=True)
    with open(seeds / "utility_seed.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["EVENT_ID", "EVENT_ID_CANON"])
        w.writeheader()
        w.writerows({"EVENT_ID": f"up-{e}", "EVENT_ID_CANON": e} for e in ids)
    if held:
        (seeds / "held_rows.txt").write_text("\n".join(f"{h}  # declared" for h in held),
                                             encoding="utf-8")
    return db


def _delivery(tmp_path, ids):
    p = tmp_path / "Utility_audited.final.csv"
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["EVENT_ID", "CONFERENCE", "SUBMISSION DEADLINE"])
        w.writeheader()
        w.writerows({"EVENT_ID": f"up-{e}", "CONFERENCE": e, "SUBMISSION DEADLINE": "11/01/2026"}
                    for e in ids)
    return p


def test_a_delivery_that_landed_passes(tmp_path):
    db = _db(tmp_path)
    rep = qi.build(db, ON, {"Utility": _delivery(tmp_path, ["2027-alpha-houston"])}, None, "none",
                   run_invariants=False)
    assert rep["status"] == "PASS", rep["flags"]
    landed = next(s for s in rep["sections"] if s["title"].startswith("Did the delivery land"))
    row = next(r for r in landed["rows"] if r[1] == "SUBMISSION DEADLINE")
    assert row[3:5] == [1, 0], "m/d/yyyy in the delivery and ISO in the database are the same date"


def test_a_delivered_row_missing_from_the_database_is_flagged(tmp_path):
    """The invisible failure WEEKLY-CYCLE warns about: accepted, never imported."""
    db = _db(tmp_path)
    rep = qi.build(db, ON, {"Utility": _delivery(tmp_path, ["2027-alpha-houston", "2027-gamma-lisbon"])},
                   None, "none", run_invariants=False)
    assert any("NOT in the database" in f for f in rep["flags"])


def test_a_fall_explained_by_recorded_merges_is_not_a_warning(tmp_path, monkeypatch):
    merged = tmp_path / "merged_rows.txt"
    merged.write_text("2026-09-15 2027-x-houston -> 2027-alpha-houston  (duplicate)\n"
                      "    source_as_of: a -> b\n", encoding="utf-8")
    monkeypatch.setattr(qi, "MERGED_ROWS", merged)
    db = _db(tmp_path)
    prev = dict(qi.db_metrics(db), Conferences=3)
    rep = qi.build(db, ON, {}, prev, "last cycle", run_invariants=False, prev_since="2026-09-14")
    assert not any("fell" in f for f in rep["flags"])
    assert any("fully accounted for by 1 merge" in n for n in rep["notes"])


def test_a_fall_beyond_the_recorded_merges_is_a_warning(tmp_path, monkeypatch):
    """Four rows vanished silently on 2026-08-08. Nothing recorded, so it must be loud."""
    merged = tmp_path / "merged_rows.txt"
    merged.write_text("", encoding="utf-8")
    monkeypatch.setattr(qi, "MERGED_ROWS", merged)
    db = _db(tmp_path)
    prev = dict(qi.db_metrics(db), Conferences=6)
    rep = qi.build(db, ON, {}, prev, "last cycle", run_invariants=False, prev_since="2026-09-14")
    assert any("4 row(s) are unaccounted for" in f for f in rep["flags"])


def test_a_declared_hold_is_not_warned_about(tmp_path):
    db = _db(tmp_path, markets=False, held=("2027-alpha-houston",), ids=("2027-alpha-houston",))
    m = qi.db_metrics(db)
    assert m["  on no market list"] == 0 and m["  on no market list, held by decision"] == 1


def test_an_undeclared_unlisted_row_is_warned_about(tmp_path):
    db = _db(tmp_path, markets=False, ids=("2027-alpha-houston",))
    rep = qi.build(db, ON, {}, None, "none", run_invariants=False)
    assert any("on no market list" in f for f in rep["flags"])


def test_customer_rows_linked_to_nothing_are_counted(tmp_path):
    from src.cfp_monitor import clients
    db = _db(tmp_path)
    con = sqlite3.connect(db)
    clients.ensure_schema(con)
    con.executemany("insert into client_conferences (client_key, their_name, event_id) values (?,?,?)",
                    [("arnica", "Alpha", "2027-alpha-houston"), ("arnica", "Omega", None)])
    con.commit()
    con.close()
    m = qi.db_metrics(db)
    assert m["  arnica: linked to our conference"] == 1 and m["  arnica: NOT linked"] == 1


def test_the_next_cycle_reads_this_cycles_numbers_back(tmp_path):
    """The database keeps no history, so the report keeps its own."""
    from src.cfp_monitor import qa_report
    db = _db(tmp_path)
    out = tmp_path / "qa"
    rep = qi.build(db, date(2026, 9, 14), {}, None, "none", run_invariants=False)
    qa_report.write(rep, "x", out)
    prev, label, since = qi.previous_metrics(out, "2026-09-21")
    assert prev["Conferences"] == 2 and "2026-09-14" in label and since == "2026-09-14"
