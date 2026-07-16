"""URL extraction for pasted and uploaded conference lists."""
from __future__ import annotations

import io
import re
URL_RE = re.compile(r'https?://[^\s"\'<>)\]]+')


def _urls_in_text(value: object) -> list[str]:
    return URL_RE.findall(str(value or ""))


def _xlsx_urls(data: bytes) -> list[str]:
    """Read literal URLs from visible Column B cells, never XLSX package XML.

    The customer workbook uses Column B for conference URLs. Deliberately ignore
    hyperlink metadata and other columns so workbook-internal links and notes cannot
    become crawl targets.
    """
    try:
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(data), read_only=False, data_only=True)
    except Exception:
        return []

    try:
        urls: list[str] = []
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(min_col=2, max_col=2):
                urls.extend(_urls_in_text(row[0].value))
        return urls
    finally:
        workbook.close()


def urls_from_upload(name: str, data: bytes) -> list[str]:
    """Extract every http(s) URL from a .txt, .csv, or .xlsx list upload."""
    if name.lower().endswith(".xlsx"):
        return _xlsx_urls(data)
    return _urls_in_text(data.decode("utf-8-sig", "ignore"))
