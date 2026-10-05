"""experiments/platform_census (ACT-25): the arithmetic and the classification behind the result files. Fixture-only."""
from datetime import datetime

from experiments.platform_census import census, countdown_scan


def test_hosts_are_put_in_a_family_by_domain_and_subdomain_only():
    assert census.family_of(census.host_of("https://sessionize.com/appsecil-2026")) == "Sessionize"
    assert census.family_of(census.host_of("https://codaspy27.hotcrp.com/")) == "HotCRP"
    assert census.family_of(census.host_of("https://events.secureworld.io/east-2026/")) == "SecureWorld (organiser platform)"
    assert census.family_of(census.host_of("https://notsessionize.com/")) == ""                 # a longer domain that merely ends the same way is not a sub-domain
    assert census.family_of(census.host_of("https://example.org/")) == "" and census.host_of("") == ""


def test_an_event_is_counted_once_per_family_even_if_two_of_its_addresses_are_on_it():
    rows = [{"event_id": "e1", "submission_url": "https://sessionize.com/a", "deadline_evidence_url": "https://sessionize.com/a", "main_info_url": "https://e1.example/", "url": ""},
            {"event_id": "e2", "submission_url": "", "deadline_evidence_url": "", "main_info_url": "https://www.secureworld.io/x", "url": ""}]
    fam = census.census(rows)
    assert list(fam["Sessionize"]) == ["e1"] and list(fam["SecureWorld (organiser platform)"]) == ["e2"]


def test_a_countdown_becomes_the_date_it_counts_to():
    assert countdown_scan.implied_date("2026-10-01T02:40:45Z", 132, 13, 14) == datetime(2027, 2, 10, 15, 54, 45)
    cd = countdown_scan.find_countdown("ACCESSIBILITY STATEMENT EXHIBITION WEBSITE BY ASP Starts:   132 DAYS 13 HOURS 14 MIN    REGISTER NOW")
    assert cd[:3] == (132, 13, 14) and cd[3].endswith("Starts:")                                  # the words before it say what it counts to


def test_a_page_with_no_countdown_has_none():
    assert countdown_scan.find_countdown("Join us June 10-12, 2027 in Boston. Early bird ends in two weeks.") is None
    assert countdown_scan.find_countdown("") is None
