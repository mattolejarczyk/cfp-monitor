"""Offline tests for aggregator-navigation scoring."""
from cfp_monitor.aggregator import score_event_link, pick_event_link, looks_like_aggregator

CTX = {"name": "Security BSides Austin", "location": "Austin, Texas, USA", "dates": "April 2026"}


def test_city_match_scores_high():
    s_austin = score_event_link("https://bsidesaustin.com/", "BSides Austin 2026", CTX)
    s_other = score_event_link("https://bsides.org/event/bsides-tampa/", "BSides Tampa", CTX)
    assert s_austin > s_other
    assert s_austin >= 1.5


def test_stale_year_loses_to_current():
    fresh = score_event_link("https://bsidesaustin.com/", "", CTX)
    stale = score_event_link("https://old.example.org/BSidesAustin2015", "BSidesAustin", CTX)
    assert fresh > stale


def test_social_host_loses_to_own_site():
    own = score_event_link("https://bsidesaustin.com/", "", CTX)
    social = score_event_link("https://twitter.com/BSidesAustin", "BSides Austin", CTX)
    assert own > social


def test_pick_prefers_own_site_over_stale_mirror():
    # Real bsides.org/events shape: stale wiki + social both name-match; own site should win.
    links = [
        {"href": "http://www.securitybsides.com/w/page/91156017/BSidesAustin2015", "text": "BSidesAustin"},
        {"href": "https://twitter.com/BSidesAustin", "text": ""},
        {"href": "https://bsidesaustin.com/", "text": ""},
    ]
    assert pick_event_link(links, CTX, "https://bsides.org") == "https://bsidesaustin.com/"


def test_pick_event_link():
    links = [
        {"href": "https://bsides.org/event/bsides-tampa/", "text": "BSides Tampa"},
        {"href": "https://bsidesaustin.com/", "text": "BSides Austin 2026"},
        {"href": "https://bsides.org/about", "text": "About"},
    ]
    assert pick_event_link(links, CTX, "https://securitybsides.com") == "https://bsidesaustin.com/"


def test_pick_none_when_no_match():
    links = [{"href": "https://x.com/about", "text": "About"},
             {"href": "https://x.com/contact", "text": "Contact"}]
    assert pick_event_link(links, CTX, "https://x.com") is None


def test_looks_like_aggregator():
    assert looks_like_aggregator(has_name=False, status_basis="insufficient_evidence", num_links=50) is True
    assert looks_like_aggregator(has_name=True, status_basis="explicit_open", num_links=50) is False
    assert looks_like_aggregator(has_name=False, status_basis="insufficient_evidence", num_links=5) is False


def _run():
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for fn in fns:
        try:
            fn(); print(f"PASS {fn.__name__}")
        except Exception as e:
            bad += 1; print(f"FAIL {fn.__name__}: {e!r}")
    print(f"--- {len(fns)-bad}/{len(fns)} passed ---")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    _run()
