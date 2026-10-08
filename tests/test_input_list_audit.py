"""scripts/input_list_audit.py (ACT-59): fixture-only tests of the hint parsing, the year-aware acceptance and the verdicts. No network, no model."""
from scripts import input_list_audit as A

DECARB_PAGE = ("Decarb Connect Europe 2027. Join us 14-15 April 2027 in Vienna, Austria for two days of industrial decarbonisation. " + "filler text about the programme. " * 20)
NULLCON_PAGE = ("Nullcon Goa 2027. Speaker announcements: November 30, 2026. The call for papers closes 30 October 2026. Nullcon Goa takes place February 27-28, 2027 in Goa, India. " + "filler. " * 40)


def _row(**k):
    base = {"CONFERENCE": "Decarb Connect Europe 2027", "EVENT_ID_CANON": "2027-decarb-connect-europe-vienna", "_market": "Utility", "EDITION": "2027", "START DATE": "6/8/2027",
            "CONFERENCE DATES": "June 8 - June 10, 2027", "LOCATION": "Hamburg, Germany", "SUBMISSION DEADLINE": ""}
    base.update(k)
    return base


def test_parse_range_and_to_iso():
    assert A.parse_range("April 14 - April 15, 2027") == ("2027-04-14", "2027-04-15")
    assert A.parse_range("June 8-10, 2027") == ("2027-06-08", "2027-06-10")
    assert A.parse_range("8-10 June 2027") == ("2027-06-08", "2027-06-10")
    assert A.parse_range("December 30, 2026 - January 2, 2027") == ("2026-12-30", "2027-01-02")
    assert A.parse_range("") == ("", "")
    assert A.to_iso("1/15/2027") == "2027-01-15" and A.to_iso("") == "" and A.to_iso("soon") == ""


def test_decarb_connect_europe_differs_in_dates_start_and_place_with_the_pages_own_quote():
    fields = {"start_date": {"value": "2027-04-14", "quote": "14-15 April 2027 in Vienna, Austria"}, "end_date": {"value": "2027-04-15", "quote": "14-15 April 2027 in Vienna, Austria"},
              "city": {"value": "Vienna", "quote": "in Vienna, Austria"}, "country": {"value": "Austria", "quote": "in Vienna, Austria"}}
    row = _row()
    acc = A.accept_all(fields, DECARB_PAGE, "2027")
    res = A.judge(row, acc, DECARB_PAGE, "2027", ["https://decarbconnecteurope.com/"])
    for f in ("START DATE", "CONFERENCE DATES", "LOCATION"):
        assert res[f]["verdict"] == "DIFFERS", f
    assert "Vienna" in res["LOCATION"]["quote"] and "14-15 April 2027" in res["CONFERENCE DATES"]["quote"]
    assert res["SUBMISSION DEADLINE"]["verdict"] == "NO_VALUE"
    prop = A.propose(row, "CONFERENCE DATES", res["CONFERENCE DATES"], True)
    assert prop["action"] == "REPLACE" and prop["proposed"] == "April 14 - April 15, 2027"
    assert A.propose(row, "START DATE", res["START DATE"], True)["proposed"] == "4/14/2027"


def test_a_correct_row_agrees():
    fields = {"start_date": {"value": "2027-04-14", "quote": "14-15 April 2027 in Vienna, Austria"}, "end_date": {"value": "2027-04-15", "quote": "14-15 April 2027 in Vienna, Austria"},
              "city": {"value": "Vienna", "quote": "in Vienna, Austria"}, "country": {"value": "Austria", "quote": "in Vienna, Austria"}}
    row = _row(**{"START DATE": "4/14/2027", "CONFERENCE DATES": "April 14 - April 15, 2027", "LOCATION": "Vienna, Austria"})
    res = A.judge(row, A.accept_all(fields, DECARB_PAGE, "2027"), DECARB_PAGE, "2027", ["u"])
    assert [res[f]["verdict"] for f in ("START DATE", "CONFERENCE DATES", "LOCATION")] == ["AGREES"] * 3


def test_nullcon_goa_deadline_differs_when_the_page_says_30_october():
    fields = {"deadline": {"value": "2026-10-30", "quote": "The call for papers closes 30 October 2026."}}
    row = _row(CONFERENCE="Nullcon Goa 2027", **{"SUBMISSION DEADLINE": "11/30/2026", "START DATE": "", "CONFERENCE DATES": "", "LOCATION": ""})
    res = A.judge(row, A.accept_all(fields, NULLCON_PAGE, "2027"), NULLCON_PAGE, "2027", ["https://nullcon.net/cfp/"])
    assert res["SUBMISSION DEADLINE"]["verdict"] == "DIFFERS" and res["SUBMISSION DEADLINE"]["page"] == "2026-10-30"
    assert A.propose(row, "SUBMISSION DEADLINE", res["SUBMISSION DEADLINE"], True)["proposed"] == "10/30/2026"


