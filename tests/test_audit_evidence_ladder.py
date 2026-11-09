"""scripts/audit_evidence.py: the browser ladder keeps what it has read, stops on its own budget, and the first pass keeps why a page failed.

2026-11-09 (Monday pages): the evidence step was killed at its 2-hour limit with 65 of 333 pages climbed and 41 of them read. None was in the
database: the results were written after the last page. 44 rows on the customer pages read 'Could not check' because of it, the run said HEALTHY,
and the 288 first-pass failures all said 'page could not be read' with the HTTP status thrown away.
"""
import asyncio
import sqlite3

import pytest

from scripts import audit_evidence as ae

PAGE = ("Call for speakers. We invite practitioners to submit talks for the 2027 conference in Lisbon. " * 3
        + "The submission deadline is January 31, 2027. Notifications are sent in March. " * 2
        + "Topics include detection engineering, incident response, cloud security and application security.")


class Killed(BaseException):
    """Stands for the caller's timeout arriving mid-ladder (a kill is not an Exception the loop may swallow)."""


def test_a_page_is_handed_over_the_moment_it_is_read_so_a_kill_keeps_it():
    seen = []

    async def read_one(url):
        if url == "u3":
            raise Killed()
        return "text of " + url, "playwright-fallback"

    with pytest.raises(Killed):
        asyncio.run(ae.climb(["u1", "u2", "u3", "u4"], read_one, on_page=lambda u, t, v: seen.append((u, v))))
    assert seen == [("u1", "playwright-fallback"), ("u2", "playwright-fallback")]


def test_the_budget_stops_before_the_next_page_and_names_what_was_not_tried(capsys):
    t = [0.0]

    async def read_one(url):
        t[0] += 10
        return "x", "crawl4ai"

    out, left = asyncio.run(ae.climb(["a", "b", "c", "d"], read_one, deadline=20, clock=lambda: t[0]))
    assert list(out) == ["a", "b"] and left == ["c", "d"]
    assert "LADDER STOPPED BY THE TIME BUDGET at page 3 of 4: 2 page(s) not attempted" in capsys.readouterr().out


def test_without_a_budget_every_page_is_tried_and_a_bad_page_does_not_stop_the_rest():
    seen = []

    async def read_one(url):
        if url == "bad":
            raise TimeoutError()
        return ("" if url == "empty" else "ok text"), "cdp"

    out, left = asyncio.run(ae.climb(["bad", "empty", "good"], read_one, on_page=lambda u, t, v: seen.append(u)))
    assert list(out) == ["good"] and left == [] and seen == ["good"]       # an empty page is not handed over as a rescue


def test_the_first_pass_keeps_the_readers_own_note():
    assert ae.unreadable_detail("page could not be read", "HTTP 403") == "page could not be read [HTTP 403]"
    assert ae.unreadable_detail("page could not be read", "TimeoutError") == "page could not be read [TimeoutError]"
    assert ae.unreadable_detail("page could not be read", "HTTP 404") == "page could not be read [HTTP 404]"
    # a page that loaded but says nothing keeps its own reason; 'ok' adds nothing
    assert ae.unreadable_detail('soft 404 - page says "Page not found"', "ok") == 'soft 404 - page says "Page not found"'
    assert ae.unreadable_detail("", "no url") == "no url"


def _db(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("""create table evidence (id integer primary key, event_id text, field text, value_claimed text, source_url text, origin text,
                   verdict text, detail text, found_quote text, method text, fetched_at text, call_type text, exportable integer, export_block text)""")
    con.execute("insert into evidence (id, event_id, field, value_claimed, source_url, origin, verdict, detail, method) "
                "values (1, 'e1', 'deadline', '2027-01-31', 'https://x.example/cfp', 'grounding', 'unreadable', 'page could not be read [HTTP 403]', 'http')")
    con.execute("insert into evidence (id, event_id, field, value_claimed, source_url, origin, verdict, detail, method) "
                "values (2, 'e2', 'deadline', '2027-02-15', 'https://y.example/cfp', 'grounding', 'unreadable', 'page could not be read [HTTP 403]', 'http')")
    con.commit()
    return con


def test_a_rescued_page_is_in_the_database_before_the_next_page_is_read(tmp_path):
    """Read from a SECOND connection: what a later step, or the run after a kill, would see."""
    db = tmp_path / "t.db"
    con = _db(db)
    claims = [dict(r) for r in con.execute("select * from evidence where id = 1")]
    tally = {"unreadable": 2, "rescued": 0, "verified": 0, "no_quote": 0, "contradicted": 0}
    assert ae.apply_rescue(con, claims, {"e1": "Example Conf 2027"}, "https://x.example/cfp", PAGE, "playwright-fallback", "2026-11-09T09:00:00", tally) is True
    other = sqlite3.connect(db)
    v1, m1 = other.execute("select verdict, method from evidence where id = 1").fetchone()
    v2, m2 = other.execute("select verdict, method from evidence where id = 2").fetchone()
    assert v1 != "unreadable" and m1 == "playwright-fallback", "the rescued page was not committed"
    assert (v2, m2) == ("unreadable", "http"), "a page not yet reached keeps its honest verdict"
    assert tally["rescued"] == 1 and tally["unreadable"] == 1


def test_a_rescue_that_is_not_readable_either_writes_nothing(tmp_path):
    db = tmp_path / "t.db"
    con = _db(db)
    claims = [dict(r) for r in con.execute("select * from evidence where id = 1")]
    tally = {"unreadable": 2, "rescued": 0}
    assert ae.apply_rescue(con, claims, {}, "https://x.example/cfp", "Access denied", "cdp", "2026-11-09T09:00:00", tally) is False
    assert sqlite3.connect(db).execute("select verdict, method from evidence where id = 1").fetchone() == ("unreadable", "http")
    assert tally == {"unreadable": 2, "rescued": 0}
