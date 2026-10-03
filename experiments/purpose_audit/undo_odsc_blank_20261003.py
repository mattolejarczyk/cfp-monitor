"""Undo my own 2026-10-03 ODSC East 2027 'fix'. The page https://odsc.ai/east/ states the 2027 edition in its header ("Menino Convention and Exhibition Center, Boston, MA | May 10-12th, 2027"),
read in a real browser on 2026-10-03; an earlier summary of the page had missed it and I cleared a CORRECT start date and set the status to Needs Verification, and pinned it blank
as 'operator verified' (the operator had not verified it). Restores START DATE 2027-05-10 and STATUS Upcoming in the approved Cybersecurity file and the database (the values the research
and the load had). Backups first; proves only those cells changed. Report by default; --apply writes. The approved file must then be re-gated and re-promoted (runbook 7.5)."""
import csv, os, shutil, sqlite3, sys
from datetime import datetime

APPLY = "--apply" in sys.argv
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
F = "C:/Users/matts/Desktop/Nicolia-PR-Prime/Markets/Cybersecurity_audited.final.csv"
DB = "C:/Users/matts/AppData/Local/CFP-Monitor/cfp_monitor.db"
EID = "2027-odsc-east-boston-speaking"
START, STATUS = "2027-05-10", "Upcoming"

raw = open(F, "rb").read(); bom, crlf = raw.startswith(b"\xef\xbb\xbf"), b"\r\n" in raw
with open(F, encoding="utf-8-sig", newline="") as fh:
    rd = csv.DictReader(fh); cols, rows = list(rd.fieldnames), list(rd)
before = [dict(r) for r in rows]
hit = [r for r in rows if r["CONFERENCE"].startswith("ODSC East 2027")]
assert len(hit) == 1
hit[0]["START DATE"], hit[0]["STATUS"] = START, STATUS
changed = {(i, c) for i, (a, b) in enumerate(zip(before, rows)) for c in a if a[c] != b[c]}
print("approved file cells:", [(c, before[i][c], rows[i][c]) for i, c in sorted(changed)])
con = sqlite3.connect(DB)
print("database now:", con.execute("select start_date,status from grounding_facts where event_id=?", (EID,)).fetchone(), "->", (START, STATUS))
if not APPLY:
    sys.exit(0)
shutil.copy(F, F.replace(".csv", f".pre-undo-odsc-{STAMP}.bak.csv"))
with open(F + ".tmp", "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL, lineterminator="\r\n" if crlf else "\n"); w.writeheader(); w.writerows(rows)
with open(F + ".tmp", encoding="utf-8-sig", newline="") as fh:
    aft = list(csv.DictReader(fh))
d2 = {(i, c) for i, (a, b) in enumerate(zip(before, aft)) for c in a if a[c] != b.get(c)}
assert len(aft) == len(before) and d2 == changed
os.replace(F + ".tmp", F)
con.close()
shutil.copy(DB, DB.replace("cfp_monitor.db", f"cfp_monitor.pre-undo-odsc-{STAMP}.db"))
con = sqlite3.connect(DB)
con.execute("update grounding_facts set start_date=?, status=? where event_id=?", (START, STATUS, EID))
con.commit()
print("written; approved file proved to differ only in those cells; database updated")
