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


def test_passed_deadline_is_resolved_free_before_any_fetch():
    from datetime import date
    from src.cfp_monitor import verify_methods as vm

    class _Boom:
        def verify(self, *a):
            raise AssertionError("a passed-deadline row must never reach the verifier")

    # a PAST-deadline row must resolve for free, never reaching the verifier (which would raise).
    con = _db_with([("a", "A", "2026-02-11", "not_found", "http://a")])
    res = sh.resolve_rows(con, sh.select_unconfirmed(con, 0), _Boom(), today=date(2026, 9, 22))
    assert res[0].action == "closed-passed" and res[0].method == vm.DEADLINE_PASSED

    # a FUTURE-deadline row DOES reach the verifier and is confirmed on evidence.
    con2 = _db_with([("b", "B", "2026-12-01", "not_found", "http://b")])
    r2 = sh.resolve_rows(con2, sh.select_unconfirmed(con2, 0),
                         _Fake(sh.VerifyResult(True, vm.FETCH_PLAIN, "http://b", "abstract deadline December 1, 2026")),
                         today=date(2026, 9, 22))
    assert r2[0].action == "confirm"


def test_customer_working_row_is_surfaced_not_healed():
    con = _db_with([("a", "A", "2026-10-19", "not_found", "http://a")],
                   clients=[("a", "Drafting Abstract")])
    rows = sh.select_unconfirmed(con, 0)
    res = sh.resolve_rows(con, rows, _Fake(sh.VerifyResult(True, "fetch:date-context", "http://a", "deadline October 19, 2026")))
    assert res[0].action == "skip:customer-working" and "Drafting Abstract" in res[0].reason


def _flag(name, dl="2026-12-01"):
    return sh.RowOutcome("e-" + name, name, dl, "http://x", "flag", sh.__dict__.get("_", "") or "fetch-plain+regex")


def _apply_db():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE grounding_facts (event_id TEXT, name TEXT, deadline TEXT, "
                "verify_state TEXT, deadline_evidence_url TEXT, deadline_quote TEXT, verify_detail TEXT)")
    con.executemany("INSERT INTO grounding_facts VALUES (?,?,?,?,?,?,?)", [
        ("a", "A", "2026-12-01", "not_found", "http://a-cited", "", ""),   # will be confirmed
        ("b", "B", "2026-12-01", "not_found", "http://b-cited", "", ""),   # stays flagged
    ])
    con.commit()
    return con


def test_apply_writes_only_confirmations_and_leaves_the_rest():
    from src.cfp_monitor import verify_methods as vm
    con = _apply_db()
    outcomes = [
        sh.RowOutcome("a", "A", "2026-12-01", "https://real.org/cfp", "confirm", vm.GROUNDED,
                      "abstract deadline December 1, 2026"),
        sh.RowOutcome("b", "B", "2026-12-01", "http://b-cited", "flag", vm.FETCH_PLAIN),
    ]
    log, backup = sh.apply_confirmations(con, outcomes, db_path=None)
    assert len(log) == 1 and backup is None
    a = con.execute("SELECT verify_state, deadline_evidence_url, deadline_quote, verify_detail "
                    "FROM grounding_facts WHERE event_id='a'").fetchone()
    assert a[0] == "verified" and a[1] == "https://real.org/cfp" and "December 1, 2026" in a[2]
    assert a[3] == "self-heal:" + vm.GROUNDED                       # provenance written
    b = con.execute("SELECT verify_state FROM grounding_facts WHERE event_id='b'").fetchone()
    assert b[0] == "not_found"                                      # the flagged row is untouched


def test_apply_never_stores_a_google_redirect_as_the_citation():
    from src.cfp_monitor import verify_methods as vm
    con = _apply_db()
    redirect = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"
    outcomes = [sh.RowOutcome("a", "A", "2026-12-01", redirect, "confirm", vm.GROUNDED, "deadline December 1, 2026")]
    sh.apply_confirmations(con, outcomes, db_path=None)
    a = con.execute("SELECT verify_state, deadline_evidence_url FROM grounding_facts WHERE event_id='a'").fetchone()
    assert a[0] == "verified" and a[1] == "http://a-cited"          # kept the clean cited url, not the redirect


def test_grounded_spike_guard_refuses_a_flood():
    from src.cfp_monitor import verify_methods as vm

    class _Boom:
        def verify(self, *a):
            raise AssertionError("the grounded verifier must not be called on a spike")

    flagged = [_flag(f"c{i}") for i in range(20)]
    out, note = sh.discover_flagged(flagged, _Boom(), max_grounded=3, spike_threshold=15)
    assert "REFUSED" in note and all(o.action == "flag" for o in out)   # nothing grounded


def test_grounded_confirms_within_budget_and_captures_evidence():
    from src.cfp_monitor import verify_methods as vm
    flagged = [_flag("PCIM Europe 2027", "2026-10-14"), _flag("SEMICON China 2027")]
    ev = {"queries": ["q1", "q2"], "source_hosts": ["mesago.com"]}
    gv = _Fake(sh.VerifyResult(True, vm.GROUNDED, "https://mesago.com/x", "abstract deadline October 14, 2026", evidence=ev))
    out, note = sh.discover_flagged(flagged, gv, max_grounded=1, spike_threshold=15)
    confirmed = [o for o in out if o.action == "confirm"]
    assert len(confirmed) == 1 and confirmed[0].method == vm.GROUNDED
    assert confirmed[0].evidence["source_hosts"] == ["mesago.com"]      # provenance captured
    assert "grounded 1" in note                                          # budget honoured


def test_every_record_carries_a_registered_method():
    from src.cfp_monitor import verify_methods as vm
    con = _db_with([("a", "A", "2026-10-19", "not_found", "http://a")])
    rows = sh.select_unconfirmed(con, 0)
    res = sh.resolve_rows(con, rows, _Fake(sh.VerifyResult(True, vm.FETCH_PLAIN, "http://a", "deadline October 19, 2026")))
    recs = sh.to_records(res)
    assert recs[0]["method"] == vm.FETCH_PLAIN and vm.is_method(recs[0]["method"])
    assert recs[0]["action"] == "confirm" and vm.FETCH_PLAIN in sh.render(res)
    # the shipped verifiers name registered methods
    assert vm.is_method(sh.DateContextVerifier.method) and vm.is_method(sh.BrowserLadderVerifier.method)


def test_escalation_tries_the_browser_only_when_the_plain_page_is_unreadable():
    from src.cfp_monitor import verify_methods as vm
    con = _db_with([("a", "A", "2026-10-19", "not_found", "http://a")])
    rows = sh.select_unconfirmed(con, 0)
    plain_blind = _Fake(sh.VerifyResult(False, vm.FETCH_PLAIN, "http://a", status="unavailable"))
    browser_ok = _Fake(sh.VerifyResult(True, vm.BROWSER_LADDER, "http://a", "abstract deadline October 19, 2026"))
    res = sh.resolve_rows(con, rows, [plain_blind, browser_ok])
    assert res[0].action == "confirm" and res[0].method == vm.BROWSER_LADDER   # escalated

    # a plain page we CAN read but that lacks the date is a real flag - do not escalate past it
    plain_flag = _Fake(sh.VerifyResult(False, vm.FETCH_PLAIN, "http://a"))
    res2 = sh.resolve_rows(con, rows, [plain_flag, browser_ok])
    assert res2[0].action == "flag" and res2[0].method == vm.FETCH_PLAIN
