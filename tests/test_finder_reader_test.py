"""experiments/finder_reader_test/run.py accept_deadline: the model's deadline stands only if the page proves it."""
from experiments.finder_reader_test.run import accept_deadline

PAGE = "Call for Papers. The submission deadline is October 30, 2026. Registration opens in January."
T = "2026-10-04"


def test_a_quoted_dated_call_sentence_is_accepted():
    assert accept_deadline({"value": "2026-10-30", "quote": "The submission deadline is October 30, 2026."}, PAGE, T) == ("2026-10-30", "ok")


def test_a_quote_not_on_the_page_a_wrong_day_or_no_call_wording_is_refused():
    assert accept_deadline({"value": "2026-10-30", "quote": "Papers are due October 30, 2026."}, PAGE, T)[0] == ""
    assert accept_deadline({"value": "2026-10-31", "quote": "The submission deadline is October 30, 2026."}, PAGE, T)[0] == ""
    assert accept_deadline({"value": "2026-10-30", "quote": "Registration opens in January."}, PAGE, T)[0] == ""
    assert accept_deadline({"value": "", "quote": ""}, PAGE, T) == ("", "blank")
