"""Self-heal Phase 1: a not_found deadline is confirmed only when it is stated, in a submission
context, on the row's own cited page - and every result knows the method that produced it. A
row the customer is working is surfaced, never healed. Deterministic: the fetch is faked.
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import self_heal as sh  # noqa: E402


# --- the pure date locator (no network) --------------------------------------

def test_deadline_forms_covers_iso_and_prose():
    forms = sh.deadline_forms("2026-10-19")
    assert "2026-10-19" in forms and "October 19, 2026" in forms and "19 October 2026" in forms
    assert sh.deadline_forms("") == [] and sh.deadline_forms("soon") == []


def test_date_in_submission_context_is_found():
    page = "Home. The abstract submission deadline is October 19, 2026. Register now."
    found, quote = sh.find_deadline_sentence(page, "2026-10-19")
    assert found and "October 19, 2026" in quote


def test_bare_date_without_context_is_not_a_deadline():
    page = "The conference will be held October 19, 2026 in Johannesburg. Hotels fill fast."
    found, _ = sh.find_deadline_sentence(page, "2026-10-19")
    assert not found          # a date alone could be the event date or a price - not enough


def test_absent_date_is_not_found():
    assert sh.find_deadline_sentence("Submit your abstract by December 1.", "2026-10-19")[0] is False


# --- resolution logic (fake verifier) ----------------------------------------

class _Fake:
    def __init__(self, result):
        self.result = result

    def verify(self, name, dl, url):
        return self.result


def _db_with(rows, clients=None):
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE grounding_facts (event_id TEXT, name TEXT, deadline TEXT, "
                "verify_state TEXT, deadline_evidence_url TEXT)")
    con.executemany("INSERT INTO grounding_facts VALUES (?,?,?,?,?)", rows)
    con.execute("CREATE TABLE client_conferences (event_id TEXT, status TEXT)")
    con.executemany("INSERT INTO client_conferences VALUES (?,?)", clients or [])
    con.commit()
    return con


def test_selects_only_notfound_with_deadline_and_url_ordered():
    con = _db_with([
        ("a", "A", "2026-10-19", "not_found", "http://a"),   # eligible
        ("b", "B", "2026-09-01", "not_found", "http://b"),   # eligible, sooner
        ("c", "C", "", "not_found", "http://c"),             # no deadline
        ("d", "D", "2026-11-01", "not_found", ""),           # no url
        ("e", "E", "2026-10-19", "verified", "http://e"),    # already verified
    ])
    got = [r["event_id"] for r in sh.select_unconfirmed(con, 0)]
    assert got == ["b", "a"]                                  # sooner deadline first
    assert [r["event_id"] for r in sh.select_unconfirmed(con, 1)] == ["b"]   # budget honoured


def test_confirm_flag_and_unavailable():
    con = _db_with([("a", "A", "2026-10-19", "not_found", "http://a")])
    rows = sh.select_unconfirmed(con, 0)
    conf = sh.resolve_rows(con, rows, _Fake(sh.VerifyResult(True, "fetch:date-context", "http://a", "the abstract deadline is October 19, 2026")))
    assert conf[0].action == "confirm" and conf[0].method == "fetch:date-context" and conf[0].quote
    flag = sh.resolve_rows(con, rows, _Fake(sh.VerifyResult(False, "fetch:date-context", "http://a")))
    assert flag[0].action == "flag"
    out = sh.resolve_rows(con, rows, _Fake(sh.VerifyResult(False, "fetch:date-context", "http://a", status="unavailable")))
    assert out[0].action == "skip:no-page"          # an outage is not a finding


def test_customer_working_row_is_surfaced_not_healed():
    con = _db_with([("a", "A", "2026-10-19", "not_found", "http://a")],
                   clients=[("a", "Drafting Abstract")])
    rows = sh.select_unconfirmed(con, 0)
    res = sh.resolve_rows(con, rows, _Fake(sh.VerifyResult(True, "fetch:date-context", "http://a", "deadline October 19, 2026")))
    assert res[0].action == "skip:customer-working" and "Drafting Abstract" in res[0].reason


def test_every_record_carries_its_method():
    con = _db_with([("a", "A", "2026-10-19", "not_found", "http://a")])
    rows = sh.select_unconfirmed(con, 0)
    res = sh.resolve_rows(con, rows, _Fake(sh.VerifyResult(True, "fetch:date-context", "http://a", "deadline October 19, 2026")))
    recs = sh.to_records(res)
    assert recs[0]["method"] == "fetch:date-context" and recs[0]["action"] == "confirm"
    assert "fetch:date-context" in sh.render(res)
