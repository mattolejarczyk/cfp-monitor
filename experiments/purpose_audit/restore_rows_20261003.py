"""Restore six rows after the 2026-10-03 live load overwrote verified evidence with blanks (narrow-first research found no quote and the blank won).
Rows: Nullcon Goa 2027, RSA Conference 2027, Black Hat Asia 2027 (Call for Summits), ACM CODASPY 2027, Apres-Cyber Slopes 2027, Global Energy Show Canada 2027 (link only).
DB: only deadline, is_projected, deadline_evidence_url, deadline_quote (and submission_url for Global Energy Show) are copied back, from the pre-load
database (Nullcon: from the pre-promotion approved file, because the database never held its 10-01 correction). Status and everything else stay as loaded.
Approved files (Markets/*_audited.final.csv): the same cells, with R11 respected (GROUNDING_CONFIDENCE follows IS_PROJECTED).
Report by default; --apply writes after backups and proves exactly those cells changed.   Usage: restore_rows_20261003.py [--apply]"""
import csv, os, shutil, sqlite3, sys
from datetime import datetime

L = "C:/Users/matts/AppData/Local/CFP-Monitor/"
M = "C:/Users/matts/Desktop/Nicolia-PR-Prime/Markets/"
APPLY = "--apply" in sys.argv
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
PRE_DB = L + "cfp_monitor.pre-golive-20261003.db"
LIVE_DB = L + "cfp_monitor.db"
PRE_CYBER = M + "Cybersecurity_audited.final.pre-promote-20261003-081209.csv"
# name fragment (lowercase) -> market; the fragment must hit exactly one DB row
TARGETS = {"nullcon goa 2027": "C", "rsa conference 2027": "C", "black hat asia 2027 (call for summits": "C",
           "17th acm conference on data and application security": "C", "apres-cyber slopes summit 2027": "C",
           "global energy show canada 2027": "U"}
DB_FIELDS = ["deadline", "is_projected", "deadline_evidence_url", "deadline_quote"]

pre, live = sqlite3.connect(PRE_DB), sqlite3.connect(LIVE_DB)
src_cyber = {r["CONFERENCE"].lower().strip(): r for r in csv.DictReader(open(PRE_CYBER, encoding="utf-8-sig", newline=""))}
plan = []                         # (event_id, name, {field: new}, market)
for frag, mk in TARGETS.items():
    rows = live.execute("select event_id, name from grounding_facts where lower(name) like ?", (frag + "%",)).fetchall()
    if len(rows) != 1:
        sys.exit(f"REFUSED: {frag!r} hits {len(rows)} database rows (need exactly 1): {rows}")
    eid, name = rows[0]
    if frag == "nullcon goa 2027":
        s = src_cyber["nullcon goa 2027"]
        new = {"deadline": s["SUBMISSION DEADLINE"], "is_projected": s["IS_PROJECTED"], "deadline_evidence_url": s["DEADLINE_EVIDENCE_URL"],
               "deadline_quote": s["DEADLINE_QUOTE"]}
    else:
        r = pre.execute(f"select {','.join(DB_FIELDS)}, submission_url from grounding_facts where event_id=?", (eid,)).fetchone()
        if r is None:
            sys.exit(f"REFUSED: {eid} not in the pre-load backup")
        new = dict(zip(DB_FIELDS, r[:4]))
        if frag.startswith("global energy show"):
            new = {"submission_url": r[4]}          # only the link regressed; the new evidence and projection were gate-verified
    plan.append((eid, name, new, mk))

print("DATABASE changes:")
for eid, name, new, mk in plan:
    cur = live.execute(f"select {','.join(new)} from grounding_facts where event_id=?", (eid,)).fetchone()
    print(f"  {name[:50]}")
    for (f, v), c in zip(new.items(), cur):
        if (v or "") != (c or ""):
            print(f"     {f:22s} {str(c or '-')[:46]!r} -> {str(v or '-')[:46]!r}")

if APPLY:
    shutil.copy(LIVE_DB, L + f"cfp_monitor.post-golive-before-restore-{STAMP}.db")
    before = {r[0]: r for r in live.execute("select * from grounding_facts")}
    for eid, name, new, mk in plan:
        live.execute(f"update grounding_facts set {','.join(f + '=?' for f in new)} where event_id=?", (*new.values(), eid))
    live.commit()
    cols = [r[1] for r in live.execute("pragma table_info(grounding_facts)")]
    after = {r[0]: r for r in live.execute("select * from grounding_facts")}
    changed = {(k, cols[i]) for k in after for i in range(len(cols)) if before[k][i] != after[k][i]}
    allowed = {(eid, f) for eid, _, new, _ in plan for f in new}
    assert changed <= allowed and len(after) == len(before), f"unexpected database change: {changed - allowed}"
    print(f"DATABASE written: {len(changed)} cell(s), all in the plan; row count {len(after)} unchanged")


# ---- approved files: same cells by CONFERENCE name, R11 respected
def conf_conf(proj: str, edition: str) -> str:
    return f"{'Projected' if proj == 'true' else 'Verified'} ({edition})"


for mk, fname in (("C", "Cybersecurity_audited.final.csv"), ("U", "Utility_audited.final.csv")):
    path = M + fname
    raw = open(path, "rb").read(); bom, crlf = raw.startswith(b"\xef\xbb\xbf"), b"\r\n" in raw
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh); cols, rows = list(rd.fieldnames), list(rd)
    before = [dict(r) for r in rows]
    for eid, name, new, m in plan:
        if m != mk:
            continue
        hit = [r for r in rows if r["CONFERENCE"].strip() == name.strip()]
        if len(hit) != 1:
            print(f"  note: {fname}: {len(hit)} rows named {name!r}; not edited there"); continue
        r = hit[0]
        if "deadline" in new:
            r["SUBMISSION DEADLINE"], r["IS_PROJECTED"] = new["deadline"] or "", new["is_projected"]
            r["DEADLINE_EVIDENCE_URL"], r["DEADLINE_QUOTE"] = new["deadline_evidence_url"] or "", new["deadline_quote"] or ""
            r["GROUNDING_CONFIDENCE"] = conf_conf(new["is_projected"], r["EDITION"])
        if "submission_url" in new:
            r["CFP_SUBMISSION_URL"] = new["submission_url"] or ""
    ch = [(i, c) for i, (a, b) in enumerate(zip(before, rows)) for c in a if a[c] != b[c]]
    print(f"\n{fname}: {len(ch)} cell(s) change")
    for i, c in ch:
        print(f"  {rows[i]['CONFERENCE'][:44]:44s} {c:22s} {before[i][c][:40]!r} -> {rows[i][c][:40]!r}")
    if APPLY and ch:
        shutil.copy(path, path.replace(".csv", f".pre-restore-{STAMP}.bak.csv"))
        with open(path + ".tmp", "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL, lineterminator="\r\n" if crlf else "\n"); w.writeheader(); w.writerows(rows)
        with open(path + ".tmp", encoding="utf-8-sig", newline="") as fh:
            aft = list(csv.DictReader(fh))
        d2 = {(i, c) for i, (a, b) in enumerate(zip(before, aft)) for c in a if a[c] != b.get(c)}
        assert len(aft) == len(before) and d2 == set(ch), "unexpected file change"
        os.replace(path + ".tmp", path)
        print("  written; proved only those cells differ from the backup")
