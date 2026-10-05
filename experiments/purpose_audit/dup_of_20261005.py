"""DUP_OF and one stamp, 2026-10-05 (answer to note 28). Upstream confirmed two Cybersecurity input rows are second listings (R15):
  - 'OWASP Global AppSec Europe 2026' duplicates 2026-owasp-global-appsec-eu-vienna, which ANOTHER input row already carries: this row gets DUP_OF (the audit skips it like a duplicate
    award; the importer does not count it as missing).
  - 'OWASP German Chapter Conference (AppSec Karlsruhe 2026)' duplicates the database row 2026-german-owasp-day-karlsruhe, but NO other input row carries that id, so the research of THIS row
    should load onto the survivor: it is stamped with the survivor's id (EVENT_ID_CANON), not marked DUP_OF (which would stop the event being researched at all).
Backup first; proves that only those cells changed. Report by default; --apply writes.   Usage: dup_of_20261005.py [--apply]"""
import csv
import shutil
import sys
from datetime import datetime

PATH = "C:/Users/matts/Desktop/Nicolia-PR-Prime/Markets/Cybersecurity_input.csv"
APPLY = "--apply" in sys.argv
DUPS = {"OWASP Global AppSec Europe 2026": "2026-owasp-global-appsec-eu-vienna"}
STAMPS = {"OWASP German Chapter Conference (AppSec Karlsruhe 2026)": "2026-german-owasp-day-karlsruhe"}

raw = open(PATH, "rb").read()
bom, crlf = raw.startswith(b"\xef\xbb\xbf"), b"\r\n" in raw
with open(PATH, encoding="utf-8-sig", newline="") as fh:
    rd = csv.DictReader(fh)
    cols, rows = list(rd.fieldnames), list(rd)
survivors = {r.get("EVENT_ID_CANON") for r in rows}
import os
import sqlite3
held = {x[0] for x in sqlite3.connect("file:" + os.environ["LOCALAPPDATA"] + "/CFP-Monitor/cfp_monitor.db?mode=ro", uri=True).execute("select event_id from grounding_facts")}
for name, eid in STAMPS.items():
    hit = [r for r in rows if r["CONFERENCE"] == name]
    if len(hit) != 1 or eid not in held or eid in survivors or (hit[0].get("EVENT_ID_CANON") or "").strip():
        sys.exit(f"cannot stamp {name!r} with {eid}: not exactly one row, not in the database, already carried, or already stamped: nothing written")
for name, survivor in DUPS.items():
    hit = [r for r in rows if r["CONFERENCE"] == name]
    if len(hit) != 1:
        sys.exit(f"{len(hit)} input rows named {name!r}: nothing written")
    if survivor not in survivors:
        sys.exit(f"the surviving id {survivor} is not carried by any input row: nothing written")
before = [dict(r) for r in rows]
if "DUP_OF" not in cols:
    cols.append("DUP_OF")
for r in rows:
    r["DUP_OF"] = DUPS.get(r["CONFERENCE"], r.get("DUP_OF", "") or "")
    if r["CONFERENCE"] in STAMPS:
        r["EVENT_ID_CANON"] = STAMPS[r["CONFERENCE"]]
changed = {(a["CONFERENCE"], c) for a, b in zip(before, rows) for c in cols if a.get(c, "") != b.get(c, "")}
print(f"{len(rows)} rows; DUP_OF set on {sum(1 for r in rows if r['DUP_OF'])}; cells changed: {sorted(changed)}")
if sorted(c for _, c in changed) != sorted(["DUP_OF"] * len(DUPS) + ["EVENT_ID_CANON"] * len(STAMPS)):
    sys.exit("unexpected cells changed: nothing written")
if not APPLY:
    print("report only. Add --apply.")
    sys.exit(0)
bak = PATH.replace(".csv", f".pre-dupof-{datetime.now():%Y%m%d-%H%M%S}.bak.csv")
shutil.copy2(PATH, bak)
with open(PATH, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL, lineterminator="\r\n" if crlf else "\n")
    w.writeheader()
    w.writerows(rows)
print("written; backup", bak.rsplit("/", 1)[-1])