def test_a_2026_date_never_proves_a_2027_row_so_the_hint_is_unsupported_not_agrees():
    page = "Decarb Connect Europe 2026. 14-15 April 2026 in Vienna, Austria. " + "filler text. " * 30
    fields = {"start_date": {"value": "2026-04-14", "quote": "14-15 April 2026 in Vienna, Austria"}}
    row = _row(**{"START DATE": "4/14/2026"})                     # even a hint equal to the 2026 date must not be 'proven' for edition 2027
    res = A.judge(row, A.accept_all(fields, page, "2027"), page, "2027", ["u"])
    assert res["START DATE"]["verdict"] == "UNSUPPORTED" and "asked edition" in res["START DATE"]["why"]
    assert "never mentions 2027" in res["START DATE"]["why"]
    p = A.propose(row, "START DATE", res["START DATE"], True)
    assert p["action"] == "BLANK" and p["proposed"] == ""


def test_unreadable_page_proposes_nothing_and_a_quote_not_on_the_page_is_refused():
    res = A.judge(_row(), A.accept_all(None, "", "2027"), "", "2027", [])
    assert res["START DATE"]["verdict"] == "UNSUPPORTED" and res["START DATE"]["why"] == "no page could be read"
    assert A.propose(_row(), "START DATE", res["START DATE"], False)["action"] == "KEEP-UNVERIFIED"
    bad = {"deadline": {"value": "2026-10-30", "quote": "closes 30 October 2026 for sure"}}
    assert A.accept_deadline(bad["deadline"], NULLCON_PAGE, "2027")[1] == "quote is not on the page"


def test_deadline_rules_year_wording_and_registration_dates():
    ok = {"value": "2026-10-30", "quote": "The call for papers closes 30 October 2026."}
    assert A.accept_deadline(ok, NULLCON_PAGE, "2027") == ("2026-10-30", "ok")
    late = {"value": "2025-10-30", "quote": "The call for papers closes 30 October 2025."}
    assert A.accept_deadline(late, NULLCON_PAGE + " The call for papers closes 30 October 2025.", "2027")[0] == ""     # two years before: another edition's call
    nowords = {"value": "2027-02-27", "quote": "takes place February 27-28, 2027 in Goa"}
    assert A.accept_deadline(nowords, NULLCON_PAGE, "2027")[0] == ""


def test_ids_with_a_year_other_than_the_edition_are_listed():
    rows = [_row(EVENT_ID_CANON="2026-nullcon-goa-bambolim", EDITION="2027"), _row(EVENT_ID_CANON="2027-x", EDITION="2027"), _row(EVENT_ID_CANON="2026-y", EDITION="", **{"START DATE": "3/2/2026"})]
    m = A.id_year_mismatch(rows)
    assert [x["id"] for x in m] == ["2026-nullcon-goa-bambolim"] and m[0]["edition"] == "2027"


def test_country_aliases_are_folded_so_uk_is_not_a_difference():
    assert A.same_country("UK", "ExCeL London, London, United Kingdom")
    assert A.same_country("United States", "Houston, Texas, USA")
    assert not A.same_country("Austria", "Hamburg, Germany")
    fields = {"city": {"value": "London", "quote": "ExCeL London, UK"}, "country": {"value": "UK", "quote": "ExCeL London, UK"}}
    page = "Cloud and Cyber Security Expo at ExCeL London, UK. " + "filler text. " * 30
    res = A.judge(_row(LOCATION="ExCeL London, London, United Kingdom"), A.accept_all(fields, page, "2027"), page, "2027", ["u"])
    assert res["LOCATION"]["verdict"] == "AGREES"


def test_a_training_or_sponsor_date_is_not_the_talk_deadline():
    page = "FIRST 38th Annual Conference 2026. Call for Trainings will close October 24, 2025. " + "filler text. " * 30
    item = {"value": "2025-10-24", "quote": "Call for Trainings will close October 24, 2025."}
    assert A.accept_deadline(item, page, "2026")[0] == ""
    ok = {"value": "2025-10-24", "quote": "Call for Papers and trainings will close October 24, 2025."}
    assert A.other_call("Sponsor registration closes 3 March 2027") and not A.other_call("Abstract submission closes 3 March 2027")
    assert A.accept_deadline(ok, page + " Call for Papers and trainings will close October 24, 2025.", "2026")[0] == "2025-10-24"
