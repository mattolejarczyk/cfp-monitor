"""Offline tests for the grounding import/normalization layer.

Covers the three things we deliberately do NOT trust the grounding model with: the city
(it returned venues), the canonical join key, and the controlled vocabulary -- plus the
crawl-free contradiction detection and the derive-don't-mutate rule.
"""
from datetime import date

from cfp_monitor.grounding import (
    clean_city, detect_issues, event_id, gated_status, normalize_cfp_model,
    normalize_rows, parse_loose_date,
)

TODAY = date(2026, 7, 29)


def _raw(**kw):
    base = {
        "CONFERENCE": "Test Conf 2027", "CONFERENCE URL": "https://t.example",
        "LOCATION": "Somewhere, Nowhere", "EDITION": "2027", "Market": "Robotics",
        "CITY": "Somewhere", "STATE_PROVINCE": "", "COUNTRY": "Nowhere",
        "SUBMISSION DEADLINE": "", "SUBMISSION URL": "https://t.example/cfp",
        "CFP MODEL TYPE": "Fixed Deadline", "STATUS": "Open", "OVERVIEW": "",
        "CATEGORIES": "", "COORDINATOR EMAIL": "", "DEADLINE_QUOTE": "x",
        "IS_PROJECTED": "x", "SOURCE_AS_OF": "x", "DEADLINE_EVIDENCE_URL": "",
        "MAIN_INFO_URL": "", "START DATE": "",
    }
    base.update(kw)
    return base


# ---- city: venue vs settlement ---------------------------------------------
def test_venue_in_city_is_repaired():
    assert clean_city("Messe Berlin, Berlin, Germany", "Messe Berlin", "Berlin", "Germany") == "Berlin"
    assert clean_city("Fira Gran Via, Barcelona, Spain", "Fira Gran Via", "", "Spain") == "Barcelona"
    assert clean_city("Makuhari Messe, Chiba, Japan", "Makuhari Messe", "", "Japan") == "Chiba"


def test_us_style_location_keeps_the_city_not_the_state():
    assert clean_city("Las Vegas, Nevada, USA", "Las Vegas", "Nevada", "USA") == "Las Vegas"


def test_city_state_is_not_destroyed_by_dropping_the_state():
    """Regression: STATE_PROVINCE == the city (Berlin, Hong Kong). Dropping the state token
    left only the venue, so the city came back empty."""
    assert clean_city("AsiaWorld-Expo, Hong Kong", "AsiaWorld-Expo", "Hong Kong", "Hong Kong") == "Hong Kong"


def test_tbd_location_yields_no_city_never_invented():
    assert clean_city("USA (Location TBD), USA", "", "", "USA") == ""
    assert clean_city("Location TBD", "", "", "") == ""


# ---- canonical id ----------------------------------------------------------
def test_event_id_excludes_market_so_one_event_has_one_id():
    a = event_id("CES 2027 (Consumer Electronics Show)", "2027", "Las Vegas")
    b = event_id("CES 2027 (Consumer Electronics Show)", "2027", "Las Vegas")
    assert a == b == "2027-ces-las-vegas"


def test_event_id_does_not_repeat_the_year():
    assert event_id("Formnext 2026", "2026", "Frankfurt").count("2026") == 1


def test_event_id_placeholders_for_missing_place():
    assert event_id("Some Conf", "2027", "").endswith("-tbd")
    assert event_id("Some Conf", "2027", "", "Online event").endswith("-virtual")
    assert not event_id("Some Conf", "2027", "").endswith("-")


# ---- vocabulary ------------------------------------------------------------
def test_cfp_model_variants_collapse_to_one_enum_value():
    for variant in ("Curated/Invite", "Invite/Curated", "Invitation Only", "invite only"):
        assert normalize_cfp_model(variant) == "Invite Only", variant
    assert normalize_cfp_model("Fixed Deadline") == "Fixed Deadline"
    assert normalize_cfp_model("") == "Not Announced"
    assert normalize_cfp_model("something novel") == "Not Announced"


