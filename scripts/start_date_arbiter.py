"""Start-date arbiter: two competing start dates, ONE page-proven answer, and a YEAR check on every row.

    python scripts/start_date_arbiter.py <candidate.csv> [--out report.json] [--no-network]     # report only; changes nothing

WHY (2026-10-03). Saturday's narrow-first research left START DATE (the research's value, equal to last week's) disagreeing with the
input list's CONFERENCE DATES on 24 of 66 Cybersecurity and 42 of 53 Utility rows. Both come from upstream; nobody has proof which is
right, and EDITION is derived from START DATE (R25.1), so a wrong year here becomes a wrong edition, key and customer page.

WHAT. For each row whose START DATE differs from the first date in CONFERENCE DATES, read the row's own pages (conference URL, main info
URL, venue and deadline evidence URL) and ask whether each candidate date is stated there IN AN EVENT CONTEXT (the existing
self_heal.find_conference_dates_sentence, which is year-specific: "October 21, 2026" never matches 2027 text). Date RANGES ("October
21-23, 2026"), the normal way a conference prints its dates, are first expanded to explicit start dates so the same matcher can see them.
  agree      the two candidates are the same date: nothing to decide
  A          only the research START DATE is proven on a page: keep it
  B          only the CONFERENCE DATES start is proven on a page: use it (quote recorded)
  both       both are proven (a page lists two editions): keep A, flagged, a person decides
  neither    no page proves either (walled page, no event sentence): keep A, flagged as UNCONFIRMED
Nothing is ever invented: the value written is always one of the two upstream values, and only B-proven rows change.
The recorded quote is the page sentence with any date range spelled out ("October 21-23, 2026" -> "October 21, 2026 - October 23, 2026"):
it is evidence of WHERE the date was read, not a byte-verbatim quote; the gate's deadline-quote rule is not applied to it.

YEAR CHECKS (every row, whatever the arbiter decides; a failure is reported by name):
  Y1 START DATE year equals EDITION            (R25.1: edition = calendar year of start date)
  Y2 CONFERENCE DATES year equals START DATE year
  Y3 a start date already in the past with STATUS Open or Upcoming (an old edition presented as live)
  Y4 SUBMISSION DEADLINE not after START DATE, and not more than 18 months before it (a deadline of one edition on another)
Pure core `arbitrate_row` / `year_checks` (no I/O) plus a CLI that fetches pages. Report only: wiring is the caller's decision."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_MON = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september",
                                    "october", "november", "december"], 1)}
_ABBR = {k[:3]: v for k, v in _MON.items()} | {"sept": 9}
_MONRE = r"(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)\.?"
_DASH = r"\s*(?:-|–|—|to|through|&)\s*"


def _month(s: str) -> int | None:
    s = s.lower().rstrip(".")
    return _MON.get(s) or _ABBR.get(s)


def first_date(conference_dates: str) -> date | None:
    """First date in a CONFERENCE DATES text: 'October 21 - October 23, 2026', 'June 23 - 24, 2026', '21-23 October 2026'."""
    t = (conference_dates or "").strip()
    y = re.search(r"(20\d\d)", t)
    if not y:
        return None
    m = re.match(rf"\s*{_MONRE}\s+(\d{{1,2}})", t, re.I)
    d = None
    if m:
        d = (_month(m.group(1)), int(m.group(2)))
    else:
        m = re.match(rf"\s*(\d{{1,2}})(?:\s*[-–]\s*\d{{1,2}})?\s+{_MONRE}", t, re.I)
        if m:
            d = (_month(m.group(2)), int(m.group(1)))
    try:
        return date(int(y.group(1)), d[0], d[1]) if d and d[0] else None
    except ValueError:
        return None


def _strip_accents(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).replace("\u00df", "ss")


def _all_month_names() -> str:
    from src.cfp_monitor.verify import _OTHER_MONTHS
    names = sorted({n for v in _OTHER_MONTHS.values() for n in v} | set(_MON), key=len, reverse=True)   # other languages AND English (September is spelled alike)
    return "|".join(names)


def expand_ranges(text: str) -> str:
    """Rewrite year-bearing ranges as explicit start and end dates so a single-date matcher can see the start. Year is never
    invented: a range without its own year is left alone."""
    t = _strip_accents(text)
    sfx = r"(?:st|nd|rd|th|er)?"
    # 23.-24.09.2026 and 23-24.09.2026 (numeric, day first)
    t = re.sub(r"(?<!\d)(\d{1,2})\.?\s*(?:-|\u2013|\u2014)\s*(\d{1,2})\.(\d{1,2})\.(20\d\d)",
               lambda m: f"{m.group(1)}.{m.group(3)}.{m.group(4)} - {m.group(2)}.{m.group(3)}.{m.group(4)}", t)
    # 23.-24. September 2026 / 23 - 24 septembre 2026 / 10-12 de mayo de 2027 (month names of other languages; the output keeps the month's own name, which date_variants knows)
    fm = _all_month_names()
    t = re.sub(rf"(?<!\d)(\d{{1,2}}){sfx}\.?\s*(?:-|\u2013|\u2014|bis|au|al)\s*(\d{{1,2}}){sfx}\.?\s+(?:de\s+)?({fm}),?\s+(?:de\s+)?(20\d\d)",
               lambda m: f"{m.group(1)} {m.group(3)} {m.group(4)} - {m.group(2)} {m.group(3)} {m.group(4)}", t, flags=re.I)
    # October 21-23, 2026  /  October 21 - 23 2026
    t = re.sub(rf"{_MONRE}\s+(?<!\d)(\d{{1,2}}){sfx}{_DASH}(\d{{1,2}}){sfx},?\s+(20\d\d)",
               lambda m: f"{m.group(1)} {m.group(2)}, {m.group(4)} - {m.group(1)} {m.group(3)}, {m.group(4)}", t, flags=re.I)
    # October 21 - November 2, 2026
    t = re.sub(rf"{_MONRE}\s+(\d{{1,2}}){sfx}{_DASH}{_MONRE}\s+(\d{{1,2}}){sfx},?\s+(20\d\d)",
               lambda m: f"{m.group(1)} {m.group(2)}, {m.group(5)} - {m.group(3)} {m.group(4)}, {m.group(5)}", t, flags=re.I)
    # 21-23 October 2026
    t = re.sub(rf"(?<!\d)(\d{{1,2}}){sfx}{_DASH}(\d{{1,2}}){sfx}\s+{_MONRE},?\s+(20\d\d)",
               lambda m: f"{m.group(1)} {m.group(3)} {m.group(4)} - {m.group(2)} {m.group(3)} {m.group(4)}", t, flags=re.I)
    # 21 October - 2 November 2026
    t = re.sub(rf"(?<!\d)(\d{{1,2}}){sfx}\s+{_MONRE}{_DASH}(\d{{1,2}}){sfx}\s+{_MONRE},?\s+(20\d\d)",
               lambda m: f"{m.group(1)} {m.group(2)} {m.group(5)} - {m.group(3)} {m.group(4)} {m.group(5)}", t, flags=re.I)
    return t


def proven(pages: list[tuple[str, str]], target: date) -> tuple[bool, str, str]:
    """(found, url, quote): is `target` stated, in an event context, on any of the (url, text) pages?"""
    from src.cfp_monitor.self_heal import find_conference_dates_sentence
    for url, text in pages:
        if not text:
            continue
        ok, quote = find_conference_dates_sentence(expand_ranges(text), target.isoformat())
        if ok:
            return True, url, quote
    return False, "", ""


def arbitrate_row(row: dict, pages: list[tuple[str, str]]) -> dict:
    a_s = (row.get("START DATE") or "").strip()
    try:
        a = datetime.strptime(a_s, "%Y-%m-%d").date() if a_s else None
    except ValueError:
        a = None
    b = first_date(row.get("CONFERENCE DATES", ""))
    out = {"A": a_s, "B": b.isoformat() if b else "", "verdict": "agree", "use": a_s, "url": "", "quote": ""}
    if a is None and b is None:
        out.update(verdict="no-dates", use="")
        return out
    if a is not None and b is not None and a == b:
        return out
    if b is None:                       # CONFERENCE DATES unreadable: nothing to arbitrate against
        out.update(verdict="no-b")
        return out
    if a is None:                       # research gave none: B only if a page proves it
        ok, url, q = proven(pages, b)
        out.update(verdict="B" if ok else "neither", use=b.isoformat() if ok else "", url=url, quote=q)
        return out
    pa, ua, qa = proven(pages, a)
    pb, ub, qb = proven(pages, b)
    if pa and pb:
        out.update(verdict="both", url=ua, quote=qa)
    elif pa:
        out.update(verdict="A", url=ua, quote=qa)
    elif pb:
        out.update(verdict="B", use=b.isoformat(), url=ub, quote=qb)
    else:
        out.update(verdict="neither")
    return out


def year_checks(row: dict, today: date, use: str | None = None) -> list[str]:
    """Names of the year checks this row fails (Y1..Y4). `use` is the start date that would ship (defaults to START DATE)."""
    fails = []
    s = (use if use is not None else row.get("START DATE") or "").strip()
    try:
        sd = datetime.strptime(s, "%Y-%m-%d").date() if s else None
    except ValueError:
        sd = None
    ed = (row.get("EDITION") or "").strip()
    if sd and ed.isdigit() and sd.year != int(ed):
        fails.append(f"Y1 START DATE {s} is not in edition {ed}")
    cd = first_date(row.get("CONFERENCE DATES", ""))
    if sd and cd and cd.year != sd.year:
        fails.append(f"Y2 CONFERENCE DATES year {cd.year} differs from START DATE year {sd.year}")
    if sd and sd < today and (row.get("STATUS") or "").strip() in ("Open", "Upcoming"):
        fails.append(f"Y3 start {s} already past but STATUS {row.get('STATUS')}")
    dl = (row.get("SUBMISSION DEADLINE") or "").strip()
    try:
        dd = datetime.strptime(dl, "%Y-%m-%d").date() if dl else None
    except ValueError:
        dd = None
    if sd and dd:
        if dd > sd:
            fails.append(f"Y4 deadline {dl} is after the start {s}")
        elif (sd - dd).days > 548:
            fails.append(f"Y4 deadline {dl} is more than 18 months before the start {s}")
    return fails


def read_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("csv_path")
    ap.add_argument("--out")
    ap.add_argument("--no-network", action="store_true")
    ap.add_argument("--today", default=date.today().isoformat())
    args = ap.parse_args()
    today = datetime.strptime(args.today, "%Y-%m-%d").date()
    rows = read_rows(Path(args.csv_path))
    from src.cfp_monitor.verify import fetch_text, is_block_page
    cache: dict[str, str] = {}

    def page(url: str) -> str:
        if args.no_network or not url.startswith("http"):
            return ""
        if url not in cache:
            try:
                text, _note = fetch_text(url)
            except Exception:                                                  # noqa: BLE001
                text = ""
            cache[url] = "" if (text and is_block_page(text)) else (text or "")
        return cache[url]

    report = []
    for r in rows:
        urls = []
        for c in ("CONFERENCE URL", "MAIN_INFO_URL", "VENUE_EVIDENCE_URL", "DEADLINE_EVIDENCE_URL"):
            u = (r.get(c) or "").strip()
            if u and u not in urls:
                urls.append(u)
        a_s, b = (r.get("START DATE") or "").strip(), first_date(r.get("CONFERENCE DATES", ""))
        needs = not (b and a_s == b.isoformat())
        pages = [(u, page(u)) for u in urls] if needs else []
        res = arbitrate_row(r, pages)
        yf = year_checks(r, today, res["use"] if res["verdict"] in ("A", "B", "both", "neither", "agree") else None)
        report.append({"conference": r["CONFERENCE"], "edition": r.get("EDITION", ""), "status": r.get("STATUS", ""), **res, "year_fails": yf})
    from collections import Counter
    c = Counter(x["verdict"] for x in report)
    print("verdicts:", dict(c), "| rows with a year-check failure:", sum(1 for x in report if x["year_fails"]))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
