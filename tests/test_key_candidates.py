"""experiments/read_the_page_pass/key_candidates.py: how a reader's accepted value is set against what we ship."""
from experiments.read_the_page_pass.key_candidates import compare, in_scope


def test_compare_statuses():
    assert compare("start_date", "2027-03-10", "2027-03-10") == "agree"
    assert compare("start_date", "2027-03-10", "2027-03-11") == "differs"
    assert compare("country", "USA", "United States") == "agree"
    assert compare("city", "Las Vegas", "Las Vegas, NV") == "agree"
    assert compare("city", "Boston", "Houston") == "differs"
    assert compare("organizer", "", "ACME") == "reader-only"
    assert compare("organizer", "ACME", "") == "unproven"
    assert compare("format", "", "") == "both-blank"


def test_only_editions_still_ahead_are_read():
    assert in_scope({"START DATE": "2026-12-09"}, "2026-10-04") is True
    assert in_scope({"START DATE": "2026-09-24"}, "2026-10-04") is False
    assert in_scope({"START DATE": "", "EDITION": "2027"}, "2026-10-04") is True
