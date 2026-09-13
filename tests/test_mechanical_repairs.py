"""Contract v2.4 mechanical repairs - replayed on the real cases of 2026-09-12, offline.

Every test that shows a repair being MADE has a partner showing a near-miss being REFUSED. A
repair tool that fixes bad input but also "fixes" good input is the 2026-08-08 clean_city
accident again, so the refusals matter at least as much.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import mechanical_repairs as mr        # noqa: E402

TODAY = date(2026, 9, 12)

# secureworld.io/events as our gate's fetcher read it on 2026-09-12. The Speaker Deadlines list
# sits directly above the Schedule list - the page round 4 wrongly said had no deadlines.
SECUREWORLD = (
    "Become a Speaker Speaker Submissions February March April May June September October "
    "November Speaker Deadlines Schedule Threat Defense 2026 2026-09-01 Threat Defense 2026 "
    "2026-10-21 2026-10-21 Twin Cities, MN 2026 2026-09-19 Twin Cities, MN 2026 2026-11-19 "
    "2026-11-19 East 2026 2026-10-04 East 2026 2026-11-18 2026-11-18 Government & Critical "
    "Infrastructure 2026 2026-10-28 Government & Critical Infrastructure 2026 2026-12-09 "
    "2026-12-09 New York City, NY 2026 2026-08-29 New York City, NY 2026 2026-10-29 2026-10-29")

DEAD, NEW, LIVE = "https://x.test/dead", "https://x.test/new", "https://x.test/live"


def row(**kw):
    base = {"CONFERENCE": "Test Event 2026", "Market": "Cybersecurity",
            "SUBMISSION DEADLINE": "2026-10-01", "IS_PROJECTED": "false",
            "GROUNDING_CONFIDENCE": "Verified (2026)", "STATUS": "Open",
            "STATUS DETAILS": "The call for speakers closes October 1, 2026.",
            "NOTES": "customer text \u2013 theirs", "SUBMISSION DATE VERIFIED": "2026-09-01"}
    base.update(kw)
    return base


def stub_fetch(table):
    return lambda url: table.get(url, (200, ""))


def stub_browser(dead):
    return lambda urls: {u for u in urls if u in dead}


def run(rows, prior=None, fetch=None, dead=(), ledger=()):
    return mr.run(rows, prior, TODAY, fetch or stub_fetch({}), stub_browser(set(dead)),
                  list(ledger))


# ============================================================ A - quote from the cited page

def test_A_secureworld_twin_cities_is_recopied_from_the_page():
    span, why = mr.find_quote_span(SECUREWORLD, "SecureWorld Twin Cities 2026", date(2026, 9, 19))
    assert span == "Twin Cities, MN 2026 2026-09-19", why


def test_A_secureworld_government_is_recopied_from_the_page():
    span, why = mr.find_quote_span(SECUREWORLD, "SecureWorld Government & Critical "
                                                "Infrastructure 2026", date(2026, 10, 28))
    assert span == "Government & Critical Infrastructure 2026 2026-10-28", why


def test_A_the_EVENT_date_is_never_taken_for_the_deadline():
    """Twin Cities' event date 2026-11-19 is on the same page. Claiming it as the deadline must
    not produce a quote, because it appears twice (the Schedule list repeats it)."""
    span, why = mr.find_quote_span(SECUREWORLD, "SecureWorld Twin Cities 2026", date(2026, 11, 19))
    assert span is None and "2 times" in why


def test_A_a_span_carrying_another_date_is_refused():
    page = "Twin Cities 2026-11-19 Detroit 2026-09-19 Denver 2026-07-30"
    span, why = mr.find_quote_span(page, "SecureWorld Twin Cities 2026", date(2026, 9, 19))
    assert span is None and "another date" in why


def test_A_a_date_not_on_the_page_is_refused():
    span, why = mr.find_quote_span(SECUREWORLD, "SecureWorld Twin Cities 2026", date(2026, 9, 20))
    assert span is None and "not on the page" in why


def test_A_sentence_route_on_an_ordinary_cfp_page():
    page = "Important dates. Abstract submissions close March 15, 2027. The event is in June."
    span, why = mr.find_quote_span(page, "Obscure Gathering 2027", date(2027, 3, 15))
    assert span == "Abstract submissions close March 15, 2027", why


def test_A_a_date_with_no_event_name_and_no_deadline_wording_is_refused():
    page = "Photos from our gallery. Taken March 15, 2027. More soon."
    span, why = mr.find_quote_span(page, "Obscure Gathering 2027", date(2027, 3, 15))
    assert span is None


def test_A_climate_change_two_digit_year_is_declined_not_guessed():
    """'19 October (26)' is not a rendering we can parse, so no repair - it goes to upstream."""
    page = "Early 19 June (26). Regular 20 June (26) to 19 October (26). Late to 20 December (26)"
    span, _ = mr.find_quote_span(page, "Nineteenth International Conference on Climate Change",
                                 date(2026, 10, 19))
    assert span is None


def test_A_repair_quote_leaves_verbatim_passed_blocked_and_unread_rows_alone():
    r = row(DEADLINE_EVIDENCE_URL=LIVE, DEADLINE_QUOTE="Twin Cities, MN 2026 2026-09-19",
            CONFERENCE="SecureWorld Twin Cities 2026", **{"SUBMISSION DEADLINE": "2026-09-19"})
    assert mr.repair_quote(r, SECUREWORLD, 200, TODAY) == (None, None)            # verbatim
    r["DEADLINE_QUOTE"] = "September 19, 2026"
    assert mr.repair_quote(r, SECUREWORLD, 403, TODAY) == (None, None)            # 403 exempt
    assert mr.repair_quote(r, "", 200, TODAY) == (None, None)                     # unread
    assert mr.repair_quote(r, SECUREWORLD, 200, date(2026, 9, 30)) == (None, None)  # passed
    rep, dec = mr.repair_quote(r, SECUREWORLD, 200, TODAY)
    assert dec is None and rep.after == "Twin Cities, MN 2026 2026-09-19"


def test_A_through_run_changes_only_the_quote():
    r = row(CONFERENCE="SecureWorld Twin Cities 2026", DEADLINE_EVIDENCE_URL=LIVE,
            DEADLINE_QUOTE="September 19, 2026", **{"SUBMISSION DEADLINE": "2026-09-19"})
    before = dict(r)
    res = run([r], fetch=stub_fetch({LIVE: (200, SECUREWORLD)}))
    changed = {k for k in r if r[k] != before[k]}
    assert changed == {"DEADLINE_QUOTE"}
    assert [x.cls for x in res.repairs] == ["A"]


# ============================================================ B - carry upstream's replacement

def test_B_round3_third_field_gets_upstreams_replacement():
    prior = [row(**{"SUBMISSION URL": DEAD, "DEADLINE_EVIDENCE_URL": DEAD,
                    "CFP_SUBMISSION_URL": DEAD})]
    cur = [row(**{"SUBMISSION URL": NEW, "DEADLINE_EVIDENCE_URL": NEW,
                  "CFP_SUBMISSION_URL": DEAD})]
    res = run(cur, prior, fetch=stub_fetch({DEAD: (404, ""), NEW: (200, "")}), dead={DEAD})
    assert cur[0]["CFP_SUBMISSION_URL"] == NEW
    assert [(x.cls, x.field) for x in res.repairs] == [("B", "CFP_SUBMISSION_URL")]


def test_B_refused_when_the_old_link_is_alive_in_a_browser():
    prior = [row(**{"SUBMISSION URL": DEAD, "CFP_SUBMISSION_URL": DEAD})]
    cur = [row(**{"SUBMISSION URL": NEW, "CFP_SUBMISSION_URL": DEAD})]
    res = run(cur, prior, fetch=stub_fetch({DEAD: (404, ""), NEW: (200, "")}), dead=set())
    assert cur[0]["CFP_SUBMISSION_URL"] == DEAD
    assert any(d.cls == "B" and "not dead" in d.why for d in res.declined)


def test_B_refused_when_upstream_sent_two_different_replacements():
    prior = [row(**{"SUBMISSION URL": DEAD, "DEADLINE_EVIDENCE_URL": DEAD,
                    "CFP_SUBMISSION_URL": DEAD})]
    cur = [row(**{"SUBMISSION URL": NEW, "DEADLINE_EVIDENCE_URL": LIVE,
                  "CFP_SUBMISSION_URL": DEAD})]
    res = run(cur, prior, fetch=stub_fetch({DEAD: (404, "")}), dead={DEAD})
    assert cur[0]["CFP_SUBMISSION_URL"] == DEAD
    assert any("different URLs" in d.why for d in res.declined)


def test_B_refused_when_the_replacement_does_not_resolve():
    prior = [row(**{"SUBMISSION URL": DEAD, "CFP_SUBMISSION_URL": DEAD})]
    cur = [row(**{"SUBMISSION URL": NEW, "CFP_SUBMISSION_URL": DEAD})]
    res = run(cur, prior, fetch=stub_fetch({DEAD: (404, ""), NEW: (404, "")}), dead={DEAD, NEW})
    assert cur[0]["CFP_SUBMISSION_URL"] == DEAD
    assert any("does not resolve" in d.why for d in res.declined)


# ============================================================ C - plain text

def test_C_round2_brackets_dashes_and_curly_quotes_on_a_verified_row():
    r = row(**{"STATUS DETAILS": "[Event concluded June 19 \u2013 CFP \u2018closed\u2019]"})
    run([r])
    assert r["STATUS DETAILS"] == "Event concluded June 19 - CFP 'closed'"


def test_C_the_contracts_own_projection_form_is_left_bracketed():
    """R4 prescribes '[Call for Speakers Pending / Expected Fall 2026]' on a projected row."""
    r = row(IS_PROJECTED="true", GROUNDING_CONFIDENCE="Projected (2026)",
            **{"STATUS DETAILS": "[Call for Speakers Pending / Expected Fall 2026]"})
    run([r])
    assert r["STATUS DETAILS"] == "[Call for Speakers Pending / Expected Fall 2026]"


def test_C_a_stub_marker_is_not_a_wrapping_bracket():
    r = row(**{"STATUS DETAILS": "[Audit Exception] Exceeded rate limits or retries."})
    run([r])
    assert r["STATUS DETAILS"] == "[Audit Exception] Exceeded rate limits or retries."


def test_C_a_serialised_list_is_declined_not_half_fixed():
    """SecureWorld Denver's CATEGORIES arrived as a Python list on 2026-09-12."""
    value = "['Cybersecurity', 'CISO Leadership', 'Information Security']"
    r = row(CATEGORIES=value)
    res = run([r])
    assert r["CATEGORIES"] == value
    assert any(d.cls == "C" and "serialised list" in d.why for d in res.declined)


