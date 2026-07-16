"""Regression tests for customer URL-list uploads."""
import io

from openpyxl import Workbook

from cfp_monitor.uploads import urls_from_upload


def _xlsx_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet["A1"] = "Conference"
    sheet["B1"] = "Conference URL"
    sheet["A2"] = "IROS"
    sheet["B2"] = "https://iros2026.org/"
    sheet["A3"] = "RoboBusiness"
    sheet["B3"] = "https://www.robobusiness.com/"
    # A hyperlink in another column is a note, not a crawl target.
    sheet["C3"] = "speaking opportunities"
    sheet["C3"].hyperlink = "https://www.robobusiness.com/speaking-opportunities/"
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
