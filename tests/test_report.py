"""Offline test for the weekly report."""
from cfp_monitor.models import ConferenceResult, Fact, CFPStatus
from cfp_monitor.quality_gate import Quality
from cfp_monitor.storage import Store
from cfp_monitor.report import weekly_report


def test_weekly_report():
    s = Store()
    run = s.start_run()
    r = ConferenceResult(start_url="https://a.com", pages_crawled=3)
    r.name = Fact(value="Alpha")
    r.cfp_status = CFPStatus("open")
    r.cfp_close_date = Fact(value="2099-06-29")
    s.upsert(r, Quality.PASS, ["Cyber"], run)
    s.finish_run(run, {"url_count": 1, "PASS": 1})
    md = weekly_report(s)
    assert "Weekly Report" in md
    assert "Tracked conferences:** 1" in md
    assert "Upcoming deadlines" in md and "2099-06-29" in md
    assert "System health" in md and "PASS 1" in md


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
