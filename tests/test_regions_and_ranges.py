"""ACT-23: a country is accepted from a state or province named in the quote (checked lookup), and a date is accepted only when the page's own label says which of several ranges it is."""
import pytest

from experiments.read_the_page_pass import pass_lib as L
from src.cfp_monitor.regions import CANADA, US, country_from_region, country_matches


@pytest.mark.parametrize("text,country", [
    ("Las Vegas, NV", "United States"), ("Boston, MA | MAY 10-12TH, 2027", "United States"), ("Austin, TX 78701", "United States"), ("Washington, DC, USA", "United States"),
    ("Toronto, ON", "Canada"), ("Calgary, Alberta", "Canada"), ("held in Quebec", "Canada"), ("Perth, Western Australia", "Australia"), ("Sacramento, California", "United States"),
])
def test_a_named_state_or_province_gives_its_country(text, country):
    assert country_from_region(text)[0] == country


@pytest.mark.parametrize("text", [
    "Tbilisi, Georgia",                 # the country, not the US state
    "Register IN the main hall, OR later",  # words in capitals after no comma-capital pair
    "Paris, France", "Berlin", "Perth, WA", "Darwin, NT",        # shared or unused codes
    "Victoria, BC and Seattle, WA",     # whatever it is, two countries named: no guess
    "Austin, TX and Toronto, ON",       # two countries named: no guess
    "Cybersecurity, IN the cloud",      # ', IN' followed by a word
    "",
])
def test_nothing_is_guessed(text):
    assert country_from_region(text) is None


def test_every_us_and_canadian_code_is_a_two_letter_uppercase_pair_and_the_tables_do_not_overlap_except_where_unused():
    assert len(US) == 51 and len(CANADA) == 13
    assert all(len(k) == 2 and k.isupper() for k in list(US) + list(CANADA))
    assert set(US) & set(CANADA) == set()


def test_country_names_are_matched_by_the_lookups_own_aliases():
    assert country_matches("USA", "United States") and country_matches("United States of America", "United States") and country_matches("Canada", "Canada")
    assert not country_matches("Canada", "United States")


PAGE_CES = "CES 2027 - the most powerful tech event. January 6-9, 2027 | Las Vegas, NV. Join the world's biggest tech show. " + "More programme text. " * 30


def test_the_country_is_accepted_from_a_state_in_the_quote_but_not_from_a_wrong_state():
    ok, why = L.accept("country", {"value": "United States", "quote": "January 6-9, 2027 | Las Vegas, NV"}, PAGE_CES, "2027")
    assert ok == "United States" and "NV" in why
    assert L.accept("country", {"value": "Canada", "quote": "January 6-9, 2027 | Las Vegas, NV"}, PAGE_CES, "2027")[0] == ""      # the model said Canada, the lookup says United States
    assert L.accept("country", {"value": "United States", "quote": "CES 2027 - the most powerful tech event."}, PAGE_CES, "2027")[0] == ""   # no state or country in the quote
    assert L.accept("country", {"value": "United States", "quote": "not on the page, Las Vegas, NV"}, PAGE_CES, "2027")[0] == ""            # the quote must still be on the page


PAGE_TWO = ("Training days: June 1-3, 2027 - hands-on courses.   Conference: June 4-5, 2027 at the Grand Hall. " + "Programme and speakers listed here. " * 20)


def test_with_two_ranges_on_the_page_the_range_used_must_carry_the_pages_own_conference_label():
    q = "Training days: June 1-3, 2027 - hands-on courses.   Conference: June 4-5, 2027"
    ok = L.accept("start_date", {"value": "2027-06-04", "quote": q}, PAGE_TWO, "2027")
    assert ok[0] == "2027-06-04" and "labelled" in ok[1]
    bad = L.accept("start_date", {"value": "2027-06-01", "quote": q}, PAGE_TWO, "2027")
    assert bad[0] == "" and "training or side range" in bad[1]                                      # the training range, whichever way the model chose it


