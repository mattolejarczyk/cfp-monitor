"""experiments/read_the_page_pass/pass_lib.py: code, not the model, decides what is accepted. Recall limiters 2 and 3: heading-year and dateless-page detection."""
from experiments.read_the_page_pass import pass_lib as L

ODSC = ("Menino Convention and Exhibition Center, Boston, MA | May 10-12th, 2027 REGISTER Your interest for 2027 REGISTER NOW. Featured East Speakers The first wave of transformative "
        "speakers for ODSC AI East 2026 is here! Join us April 28-30 in Boston to celebrate our 11th anniversary.")


def test_a_quote_that_is_not_on_the_page_is_never_accepted():
    assert L.accept("start_date", {"value": "2027-05-10", "quote": "Boston on May 10, 2027"}, ODSC, "2027")[0] == ""


def test_header_date_with_its_year_is_accepted_and_a_wrong_day_is_not():
    assert L.accept("start_date", {"value": "2027-05-10", "quote": "May 10-12th, 2027"}, ODSC, "2027")[0] == "2027-05-10"
    assert L.accept("start_date", {"value": "2027-06-10", "quote": "May 10-12th, 2027"}, ODSC, "2027")[0] == ""


def test_year_taken_from_the_heading_only_when_it_equals_the_date_and_the_edition():
    ok = L.accept("start_date", {"value": "2026-04-28", "quote": "April 28-30"}, ODSC, "2026")
    assert ok[0] == "2026-04-28" and "taken from the nearest earlier year" in ok[1]
    assert L.accept("start_date", {"value": "2027-04-28", "quote": "April 28-30"}, ODSC, "2027")[0] == ""      # the nearest earlier year is 2026, not 2027
    assert L.accept("start_date", {"value": "2026-04-28", "quote": "April 28-30"}, ODSC, "2027")[0] == ""      # asked edition 2027, date is 2026
    far = "ODSC AI East 2026 " + ("x " * 400) + "Join us April 28-30"
    assert L.accept("start_date", {"value": "2026-04-28", "quote": "April 28-30"}, far, "2026")[0] == ""        # the year is too far away to be the heading


def test_german_dates_are_read_and_the_wrong_edition_is_not():
    page = "Das Konferenz findet am 23.–24. September 2026 in Karlsruhe statt. " + "x" * 50
    assert L.accept("start_date", {"value": "2026-09-23", "quote": "23.–24. September 2026"}, page, "2026")[0] == "2026-09-23"
    assert L.accept("start_date", {"value": "2026-09-23", "quote": "23.–24. September 2026"}, page, "2027")[0] == ""


def test_dateless_pages_are_sent_to_the_browser_and_dated_pages_are_not():
    assert L.looks_dateless("<div id=app></div> loading " * 40)
    assert not L.looks_dateless(ODSC * 2)
    assert not L.looks_dateless("Das Konferenz findet am 23.09.2026 in Karlsruhe statt. " * 8)
    assert L.looks_dateless("short")


def test_scoring_ignores_failed_calls_and_counts_false_accepts():
    items = [{"event": "a", "field": "start_date", "gold": "2027-01-26", "accepted": "2027-01-26"},
             {"event": "b", "field": "start_date", "gold": "", "accepted": "2027-05-10"},
             {"event": "c", "field": "start_date", "gold": "2027-02-27", "accepted": "", "call_failed": True}]
    s = L.score(items)
    assert s["calls_failed"] == 1 and s["false_accept"] == 1 and s["correct"] == 1 and s["facts"] == 2
