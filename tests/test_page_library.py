"""The page library keeps one copy per page, keeps history when a page changes, and refuses to treat a block page as content."""
import importlib.util
import tempfile
from pathlib import Path

_spec = importlib.util.spec_from_file_location("page_library", Path(__file__).resolve().parents[1] / "scripts" / "page_library.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)


def _db():
    return pl.connect(Path(tempfile.mkdtemp()) / "lib.db")


def test_block_page_is_flagged_and_not_usable():
    f = pl.flags(" Request unsuccessful. Incapsula incident ID: 123 ", lambda t: "")
    assert f["blocked"] is True and f["usable"] is False


def test_real_page_is_usable():
    f = pl.flags("Call for papers. Submission deadline: 15 October 2026. " * 20, lambda t: "")
    assert f == {"blocked": False, "soft404": "", "usable": True}


def test_empty_body_is_not_usable():
    assert pl.flags("")["usable"] is False


def test_upsert_new_then_unchanged_then_changed_keeps_history():
    db = _db()
    rec = {"url": "https://x.example/cfp", "host": "x.example", "tier": "P1", "text": "deadline 1 May 2026", "fetched_at": "2026-10-01T00:00:00Z"}
    assert pl.upsert_page(db, rec) == "new"
    assert pl.upsert_page(db, dict(rec, fetched_at="2026-10-02T00:00:00Z")) == "unchanged"
    assert db.execute("select count(*) from page_versions").fetchone()[0] == 0
    assert pl.upsert_page(db, dict(rec, text="deadline 8 May 2026", fetched_at="2026-10-03T00:00:00Z")) == "changed"
    versions = db.execute("select text from page_versions where url=?", (rec["url"],)).fetchall()
    assert versions == [("deadline 1 May 2026",)]
    now = db.execute("select text, fetches, first_fetched_at from pages where url=?", (rec["url"],)).fetchone()
    assert now[0] == "deadline 8 May 2026" and now[1] == 3 and now[2] == "2026-10-01T00:00:00Z"


def test_load_text_returns_saved_text_or_empty():
    path = Path(tempfile.mkdtemp()) / "lib.db"
    db = pl.connect(path)
    pl.upsert_page(db, {"url": "https://a.example/", "host": "a.example", "text": "hello"})
    db.close()
    assert pl.load_text("https://a.example/", path) == "hello"
    assert pl.load_text("https://missing.example/", path) == ""


def test_interleave_never_puts_one_host_twice_in_a_row_while_others_remain():
    out = pl.interleave({"a": [("a", "a1", "P1"), ("a", "a2", "P1")], "b": [("b", "b1", "P1"), ("b", "b2", "P1")], "c": [("c", "c1", "P1")]})
    hosts = [x[0] for x in out]
    assert hosts == ["a", "b", "c", "a", "b"]
