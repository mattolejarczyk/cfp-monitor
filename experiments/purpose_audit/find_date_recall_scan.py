"""How many date renderings on REAL saved pages can verify.find_date match? Offline, no network.

    python experiments/purpose_audit/find_date_recall_scan.py > scan.json

Scans every page in page_library/page_library.db for date strings in the styles listed in PATTERNS, parses each with
dateutil, then asks find_date(page text, parsed date). Reports, per style, how many were found and how many missed,
and three examples of each miss. Used on 2026-10-02 to size the "(26)" / "12th of October" gap before and after the fix.
Also scans for the FALSE-POSITIVE direction: a target whose day is a suffix of a longer day ("2 October 2026" vs a page
that only says "12 October 2026")."""
import json
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from dateutil import parser as dparser

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.cfp_monitor import verify  # noqa: E402

M = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
PATTERNS = {
    "day month year4        (12 October 2026)": rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{M}\s+20\d\d\b",
    "month day, year4       (October 12, 2026)": rf"\b{M}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+20\d\d\b",
    "day of month year4     (12th of October, 2026)": rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+of\s+{M},?\s+20\d\d\b",
    "day month (yy)         (19 October (26))": rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{M}\s*\(\s*\d\d\s*\)",
    "day month yy           (12 October 26)": rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{M}\s+\d\d\b(?!\d)",
    "month day (yy)         (October 19 (26))": rf"\b{M}\s+\d{{1,2}}(?:st|nd|rd|th)?\s*\(\s*\d\d\s*\)",
}


def parse(s: str):
    s = re.sub(r"\(\s*(\d\d)\s*\)", r"20\1", s)                       # "(26)" -> 2026 for the parser only
    s = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", s).replace(" of ", " ")
    s = re.sub(r"\b(\d{1,2}\s+[A-Za-z.]+)\s+(\d\d)\b(?!\d)", r"\1 20\2", s)
    try:
        d = dparser.parse(s, dayfirst=True, default=datetime(2000, 1, 1)).date()
    except (ValueError, OverflowError):
        return None
    return d if 2024 <= d.year <= 2029 else None


def main() -> None:
    lib = sqlite3.connect(ROOT / "page_library" / "page_library.db")
    stats = defaultdict(lambda: {"seen": 0, "found": 0, "missed": []})
    fp = {"checked": 0, "false_hit": []}
    for url, text in lib.execute("select url, text from pages where text is not null and text != ''"):
        for label, pat in PATTERNS.items():
            for mm in re.finditer(pat, text):
                d = parse(mm.group(0))
                if d is None:
                    continue
                s = stats[label]
                s["seen"] += 1
                if verify.find_date(text, d):
                    s["found"] += 1
                elif len(s["missed"]) < 3:
                    s["missed"].append([mm.group(0), url[:70]])
        # false-positive direction: for "NN Month YYYY" with NN in 10..31, test the date whose day is the last digit
        for mm in re.finditer(PATTERNS["day month year4        (12 October 2026)"], text):
            d = parse(mm.group(0))
            if d is None or d.day < 10:
                continue
            alt_day = d.day % 10
            if alt_day == 0:
                continue
            try:
                alt = d.replace(day=alt_day)
            except ValueError:
                continue
            fp["checked"] += 1
            # the alt date is only legitimately present if the page ALSO states it on its own
            own = re.search(rf"(?<!\d){alt_day}(?:st|nd|rd|th)?\s+{M}\s+{d.year}", text)
            if verify.find_date(text, alt) and not own and len(fp["false_hit"]) < 5:
                fp["false_hit"].append([mm.group(0), f"matched as {alt.isoformat()}", url[:60]])
    json.dump({"patterns": {k: {"seen": v["seen"], "found": v["found"], "missed_n": v["seen"] - v["found"],
                                "missed_examples": v["missed"]} for k, v in stats.items()},
               "false_positive_scan": fp}, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
