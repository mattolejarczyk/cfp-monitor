"""Offline tests for the alerts engine."""
from datetime import date, timedelta

from cfp_monitor.models import ConferenceResult, Fact, CFPStatus
from cfp_monitor.quality_gate import Quality
from cfp_monitor.storage import Store
from cfp_monitor.alerts import parse_deadline, compute_alerts, digest_markdown, Alert


def mk(url, name, status="unclear", close=None):
    r = ConferenceResult(start_url=url, pages_crawled=3)
    r.name = Fact(value=name)
    r.cfp_status = CFPStatus(status)
    if close:
        r.cfp_close_date = Fact(value=close)
    return r


def test_parse_deadline():
    assert parse_deadline("2026-06-29") == date(2026, 6, 29)
    assert parse_deadline("15 May 2026") == date(2026, 5, 15)
    assert parse_deadline("May 15, 2026") == date(2026, 5, 15)
    assert parse_deadline("TBD") is None


def test_new_conference_alert():
    s = Store()
    s.upsert(mk("https://a.com", "Alpha"), Quality.PASS, run_id=s.start_run())
    al = compute_alerts(s, today=date(2026, 1, 1))
    assert any(a.kind == "new_conference" and a.level == "MEDIUM" for a in al)


def test_cfp_open_alert():
    s = Store()
    s.upsert(mk("https://a.com", "Alpha", status="unclear"), Quality.PASS, run_id=s.start_run())
    run2 = s.start_run()
    s.upsert(mk("https://a.com", "Alpha", status="open"), Quality.PASS, run_id=run2)
    al = compute_alerts(s, run_id=run2, today=date(2026, 1, 1))
    assert any(a.kind == "cfp_open" and a.level == "HIGH" for a in al)


def test_deadline_soon_alert():
    s = Store()
    soon = (date.today() + timedelta(days=10)).isoformat()
    s.upsert(mk("https://b.com", "Beta", close=soon), Quality.PASS, run_id=s.start_run())
    al = compute_alerts(s)
    assert any(a.kind == "deadline_soon" and a.level == "HIGH" for a in al)


def test_digest_markdown():
    md = digest_markdown([Alert("HIGH", "x", "C", "the message", "http://u")])
    assert "HIGH" in md and "the message" in md
    assert "No new alerts" in digest_markdown([])


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