# ---- crawl-free contradictions --------------------------------------------
def test_open_with_passed_deadline_is_flagged_with_day_count():
    rows, _ = normalize_rows([_raw(STATUS="Open", **{"SUBMISSION DEADLINE": "3/15/2026"})], TODAY)
    flags = " ".join(rows[0].issues)
    assert "PASSED_DEADLINE" in flags and "136 days past" in flags


def test_closed_with_future_deadline_is_flagged():
    rows, _ = normalize_rows([_raw(STATUS="Closed", **{"SUBMISSION DEADLINE": "12/1/2026"})], TODAY)
    assert "CLOSED_BUT_DEADLINE_FUTURE" in rows[0].issues


def test_deadline_after_event_start_is_flagged():
    rows, _ = normalize_rows(
        [_raw(**{"SUBMISSION DEADLINE": "8/31/2026", "START DATE": "3/12/2026"})], TODAY)
    assert "DEADLINE_AFTER_EVENT_START" in rows[0].issues


def test_consistent_future_deadline_has_no_date_issue():
    rows, _ = normalize_rows([_raw(STATUS="Open", **{"SUBMISSION DEADLINE": "12/1/2026"})], TODAY)
    assert not [i for i in rows[0].issues if "DEADLINE" in i]


# ---- derive, don't mutate --------------------------------------------------
def test_raw_status_is_preserved_while_gate_derives_closed():
    rows, _ = normalize_rows([_raw(STATUS="Open", **{"SUBMISSION DEADLINE": "3/15/2026"})], TODAY)
    r = rows[0]
    assert r.grounding_status == "Open"            # source untouched, for audit
    assert gated_status(r, TODAY) == "Closed"      # display value derived
    assert r.raw["STATUS"] == "Open"


def test_gate_leaves_a_live_row_alone():
    rows, _ = normalize_rows([_raw(STATUS="Open", **{"SUBMISSION DEADLINE": "12/1/2026"})], TODAY)
    assert gated_status(rows[0], TODAY) == "Open"


# ---- dedupe / membership ---------------------------------------------------
def test_same_event_in_two_markets_is_kept_with_one_id():
    rows, rep = normalize_rows([
        _raw(CONFERENCE="CES 2027", CITY="Las Vegas", Market="ConsumerElectronics"),
        _raw(CONFERENCE="CES 2027", CITY="Las Vegas", Market="Semiconductor"),
    ], TODAY)
    assert len(rows) == 2                      # both market memberships survive
    assert rows[0].event_id == rows[1].event_id
    assert rep["distinct_events"] == 1
    assert rep["duplicates"] == 0


def test_exact_repeat_of_event_and_market_is_dropped():
    rows, rep = normalize_rows([
        _raw(CONFERENCE="Black Hat USA 2026", CITY="Las Vegas", Market="Cybersecurity"),
        _raw(CONFERENCE="Black Hat USA 2026", CITY="Las Vegas", Market="Cybersecurity"),
    ], TODAY)
    assert len(rows) == 1 and rep["duplicates"] == 1


def test_placeholder_provenance_fields_read_as_empty():
    """The backfill wrote 'x' into the new provenance columns; that is not a real quote."""
    rows, _ = normalize_rows([_raw(DEADLINE_QUOTE="x", IS_PROJECTED="x")], TODAY)
    assert rows[0].deadline_quote == "" and rows[0].is_projected == ""


# ---- date parsing ----------------------------------------------------------
def test_loose_date_parsing_is_conservative():
    assert parse_loose_date("3/15/2026") == date(2026, 3, 15)
    assert parse_loose_date("2026-03-15") == date(2026, 3, 15)
    for vague in ("March 2026", "TBD", "", None, "Q4 2026"):
        assert parse_loose_date(vague) is None


