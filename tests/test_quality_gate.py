"""Offline tests for the crawl quality gate."""
from cfp_monitor.quality_gate import CrawlSignals, Quality, classify, classify_result
from cfp_monitor.models import ConferenceResult, Fact, CFPStatus


def _sig(**kw):
    base = dict(url="https://x.test", fetched=True, status_code=200, content_chars=2000)
    base.update(kw)
    return CrawlSignals(**base)


def test_error_wins():
    assert classify(_sig(error="boom")).verdict is Quality.ERROR


def test_no_response_blocked():
    assert classify(_sig(fetched=False, status_code=None, content_chars=0)).verdict is Quality.BLOCKED


def test_antibot_status_blocked():
    for code in (403, 429, 503):
        assert classify(_sig(status_code=code)).verdict is Quality.BLOCKED, code


def test_server_error_blocked():
    assert classify(_sig(status_code=502)).verdict is Quality.BLOCKED


def test_body_marker_blocked():
    r = classify(_sig(status_code=200, body_sample="Just a moment... Cloudflare"))
    assert r.verdict is Quality.BLOCKED


def test_404_partial():
    assert classify(_sig(status_code=404)).verdict is Quality.PARTIAL


def test_thin_content_partial():
    assert classify(_sig(status_code=200, content_chars=120)).verdict is Quality.PARTIAL


def test_good_pass():
    assert classify(_sig(status_code=200, content_chars=5000)).verdict is Quality.PASS


def test_result_no_pages_blocked():
    r = ConferenceResult(start_url="https://x.test", pages_crawled=0)
    assert classify_result(r).verdict is Quality.BLOCKED


def test_result_insufficient_partial():
    r = ConferenceResult(start_url="https://x.test", pages_crawled=4)
    r.status_basis = "insufficient_evidence"
    assert classify_result(r).verdict is Quality.PARTIAL


def test_result_core_pass():
    r = ConferenceResult(start_url="https://x.test", pages_crawled=4)
    r.name = Fact(value="Big Conf")
    r.cfp_status = CFPStatus.open
    assert classify_result(r).verdict is Quality.PASS


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
