"""ACT-67 follow-up 3 rehearsal (git-ignored work dirs): upstream's reply with 41 award ids, end to end on COPIES.

Steps: copy of the live list -> auto-add (the Fast Company sibling) -> --relabel (dry, apply, second apply) -> --reply-plan -> stamp_given_ids --awards (new ids, then existing ids with --allow-held)
-> coverage and waiting-for-id -> Friday import with stand-in research (the real 2026-10-09 file plus one researched row per award that has an id now; the research for those did not exist) with the
first-load switch ON -> import_awards -> read-back proof -> duplicates check. DB = reconstruction (+ the two existing -tbd- ids), gate = real accept_delivery --no-network."""
import csv
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import rehearse_fastcompany as fc                      # noqa: E402
import scripts.weekend_import as wi                    # noqa: E402
from scripts import customer_awards as ca              # noqa: E402

N = HERE / "work_reply"
REPLY = ROOT / "docs" / "operations" / "award_ids_reply_20261012.csv"
EXISTING = {"Computing Security Awards": "2026-computing-security-awards-tbd-awards", "Fast Company World Changing Ideas": "2026-fast-company-world-changing-ideas-tbd-awards"}


def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig", newline="")))


def sg(args):
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "stamp_given_ids.py"), "--awards", "--markets-dir", str(N / "markets"), "--db", str(N / "db.sqlite"), "--ledger", str(N / "ledger.csv")] + args,
                       capture_output=True, text=True, cwd=str(ROOT))
    return p.stdout.strip() or p.stderr.strip()


