"""Transform our internal source-of-truth records into the customer's 15-column
sheet format (docs/voc/Utility Global Conference List 2026.xlsx).

Our DB is the rich 54-column-capable source of truth; the customer sees this
narrower view (and later Brandable consumes the same shape). Stdlib only — writes
CSV; also exposes an Excel-serial date helper for a future .xlsx writer.
"""
from __future__ import annotations

import csv
import re
import unicodedata
from datetime import date, datetime
from typing import Iterable, Optional

from .tracks import track_label

# Exact customer column order + headers. The first 15 are verbatim from the real sheet;
# TRACK is appended LAST so the customer's existing column sequence is never disturbed.
# TRACK is a read-only, derived label (Speaking / Awards / Other) — see tracks.py.
CUSTOMER_HEADERS = [
    "CONFERENCE", "CONFERENCE URL", "LOCATION", "START DATES", "LATEST UPDATE",
    "SUBMISSION DEADLINE", "SUBMISSION DATE VERIFIED", "PRIORITY", "STATUS",
    "STATUS DETAILS", "SUBMISSION URL", "COORDINATOR EMAIL", "OVERVIEW",
    "CATEGORIES", "NOTES",
    "TRACK",
]

# Our detection status (cfp_status) -> customer-facing STATUS wording. Customer
# workflow states like "Submitted" are set by humans, not detection, so we don't emit them.
_STATUS_MAP = {
    "open": "Open",
    "closed": "Closed",
    "upcoming": "Upcoming",
    "unclear": "Needs Review",
    "none": "No Opportunity",
}

_EXCEL_EPOCH = date(1899, 12, 30)  # Excel's day-0 (accounts for the 1900 leap bug)

# Preserve the meaning of common smart punctuation before ASCII normalization.
_EXCEL_ASCII_REPLACEMENTS = str.maketrans({
    "—": "-", "–": "-", "−": "-", "…": "...", " ": " ",
    "‘": "'", "’": "'", "‚": "'", "“": '"', "”": '"', "„": '"',
    "™": "TM", "®": "(R)", "©": "(C)",
})


def excel_safe_text(value: object) -> str:
    """Return plain ASCII for customer exports and Excel legacy import paths.

    Smart punctuation such as an em dash can render as mojibake (for example,
    ``â€”``) when Excel opens a UTF-8 CSV as an ANSI code page. Normalize accented
    letters where possible and drop other non-ASCII characters.
    """
    if value is None:
        return ""
    text = str(value).replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    text = text.translate(_EXCEL_ASCII_REPLACEMENTS)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def excel_serial(d) -> Optional[int]:
    """Convert a date / datetime / ISO-ish string to an Excel serial number, matching
    how the customer sheet stores dates. Returns None if unparseable (never guesses)."""
    parsed = _coerce_date(d)
    return (parsed - _EXCEL_EPOCH).days if parsed else None


def _coerce_date(d) -> Optional[date]:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    if not d:
        return None
    s = str(d).strip()
    # ISO first (our last_checked timestamps).
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    return None


def to_customer_row(rec: dict) -> dict:
    """Map one internal export dict (Store.export_dicts item) to the 15 columns."""
    status = _STATUS_MAP.get((rec.get("status") or "").lower(), rec.get("status") or "")
    verified = "Yes" if rec.get("verified") else "Needs Verification"
    # Honest deadline handling: if an opportunity exists but no public deadline was found,
    # say so explicitly (feeds the human-verification workflow) rather than leaving a blank
    # cell that implies there is none. Many expos simply don't publish a submission deadline.
    details = rec.get("status_details") or ""
    has_opp = (rec.get("status") or "").lower() in ("open", "upcoming", "unclear") or bool(rec.get("submission_url"))
    if has_opp and not (rec.get("submission_deadline") or "").strip():
        note = "No public deadline found - needs verification"
        details = f"{details} - {note}" if details else note
    row = {
        "CONFERENCE": rec.get("name") or "",
        "CONFERENCE URL": rec.get("url") or "",
        "LOCATION": rec.get("location") or "",
        "START DATES": rec.get("start_dates") or "",
        "LATEST UPDATE": _short_date(rec.get("last_checked")),
        "SUBMISSION DEADLINE": rec.get("submission_deadline") or "",
        "SUBMISSION DATE VERIFIED": verified,
        "PRIORITY": rec.get("priority") or "",
        "STATUS": status,
        "STATUS DETAILS": details,
        "SUBMISSION URL": rec.get("submission_url") or "",
        "COORDINATOR EMAIL": rec.get("coordinator_email") or "",
        "OVERVIEW": rec.get("overview") or "",
        "CATEGORIES": rec.get("categories") or "",
        "NOTES": rec.get("notes") or "",
        # Derived, read-only: which opportunity track(s) the crawl detected. Blank when none.
        "TRACK": track_label(rec.get("opportunity_types")),
    }
    return {header: excel_safe_text(value) for header, value in row.items()}


def _short_date(iso: Optional[str]) -> str:
    """Render our ISO timestamp as a plain YYYY-MM-DD for the customer view."""
    d = _coerce_date(iso)
    return d.isoformat() if d else (iso or "")


def to_customer_rows(records: Iterable[dict]) -> list[dict]:
    return [to_customer_row(r) for r in records]


def to_customer_csv_text(records: Iterable[dict]) -> str:
    """The customer 15-column CSV as a string (for downloads / in-memory use)."""
    import io
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CUSTOMER_HEADERS)
    writer.writeheader()
    writer.writerows(to_customer_rows(records))
    return buf.getvalue()


def write_customer_csv(records: Iterable[dict], path: str) -> int:
    """Write the customer 15-column CSV. Returns the number of data rows written."""
    rows = to_customer_rows(records)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CUSTOMER_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
