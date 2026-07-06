"""Load the customer spreadsheet as the crawl URL list + a partial gold set.

The customer xlsx (Utility Global Conference List) doubles as URL list and gold set.
Trustworthy truth columns: SUBMISSION DEADLINE (F), STATUS (I), STATUS DETAILS (J),
LATEST UPDATE (E). STATUS is a customer *workflow* state (Submitted/Accepted/Closed…),
an indicator — not our open/closed detection label. Stdlib only.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional
from xml.etree import ElementTree as ET

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_EXCEL_EPOCH = date(1899, 12, 30)


def serial_to_date(v) -> Optional[date]:
    """Excel serial number -> date. None if not a plausible date serial."""
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    if n < 1 or n > 80000:               # ~year 2119 upper guard
        return None
    return _EXCEL_EPOCH + timedelta(days=n)


@dataclass
class GoldRecord:
    name: str
    url: str
    deadline: Optional[date]             # parsed from F when it's a real serial date
    deadline_raw: str                    # raw F cell (may be text like "Sponsorship Required")
    status: str                          # customer workflow state (I)
    status_details: str                  # J
    latest_update: Optional[date]        # E
    location: str = ""                   # C (city/venue) - feeds aggregator navigation
    start_date: Optional[date] = None    # D (event start) - parsed when a real serial date
    start_date_raw: str = ""             # raw D cell

    def context(self) -> dict:
        """Row context for aggregator navigation: name / location / target year."""
        dates = self.start_date.isoformat() if self.start_date else self.start_date_raw
        return {"name": self.name, "location": self.location, "dates": dates}


def _read_rows(path: str) -> list[dict]:
    z = zipfile.ZipFile(path)
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        t = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in t.iter(_NS + "si"):
            shared.append("".join(x.text or "" for x in si.iter(_NS + "t")))
    ws = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = []
    for row in ws.iter(_NS + "row"):
        cells = {}
        for c in row.iter(_NS + "c"):
            col = re.match(r"[A-Z]+", c.get("r")).group()
            tp = c.get("t")
            v = c.find(_NS + "v")
            if tp == "s" and v is not None:
                val = shared[int(v.text)]
            elif v is not None:
                val = v.text
            else:
                val = ""
            cells[col] = val
        rows.append(cells)
    return rows


def load_gold(path: str, require_truth: bool = False) -> list[GoldRecord]:
    """Rows with a real URL. If require_truth, also require at least one truth cell (F/I/J)."""
    out = []
    for r in _read_rows(path)[1:]:                     # drop header
        url = (r.get("B") or "").strip()
        if not url.lower().startswith("http"):
            continue
        f = (r.get("F") or "").strip()
        has_truth = bool(f or (r.get("I") or "").strip() or (r.get("J") or "").strip())
        if require_truth and not has_truth:
            continue
        d = (r.get("D") or "").strip()
        out.append(GoldRecord(
            name=(r.get("A") or "").strip(),
            url=url,
            deadline=serial_to_date(f),
            deadline_raw=f,
            status=(r.get("I") or "").strip(),
            status_details=(r.get("J") or "").strip(),
            latest_update=serial_to_date((r.get("E") or "").strip()),
            location=(r.get("C") or "").strip(),
            start_date=serial_to_date(d),
            start_date_raw=d,
        ))
    return out


def load_inputs(items: list[str]) -> tuple[list[str], list[Optional[dict]]]:
    """Resolve CLI / file inputs to parallel (urls, contexts) lists.

    An .xlsx (the customer list) yields per-row CONTEXT (name / location / dates) that powers
    aggregator navigation; a .txt file (one URL per line) and bare URLs carry no context, so
    navigation stays off for them. Contexts align with urls by index (None where unknown).
    """
    import os

    urls: list[str] = []
    contexts: list[Optional[dict]] = []
    for it in items:
        if os.path.isfile(it) and it.lower().endswith((".xlsx", ".xlsm")):
            for rec in load_gold(it):
                urls.append(rec.url)
                contexts.append(rec.context())
        elif os.path.isfile(it):
            with open(it, encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if ln and not ln.startswith("#"):
                        urls.append(ln)
                        contexts.append(None)
        else:
            urls.append(it)
            contexts.append(None)
    return urls, contexts


def compare(result, gold: GoldRecord) -> dict:
    """Side-by-side of our extraction vs gold truth (honest indicators, not one %)."""
    our_close = (result.cfp_close_date.value or "")
    we_found = bool(our_close.strip())
    gold_has = gold.deadline is not None
    year_match = (str(gold.deadline.year) in our_close) if (gold_has and we_found) else None
    return {
        "url": gold.url, "name": gold.name,
        "gold_status": gold.status,
        "gold_deadline": gold.deadline.isoformat() if gold.deadline else (gold.deadline_raw or ""),
        "gold_details": gold.status_details,
        "our_status": result.cfp_status.value,
        "our_deadline": our_close,
        "our_submit": result.submission_url.value,
        "we_found_deadline": we_found,
        "gold_has_deadline": gold_has,
        "deadline_year_match": year_match,
    }