def test_C_never_touches_a_quote_or_the_customers_fields():
    r = row(DEADLINE_QUOTE="Submissions close \u2013 \u201cSept. 30\u201d")
    run([r])
    assert r["DEADLINE_QUOTE"] == "Submissions close \u2013 \u201cSept. 30\u201d"
    assert r["NOTES"] == "customer text \u2013 theirs"


# ============================================================ D - withdraw a dead citation

def test_D_dead_evidence_url_is_withdrawn_and_the_deadline_is_untouched():
    r = row(DEADLINE_EVIDENCE_URL=DEAD, DEADLINE_QUOTE="closes October 1, 2026")
    run([r], fetch=stub_fetch({DEAD: (404, "")}), dead={DEAD})
    assert r["DEADLINE_EVIDENCE_URL"] == "" and r["DEADLINE_QUOTE"] == ""
    assert r["IS_PROJECTED"] == "true" and r["GROUNDING_CONFIDENCE"] == "Projected (2026)"
    assert r["SUBMISSION DEADLINE"] == "2026-10-01"
    assert r["SUBMISSION DATE VERIFIED"] == "2026-09-01" and r["NOTES"] == "customer text \u2013 theirs"


def test_D_refused_where_it_would_break_check_4_the_london_shape():
    r = row(DEADLINE_EVIDENCE_URL=DEAD, **{
        "STATUS DETAILS": "The Call for Speakers is open via an active rolling application form."})
    res = run([r], fetch=stub_fetch({DEAD: (404, "")}), dead={DEAD})
    assert r["DEADLINE_EVIDENCE_URL"] == DEAD and r["IS_PROJECTED"] == "false"
    assert any(d.cls == "D" and "check 4" in d.why for d in res.declined)


