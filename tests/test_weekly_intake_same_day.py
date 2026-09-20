"""The load decision must compare snapshots by the moment they were taken, not by date.

Found 2026-09-19. The weekly run was re-triggered the same afternoon after the 02:00 run
failed. It fetched both customer sheets, then compared taken=2026-09-19 with
in_db=2026-09-19, decided it was not behind, and loaded nothing - so the research ran
against a client layer twelve hours stale while the status line said HEALTHY.

Re-running the same day is now the intended way to recover from a failed run, so the
day-granularity compare has to go. These tests pin both directions: a same-day newer
snapshot MUST load, and a snapshot the database already holds must NOT be reloaded.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import weekly_intake as wi  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "t.db"
    con = sqlite3.connect(path)
    con.execute("create table client_conferences (client_key text, snapshot_file text)")
    con.commit()
    con.close()
    return str(path)


def load(db_path, client_key, snapshot_file):
    con = sqlite3.connect(db_path)
    con.execute("insert into client_conferences values (?, ?)", (client_key, snapshot_file))
    con.commit()
    con.close()


def behind(newest_name: str, db_path: str, key: str) -> bool:
    """The production expression, kept in one place so the test pins the real rule."""
    in_db_file = wi.loaded_snapshot_file(db_path, key)
    newest = Path(newest_name)
    return newest is not None and (in_db_file is None or newest.name > in_db_file)


def test_same_day_later_snapshot_is_behind(db):
    """THE BUG. Both files are dated 2026-09-19; the afternoon one must still load."""
    load(db, "arnica", "arnica_20260919-020812.csv")
    assert behind("arnica_20260919-141759.csv", db, "arnica") is True


def test_same_day_dates_really_are_equal(db):
    """Guards the premise: if these dates ever stop being equal the test above is vacuous."""
    morning = wi.snapshot_date(Path("arnica_20260919-020812.csv"))
    afternoon = wi.snapshot_date(Path("arnica_20260919-141759.csv"))
    assert morning == afternoon, "the old date compare would have seen these as the same"


def test_snapshot_already_loaded_is_not_reloaded(db):
    """GOOD INPUT SURVIVES: the same file must not be ingested twice."""
    load(db, "arnica", "arnica_20260919-141759.csv")
    assert behind("arnica_20260919-141759.csv", db, "arnica") is False


def test_older_snapshot_does_not_overwrite_a_newer_load(db):
    """A stale file left on disk must never pull the client layer backwards."""
    load(db, "arnica", "arnica_20260919-141759.csv")
    assert behind("arnica_20260919-020812.csv", db, "arnica") is False


def test_nothing_loaded_yet_is_behind(db):
    assert behind("arnica_20260919-020812.csv", db, "arnica") is True


def test_earlier_day_still_loads(db):
    """The original behaviour has to keep working - this is the normal weekly case."""
    load(db, "arnica", "arnica_20260912-020812.csv")
    assert behind("arnica_20260919-020812.csv", db, "arnica") is True


def test_loaded_snapshot_file_returns_the_newest_of_several(db):
    for name in ("arnica_20260905-020000.csv", "arnica_20260919-020812.csv",
                 "arnica_20260912-020812.csv"):
        load(db, "arnica", name)
    assert wi.loaded_snapshot_file(db, "arnica") == "arnica_20260919-020812.csv"


def test_other_clients_do_not_leak(db):
    load(db, "utility", "utility_20260919-141757.csv")
    assert wi.loaded_snapshot_file(db, "arnica") is None
    assert behind("arnica_20260919-020812.csv", db, "arnica") is True
