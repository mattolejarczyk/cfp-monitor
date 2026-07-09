"""Reconcile our crawl results against the customer's master sheet — pure, testable logic.

Given the customer's rows (keyed by their column headers) and our per-conference facts (keyed by
normalized URL), classify each comparable field with a shared taxonomy. The .xlsx writer
(reconcile_xlsx.py) turns this into a highlighted, commented copy of their sheet.

We only compare fields WE produce as facts. We deliberately do NOT touch STATUS — the customer's
STATUS is their workflow state (Submitted/Accepted/Closed…), a different vocabulary from our
detection label, so treating a difference there as a "change" would be misleading.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# Taxonomy (the shared language for a difference).
CONFIRMED = "confirmed"       # ours matches theirs
CHANGED = "changed"           # both present, differ -> human reviews (update vs conflict)
GAP_FILLED = "gap_filled"     # their cell was blank, we found a value
UNVERIFIED = "unverified"     # we crawled but couldn't confirm this row (blocked/error)
NOT_CRAWLED = "not_crawled"   # no crawl record for this URL

# Customer column header -> our fact key. Order = display order.
FIELDS = [
    ("CONFERENCE", "name"),
    ("LOCATION", "location"),
    ("START DATES", "start_dates"),
    ("SUBMISSION DEADLINE", "submission_deadline"),
    ("SUBMISSION URL", "submission_url"),
]


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


# Date columns compare by (year, month), not raw text — the customer stores Excel serial dates
# while we capture verbatim strings ("13-15 October 2026"), so a text compare is all false-positives.
_DATE_COLS = {"START DATES", "SUBMISSION DEADLINE"}
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def _date_sig(s):
    """(year, month) signature from a date-ish value, or None if no year is present."""
    t = str(s or "").lower()
    ym = re.search(r"(20\d{2})", t)
    if not ym:
        return None
    year = int(ym.group(1))
    month = None
    for name, num in _MONTHS.items():
        if name in t:
            month = num
            break
    if month is None:
        iso = re.search(r"20\d{2}-(\d{2})", t)      # ISO / datetime form
        if iso:
            month = int(iso.group(1))
    return (year, month)


def _same_value(column: str, theirs, ours) -> bool:
    if column in _DATE_COLS:
        dt, do = _date_sig(theirs), _date_sig(ours)
        if dt and do:
            return dt == do
    return _norm(theirs) == _norm(ours)


@dataclass
class FieldDiff:
    column: str
    category: str
    theirs: str
    ours: str


@dataclass
class RowRecon:
    url: str
    name: str
    row_category: Optional[str]        # UNVERIFIED / NOT_CRAWLED, else None
    source_url: str                    # where a reviewer can check (last-checked in `checked`)
    checked: str
    fields: list = field(default_factory=list)   # list[FieldDiff] (only non-confirmed, non-empty)

    @property
    def changed(self) -> list:
        return [f for f in self.fields if f.category in (CHANGED, GAP_FILLED)]


def reconcile_row(their_row: dict, our: Optional[dict]) -> RowRecon:
    """Classify one customer row against our fact dict (or None if we have no record)."""
    url = their_row.get("CONFERENCE URL", "") or ""
    name = their_row.get("CONFERENCE", "") or ""
    if our is None:
        return RowRecon(url, name, NOT_CRAWLED, "", "", [])

    row_cat = UNVERIFIED if (our.get("quality") in ("ERROR", "BLOCKED")) else None
    diffs: list[FieldDiff] = []
    for col, key in FIELDS:
        theirs = their_row.get(col, "") or ""
        ours = our.get(key, "") or ""
        tn, on = _norm(theirs), _norm(ours)
        if not tn and not on:
            continue
        if not tn and on:
            cat = GAP_FILLED
        elif tn and not on:
            continue                    # we add nothing here — leave their value untouched
        elif _same_value(col, theirs, ours):
            cat = CONFIRMED
        else:
            cat = CHANGED
        diffs.append(FieldDiff(col, cat, str(theirs), str(ours)))
    return RowRecon(url, name, row_cat, our.get("url", url), our.get("last_checked", "") or "", diffs)


def reconcile_all(customer_rows: list[dict], our_by_key: dict, key_of) -> tuple[list, dict]:
    """Reconcile every customer row. `our_by_key` maps normalized-url -> our fact dict; `key_of`
    normalizes a URL to that key. Returns (rows, summary counts by category)."""
    rows, counts = [], {c: 0 for c in (CONFIRMED, CHANGED, GAP_FILLED, UNVERIFIED, NOT_CRAWLED)}
    for tr in customer_rows:
        our = our_by_key.get(key_of(tr.get("CONFERENCE URL", "")))
        rr = reconcile_row(tr, our)
        rows.append(rr)
        if rr.row_category in (UNVERIFIED, NOT_CRAWLED):
            counts[rr.row_category] += 1
        for f in rr.fields:
            if f.category in counts:
                counts[f.category] += 1
    return rows, counts
