"""Offline tests for URL normalization dedupe + junk-URL filtering (HubSpot fix)."""
from cfp_monitor.scoring import normalize_url, is_crawlable


def test_strips_locale_and_tracking_params():
    base = normalize_url("https://x.com/speakers")
    assert normalize_url("https://x.com/speakers?hsLang=en-au") == base
    assert normalize_url("https://x.com/speakers?utm_source=news&utm_medium=email") == base
    assert normalize_url("https://x.com/speakers/?hsLang=fr") == base


def test_keeps_meaningful_query():
    assert "event=abc" in normalize_url("https://x.com/e?event=abc")


def test_is_crawlable_rejects_junk():
    assert is_crawlable("https://x.com/cs/c?cta_guid=340d8cfc") is False   # HubSpot CTA tracking
    assert is_crawlable("https://x.com/hs-fs/hubfs/pic.jpg") is False
    assert is_crawlable("https://x.com/brochure.pdf") is False
    assert is_crawlable("https://x.com/_hcms/mem/login") is False


def test_is_crawlable_allows_content():
    assert is_crawlable("https://x.com/speakers") is True
    assert is_crawlable("https://x.com/call-for-papers") is True


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
