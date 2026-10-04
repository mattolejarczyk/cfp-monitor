"""experiments/finder_reader_test/main_call.py: which accepted deadline is the main call's."""
from experiments.finder_reader_test.main_call import choose_main

T = "2026-10-04"


def c(v, url, what="", home=False):
    return {"value": v, "url": url, "what": what, "quote": "", "home": home}


def test_a_posters_date_never_beats_the_papers_call():
    r = choose_main([c("2027-04-05", "https://x.eu/call-for-posters/", "poster abstracts due"), c("2026-11-16", "https://x.eu/call-for-abstracts/", "abstract submission deadline")], T)
    assert r["pick"] == "2026-11-16" and r["other_calls"] == [("2027-04-05", "https://x.eu/call-for-posters/")]


def test_a_page_named_for_the_call_beats_the_home_page_and_the_earliest_open_round_wins():
    r = choose_main([c("2026-11-20", "https://x.org/", "dates", home=True), c("2026-12-20", "https://x.org/cfp", "late round"), c("2026-10-19", "https://x.org/cfp", "regular round")], T)
    assert r["pick"] == "2026-10-19" and r["rounds"] == 2 and "main-page" in r["why"]


def test_only_other_calls_means_an_honest_blank_and_passed_dates_are_ignored():
    assert choose_main([c("2027-05-07", "https://x.com/awards", "award nominations")], T)["pick"] == ""
    assert choose_main([c("2026-06-19", "https://x.org/cfp", "early round")], T)["pick"] == ""
    assert choose_main([c("2026-10-30", "https://x.org/", "submission deadline", home=True)], T)["pick"] == "2026-10-30"
