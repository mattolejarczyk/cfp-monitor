"""Which grounding claim describes which crawl record.

The rule under test: when several claims share a conference key, attach the one that clearly
describes this record -- and when none clearly does, attach NOTHING. A row wearing another
event's evidence is wrong in a way nobody downstream can see.
"""
from cfp_monitor.storage import pick_claim


def claim(name, edition, state="verified", **kw):
    d = {"_name": name, "_edition": edition, "verify_state": state,
         "verify_detail": "d", "deadline_quote": "q", "deadline_evidence_url": "u",
         "is_projected": "false"}
    d.update(kw)
    return d


def rec(name, edition):
    return {"name": name, "edition": edition}


def test_no_candidates_gives_nothing():
    assert pick_claim(rec("CES 2027", "2027"), []) == {}


def test_a_single_candidate_is_used():
    out = pick_claim(rec("CES 2027", "2027"), [claim("CES 2027", "2027")])
    assert out["verify_state"] == "verified"


def test_internal_matching_fields_never_leak_into_the_export():
    out = pick_claim(rec("CES 2027", "2027"), [claim("CES 2027", "2027")])
    assert "_name" not in out and "_edition" not in out


def test_a_different_edition_is_never_borrowed():
    """Our 2025 record must not wear a 2027 claim's evidence."""
    assert pick_claim(rec("ShowStoppers @ IFA 25", "2025"),
                      [claim("ShowStoppers at CES 2027", "2027")]) == {}


def test_the_real_showstoppers_collision_declines():
    """Both claims sit on showstoppers.com; neither is our 2025 record."""
    out = pick_claim(rec("ShowStoppers @ IFA 25", "2025"),
                     [claim("ShowStoppers at CES 2027", "2027"),
                      claim("ShowStoppers at IFA 2026", "2026")])
    assert out == {}


def test_edition_alone_can_disambiguate():
    out = pick_claim(rec("ShowStoppers", "2026"),
                     [claim("ShowStoppers at CES 2027", "2027", state="not_found"),
                      claim("ShowStoppers at IFA 2026", "2026", state="contradicted")])
    assert out["verify_state"] == "contradicted"


def test_same_edition_siblings_need_a_name_to_separate_them():
    """CES 2027 and CES Unveiled Las Vegas 2027 share ces.tech AND the edition."""
    out = pick_claim(rec("CES 2027", "2027"),
                     [claim("CES 2027 (Consumer Electronics Show)", "2027", state="verified"),
                      claim("CES Unveiled Las Vegas 2027", "2027", state="not_found")])
    assert out["verify_state"] == "verified"


def test_an_exact_name_beats_a_merely_nested_one():
    out = pick_claim(rec("IFA Berlin 2026", "2026"),
                     [claim("IFA Berlin 2026", "2026", state="verified"),
                      claim("IFA Berlin 2026 Global Markets", "2026", state="not_found")])
    assert out["verify_state"] == "verified"


def test_two_equally_plausible_names_decline_rather_than_guess():
    out = pick_claim(rec("OWASP Global AppSec", "2026"),
                     [claim("OWASP Global AppSec Europe 2026", "2026"),
                      claim("OWASP Global AppSec USA 2026", "2026")])
    assert out == {}


def test_an_unknown_edition_on_our_side_does_not_block_a_lone_claim():
    out = pick_claim(rec("Tokyo Game Show", ""), [claim("Tokyo Game Show 2026", "2026")])
    assert out["verify_state"] == "verified"


def test_claims_with_no_edition_are_usable_when_ours_is_known():
    """Older grounding rows predate the edition column; they should not be discarded."""
    out = pick_claim(rec("Some Event", "2027"), [claim("Some Event", "")])
    assert out["verify_state"] == "verified"


def test_a_dated_claim_is_preferred_over_an_undated_one():
    out = pick_claim(rec("Some Event", "2027"),
                     [claim("Some Event", "2027", state="contradicted"),
                      claim("Some Event", "", state="verified")])
    assert out["verify_state"] == "contradicted"


