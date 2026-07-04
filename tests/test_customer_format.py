"""Offline tests for the 15-column customer-format transform/export."""
import csv
import os
import tempfile

from cfp_monitor.customer_format import (
    CUSTOMER_HEADERS, excel_serial, to_customer_row, write_customer_csv,
)


def _rec(**kw):
    base = dict(name="Alpha Conf", url="https://alpha.test", location="Austin, TX",
                start_dates="Sept 2026", last_checked="2026-07-03T12:00:00+00:00",
                submission_deadline="2026-06-29", verified=False, priority="High",
                status="open", status_details="Open — page states the call is open",
                submission_url="https://alpha.test/cfp", coordinator_email="",
                overview="A conference.", categories="Cyber,AppSec", notes=None)
    base.update(kw)
    return base


def test_row_has_exact_headers():
    row = to_customer_row(_rec())
    assert list(row.keys()) == CUSTOMER_HEADERS


def test_status_mapping():
    assert to_customer_row(_rec(status="open"))["STATUS"] == "Open"
    assert to_customer_row(_rec(status="closed"))["STATUS"] == "Closed"
    assert to_customer_row(_rec(status="unclear"))["STATUS"] == "Needs Review"
    assert to_customer_row(_rec(status="none"))["STATUS"] == "No Opportunity"


def test_verified_label():
    assert to_customer_row(_rec(verified=False))["SUBMISSION DATE VERIFIED"] == "Needs Verification"
    assert to_customer_row(_rec(verified=True))["SUBMISSION DATE VERIFIED"] == "Yes"


def test_latest_update_shortened():
    assert to_customer_row(_rec())["LATEST UPDATE"] == "2026-07-03"


def test_write_csv_roundtrip():
    path = os.path.join(tempfile.mkdtemp(), "out.csv")
    n = write_customer_csv([_rec(name="A"), _rec(name="B")], path)
    assert n == 2
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == CUSTOMER_HEADERS
    assert len(rows) == 3                      # header + 2
    assert rows[1][0] == "A" and rows[2][0] == "B"


def test_excel_serial_known_value():
    # 2020-01-01 is Excel serial 43831 — well-known reference value.
    assert excel_serial("2020-01-01") == 43831
    assert excel_serial(None) is None
    assert excel_serial("not a date") is None


def test_no_public_deadline_note():
    row = to_customer_row(_rec(submission_deadline="", status="open",
                               submission_url="https://alpha.test/cfp", status_details="Open"))
    assert "No public deadline found" in row["STATUS DETAILS"]


def test_deadline_present_no_note():
    row = to_customer_row(_rec(submission_deadline="2026-06-29", status="open"))
    assert "No public deadline" not in row["STATUS DETAILS"]


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
