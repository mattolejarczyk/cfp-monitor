"""Append newly loaded events to a market's research INPUT list and SEED sheet, stamping EVENT_ID_CANON.
Guarded: refuses unless every id is already in grounding_facts; never edits an existing row; proves that after writing.
Report by default; --apply writes after timestamped backups.  Usage: add_inputs_and_seeds.py <cyber|util> [--apply]"""
import csv, os, shutil, sqlite3, sys
from datetime import datetime

P = "C:/Users/matts/cfp-monitor/experiments/purpose_audit/load6/"
MK = {"cyber": ("Cybersecurity", "Cybersecurity_input.csv", "cyber_seed.csv"), "util": ("Utility", "Utility_input.csv", "utility_seed.csv"),
      "basc": ("Cybersecurity", "Cybersecurity_input.csv", "cyber_seed.csv"),
      "arnica": ("Cybersecurity", "Cybersecurity_input.csv", "cyber_seed.csv"),
      "expo": ("Utility", "Utility_input.csv", "utility_seed.csv")}
MARKETS = "C:/Users/matts/Desktop/Nicolia-PR-Prime/Markets/"
LIVE = "C:/Users/matts/AppData/Local/CFP-Monitor/"
name = sys.argv[1]
market, input_name, seed_name = MK[name]
apply = "--apply" in sys.argv
stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
new = list(csv.DictReader(open(P + f"{name}6.csv", encoding="utf-8", newline="")))
seed_new = list(csv.DictReader(open(P + f"{name}6_seed.csv", encoding="utf-8-sig", newline="")))
db = sqlite3.connect(LIVE + "cfp_monitor.db")
for r in new:
    if not db.execute("select 1 from grounding_facts where event_id=?", (r["EVENT_ID"],)).fetchone():
        sys.exit(f"REFUSED: {r['EVENT_ID']} is not in the database")


def rewrite(path, cols, rows, like):
    raw = open(like, "rb").read()
    bom, crlf = raw.startswith(b"\xef\xbb\xbf"), b"\r\n" in raw
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL, lineterminator="\r\n" if crlf else "\n")
        w.writeheader()
        w.writerows(rows)
    return tmp


# ---- input list
ipath = MARKETS + input_name
with open(ipath, encoding="utf-8-sig", newline="") as fh:
    rd = csv.DictReader(fh)
    icols, irows = list(rd.fieldnames), list(rd)
have = {r["CONFERENCE"].strip() for r in irows}
add_in = []
for r in new:
    if r["CONFERENCE"].strip() in have:
        continue
    o = {c: "" for c in icols}
    for c in ("CONFERENCE", "CONFERENCE URL", "LOCATION", "CONFERENCE DATES", "EDITION", "START DATE", "Market"):
        o[c] = r[c]
    if o["START DATE"]:
        y, m, d = o["START DATE"].split("-")
        o["START DATE"] = f"{int(m)}/{int(d)}/{y}"
    o["RESEARCH STATUS"] = "Needs Verification"
    o["EVENT_ID_CANON"] = r["EVENT_ID"]
    add_in.append(o)
print(f"{market} input list {input_name}: {len(irows)} rows; to add {len(add_in)}: {[a['CONFERENCE'][:30] for a in add_in]}")

# ---- seed sheet
spath = LIVE + "market_sheets/" + seed_name
with open(spath, encoding="utf-8-sig", newline="") as fh:
    rd = csv.DictReader(fh)
    scols, srows = list(rd.fieldnames), list(rd)
if scols != list(seed_new[0].keys()):
    sys.exit("REFUSED: seed header differs from the import's seed header")
have_s = {r["EVENT_ID_CANON"] for r in srows}
add_s = [r for r in seed_new if r["EVENT_ID_CANON"] not in have_s]
print(f"{market} seed {seed_name}: {len(srows)} rows; to add {len(add_s)}")
if not apply:
    sys.exit(0)
for path, cols, rows, add in ((ipath, icols, irows, add_in), (spath, scols, srows, add_s)):
    shutil.copy(path, path.replace(".csv", f".pre-6more-{stamp}.bak.csv"))
    tmp = rewrite(path, cols, rows + add, path)
    with open(tmp, encoding="utf-8-sig", newline="") as fh:
        after = list(csv.DictReader(fh))
    assert len(after) == len(rows) + len(add) and after[: len(rows)] == rows, "existing rows changed"
    os.replace(tmp, path)
    print("written:", os.path.basename(path), len(after), "rows")
