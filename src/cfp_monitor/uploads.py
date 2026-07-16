"""URL extraction for pasted and uploaded conference lists."""
from __future__ import annotations

import io
import re
URL_RE = re.compile(r'https?://[^\s"\'<>)\]]+')


def _urls_in_text(value: object) -> list[str]:
    return URL_RE.findall(str(value or ""))


def _xlsx_urls(data: bytes) -> list[str]:
    """Read URLs from visible workbook cells and hyperlinks, never XLSX package XML."""
    try:
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(data), read_only=False, data_only=True)
    except Exception:
        return []

    try:
        urls: list[str] = []
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    urls.extend(_urls_in_text(cell.value))
                    if cell.hyperlink and cell.hyperlink.target:
                        urls.extend(_urls_in_text(cell.hyperlink.target))
        return urls
    finally:
        workbook.close()


def urls_from_upload(name: str, data: bytes) -> list[str]:
    """Extract every http(s) URL from a .txt, .csv, or .xlsx list upload."""
    if name.lower().endswith(".xlsx"):
        return _xlsx_urls(data)
    return _urls_in_text(data.decode("utf-8-sig", "ignore"))