# ---- duplicates are not rivals ----------------------------------------------
def test_the_same_event_delivered_twice_is_collapsed_not_declined():
    """Upstream renames events between deliveries, so one event arrives under two ids.
    Declining on those throws away evidence we actually hold."""
    out = pick_claim(rec("gamescom 2026", "2026"),
                     [claim("gamescom 2026", "2026", state="not_found"),
                      claim("gamescom 2026", "2026", state="not_found")])
    assert out["verify_state"] == "not_found"


def test_a_duplicate_pair_yields_the_row_that_resolved_something():
    out = pick_claim(rec("Troopers", "2026"),
                     [claim("Troopers 2026", "2026", state="not_found"),
                      claim("Troopers 2026", "2026", state="verified")])
    assert out["verify_state"] == "verified"


def test_duplicates_that_disagree_decisively_still_decline():
    """verified vs contradicted on one event is a real conflict, not a duplicate."""
    out = pick_claim(rec("Troopers", "2026"),
                     [claim("Troopers 2026", "2026", state="verified"),
                      claim("Troopers 2026", "2026", state="contradicted")])
    assert out == {}


def test_a_renamed_duplicate_is_still_matched_through_the_name_test():
    out = pick_claim(rec("IoT Tech Expo", "2027"),
                     [claim("IoT Tech Expo Global 2027", "2027", state="not_found"),
                      claim("IoT Tech Expo Global 2027", "2027", state="not_found")])
    assert out["verify_state"] == "not_found"


def test_distinct_sibling_events_are_never_collapsed():
    """Same key, same edition, genuinely different events -- must still decline."""
    out = pick_claim(rec("OWASP Global AppSec", "2026"),
                     [claim("OWASP Global AppSec Europe 2026", "2026"),
                      claim("OWASP Global AppSec USA 2026", "2026")])
    assert out == {}


# ---- is the collapsed claim actually OURS? ----------------------------------
def test_a_sibling_call_on_the_same_domain_is_not_borrowed():
    """Real case: IBC's Accelerator programme wore IBC Technical Papers' evidence, purely
    because both live on show.ibc.org in the same edition."""
    out = pick_claim(rec("IBC Accelerator Media Innovation Programme", "2026"),
                     [claim("IBC 2026 (International Broadcasting Convention)", "2026"),
                      claim("IBC 2026 (International Broadcasting Convention)", "2026")])
    assert out == {}


def test_a_reordered_year_still_counts_as_the_same_event():
    """'AAOS 2027 Annual Meeting' vs 'AAOS Annual Meeting 2027' -- neither contains the
    other, so substring matching would wrongly decline."""
    out = pick_claim(rec("AAOS 2027 Annual Meeting", "2027"),
                     [claim("AAOS Annual Meeting 2027", "2027", state="verified")])
    assert out["verify_state"] == "verified"


def test_our_abbreviated_name_still_matches_their_full_one():
    out = pick_claim(rec("TROOPERS", "2026"),
                     [claim("Troopers 2026 (Troopers Cybersecurity Conference)", "2026",
                            state="verified")])
    assert out["verify_state"] == "verified"


def test_an_unnamed_record_falls_back_to_the_key_match():
    out = pick_claim(rec("", "2026"), [claim("Anything 2026", "2026", state="not_found")])
    assert out["verify_state"] == "not_found"


def test_duplicates_spelled_differently_are_still_collapsed():
    """Real case: 'AAOS 2027 Annual Meeting' and 'AAOS Annual Meeting 2027' arrived as two
    rows for one event, and exact-spelling grouping declined both."""
    out = pick_claim(rec("AAOS 2027 Annual Meeting", "2027"),
                     [claim("AAOS 2027 Annual Meeting", "2027", state="not_found"),
                      claim("AAOS Annual Meeting 2027", "2027", state="verified")])
    assert out["verify_state"] == "verified"


def test_weakly_related_siblings_are_not_collapsed():
    """'Troopers 2026 (18th Annual)' and 'Troopers 2026 (Cybersecurity Conference)' may well
    be one event, but nothing here proves it -- decline rather than guess."""
    out = pick_claim(rec("TROOPERS", "2026"),
                     [claim("Troopers 2026 (Troopers Cybersecurity Conference)", "2026"),
                      claim("Troopers 2026 (18th Annual)", "2026")])
    assert out == {}


if __name__ == "__main__":
    import sys
    mod = sys.modules[__name__]
    fns = [v for k, v in sorted(vars(mod).items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"{len(fns)} passed")
