"""The awards deadline check: what it claims, and the one verdict it refuses to claim."""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("cad",
                                               ROOT / "scripts" / "check_award_deadlines.py")
cad = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cad)

from src.cfp_monitor.storage import Store              # noqa: E402


def _db(tmp_path, rows):
    p = tmp_path / "t.db"
    Store(str(p)).db.close()
    con = sqlite3.connect(str(p))
    con.execute("alter table award_grounding_facts add column upstream_event_id TEXT")
    for r in rows:
        cols = ", ".join(r)
        marks = ", ".join("?" for _ in r)
        con.execute(f"insert into award_grounding_facts ({cols}) values ({marks})",
                    list(r.values()))
    con.commit()
    con.close()
    return str(p)


def _row(**kw):
    base = {"event_id": "ours-1", "upstream_event_id": "theirs-1", "name": "An Award",
            "deadline": "2027-03-19", "deadline_quote": "Entries close March 19 2027",
            "deadline_evidence_url": "https://a.test/dates"}
    base.update(kw)
    return base


def test_a_quote_on_the_page_is_verified(tmp_path):
    rows = cad.claims(_db(tmp_path, [_row()]))
    out = cad.verdicts(rows, {"https://a.test/dates": ["Key dates. Entries close March 19 2027. See you there."]})
    assert out[0]["CHECK"] == "verified"
    assert out[0]["CHECK_QUOTE"] == "Entries close March 19 2027"


def test_whitespace_and_case_do_not_defeat_the_match(tmp_path):
    rows = cad.claims(_db(tmp_path, [_row()]))
    out = cad.verdicts(rows, {"https://a.test/dates": ["ENTRIES   CLOSE\n  March 19   2027"]})
    assert out[0]["CHECK"] == "verified"


def test_a_page_that_loaded_without_the_sentence_is_no_quote(tmp_path):
    rows = cad.claims(_db(tmp_path, [_row()]))
    out = cad.verdicts(rows, {"https://a.test/dates": ["Welcome to our awards programme."]})
    assert out[0]["CHECK"] == "no_quote"
    assert out[0]["CHECK_QUOTE"] == "", "we only republish a quote we just re-read"


def test_a_page_we_could_not_open_is_unreadable_not_a_disproof(tmp_path):
    rows = cad.claims(_db(tmp_path, [_row()]))
    out = cad.verdicts(rows, {})
    assert out[0]["CHECK"] == "unreadable"


def test_contradicted_is_never_emitted(tmp_path):
    """Even where the page states a plainly different date.

    `contradicted` is the only verdict that argues the DATE is wrong, and an absent quote does
    not establish that - a page can reword, retitle, or hide a sentence behind a tab. Claiming
    it from an absence would be the guess 2.5 forbids.
    """
    rows = cad.claims(_db(tmp_path, [_row()]))
    out = cad.verdicts(rows, {"https://a.test/dates": ["Entries close September 1 2027"]})
    assert out[0]["CHECK"] == "no_quote"
    assert {o["CHECK"] for o in out}.isdisjoint({"contradicted"})


def test_the_csv_is_keyed_on_upstreams_id_because_the_page_is(tmp_path):
    """The page is built from the delivery CSV, whose EVENT_ID is upstream's. Our canonical
    id would join to nothing."""
    rows = cad.claims(_db(tmp_path, [_row(event_id="2027-an-award-tbd-awards",
                                          upstream_event_id="2027-an-award-unknown-awards")]))
    out = cad.verdicts(rows, {"https://a.test/dates": ["Entries close March 19 2027"]})
    assert out[0]["EVENT_ID"] == "2027-an-award-unknown-awards"


def test_rows_without_a_citation_are_not_claimed_as_checked(tmp_path):
    """A stub has nothing to verify. Emitting it at all would let the page count it."""
    db = _db(tmp_path, [_row(), _row(event_id="ours-2", upstream_event_id="theirs-2",
                                     name="A Stub", deadline_evidence_url="",
                                     deadline_quote="")])
    rows = cad.claims(db)
    assert [r["upstream_event_id"] for r in rows] == ["theirs-1"]


def test_a_quote_found_in_ANY_rendering_counts(tmp_path):
    """The 2026-09-08 regression, pinned.

    The ladder returns markdown and splices `[label](href)` through the prose; verify.fetch_text
    returns flat text, which is what citations are cut from and what the gate checks against.
    Reading only the ladder reported no_quote on 12 rows whose deadline was still ahead, four of
    which the gate had verified hours earlier. A renderer that garbled the sentence is our
    artefact, not the site's.
    """
    rows = cad.claims(_db(tmp_path, [_row()]))
    mangled = "Entries [close](https://a.test/x) March 19 2027"
    clean = "Entries close March 19 2027"
    assert cad.verdicts(rows, {"https://a.test/dates": [mangled]})[0]["CHECK"] == "no_quote"
    assert cad.verdicts(rows, {"https://a.test/dates": [mangled, clean]})[0]["CHECK"] == "verified"
    assert cad.verdicts(rows, {"https://a.test/dates": [clean, mangled]})[0]["CHECK"] == "verified"


def test_empty_renderings_are_unreadable_not_no_quote(tmp_path):
    rows = cad.claims(_db(tmp_path, [_row()]))
    assert cad.verdicts(rows, {"https://a.test/dates": ["", ""]})[0]["CHECK"] == "unreadable"
