"""D11 on Daily Review (Matt, 2026-11-09): "A. Report only in November; switch on in December".

Plan step 9 (docs/design/customer-context-plan.md): rows the client is working on (their status Info Needed, Drafting or Submitted, or their
own deadline within 30 days) are never skipped by the refresh plan. Until CUSTOMER_WORKING_FROM (2026-12-01) the plan only REPORTS which
skipped rows that would bring back; from that day they are researched. Every name, id and status here is fake (public repo)."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from scripts import refresh_plan as rp

NOV = date(2026, 11, 14)            # a Saturday in November: report only
DEC = date(2026, 12, 5)             # a Saturday in December: switched on
POL = {**rp.DEFAULT_POLICY, "guard_max_skip_share": 1.0}


def fmt(d: date) -> str:
    return d.strftime("%B ") + str(d.day) + d.strftime(", %Y")


def dormant(today: date) -> dict:
    """A Closed conference that ended 30 days ago: the plan skips it (group 3, outside its one check)."""
    end = today - timedelta(days=30)
    return {"STATUS": "Closed", "CONFERENCE DATES": fmt(end), "START DATE": end.isoformat(), "CONFERENCE URL": "https://conf.example/", "SUBMISSION URL": ""}


def rows(n: int) -> list[dict]:
    return [{"CONFERENCE": f"Fake Conf {i}", "EVENT_ID_CANON": f"fake-{i}", "DUP_OF": ""} for i in range(n)]


def test_the_switch_date_is_december_first():
    assert rp.CUSTOMER_WORKING_FROM == date(2026, 12, 1)


def test_what_counts_as_the_customer_working_on_a_row():
    t = NOV
    assert rp.working_reason("Info Needed", "", t) == "their status is 'Info Needed'"
    assert rp.working_reason("Drafting Abstract", "", t) == "their status is 'Drafting Abstract'"
    assert rp.working_reason("Submitted", "", t) == "their status is 'Submitted'"
    assert rp.working_reason("", (t + timedelta(days=30)).isoformat(), t) == f"their deadline {(t + timedelta(days=30)).isoformat()} is within 30 days"
    assert rp.working_reason("", (t + timedelta(days=31)).isoformat(), t) == ""
    assert rp.working_reason("", (t - timedelta(days=1)).isoformat(), t) == "", "a deadline that has passed is not work ahead"
    assert rp.working_reason("Closed", "", t) == "" and rp.working_reason("Accepted", "", t) == "" and rp.working_reason("", "", t) == ""
    assert rp.working_reason("", "sometime in spring", t) == "", "free text is not a date"


def test_november_reports_the_row_but_still_skips_it():
    pl = rp.conference_plan(rows(1), {"fake-0": dormant(NOV)}, {}, set(), NOV, POL, working={"fake-0": "their status is 'Info Needed'"})
    assert 0 in pl["skip"], "report only: the mark is unchanged in November"
    assert pl["decisions"][0]["would_force"] == "their status is 'Info Needed'"
    assert pl["counts"]["customer_working_report_only"] == 1
    line = rp.summary_line("Cybersecurity", pl, POL)
    assert "CUSTOMER-WORKING: 1 skipped row(s) the customer is working on would be researched from 2026-12-01 (report only" in line


def test_december_researches_it_as_an_override():
    pl = rp.conference_plan(rows(1), {"fake-0": dormant(DEC)}, {}, set(), DEC, POL, working={"fake-0": "their status is 'Submitted'"})
    assert 0 not in pl["skip"]
    d = pl["decisions"][0]
    assert d["research"] and d["override"] == "customer-working" and "the customer is working on it: their status is 'Submitted'" in d["reason"]
    assert pl["counts"]["customer_working_report_only"] == 0 and "CUSTOMER-WORKING" not in rp.summary_line("Cybersecurity", pl, POL)


def test_without_the_customer_layer_nothing_changes():
    a = rp.conference_plan(rows(2), {"fake-0": dormant(NOV), "fake-1": dormant(NOV)}, {}, set(), NOV, POL)
    b = rp.conference_plan(rows(2), {"fake-0": dormant(NOV), "fake-1": dormant(NOV)}, {}, set(), NOV, POL, working={})
    assert a["skip"] == b["skip"] and a["counts"]["customer_working_report_only"] == 0


def test_the_client_layer_is_read_by_our_own_id_and_skips_withdrawn_and_unmatched_rows(tmp_path):
    db = tmp_path / "t.db"
    con = sqlite3.connect(db)
    con.execute("create table client_conferences (client_key text, their_name text, event_id text, status text, their_deadline text, withdrawn_by_customer text)")
    con.executemany("insert into client_conferences values (?,?,?,?,?,?)", [
        ("a", "Fake One", "fake-1", "Info Needed", "", ""),
        ("a", "Fake Two", "fake-2", "Drafting Abstract", "", "yes"),                       # withdrawn: not work
        ("a", "Fake Three", "", "Submitted", "", ""),                                        # not matched to an id: cannot be joined
        ("a", "Fake Four", "fake-4", "", (NOV + timedelta(days=10)).isoformat(), ""),
        ("a", "Fake Five", "fake-5", "Closed", "", ""),
    ])
    con.commit()
    con.close()
    assert rp.customer_working_conferences(db, NOV) == {"fake-1": "their status is 'Info Needed'",
                                                        "fake-4": f"their deadline {(NOV + timedelta(days=10)).isoformat()} is within 30 days"}


# ------------------------------------------------------------------ awards (Friday): matched by name or deep link, never by id
AW_T = date(2026, 11, 13)


def aw_rec(today=AW_T):
    """Closed, next cycle far, researched 10 days before `today`: dormant on that day (never due by rotation or staleness)."""
    return {"status": "Closed", "deadline": "2026-06-01", "submission_opens": "2026-05-01", "source_as_of": (today - timedelta(days=10)).isoformat()}   # next opening 2027-05-01: far on both test days


def test_awards_working_index_and_the_plan_report_only_in_november(tmp_path):
    sheets = [{"name": "Fake Award (2026)", "url": "https://fake-award.example/enter", "status": "Info Needed", "deadline": ""},
              {"name": "Other Fake Award", "url": "", "status": "Accepted", "deadline": ""}]
    idx = rp.working_award_index(sheets, AW_T)
    assert idx["names"] and list(idx["names"].values()) == ["their status is 'Info Needed'"]
    awards = [{"CONFERENCE": "Fake Award 2026", "CONFERENCE URL": "", "SUBMISSION URL": "", "EVENT_ID_CANON": "aw-1", "DUP_OF": ""},
              {"CONFERENCE": "Unlisted", "CONFERENCE URL": "", "SUBMISSION URL": "https://fake-award.example/enter/", "EVENT_ID_CANON": "aw-2", "DUP_OF": ""},
              {"CONFERENCE": "Nobody", "CONFERENCE URL": "", "SUBMISSION URL": "", "EVENT_ID_CANON": "aw-3", "DUP_OF": ""}]
    db = {f"aw-{i}": aw_rec() for i in (1, 2, 3)}
    pl = rp.plan(awards, db, AW_T, 1.0, working=idx)
    assert set(pl["skip"]) == {0, 1, 2}, "November: report only, the marks are unchanged"
    assert [w[0] for w in pl["customer_working"]] == [0, 1], "matched by name key, and by the deep submission link"
    dec = date(2026, 12, 4)
    pl_dec = rp.plan(awards, {f"aw-{i}": aw_rec(dec) for i in (1, 2, 3)}, dec, 1.0, working=idx)
    assert set(pl_dec["skip"]) == {2} and pl_dec["researched"].get("customer-working") == 2 and pl_dec["customer_working"] == []
