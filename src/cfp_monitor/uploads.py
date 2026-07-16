"""URL extraction and scoped row-context loading for customer list uploads."""
from __future__ import annotations

import io
import re
from datetime import date, datetime

from .scoring import normalize_url

URL_RE = re.compile(r'https?://[^\s"\'<>)\]]+')


def _urls_in_text(value: object) -> list[str]:
    return URL_RE.findall(str(value or ""))


def _context_value(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return str(value or "").strip()


def _row_context(row: tuple[object, ...]) -> dict | None:
    """The narrowly scoped context used for one-hop aggregator resolution."""
    context = {
        "name": _context_value(row[0]),
        "location": _context_value(row[2]),
        "dates": _context_value(row[3]),
    }
    return context if any(context.values()) else None


def _xlsx_urls_and_contexts(data: bytes) -> tuple[list[str], list[dict | None]]:
    """Read literal Column B URLs plus A/C/D context from visible workbook cells.

    Only a literal URL in Column B can create a crawl target. Column A (name),
    C (location), and D (event date) are retained solely to resolve a directory
    or organization page to its specific event. Hyperlinks, workbook XML, notes,
    and all other columns are ignored.
    """
    try:
        from openpyxl import load_workbook
        workbook = load_workbook(io.BytesIO(data), read_only=False, data_only=True)
    except Exception:
        return [], []

    try:
        urls: list[str] = []
        contexts: list[dict | None] = []
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(min_col=1, max_col=4, values_only=True):
                context = _row_context(row)
                for url in _urls_in_text(row[1]):
                    urls.append(url)
                    contexts.append(context)
        return urls, contexts
    finally:
        workbook.close()


def normalize_urls_and_contexts(raw_urls: list[str], raw_contexts: list[dict | None]) -> tuple[list[str], list[dict | None]]:
    """Normalize/dedupe URLs while keeping the first useful row context aligned."""
    seen: dict[str, int] = {}
    urls: list[str] = []
    contexts: list[dict | None] = []
    for index, value in enumerate(raw_urls):
        url = (value or "").strip().rstrip(",;")
        if not url.lower().startswith("http"):
            continue
        context = raw_contexts[index] if index < len(raw_contexts) else None
        key = normalize_url(url)
        if key in seen:
            existing = seen[key]
            if context and not contexts[existing]:
                contexts[existing] = context
            continue
        seen[key] = len(urls)
        urls.append(url)
        contexts.append(context)
    return urls, contexts


def uploaded_urls_and_contexts(name: str, data: bytes) -> tuple[list[str], list[dict | None]]:
    """Load uploaded URLs and per-URL context, preserving list-index alignment."""
    if name.lower().endswith(".xlsx"):
        return _xlsx_urls_and_contexts(data)
    urls = _urls_in_text(data.decode("utf-8-sig", "ignore"))
    return urls, [None] * len(urls)


def urls_from_upload(name: str, data: bytes) -> list[str]:
    """Extract every HTTP(S) URL from a .txt, .csv, or .xlsx list upload."""
    return uploaded_urls_and_contexts(name, data)[0]
