"""Review-view filter helpers (deadline parsing + windowing).

Componentized and conservative on purpose: the deadline parser only returns a real date when
the string unambiguously contains year, month, AND day. Anything vaguer (no year, "September
2026" with no day, a two-digit year) returns None and is simply excluded from date-window
filters rather than being guessed — a PR user must never see a false "closing soon".
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional

try:  # dateutil ships with pandas; guard so the package never hard-depends on it.
    from dateutil import parser as _dparser
except Exception:  # pragma: no cover - only hit if dateutil is truly absent
    _dparser = None

_FULL_YEAR = re.compile(r"(?<!\d)20\d{2}(?!\d)")


def parse_deadline(text: Optional[str]) -> Optional[date]:
    """Best-effort deadline date, or None. Returns a date ONLY when year+month+day are all
    explicitly present in the string (checked by re-parsing against two different defaults and
    requiring the result to be stable). Messy / partial / undated strings return None."""
    if not text or _dparser is None:
        return None
    s = str(text).strip()
    if not _FULL_YEAR.search(s):          # require a real 4-digit year; no 2-digit guessing
        return None
    try:
        d1 = _dparser.parse(s, default=datetime(2000, 1, 1), fuzzy=True)
        d2 = _dparser.parse(s, default=datetime(2001, 2, 2), fuzzy=True)
    except (ValueError, OverflowError, TypeError):
        return None
    # If any of y/m/d were absent from the string, they'd differ between the two defaults.
    if (d1.year, d1.month, d1.day) != (d2.year, d2.month, d2.day):
        return None
    return d1.date()


def days_until(text: Optional[str], today: Optional[date] = None) -> Optional[int]:
    """Whole days from `today` until the parsed deadline (negative = already past). None if
    the deadline can't be parsed to a full date."""
    d = parse_deadline(text)
    if d is None:
        return None
    return (d - (today or date.today())).days


def closing_within(text: Optional[str], window_days: int, today: Optional[date] = None) -> bool:
    """True if the deadline parses to a full date that is between today and `window_days` out
    (inclusive). Past deadlines and unparseable deadlines are False."""
    n = days_until(text, today)
    return n is not None and 0 <= n <= window_days
