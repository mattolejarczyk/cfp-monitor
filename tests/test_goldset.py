"""Offline tests for the gold-set loader/scorer (no xlsx needed)."""
from datetime import date

from cfp_monitor.goldset import serial_to_date, compare, GoldRecord
from cfp_monitor.models import ConferenceResult, Fact, CFPStatus


def test_serial_to_date():
    assert serial_to_date(43831) == date(2020, 1, 1)     # well-known Excel serial
    assert serial_to_date("43831") == date(2020, 1, 1)
    assert serial_to_date("Sponsorship Required") is None
    assert serial_to_date("") is None
    assert serial_to_date(0) is None


def _result(close=None, status="unclear", submit=None):
    r = ConferenceResult(start_url="https://c.test")
    if close:
        r.cfp_close_date = Fact(value=close)
    if submit:
        r.submission_url = Fact(value=submit)
    r.cfp_status = CFPStatus(status)
    return r


def test_compare_deadline_found_and_year_match():
    gold = GoldRecord("Conf", "https://c.test", date(2026, 6, 29), "45832", "Submitted", "", None)
    row = compare(_result(close="June 29, 2026", status="open"), gold)
    assert row["we_found_deadline"] is True
    assert row["gold_has_deadline"] is True
    assert row["deadline_year_match"] is True
    assert row["our_status"] == "open"
    assert row["gold_status"] == "Submitted"


def test_compare_no_deadline_extracted():
    gold = GoldRecord("Conf", "https://c.test", date(2026, 6, 29), "45832", "Submitted", "", None)
    row = compare(_result(close=None), gold)
    assert row["we_found_deadline"] is False
    assert row["deadline_year_match"] is None          # can't compare when we found nothing


def test_compare_gold_has_no_date():
    gold = GoldRecord("Conf", "https://c.test", None, "Sponsorship Required", "Closed", "detail", None)
    row = compare(_result(close="TBD"), gold)
    assert row["gold_has_deadline"] is False
    assert row["gold_deadline"] == "Sponsorship Required"


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