def test_a_rival_range_that_is_labelled_makes_an_unlabelled_range_unacceptable():
    page = "Programme overview. June 1-3, 2027 in the Grand Hall. Workshops: June 4-5, 2027 elsewhere. " + "More text here. " * 20
    r = L.accept("start_date", {"value": "2027-06-01", "quote": "June 1-3, 2027 in the Grand Hall."}, page, "2027")
    assert r[0] == "" and "nothing labels this one" in r[1]


def test_a_rival_range_that_says_nothing_about_itself_is_not_a_rival():
    page = "Programme overview. June 10-12, 2027 in the Grand Hall. Early bird rate June 1-15 only. " + "More text here. " * 20
    assert L.accept("start_date", {"value": "2027-06-10", "quote": "June 10-12, 2027 in the Grand Hall."}, page, "2027")[0] == "2027-06-10"


def test_the_real_troopers_page_shape_three_labelled_ranges():
    page = ("We plan the next TROOPERS on-site event in Heidelberg from June 21st to June 25th, 2027! TROOPERS27 main conference: June 23rd - 24th, 2027 Submit your Paper. "
            "Our trainings will be happening from June 21st to 22nd, 2027. " + "More text here. " * 20)
    ok = L.accept("start_date", {"value": "2027-06-23", "quote": "main conference: June 23rd - 24th, 2027"}, page, "2027")
    assert ok[0] == "2027-06-23" and "labelled" in ok[1]
    tr = L.accept("start_date", {"value": "2027-06-21", "quote": "trainings will be happening from June 21st to 22nd, 2027"}, page, "2027")
    assert tr[0] == "" and "training or side range" in tr[1]
    on = L.accept("start_date", {"value": "2027-06-21", "quote": "on-site event in Heidelberg from June 21st to June 25th, 2027"}, page, "2027")
    assert on[0] == "" and "nothing labels this one" in on[1]


def test_the_quote_alone_is_judged_by_the_text_around_it_on_the_page():
    # the model quotes only the training sentence; the conference range sits beside it on the page
    bad = L.accept("start_date", {"value": "2027-06-01", "quote": "Training days: June 1-3, 2027 - hands-on courses."}, PAGE_TWO, "2027")
    assert bad[0] == "" and "training" in bad[1]
    good = L.accept("start_date", {"value": "2027-06-04", "quote": "Conference: June 4-5, 2027 at the Grand Hall."}, PAGE_TWO, "2027")
    assert good[0] == "2027-06-04"


def test_another_editions_range_beside_it_is_not_a_rival():
    page = "ODSC East 2026: April 28-30, 2026 was great. ODSC East 2027: May 10-12, 2027 in Boston. " + "More text here. " * 20
    assert L.accept("start_date", {"value": "2027-05-10", "quote": "May 10-12, 2027 in Boston."}, page, "2027")[0] == "2027-05-10"


def test_a_page_with_one_range_is_unchanged_by_the_new_rule():
    page = "ODSC East 2027. Boston, MA | MAY 10-12TH, 2027. Register your interest. " + "More text. " * 30
    assert L.accept("start_date", {"value": "2027-05-10", "quote": "Boston, MA | MAY 10-12TH, 2027"}, page, "2027")[0] == "2027-05-10"


def test_date_ranges_are_counted_once_each_and_only_real_ranges():
    assert len(L.date_ranges("June 1-3, 2027 and 5-6 July 2027 and June 29 - July 1, 2027")) == 3
    assert len(L.date_ranges("June 1-3, 2027 repeated: June 1-3, 2027")) == 1
    assert L.date_ranges("Deadline June 15, 2027") == []


def test_the_prompt_has_the_state_rule_and_the_two_range_rule_but_keeps_one_range_as_stated():
    assert "state or province" in L.SYSTEM and "TWO OR MORE SEPARATE" in L.SYSTEM and "ONE range for the whole event" in L.SYSTEM


def test_usa_and_united_states_are_the_same_country_for_scoring():
    assert L.same("country", "United States", "USA") and L.same("country", "USA", "United States of America") and not L.same("country", "Canada", "USA")