def test_D_refused_when_a_browser_can_load_it():
    r = row(DEADLINE_EVIDENCE_URL=DEAD)
    res = run([r], fetch=stub_fetch({DEAD: (404, "")}), dead=set())
    assert r["DEADLINE_EVIDENCE_URL"] == DEAD
    assert any("alive in a real browser" in d.why for d in res.declined)


def test_D_a_403_is_never_withdrawn():
    r = row(DEADLINE_EVIDENCE_URL=DEAD)
    run([r], fetch=stub_fetch({DEAD: (403, "")}), dead={DEAD})
    assert r["DEADLINE_EVIDENCE_URL"] == DEAD


def test_D_passed_deadline_is_decay_not_a_repair():
    r = row(DEADLINE_EVIDENCE_URL=DEAD, **{"SUBMISSION DEADLINE": "2026-08-01", "STATUS": "Closed"})
    res = run([r], fetch=stub_fetch({DEAD: (404, "")}), dead={DEAD})
    assert r["DEADLINE_EVIDENCE_URL"] == DEAD and not res.repairs


def test_D_dead_submission_url_clears_only_that_field():
    r = row(**{"SUBMISSION URL": DEAD, "DEADLINE_EVIDENCE_URL": LIVE})
    run([r], fetch=stub_fetch({DEAD: (404, ""), LIVE: (200, "")}), dead={DEAD})
    assert r["SUBMISSION URL"] == "" and r["DEADLINE_EVIDENCE_URL"] == LIVE
    assert r["IS_PROJECTED"] == "false"