# ---- market vocabulary must not fork on import ------------------------------
def test_grounding_market_labels_resolve_to_our_canonical_markets():
    """Regression: grounding emits camel-case contractions ("AdditiveMfg"). Passing those
    through unmapped forked the vocabulary -- 8 markets became 13 and every filter split."""
    import sqlite3
    from cfp_monitor.markets import MarketRegistry

    reg = MarketRegistry(sqlite3.connect(":memory:"))
    assert reg.resolve("AdditiveMfg") == "Additive Mfg"
    assert reg.resolve("ConsumerElectronics") == "Consumer Electronics"
    assert reg.resolve("Bioeconomy") == "Bioeconomy"
    assert reg.resolve("BioMedTech") == "BioMedTech"
    # the client-workbook label for the cyber market resolves to the market name
    assert reg.resolve("Arnica") == "Cybersecurity"
    # our earlier, longer names still resolve so nothing breaks on old data
    assert reg.resolve("Additive Manufacturing & 3D Printing") == "Additive Mfg"
    assert reg.resolve("Biotech & MedTech") == "BioMedTech"
    for exact in ("Robotics", "Semiconductor", "Utility"):
        assert reg.resolve(exact) == exact


def test_unknown_market_label_is_not_auto_registered():
    """An unrecognized label must be reported, never invented into the registry."""
    import sqlite3
    from cfp_monitor.markets import MarketRegistry

    reg = MarketRegistry(sqlite3.connect(":memory:"))
    before = set(reg.all())
    assert reg.resolve("SomeBrandNewSector") is None
    assert set(reg.all()) == before


# ---- one event, several calls ------------------------------------------------
def test_speaking_stays_unsuffixed_so_existing_keys_do_not_move():
    """Everything imported before OPPORTUNITY_TYPE existed is a speaking row. Suffixing it
    would orphan several hundred already-loaded records across eight markets."""
    from cfp_monitor.grounding import event_id
    bare = event_id("CEDIA Expo", "2026", "Denver")
    assert event_id("CEDIA Expo", "2026", "Denver", opportunity="Speaking") == bare
    assert event_id("CEDIA Expo", "2026", "Denver", opportunity="") == bare


def test_a_second_opportunity_gets_its_own_key():
    """The collision this prevents: CEDIA's call for presentations and its Best of Show awards
    entry are different calls with different deadlines; on one key the second overwrites."""
    from cfp_monitor.grounding import event_id
    speaking = event_id("CEDIA Expo", "2026", "Denver", opportunity="Speaking")
    awards = event_id("CEDIA Expo", "2026", "Denver", opportunity="Awards")
    exhibiting = event_id("CEDIA Expo", "2026", "Denver", opportunity="Exhibiting")
    assert len({speaking, awards, exhibiting}) == 3
    assert awards.endswith("-awards")


def test_opportunity_rows_both_survive_the_loader():
    """End to end: two rows, same event, different calls -- neither may be dropped."""
    from cfp_monitor.grounding import normalize_rows
    base = {"CONFERENCE": "CEDIA Expo", "CONFERENCE URL": "https://cediaexpo.com/",
            "Market": "ConsumerElectronics", "EDITION": "2026", "CITY": "Denver",
            "STATE_PROVINCE": "Colorado", "COUNTRY": "USA", "LOCATION": "Denver, CO"}
    rows, rep = normalize_rows([
        dict(base, OPPORTUNITY_TYPE="Speaking", **{"SUBMISSION DEADLINE": "3/31/2026"}),
        dict(base, OPPORTUNITY_TYPE="Awards", **{"SUBMISSION DEADLINE": "8/21/2026"}),
    ])
    assert rep["duplicates"] == 0
    assert len(rows) == 2
    assert len({r.event_id for r in rows}) == 2


def test_a_true_duplicate_is_still_collapsed():
    """The dedupe must keep working: same event, same opportunity, twice."""
    from cfp_monitor.grounding import normalize_rows
    base = {"CONFERENCE": "CEDIA Expo", "CONFERENCE URL": "https://cediaexpo.com/",
            "Market": "ConsumerElectronics", "EDITION": "2026", "CITY": "Denver"}
    rows, rep = normalize_rows([dict(base, OPPORTUNITY_TYPE="Awards"),
                                dict(base, OPPORTUNITY_TYPE="Awards")])
    assert rep["duplicates"] == 1
    assert len(rows) == 1
