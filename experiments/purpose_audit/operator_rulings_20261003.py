"""Operator rulings 2026-10-03: five Utility rows whose START DATE and CONFERENCE DATES disagreed (operator verified on the live pages).
Applies ONLY the listed cells, in Markets/Utility_audited.csv (this week's research output, which weekend_import reads) AND
Markets/Utility_input.csv (the input list the research copies unasked fields from, where the wrong text came from), after timestamped
backups, and proves exactly those cells changed. Report by default; --apply writes.   Usage: operator_rulings_20261003.py [--apply]"""
import csv, os, shutil, sys
from datetime import datetime

M = "C:/Users/matts/Desktop/Nicolia-PR-Prime/Markets/"
APPLY = "--apply" in sys.argv
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

# conference-name prefix -> {column: new value}; START DATE is ISO here and converted for the input list (M/D/YYYY)
RULINGS = {
    "European Carbon Capture, Utilization & Storage Conference 2027":
        {"CONFERENCE DATES": "January 26 - January 27, 2027", "START DATE": "2027-01-26"},
    "Carbon Capture USA 2026":
        {"CONFERENCE DATES": "November 16 - November 17, 2026", "START DATE": "2026-11-16",
         "CFP_SUBMISSION_URL": "https://www.usa.carbon-capture-conference.com/speakers"},
    "Future Fuels MENA Summit 2026":
        {"CONFERENCE DATES": "", "START DATE": ""},
    "Sustainable Fuels Global Summit 2027":
        {"CONFERENCE DATES": "April 13 - April 14, 2027", "START DATE": "2027-04-13"},
    "Carbon Capture Technology Expo MENA 2026":
        {"CONFERENCE DATES": "", "START DATE": ""},
}


def mdy(iso: str) -> str:
    if not iso:
        return ""
    y, m, d = iso.split("-")
    return f"{int(m)}/{int(d)}/{y}"


def run(path: str, is_input: bool) -> None:
    raw = open(path, "rb").read()
    bom, crlf = raw.startswith(b"\xef\xbb\xbf"), b"\r\n" in raw
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        cols, rows = list(rd.fieldnames), list(rd)
    before = [dict(r) for r in rows]
    touched = {}
    for name, cells in RULINGS.items():
        hit = [i for i, r in enumerate(rows) if r["CONFERENCE"].strip() == name]
        if len(hit) != 1:
            sys.exit(f"REFUSED: {os.path.basename(path)}: {len(hit)} rows named {name!r} (need exactly 1)")
        i = hit[0]
        for col, val in cells.items():
            if col not in cols:                       # the input list has no CFP_SUBMISSION_URL
                continue
            new = mdy(val) if (is_input and col == "START DATE") else val
            if rows[i][col] != new:
                touched[(i, col)] = (rows[i][col], new)
                rows[i][col] = new
    print(f"\n{os.path.basename(path)}: {len(touched)} cell(s) change")
    for (i, col), (o, n) in touched.items():
        print(f"  {rows[i]['CONFERENCE'][:46]:46s} {col:20s} {o!r} -> {n!r}")
    if not APPLY:
        return
    shutil.copy(path, path.replace(".csv", f".pre-rulings-{STAMP}.bak.csv"))
    with open(path + ".tmp", "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL, lineterminator="\r\n" if crlf else "\n")
        w.writeheader()
        w.writerows(rows)
    with open(path + ".tmp", encoding="utf-8-sig", newline="") as fh:
        after = list(csv.DictReader(fh))
    diff = {(i, c) for i, (a, b) in enumerate(zip(before, after)) for c in a if a[c] != b.get(c)}
    assert len(after) == len(before) and diff == set(touched), "unexpected change"
    os.replace(path + ".tmp", path)
    print("  written; proved only those cells differ from the backup")


run(M + "Utility_audited.csv", False)
run(M + "Utility_input.csv", True)
