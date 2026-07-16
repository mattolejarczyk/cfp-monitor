"""Regression tests for customer URL-list uploads."""
import io
from datetime import date

from openpyxl import Workbook

from cfp_monitor.uploads import (
    normalize_urls_and_contexts,
    uploaded_urls_and_contexts,
    urls_from_upload,
)


def _xlsx_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet["A1"] = "Conference"
    sheet["B1"] = "Conference URL"
    sheet["A2"] = "IROS 2026"
    sheet["B2"] = "https://iros2026.org/"
    sheet["C2"] = "Kyoto, Japan"
    sheet["D2"] = date(2026, 9, 27)
    sheet["A3"] = "RoboBusiness"
    sheet["B3"] = "https://www.robobusiness.com/"
    sheet["C3"] = "Santa Clara, California"
    sheet["D3"] = "2026-10-14"
    out = io.BytesIO()
    workbook.save(out)
    workbook.close()
    return out.getvalue()


def test_xlsx_reads_visible_cells_not_internal_xml_namespaces():
    urls = urls_from_upload("two-conferences.xlsx", _xlsx_bytes())
    assert urls == [
        "https://iros2026.org/",
        "https://www.robobusiness.com/",
    ]
    assert all("openxmlformats" not in url for url in urls)


def test_xlsx_keeps_scoped_row_context_aligned_to_each_column_b_url():
    urls, contexts = uploaded_urls_and_contexts("two-conferences.xlsx", _xlsx_bytes())
    assert urls == ["https://iros2026.org/", "https://www.robobusiness.com/"]
    assert contexts == [
        {"name": "IROS 2026", "location": "Kyoto, Japan", "dates": "2026-09-27"},
        {"name": "RoboBusiness", "location": "Santa Clara, California", "dates": "2026-10-14"},
    ]


def test_normalization_dedupes_urls_without_losing_their_aligned_context():
    urls, contexts = normalize_urls_and_contexts(
        [" https://iros2026.org/ ", "https://iros2026.org", "https://robobusiness.com"],
        [{"name": "IROS 2026"}, None, {"name": "RoboBusiness"}],
    )
    assert urls == ["https://iros2026.org/", "https://robobusiness.com"]
    assert contexts == [{"name": "IROS 2026"}, {"name": "RoboBusiness"}]


def test_text_upload_still_extracts_urls():
    urls = urls_from_upload("list.txt", b"IROS https://iros2026.org/\n")
    assert urls == ["https://iros2026.org/"]


def _run():
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:
            failures += 1
            print(f"FAIL {fn.__name__}: {exc!r}")
    print(f"--- {len(fns) - failures}/{len(fns)} passed ---")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    _run()
