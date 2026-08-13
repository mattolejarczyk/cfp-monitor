"""Matching a customer sheet to our rows.

Every ingest of the customer's validation feedback starts here, so a wrong match silently
attributes their confirmation to the wrong conference. These tests cover the judgements, not
the plumbing.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "mcs", ROOT / "scripts" / "match_customer_sheet.py")
mcs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcs)


# ------------------------------------------------------------------ domains --
def test_host_strips_www_and_scheme():
    assert mcs.host("https://www.Example.com/path?q=1") == "example.com"


def test_host_keeps_the_registrable_part_of_a_country_domain():
    assert mcs.host("https://h2council.com.au/events") == "h2council.com.au"


def test_host_of_junk_is_empty_not_an_exception():
    assert mcs.host("") == ""
    assert mcs.host("not a url") == ""


# -------------------------------------------------------------------- names --
def test_the_year_is_not_part_of_identity():
    """Their sheet says "Industrial Net Zero Conference", ours says "... 2027". Same event."""
    assert mcs.sim("Industrial Net Zero Conference",
                   "Industrial Net Zero Conference 2027") > 0.9


def test_an_abbreviation_still_scores():
    assert mcs.sim("WFCC2026", "World Fuel Cell Conference 2026 (WFCC 2026)") > 0.0


def test_unrelated_events_do_not_score_as_similar():
    assert mcs.sim("Barclays CEO Energy-Power Conference",
                   "CrowdStrike Fal.Con 2026") < 0.3


def test_generic_words_alone_never_make_a_match():
    """"Conference"/"Summit"/"Expo" carry no identity - two events sharing only those must not
    look similar, which is how European Hydrogen Week was matched to a Houston summit."""
    assert mcs.sim("International Conference Summit Expo",
                   "Annual World Congress Forum Show") == 0.0


# ------------------------------------------------------------------ editions --
def test_series_drops_the_leading_year():
    assert mcs.series("2027-world-hydrogen-summit-rotterdam") == "world-hydrogen-summit-rotterdam"
    assert mcs.series("no-year-here") == "no-year-here"


def test_two_editions_of_one_conference_share_a_series():
    a = "2026-hydrogen-technology-world-expo-hamburg"
    b = "2027-hydrogen-technology-world-expo-hamburg"
    assert mcs.series(a) == mcs.series(b)


def test_different_conferences_do_not_share_a_series():
    assert mcs.series("2026-carbon-capture-usa-houston") != \
           mcs.series("2026-decarb-connect-north-america-houston")


# --------------------------------------------------------------------- dates --
def test_dates_parse_in_the_formats_their_sheets_actually_use():
    assert mcs.pdate("9/16/2025") == date(2025, 9, 16)
    assert mcs.pdate("2027-02-09") == date(2027, 2, 9)


def test_a_bare_year_is_accepted_but_a_blank_is_not_invented():
    assert mcs.pdate("sometime in 2027").year == 2027
    assert mcs.pdate("") is None
    assert mcs.pdate("to be announced") is None


# ------------------------------------------------------------------- urls --
def test_url_comparison_ignores_trailing_slash_and_case():
    assert mcs.norm_url("HTTPS://Example.com/Path/") == mcs.norm_url("https://example.com/Path")


def test_norm_url_of_blank_is_blank():
    assert mcs.norm_url("") == ""
    assert mcs.norm_url(None) == ""
