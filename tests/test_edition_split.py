"""The identity freeze, and the derivation that replaces it.

The property under test is not "edition is correct" - it is that CORRECTING THE EDITION CANNOT
MOVE A KEY. That is the whole point of the split, and it is the failure the 2026-08-08 incident
would have produced again.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fe = _load("fix_edition")


# ------------------------------------------------------------------ the year rule --
def test_year_prefers_a_real_date_over_nothing():
    assert fe._year("2027-02-09") == "2027"
    assert fe._year("February 09 - February 11, 2027") == "2027"


def test_year_takes_the_latest_when_an_event_straddles_new_year():
    assert fe._year("December 28, 2026 - January 03, 2027") == "2027"


def test_year_falls_through_in_order():
    assert fe._year("", None, "March 3, 2028") == "2028"


def test_year_never_invents_one():
    """2.5 - decline rather than guess. A row with no date keeps whatever it had."""
    assert fe._year("") is None
    assert fe._year(None) is None
    assert fe._year("dates to be announced") is None
    assert fe._year("the 39th symposium") is None      # an ordinal is not a year


def test_year_ignores_numbers_that_are_not_years():
    assert fe._year("1998 founding") is None            # outside the 20xx window
    assert fe._year("suite 2027b") is None              # 2027b is a suite number, not a year
    assert fe._year("hall 12027") is None               # not a year just because it contains one
    assert fe._year("March 3, 2027, hall 2027b") == "2027"   # the real one still found


# ------------------------------------------------- the property that actually matters --
def _db(tmp_path: Path) -> str:
    p = tmp_path / "t.db"
    con = sqlite3.connect(p)
    con.execute("create table grounding_facts (event_id text, name text, edition text)")
    con.executemany(
        "insert into grounding_facts values (?,?,?)",
        [("2026-awe-usa-long-beach", "AWE USA 2027", "2026"),
         ("2027-ceraweek-houston", "CERAWeek 2027", "2027")])
    con.commit()
    con.close()
    return str(p)


def test_correcting_the_edition_does_not_move_the_key(tmp_path):
    db = _db(tmp_path)
    before = {r[0] for r in sqlite3.connect(db).execute("select event_id from grounding_facts")}

    fe.apply(db, [("2026-awe-usa-long-beach", "AWE USA 2027", "2026", "2027", "change")])

    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = {r["event_id"]: r for r in con.execute("select * from grounding_facts")}
    assert set(rows) == before, "a key moved - this is the 2026-08-08 failure"
    assert rows["2026-awe-usa-long-beach"]["edition"] == "2027", "edition was not corrected"
    assert rows["2026-awe-usa-long-beach"]["key_year"] == "2026", "identity did not freeze"


def test_key_year_freezes_from_the_OLD_edition_on_every_row(tmp_path):
    """Freezing must happen BEFORE correction and for rows that are not changing.

    If key_year were captured after the edition moved, the key's year and key_year would agree
    on a value the key never had, and invariant 7 would pass while meaning nothing.
    """
    db = _db(tmp_path)
    fe.apply(db, [("2026-awe-usa-long-beach", "AWE USA 2027", "2026", "2027", "change")])
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    for r in con.execute("select * from grounding_facts"):
        assert r["event_id"].startswith(r["key_year"] + "-"), (
            f"{r['event_id']} no longer carries its own key_year {r['key_year']}")


def test_rows_with_no_date_are_left_completely_alone(tmp_path):
    db = _db(tmp_path)
    fe.apply(db, [("2027-ceraweek-houston", "CERAWeek 2027", "2027", None, "no date")])
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    r = dict(con.execute(
        "select * from grounding_facts where event_id='2027-ceraweek-houston'").fetchone())
    assert r["edition"] == "2027", "a row with no derivable date was changed"


def test_apply_is_idempotent(tmp_path):
    """Running it twice must not re-freeze key_year from an already-corrected edition."""
    db = _db(tmp_path)
    ch = [("2026-awe-usa-long-beach", "AWE USA 2027", "2026", "2027", "change")]
    fe.apply(db, ch)
    fe.apply(db, ch)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    r = con.execute("select * from grounding_facts "
                    "where event_id='2026-awe-usa-long-beach'").fetchone()
    assert r["key_year"] == "2026", "second run overwrote the frozen year"
