"""One-off 2026-10-02: after upstream's second sparse patch (note 20 follow-up) refresh ONLY the six Arnica rows in the Cybersecurity
input list (LOCATION, CONFERENCE DATES, START DATE) and seed sheet (whole rows from load6/arnica6b_seed.csv). Backups first; proves no other row changed."""
import csv, shutil
from datetime import datetime
M = "C:/Users/matts/Desktop/Nicolia-PR-Prime/Markets/Cybersecurity_input.csv"
S = "C:/Users/matts/AppData/Local/CFP-Monitor/market_sheets/cyber_seed.csv"
NEW = "C:/Users/matts/cfp-monitor/experiments/purpose_audit/load6/arnica6b_seed.csv"
new = {r["EVENT_ID_CANON"]: r for r in csv.DictReader(open(NEW, encoding="utf-8-sig", newline=""))}
stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

def rw(path, fn):
    raw = open(path, "rb").read(); bom, crlf = raw.startswith(b"\xef\xbb\xbf"), b"\r\n" in raw
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh); cols, rows = list(rd.fieldnames), list(rd)
    before = [dict(r) for r in rows]
    n = fn(rows)
    changed_ids = {i for i, (a, b) in enumerate(zip(before, rows)) if a != b}
    shutil.copy(path, path.replace(".csv", f".pre-arnica6b-{stamp}.bak.csv"))
    with open(path + ".tmp", "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL, lineterminator="\r\n" if crlf else "\n"); w.writeheader(); w.writerows(rows)
    import os; os.replace(path + ".tmp", path)
    print(path.split("/")[-1], "rows", len(rows), "changed", len(changed_ids), "touched ids ok:", all(rows[i]["EVENT_ID_CANON"] in new for i in changed_ids))

def f_input(rows):
    for r in rows:
        n = new.get(r.get("EVENT_ID_CANON", ""))
        if n:
            r["LOCATION"], r["CONFERENCE DATES"] = n["LOCATION"], n["CONFERENCE DATES"]
            s = n["START DATE"]
            r["START DATE"] = (lambda y, m, d: f"{int(m)}/{int(d)}/{y}")(*s.split("-")) if s else ""
def f_seed(rows):
    for i, r in enumerate(rows):
        if r["EVENT_ID_CANON"] in new: rows[i] = {c: new[r["EVENT_ID_CANON"]].get(c, r[c]) for c in r}
rw(M, f_input); rw(S, f_seed)
