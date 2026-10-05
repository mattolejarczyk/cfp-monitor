"""ACT-18: a verification label carries its BASIS (date found vs only the call status read); the migration changes nothing else."""
import sqlite3

import pytest

from src.cfp_monitor.verify_basis import backfill, basis_from_detail, ensure_column, has_column, write_verify


@pytest.mark.parametrize("state,detail,basis", [
    ("verified", "[L2] page states 2026-11-16  <- https://x.org/cfp", "date"),
    ("verified", "[L0] our crawl of the page also reports 2026-11-16", "date"),
    ("verified", "[merge] quote confirmed on the cited page at merge time", "date"),
    ("verified", "[L2] page states 2026-11-16 (not the cited page; cited page unreadable)", "date"),
    ("verified", "verified 2026-09-14 https://iba.stevieawards.com/", "date"),
    ("verified", "[L0s] the page itself states the call is open", "status"),
    ("verified", "[L0s] the page itself states the call is closed", "status"),
    ("verified", "[L2] the page confirms the call is closed for this edition", "status"),
    ("contradicted", "[L0s] the page itself states the call is OPEN, not closed", "status"),
    ("contradicted", "[L2] the page states the call is CLOSED: \"x\"", "status"),
    ("contradicted", "[L2] page gives a different deadline: 12/23/2026", "date"),
    ("contradicted", "[L1] submission link returns 404 - page does not exist", "link"),
    ("not_found", "[L2] deadline not stated on the page - grounding value stands", "none-found"),
    ("not_found", "no_quote 2026-09-14 https://x.org", "none-found"),
    ("unverified", "", "none-found"),
    ("verified", "something we have never seen", ""),          # never guessed
    ("", "", ""),
])
def test_basis_from_detail(state, detail, basis):
    assert basis_from_detail(state, detail) == basis


def _db(tmp_path, rows):
    p = tmp_path / "t.db"
    con = sqlite3.connect(p)
    for t in ("grounding_facts", "award_grounding_facts"):
        con.execute(f"create table {t} (event_id text primary key, name text, verify_state text, verify_detail text, upstream_event_id text)")
    for t, r in rows:
        con.execute(f"insert into {t} (event_id, name, verify_state, verify_detail, upstream_event_id) values (?,?,?,?,?)", r)
    con.commit()
    return con


def test_column_added_once_backfill_fills_only_nulls_and_touches_nothing_else(tmp_path):
    con = _db(tmp_path, [("grounding_facts", ("a", "A", "verified", "[L0s] the page itself states the call is open", "")),
                         ("grounding_facts", ("b", "B", "verified", "[L2] page states 2026-11-16", "")),
                         ("award_grounding_facts", ("c", "C", "not_found", "no_quote 2026-09-14 u", "up-c"))])
    before = [tuple(r) for r in con.execute("select event_id, name, verify_state, verify_detail from grounding_facts order by 1")]
    assert ensure_column(con, "grounding_facts") and not ensure_column(con, "grounding_facts")
    ensure_column(con, "award_grounding_facts")
    con.execute("update grounding_facts set verify_basis='date' where event_id='a'")        # a value already there is never overwritten
    assert backfill(con, "grounding_facts") == {"date": 1}
    assert dict(con.execute("select event_id, verify_basis from grounding_facts")) == {"a": "date", "b": "date"}
    assert backfill(con, "award_grounding_facts") == {"none-found": 1}
    assert [tuple(r) for r in con.execute("select event_id, name, verify_state, verify_detail from grounding_facts order by 1")] == before


def test_write_verify_works_before_and_after_the_migration(tmp_path):
    con = _db(tmp_path, [("grounding_facts", ("a", "A", "unverified", "", ""))])
    assert not has_column(con, "grounding_facts")
    assert write_verify(con, "grounding_facts", "event_id", "a", "verified", "[L0s] the page itself states the call is open") == 1      # old database: still works
    ensure_column(con, "grounding_facts")
    write_verify(con, "grounding_facts", "event_id", "a", "verified", "[L2] page states 2026-11-16")
    assert con.execute("select verify_state, verify_basis from grounding_facts").fetchone() == ("verified", "date")


def test_the_migration_script_proves_and_restores(tmp_path, monkeypatch):
    from scripts import migrate_verify_basis as m
    con = _db(tmp_path, [("grounding_facts", ("a", "A", "verified", "[L0s] the page itself states the call is open", ""))])
    con.close()
    db = str(tmp_path / "t.db")
    monkeypatch.setattr(m, "board_figures", lambda db_, md, today: {"x": 1})
    assert m.apply(db, tmp_path / "bk", str(tmp_path), "2026-10-05") == 0
    c = sqlite3.connect(db)
    assert c.execute("select verify_basis from grounding_facts").fetchone() == ("status",)
    c.close()
    # a proof that fails (the board figures moved) restores the backup
    db2 = tmp_path / "u.db"
    import shutil
    shutil.copy(tmp_path / "bk" / next(p.name for p in (tmp_path / "bk").iterdir()), db2)
    figs = iter([{"x": 1}, {"x": 2}])
    monkeypatch.setattr(m, "board_figures", lambda *a: next(figs))
    assert m.apply(str(db2), tmp_path / "bk2", str(tmp_path), "2026-10-05") == 1
    assert not has_column(sqlite3.connect(db2), "grounding_facts")