def main():
    if N.exists():
        shutil.rmtree(N)
    (N / "markets").mkdir(parents=True)
    fc.W = N
    db = fc.build()
    md = N / "markets"
    con = sqlite3.connect(db)
    for nm, eid in EXISTING.items():
        con.execute("update award_grounding_facts set event_id=? where name=?", (eid, nm))
    con.commit()
    con.close()
    live = HERE / "live"
    print("STEP 0  the copy of the live list; auto-add (Fast Company sibling)")
    print("  ", ca.run("2026-10-12", live, md, ca.NOT_RESEARCHED, N / "q0", 30, True)[0][-1])
    n_before = len(rd(md / "Awards_input.csv"))

    print("STEP 1  --relabel")
    print("  ", ca.run_relabel(REPLY, md, N / "q1", False)[0])
    before = rd(md / "Awards_input.csv")
    print("  ", ca.run_relabel(REPLY, md, N / "q1", True)[0])
    after = rd(md / "Awards_input.csv")
    changed = {(i, c) for i, (a, b) in enumerate(zip(before, after)) for c in a if a[c] != b[c]}
    print(f"   cells changed: {len(changed)} (all DUP_OF: {all(c == 'DUP_OF' for _, c in changed)}), rows {len(before)} -> {len(after)}")
    print("  ", ca.run_relabel(REPLY, md, N / "q1", True)[0], "(second apply)")

    print("STEP 2  --reply-plan, then stamp (dry run first)")
    print("  ", ca.run_reply_plan(REPLY, md, N / "q2", None)[0])
    (N / "ledger.csv").write_text("event_id,market,given_on,source\n", encoding="utf-8")
    print("   new ids, dry run:", sg(["--ids-csv", str(N / "q2" / "ids_new.csv")]).splitlines()[0])
    print("   new ids, apply  :", [l for l in sg(["--ids-csv", str(N / "q2" / "ids_new.csv"), "--apply"]).splitlines() if l.startswith(("Awards_input", "ledger"))])
    print("   existing, dry   :", sg(["--ids-csv", str(N / "q2" / "ids_existing.csv"), "--allow-held"]).splitlines()[0])
    print("   existing, apply :", [l for l in sg(["--ids-csv", str(N / "q2" / "ids_existing.csv"), "--allow-held", "--apply"]).splitlines() if l.startswith(("Awards_input", "ledger"))])
    print("   second plan     :", ca.run_reply_plan(REPLY, md, N / "q2b", None)[0])
    inp = rd(md / "Awards_input.csv")
    waiting = ca.waiting_for_id(inp)
    print(f"   rows {n_before} -> {len(inp)}; waiting for an id: {len(waiting)} {[w['name'][:30] for w in waiting]}")
    ids = [r["EVENT_ID_CANON"] for r in inp if r["EVENT_ID_CANON"]]
    live_ids = [(r["Market"], r["EVENT_ID_CANON"]) for r in inp if r["EVENT_ID_CANON"] and not r["DUP_OF"]]
    print(f"   input ids: {len(ids)}; the same id on two live rows of one market: {len(live_ids) - len(set(live_ids))}")
    print("  ", ca.run("2026-10-12", live, md, ca.NOT_RESEARCHED, N / "q3", 30, False)[0])

    print("STEP 3  Friday: stand-in research for every award that now has an id, switch ON")
    raw = rd(fc.WK / "Awards_audited.csv")
    cols = list(csv.DictReader(open(fc.WK / "Awards_audited.csv", encoding="utf-8-sig")).fieldnames)
    tmpl = next(x for x in rd(fc.MK / "Awards_audited.final.csv") if x["Market"] == "Cybersecurity" and x["STATUS"] == "Closed")
    ident = rd(md / "Awards_audited.identity.csv")
    new_names = {ca.name_key(q["award_name"]): q for q in rd(REPLY) if q["action"] in ("NEW", "STAMP_NONAWARD", "STAMP_EXISTING")}
    ledger_ids = {r["event_id"] for r in rd(N / "ledger.csv")}
    researched = []
    for r in inp:
        q = new_names.get(ca.name_key(r["CONFERENCE"]))
        if q is None or not r["EVENT_ID_CANON"]:
            continue
        have_raw = [x for x in raw if x["CONFERENCE"] == r["CONFERENCE"]]
        if have_raw:                                                   # the real 10-09 research already answered this input row (it was held for want of an id): only its identity changes
            for ir in ident:
                if ir["INPUT_CONFERENCE"] == r["CONFERENCE"]:
                    ir["EVENT_ID_CANON"] = r["EVENT_ID_CANON"]
            continue
        row = dict(tmpl)
        slug = re.sub(r"[^a-z0-9]+", "-", r["CONFERENCE"].lower()).strip("-")
        opp = {"World Hydrogen and Carbon Asia": "Speaking", "Clinton Global Initiative (CGI) Commitments to Action 2026": "Registration"}.get(r["CONFERENCE"], "Awards")
        row.update({"CONFERENCE": r["CONFERENCE"], "EVENT_ID": f"{r['EVENT_ID_CANON'][:4]}-{slug}-nan-{opp.lower()}", "EDITION": r["EVENT_ID_CANON"][:4], "Market": r["Market"], "SUBMISSION DEADLINE": "2026-06-01",
                    "STATUS": "Closed", "OPPORTUNITY_TYPE": opp, "SUBMISSION URL": r["SUBMISSION URL"]})
        raw.append(row)
        ident.append({"OUTPUT_EVENT_ID": row["EVENT_ID"], "OUTPUT_CONFERENCE": r["CONFERENCE"], "INPUT_CONFERENCE": r["CONFERENCE"], "EVENT_ID_CANON": r["EVENT_ID_CANON"]})
        researched.append(r["CONFERENCE"])
    with open(md / "Awards_audited.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL, extrasaction="ignore")
        w.writeheader()
        w.writerows(raw)
    with open(md / "Awards_audited.identity.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["OUTPUT_EVENT_ID", "OUTPUT_CONFERENCE", "INPUT_CONFERENCE", "EVENT_ID_CANON"], quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(ident)
    work = N / "work"
    work.mkdir()
    log = []
    wi.run = fc.fake_run_factory(log, use_repaired=False)
    wi.gate = fc.real_gate_no_network
    res = wi.resolve_market(wi.AWARDS, md, work, db, {}, log, None, {"enabled": True, "ledger": N / "ledger.csv"})
    if res["status"] != "ACCEPTED":
        print("   NOT ACCEPTED:", res.get("why"), res.get("decisions", [])[:3]); return
    cand = rd(res["candidate"])
    print(f"   {res['status']}: {len(cand)} candidate rows, rounds {res['rounds']}; new awards to load: {len(res['new_events'])}; held: {len(res['new_events_held'])}")
    for h in res["new_events_held"]:
        print(f"   HELD {h['conference'][:50]:50s} [{h.get('kind', '-')}] {h['reason'][:90]}")
    gj = json.loads(Path(res["accept_json"]).read_text(encoding="utf-8"))
    print("   gate R8c:", [c["passed"] for v in gj.values() for c in v if c["check"] == "R8c"])
    for v in gj.values():
        for c in v:
            if not c.get("passed") and all(str(f).startswith("SKIPPED") for f in c.get("failures", [])):
                c["passed"], c["failures"] = True, []
    gp = Path(res["accept_json"]).with_name("rehearsal_gate.json")
    gp.write_text(json.dumps({Path(res["candidate"]).name: next(iter(gj.values()))}), encoding="utf-8")
    before_ids = wi.award_ids(db)
    n0 = len(before_ids)
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "import_awards.py"), res["candidate"], "--db", str(db), "--gate-json", str(gp), "--seed", res["input"], "--ids", res["ids_csv"],
                        "--source-list", "weekly-awards-rehearsal", "--apply"], capture_output=True, text=True, cwd=str(ROOT))
    print("   import_awards:", [l.strip() for l in p.stdout.splitlines() if "new," in l or l.startswith(("written", "reconciled", "REFUSED"))], "exit", p.returncode)
    print("   read-back proof:", wi.prove_first_awards(res, before_ids, db, True) or "OK")
    con = sqlite3.connect(db)
    n1 = con.execute("select count(*) from award_grounding_facts").fetchone()[0]
    dupn = con.execute("select count(*) from (select lower(name) n, count(*) c from award_grounding_facts group by n having c > 1)").fetchone()[0]
    print(f"   award records {n0} -> {n1} (+{n1 - n0}); names held by two records: {dupn}")
    for nm in ("Computing Security Awards", "Fast Company World Changing Ideas", "The Cloud Awards - Security Awards", "TIME Best Inventions 2026"):
        print("   ", nm, "->", con.execute("select count(*) from award_grounding_facts where name=?", (nm,)).fetchone()[0], "record")
    print("   non-awards loaded into the award tables:", con.execute("select count(*) from award_grounding_facts where name like 'World Hydrogen and Carbon%' or name like 'Clinton Global%'").fetchone()[0])
    con.close()


if __name__ == "__main__":
    main()