# ============================================================ safeguards

def test_same_repair_in_an_earlier_cycle_is_routed_to_upstream_as_a_pattern():
    earlier = (TODAY - timedelta(days=7)).isoformat()
    ledger = [f"{earlier}\tCybersecurity\tTest Event 2026\tSTATUS DETAILS\tC\tx\ty\tf.csv"]
    r = row(**{"STATUS DETAILS": "[Verified and open]"})
    res = run([r], ledger=ledger)
    assert r["STATUS DETAILS"] == "[Verified and open]"
    assert any("PATTERN" in d.why for d in res.declined)


def test_a_rerun_the_same_day_is_not_a_pattern_and_an_old_one_has_expired():
    for when in (TODAY, TODAY - timedelta(days=mr.PATTERN_WINDOW_DAYS + 1)):
        ledger = [f"{when.isoformat()}\tCybersecurity\tTest Event 2026\tSTATUS DETAILS\tC\tx\ty\tf"]
        r = row(**{"STATUS DETAILS": "[Verified and open]"})
        run([r], ledger=ledger)
        assert r["STATUS DETAILS"] == "Verified and open"


def test_no_class_ever_moves_a_date_status_or_identity():
    rows = [
        row(CONFERENCE="SecureWorld Twin Cities 2026", DEADLINE_EVIDENCE_URL=LIVE,
            DEADLINE_QUOTE="September 19, 2026", **{"SUBMISSION DEADLINE": "2026-09-19",
                                                    "STATUS DETAILS": "[Open \u2013 verified]"}),
        row(DEADLINE_EVIDENCE_URL=DEAD, **{"SUBMISSION URL": DEAD}),
    ]
    frozen = [{k: r.get(k) for k in ("CONFERENCE", "SUBMISSION DEADLINE", "STATUS", "CITY",
                                      "EVENT_ID", "START DATE", "CONFERENCE DATES")} for r in rows]
    run(rows, fetch=stub_fetch({LIVE: (200, SECUREWORLD), DEAD: (404, "")}), dead={DEAD})
    assert frozen == [{k: r.get(k) for k in frozen[0]} for r in rows]
