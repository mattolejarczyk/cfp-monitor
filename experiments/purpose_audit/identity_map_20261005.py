"""Identity map 2026-10-05: upstream's answer to note 27 confirmed that nine input-list rows are events we already hold, and named the id we hold for each.
Stamps EVENT_ID_CANON on exactly those input rows (Markets/<Market>_input.csv), after timestamped backups, so Saturday's research loads them onto the held id instead of
holding them back as 'no permanent id'. Each id is checked first: it must exist in the live database, and no OTHER input row in that market may already carry it.
NOT stamped: 'OWASP Global AppSec Europe 2026' and 'OWASP German Chapter Conference (AppSec Karlsruhe 2026)'. Each is a second listing of an event another input row already carries
(upstream: duplicates, R15); stamping the same id twice would make the gate hold both back (R8c). They need a DUP_OF decision, not an id.
Report by default; --apply writes.   Usage: identity_map_20261005.py [--apply]"""
import csv
import os
import shutil
import sqlite3
import sys
from datetime import datetime

M = "C:/Users/matts/Desktop/Nicolia-PR-Prime/Markets/"
DB = os.environ["LOCALAPPDATA"] + "/CFP-Monitor/cfp_monitor.db"
APPLY = "--apply" in sys.argv
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
MAP = {
    "Cybersecurity": {
        "Hack In The Box (HITB Security Conference 2026)": "2026-hack-in-the-box-phuket",
    },
    "Utility": {
        "Decarb Connect Europe 2027": "2027-decarb-connect-europe-vienna",
        "World Hydrogen & Carbon Capture Conference Indonesia (IICCS Forum 2026)": "2026-the-4th-international-indonesia-ccs-forum-jakarta",
        "2026 World Conference on Carbon Capture, Utilisation & Storage (CCUS Event 2026)": "2026-world-conference-on-carbon-capture-utilisation-the-woodlands",
        "Decarb Connect Canada 2026": "2026-decarb-connect-canada-toronto",
        "India Energy Week 2027 (IEW 2027)": "2027-india-energy-week-kolkata",
        "Decarbonization Congress 2026 (Resilient & Net-Zero Industry Congress)": "2026-decarbonization-congress-v-sendorf",
        "Innovation Zero 2027 (The UK's Clean Tech Congress)": "2027-innovation-zero-london",
        "World Hydrogen Energy Conference 2026 (WHEC 2026 - 24th Edition)": "2026-world-hydrogen-energy-conference-singapore",
    },
}


def main() -> int:
    held = {r[0] for r in sqlite3.connect(f"file:{DB}?mode=ro", uri=True).execute("select event_id from grounding_facts")}
    problems, plan = [], []
    for market, names in MAP.items():
        path = f"{M}{market}_input.csv"
        raw = open(path, "rb").read()
        bom, crlf = raw.startswith(b"\xef\xbb\xbf"), b"\r\n" in raw
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rd = csv.DictReader(fh)
            cols, rows = list(rd.fieldnames), list(rd)
        for name, eid in names.items():
            hits = [r for r in rows if r["CONFERENCE"] == name]
            if len(hits) != 1:
                problems.append(f"{market}: {len(hits)} input rows named {name!r}")
                continue
            if eid not in held:
                problems.append(f"{market}: {eid} is not in the live database")
                continue
            other = [r["CONFERENCE"] for r in rows if r.get("EVENT_ID_CANON") == eid and r is not hits[0]]
            if other:
                problems.append(f"{market}: {eid} is already carried by {other}")
                continue
            if (hits[0].get("EVENT_ID_CANON") or "").strip() not in ("", eid):
                problems.append(f"{market}: {name!r} already carries a different id {hits[0]['EVENT_ID_CANON']}")
                continue
            plan.append((market, path, name, eid, hits[0], rows, cols, bom, crlf))
    for p in plan:
        print(f"  {p[0]:13} {p[2][:60]:60} -> {p[3]}")
    for x in problems:
        print("  PROBLEM:", x)
    if problems:
        print("nothing written: fix the problems first")
        return 1
    if not APPLY:
        print(f"report only: {len(plan)} row(s) would be stamped. Add --apply.")
        return 0
    for market in MAP:
        mine = [p for p in plan if p[0] == market]
        if not mine:
            continue
        path, rows, cols, bom, crlf = mine[0][1], mine[0][5], mine[0][6], mine[0][7], mine[0][8]
        bak = path.replace(".csv", f".pre-identity-{STAMP}.bak.csv")
        shutil.copy2(path, bak)
        before = [dict(r) for r in rows]
        for p in mine:
            p[4]["EVENT_ID_CANON"] = p[3]
        changed = sum(1 for a, b in zip(before, rows) for c in cols if a.get(c) != b.get(c))
        with open(path, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL, lineterminator="\r\n" if crlf else "\n")
            w.writeheader()
            w.writerows(rows)
        print(f"{market}: stamped {len(mine)} row(s); {changed} cell(s) changed (expected {len(mine)}); backup {os.path.basename(bak)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
