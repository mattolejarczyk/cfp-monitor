"""scripts/shadow_reader.py (ACT-20): fixture-only tests of the comparison, the selection, the proof rules and the report. No network, no model."""
import json

from scripts import shadow_reader as S

PAGE = ("Industry Connect Canada 2026. 27 - 27 October, 2026 Toronto, ON, Canada. The conference will be held at Schwartz Reisman Institute. Organised by Acme Events Ltd. "
        "An in-person event. " + "filler text about the programme. " * 20)


def test_agree_differs_reader_only_ours_only_and_none():
    assert S.compare_field("city", "Toronto", "Toronto") == "agree"
    assert S.compare_field("city", "Toronto", "Ottawa", "held in Ottawa") == "differs"
    assert S.compare_field("organizer", "", "Acme Events Ltd") == "reader-only"
    assert S.compare_field("organizer", "Acme", "") == "ours-only"
    assert S.compare_field("organizer", "", "") == "none"
    assert S.compare_field("start_date", "2026-10-26", "2026-10-27") == "differs"
    assert S.compare_field("start_date", "2026-10-27", "2026-10-27") == "agree"


def test_our_value_inside_the_readers_own_quote_is_not_a_conflict_but_a_date_never_softens():
    assert S.compare_field("city", "Songdo", "Incheon", "Songdo, Incheon, Korea") == "agree"
    assert S.compare_field("organizer", "RX", "Reed Exhibitions Limited", '(c) 2026 Reed Exhibitions Limited ("RX").') == "agree"
    assert S.compare_field("start_date", "2026-10-26", "2026-10-27", "26 - 27 October 2026") == "differs"


def test_venue_has_no_column_it_is_agree_or_reader_only_never_differs():
    assert S.compare_field("venue", "ADNEC, Abu Dhabi", "Abu Dhabi National Exhibition Centre (ADNEC)") == "agree"      # the acronym in brackets is named in ours
    assert S.compare_field("venue", "Toronto, Ontario, Canada", "Schwartz Reisman Institute") == "reader-only"
    assert S.compare_field("venue", "Toronto", "") == "none"


def _row(**k):
    base = {"CONFERENCE": "Industry Connect Canada 2026", "EVENT_ID": "e1", "_market": "Utility", "STATUS": "Upcoming", "EDITION": "2026", "START DATE": "2026-10-26", "CITY": "Toronto", "COUNTRY": "Canada",
            "LOCATION": "Toronto, Ontario, Canada", "ORGANIZER": "", "FORMAT": "In-Person", "MAIN_INFO_URL": "https://x.example/", "CONFERENCE URL": "https://x.example/", "CFP_SUBMISSION_URL": "https://x.example/speak"}
    base.update(k)
    return base


def test_selection_takes_live_rows_with_a_page_least_recently_read_first():
    rows = [_row(CONFERENCE="A", EVENT_ID="a"), _row(CONFERENCE="B", EVENT_ID="b", **{"START DATE": "2026-10-20"}), _row(CONFERENCE="Closed", EVENT_ID="c", STATUS="Closed"),
            _row(CONFERENCE="Past", EVENT_ID="d", **{"START DATE": "2026-09-01"}), _row(CONFERENCE="NoPage", EVENT_ID="e", MAIN_INFO_URL="", **{"CONFERENCE URL": "", "CFP_SUBMISSION_URL": ""}),
            _row(CONFERENCE="OldEdition", EVENT_ID="f", EDITION="2025", **{"START DATE": ""})]
    sel = S.select_rows(rows, "2026-10-05", 10)
    assert [r["CONFERENCE"] for r in sel] == ["B", "A"]                     # soonest start first when nothing was read
    assert len(sel[0]["_urls"]) == 2                                          # the duplicate URL is read once
    sel2 = S.select_rows(rows, "2026-10-05", 10, {"b": "2026-10-01", "a": "2026-09-01"})
    assert [r["CONFERENCE"] for r in sel2] == ["A", "B"]                     # least recently read first
    assert len(S.select_rows(rows, "2026-10-05", 1)) == 1


def test_a_field_is_accepted_only_with_a_quote_that_is_on_the_page_and_a_failed_call_is_not_a_result():
    pages = [("https://x.example/", PAGE)]
    fields = {"city": {"value": "Toronto", "quote": "Toronto, ON, Canada"}, "organizer": {"value": "Acme Events Ltd", "quote": "Organised by Acme Events Ltd"},
              "country": {"value": "Canada", "quote": "a sentence that is not on the page"}, "start_date": {"value": "2026-10-27", "quote": "27 - 27 October, 2026"},
              "venue": {"value": "Schwartz Reisman Institute", "quote": "held at Schwartz Reisman Institute"}}
    rec = S.read_record(_row(), fields, PAGE, pages)
    f = rec["fields"]
    assert f["city"]["relation"] == "agree" and f["organizer"]["relation"] == "reader-only" and f["organizer"]["url"] == "https://x.example/"
    assert f["country"]["reader"] == "" and f["country"]["relation"] == "ours-only" and "not on the page" in f["country"]["why"]       # an unprovable claim is never accepted
    assert f["venue"]["relation"] == "reader-only" and f["format"]["relation"] == "ours-only"
    failed = S.read_record(_row(), None, PAGE, pages)
    assert all(v["relation"] == "failed" for v in failed["fields"].values())
    summ = S.summarize([rec, failed])
    assert summ["city"]["agree"] == 1 and sum(summ["city"][k] for k in S.RELATIONS) == 1          # the failed call is not counted


def test_the_report_lists_the_differences_and_reader_only_facts_with_their_quotes():
    pages = [("https://x.example/", PAGE)]
    rec = S.read_record(_row(), {"organizer": {"value": "Acme Events Ltd", "quote": "Organised by Acme Events Ltd"}, "city": {"value": "Toronto", "quote": "Toronto, ON, Canada"}}, PAGE, pages)
    md = S.report_md([rec], S.summarize([rec]), {"stamp": "s", "selected": 1, "skipped": 0, "failed": 0, "stopped": "", "minutes": 1.0, "usd": 0.002})
    assert "Reader-only" in md and "Organised by Acme Events Ltd" in md and "| organizer |" in md and "changes nothing" in md
    rows = S.csv_rows([rec])
    assert len(rows) == len(S.FIELDS) and {r["field"] for r in rows} == {k for k, _c, _l in S.FIELDS}


def test_history_gives_the_last_read_date_per_event(tmp_path):
    p = tmp_path / "h.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in [{"id": "a", "read_on": "2026-09-01"}, {"id": "a", "read_on": "2026-10-01"}, {"id": "b", "read_on": "2026-09-15"}]) + "\nnot json\n", encoding="utf-8")
    assert S.load_last_read(p) == {"a": "2026-10-01", "b": "2026-09-15"}
    assert S.load_last_read(tmp_path / "missing.jsonl") == {}


def test_the_script_is_read_only_and_capped():
    src = open(S.__file__, encoding="utf-8").read()
    for bad in ("sqlite3", "UPDATE ", "INSERT ", "shutil.copy", "os.remove"):
        assert bad not in src
    assert 'default=0.60' in src and 'default=120' in src and "--out-dir" in src and "never raises" in src.lower()
