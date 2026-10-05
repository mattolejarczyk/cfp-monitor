"""ACT-19: the parts of trap cases T06, T07 and T08 that code can judge, as offline tests. What needs a person stays HUMAN in docs/qa/trap-cases.json.

  T06 one event under two names   code CAN: report the pair (same page, city, start date), and refuse an unevidenced 'discontinued'. A person judges: which name is right.
  T07 a dead domain               code CAN: with no page nothing is accepted, nothing is proven, no date is read. A person judges: whether the event is really over.
  T08 one brand, two events       code CAN: two ids, never paired by the duplicate detector. A person judges: whether a method keeps the two sets of dates apart.
"""
import importlib.util
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("fde", ROOT / "scripts" / "find_duplicate_events.py")
fde = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fde)

from src.cfp_monitor.grounding import event_id          # noqa: E402

SAF_OLD = {"event_id": "2027-saf-europe-summit-rotterdam", "name": "SAF Europe Summit 2027", "url": "https://www.sustainablefuelsglobal.com/",
           "city": "Rotterdam", "start_date": "2027-04-13"}
SAF_NEW = {"event_id": "2027-sustainable-fuels-global-summit-rotterdam", "name": "Sustainable Fuels Global Summit 2027", "url": "https://sustainablefuelsglobal.com",
           "city": "Rotterdam", "start_date": "2027-04-13"}
MILE_HIGH = {"event_id": "2026-wild-west-hackin-fest-mile-high-denver", "name": "Wild West Hackin' Fest @ Mile High 2026", "url": "https://wildwesthackinfest.com/",
             "city": "Denver", "start_date": "2026-03-12"}
DEADWOOD = {"event_id": "2026-wild-west-hackin-fest-deadwood-deadwood", "name": "Wild West Hackin' Fest Deadwood 2026", "url": "https://wildwesthackinfest.com/",
            "city": "Deadwood", "start_date": "2026-10-08"}


def test_t06_two_names_one_page_city_and_date_are_reported_as_a_pair_and_nothing_is_decided():
    assert fde.same_site_pairs([SAF_OLD, SAF_NEW]) == [(SAF_OLD, SAF_NEW)]
    assert fde.same_site_pairs([SAF_NEW, SAF_OLD, MILE_HIGH]) == [(SAF_NEW, SAF_OLD)]
    # a different start date or city, or a listing/platform host, is not a rename
    assert not fde.same_site_pairs([SAF_OLD, {**SAF_NEW, "start_date": "2027-06-01"}])
    assert not fde.same_site_pairs([SAF_OLD, {**SAF_NEW, "city": "Amsterdam"}])
    assert not fde.same_site_pairs([{**SAF_OLD, "url": "https://sessionize.com/x"}, {**SAF_NEW, "url": "https://sessionize.com/x"}])
    assert not fde.same_site_pairs([{**SAF_OLD, "url": "https://cfptime.org/"}, {**SAF_NEW, "url": "https://cfptime.org/"}])


def test_t06_a_retire_claim_without_its_own_evidence_page_is_refused_by_the_gate(tmp_path):
    from scripts.accept_delivery import Gate
    g = Gate(str(tmp_path / "x.csv"), network=False)
    base = {"CONFERENCE": "SAF Europe Summit 2027", "STATUS": "Closed", "STATUS DETAILS": "This event has been discontinued in favor of the new brand.",
            "NOTES": "", "IS_PROJECTED": "false", "LIFECYCLE_EVIDENCE_URL": "", "LIFECYCLE_QUOTE": ""}
    g.rows = [base]
    g.check_schema_rules()
    r16 = [x for x in g.results if x[0] == "R16"][0]
    assert r16[2] is False                                              # asserted, no evidence: refused
    g2 = Gate(str(tmp_path / "y.csv"), network=False)
    g2.rows = [{**base, "LIFECYCLE_EVIDENCE_URL": "https://www.sustainablefuelsglobal.com/", "LIFECYCLE_QUOTE": "SAF Europe Summit is now Sustainable Fuels Global Summit"}]
    g2.check_schema_rules()
    assert [x for x in g2.results if x[0] == "R16"][0][2] is True       # evidenced: allowed


def test_t07_a_dead_domain_yields_no_page_so_nothing_is_accepted_proven_or_read():
    from experiments.read_the_page_pass.pass_lib import accept, looks_dateless
    from scripts.start_date_arbiter import proven
    from src.cfp_monitor.self_heal import find_conference_dates_sentence
    from src.cfp_monitor.verify import earliest_deadline
    page = ""                                                           # fetch_text returns "" for a domain that does not resolve
    assert looks_dateless(page)                                         # the reader knows it has read nothing
    assert accept("start_date", {"value": "2026-04-01", "quote": "Nov 24-25, 2026"}, page, "2026") == ("", "quote is not on the page")
    assert proven([("https://futurefuelsmena.com/", page)], date(2026, 11, 24))[0] is False
    assert find_conference_dates_sentence(page, "2026-11-24") == (False, "")
    assert earliest_deadline(page, date(2026, 10, 3))["date"] == ""
    assert accept("start_date", {"value": "", "quote": ""}, page, "2026") == ("", "blank")                # a blank answer stays blank


def test_t08_one_brand_two_events_keep_two_ids_and_are_never_paired():
    assert event_id(MILE_HIGH["name"], "2026", "Denver") != event_id(DEADWOOD["name"], "2026", "Deadwood")
    assert not fde.same_site_pairs([MILE_HIGH, DEADWOOD])               # same page, different city and dates: two events
    assert {r["start_date"] for r in (MILE_HIGH, DEADWOOD)} == {"2026-03-12", "2026-10-08"}
