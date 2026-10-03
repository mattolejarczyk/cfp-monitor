"""Apply docs/operations/pinned_rows.json to what is LIVE right now (2026-10-03): the approved Cybersecurity file and the database, so the two rulings (CODASPY, Apres-Cyber)
hold today and not only from the next Saturday load. Backups first; proves only the pinned cells changed. Report by default; --apply writes.
After --apply the approved file must be re-gated with the network and re-promoted (runbook 7.5)."""
import csv, os, shutil, sqlite3, sys
from datetime import date, datetime

sys.path.insert(0, "C:/Users/matts/cfp-monitor")
from scripts.pinned_rows import apply_pins, load_pins
from src.cfp_monitor.identity import seed_map, to_canonical

APPLY = "--apply" in sys.argv
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
L = "C:/Users/matts/AppData/Local/CFP-Monitor/"
F = "C:/Users/matts/Desktop/Nicolia-PR-Prime/Markets/Cybersecurity_audited.final.csv"
DBCOL = {"SUBMISSION DEADLINE": "deadline", "DEADLINE_EVIDENCE_URL": "deadline_evidence_url", "DEADLINE_QUOTE": "deadline_quote",
         "IS_PROJECTED": "is_projected", "CFP_SUBMISSION_URL": "submission_url"}
pins = load_pins()
up_to_canon, _ = seed_map(L + "cfp_monitor.db")

raw = open(F, "rb").read(); bom, crlf = raw.startswith(b"\xef\xbb\xbf"), b"\r\n" in raw
with open(F, encoding="utf-8-sig", newline="") as fh:
    rd = csv.DictReader(fh); cols, rows = list(rd.fieldnames), list(rd)
before = [dict(r) for r in rows]
rows, rep = apply_pins(rows, up_to_canon, to_canonical, pins, date.today())
changed = {(i, c) for i, (a, b) in enumerate(zip(before, rows)) for c in a if a[c] != b[c]}
print(f"APPROVED FILE: {len(changed)} cell(s) change on {len({i for i, _ in changed})} row(s); pins lapsed: {rep['lapsed']}")
for i, c in sorted(changed):
    print(f"  {rows[i]['CONFERENCE'][:40]:40s} {c:22s} {before[i][c][:44]!r} -> {rows[i][c][:44]!r}")

con = sqlite3.connect(L + "cfp_monitor.db")
dbplan = []
for p in pins:
    cur = con.execute(f"select {','.join(DBCOL.values())} from grounding_facts where event_id=?", (p["canonical"],)).fetchone()
    if cur is None:
        sys.exit(f"REFUSED: {p['canonical']} is not in the database")
    new = {DBCOL[k]: v for k, v in p["set"].items() if k in DBCOL}
    diff = {k: (c, new[k]) for k, c in zip(DBCOL.values(), cur) if k in new and (c or "") != new[k]}
    dbplan.append((p["canonical"], diff))
    print(f"DATABASE {p['event']}: " + (", ".join(f"{k} {str(a)[:30]!r}->{str(b)[:30]!r}" for k, (a, b) in diff.items()) or "no change"))
if not APPLY:
    sys.exit(0)

shutil.copy(F, F.replace(".csv", f".pre-pins-{STAMP}.bak.csv"))
with open(F + ".tmp", "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL, lineterminator="\r\n" if crlf else "\n"); w.writeheader(); w.writerows(rows)
with open(F + ".tmp", encoding="utf-8-sig", newline="") as fh:
    aft = list(csv.DictReader(fh))
d2 = {(i, c) for i, (a, b) in enumerate(zip(before, aft)) for c in a if a[c] != b.get(c)}
assert len(aft) == len(before) and d2 == changed, "unexpected change in the approved file"
os.replace(F + ".tmp", F)
print("approved file written; proved only the pinned cells changed")

shutil.copy(L + "cfp_monitor.db", L + f"cfp_monitor.pre-pins-{STAMP}.db")
for eid, diff in dbplan:
    if diff:
        con.execute(f"update grounding_facts set {','.join(k + '=?' for k in diff)} where event_id=?", (*[b for _, b in diff.values()], eid))
con.commit()
print("database written")
