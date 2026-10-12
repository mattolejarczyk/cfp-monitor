"""ACT-67 rehearsal (git-ignored): reproduce the 2026-10-09 Fast Company drop on COPIES of the real Friday files, with the old and the new failure-to-row rule.

Inputs are read-only copies: the weekend folder 20261009-135429 (raw research, repaired file), Markets/Awards_20261002_out.csv (the prior the run used), Awards_input.csv, identity.csv.
The database is a RECONSTRUCTION (the live one was not readable here): award ids from the input list's EVENT_ID_CANON, upstream ids from the prior file matched by name. The gate is the REAL
accept_delivery.py with --no-network (every check that needs no network runs; SKIPPED ones are ignored): check 6 (past deadline shown as open) is the one that fired on the day."""
import csv
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import scripts.weekend_import as wi                      # noqa: E402
from src.cfp_monitor.storage import Store                # noqa: E402

MK = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
WK = MK / "weekend" / "20261009-135429"
W = Path(__file__).resolve().parent / "work_fc"
TODAY = "2026-10-09"


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig", newline="")))


def build():
    if W.exists():
        shutil.rmtree(W)
    (W / "markets").mkdir(parents=True)
    for n, src in (("Awards_input.csv", MK / "Awards_input.csv"), ("Awards_audited.csv", WK / "Awards_audited.csv"), ("Awards_audited.identity.csv", MK / "Awards_audited.identity.csv"),
                   ("Awards_20261002_out.csv", MK / "Awards_20261002_out.csv")):
        shutil.copy2(src, W / "markets" / n)
    shutil.copy2(WK / "Awards_audited.repaired.csv", W / "repaired_from_run.csv")
    inp, prior = rd(W / "markets" / "Awards_input.csv"), rd(W / "markets" / "Awards_20261002_out.csv")
    canon_by_name = {norm(r["CONFERENCE"]): r["EVENT_ID_CANON"] for r in inp if r["EVENT_ID_CANON"].strip()}
    db = W / "db.sqlite"
    Store(str(db)).db.close()
    con = sqlite3.connect(db)
    con.execute("alter table award_grounding_facts add column upstream_event_id TEXT")
    seen = set()
    for p in prior:
        c = canon_by_name.get(norm(p["CONFERENCE"]))
        if c is None and "most innovative companies 2026" in norm(p["CONFERENCE"]):
            c = "2027-fast-company-most-innovative-companies-2026-tbd-awards"        # ASSUMED: the DUP_OF row has no id on the input list; the database holds its own record
        c = c or p["EVENT_ID"]                                      # a prior row with no id on the input list: the database record is under its own id (ASSUMED)
        if c not in seen:
            seen.add(c)
            con.execute("insert into award_grounding_facts (event_id, upstream_event_id, name, deadline, status) values (?,?,?,?,?)",
                        (c, p["EVENT_ID"], p["CONFERENCE"], p["SUBMISSION DEADLINE"], p["STATUS"]))
    for c in canon_by_name.values():                                                      # every id on the input list is in the database (they were stamped from it)
        if c not in seen:
            seen.add(c)
            con.execute("insert into award_grounding_facts (event_id, name) values (?, '')", (c,))
    con.commit()
    con.close()
    return db


def fake_run_factory(log, use_repaired=True):
    def fake_run(cmd, cwd, out, timeout=7200):
        name = Path(str(cmd[1])).name
        if name == "mechanical_repairs.py" and use_repaired:
            stage = Path(str(cmd[2]))
            shutil.copy2(W / "repaired_from_run.csv", stage.with_name(stage.stem + ".repaired.csv"))
        return 0
    return fake_run


def real_gate_no_network(csv_path, cwd, log, network=True, db=None, market=None):
    js = csv_path.with_name(csv_path.stem + ".gate.json")
    # the real gate, as of the day of the run: check 6 compares deadlines with 'today'
    head = ["import datetime as _d", "_real = _d.date", "class _D(_real):", "    @classmethod", "    def today(cls):", "        return _real(2026, 10, 9)", "_d.date = _D",
            "import sys", f"sys.argv = ['accept_delivery.py', r'{csv_path}', '--json', r'{js}', '--no-network']", f"sys.path.insert(0, r'{ROOT}')", "import runpy",
            f"runpy.run_path(r'{ROOT / 'scripts' / 'accept_delivery.py'}', run_name='__main__')"]
    runner = W / "gate_runner.py"
    runner.write_text(chr(10).join(head) + chr(10), encoding="utf-8")
    subprocess.run([sys.executable, str(runner)], capture_output=True, text=True, cwd=str(ROOT))
    payload = json.loads(js.read_text(encoding="utf-8"))
    fails = [(str(r.get("check")), str(f)) for res in payload.values() for r in res if not r.get("passed") for f in r.get("failures", []) if not str(f).startswith("SKIPPED")]
    return ("REJECTED" if fails else "ACCEPTED"), fails, js


def old_rows_for_failure(text, rows):
    hits = []
    for i, r in enumerate(rows):
        name = (r.get("CONFERENCE") or "").strip()
        if name and text.startswith(name[:wi.NAME_PREFIX]):
            hits.append(i)
    return hits


def go(label, db, old_rule):
    work = W / ("work_" + label)
    work.mkdir(exist_ok=True)
    log = []
    new_rf = wi.rows_for_failure
    if old_rule:
        wi.rows_for_failure = old_rows_for_failure
    wi.run = fake_run_factory(log)
    wi.gate = real_gate_no_network
    try:
        res = wi.resolve_market(wi.AWARDS, W / "markets", work, db, {}, log, None, {"enabled": False})
    finally:
        wi.rows_for_failure = new_rf
    cand = rd(res["candidate"]) if res.get("candidate") else []
    fc = [r for r in cand if "most innovative" in r["CONFERENCE"].lower()]
    print(f"== {label}: status {res['status']}, candidate rows {len(cand)}, rounds {res.get('rounds')}")
    print("   Fast Company Most Innovative rows in the candidate:", [(r["CONFERENCE"], r["SUBMISSION DEADLINE"], r["STATUS"]) for r in fc])
    for d in res["decisions"]:
        if "fast company" in d["conference"].lower() or d["action"] == "held-back":
            print("   decision:", d["action"], "|", d["conference"][:60], "|", "; ".join(d["reasons"])[:110])
    return res


if __name__ == "__main__":
    db = build()
    go("old_rule", db, True)
    go("new_rule", db, False)
