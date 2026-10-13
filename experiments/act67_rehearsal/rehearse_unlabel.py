"""ACT-67 follow-up 2 rehearsal (git-ignored): the whole Friday path with the DUP_OF awards the customer lists UN-LABELLED.

Copies only. Stand-in research: the real 2026-10-09 Awards_audited.csv plus one researched row per un-labelled award (a copy of a real Closed row with that award's name; the real 10-09 run skipped
these rows because they were labelled DUP_OF, so there is no real research for them). Stand-in ids for the load step are FABRICATED and live only in work_ul2/ledger.csv.
Scenarios: A = switch off, no ids; B = one un-labelled award is named alike to its survivor by the research (same output EVENT_ID); C = upstream gave ids to two, switch on."""
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

N = HERE / "work_ul2"


def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig", newline="")))


def prep(collide=False):
    if N.exists():
        shutil.rmtree(N)
    (N / "markets").mkdir(parents=True)
    fc.W = N
    db = fc.build()
    md = N / "markets"
    lines = ca.run_unlabel("2026-10-12", HERE / "live", md, N / "qa", True)
    print("  ", lines[0])
    inp = rd(md / "Awards_input.csv")
    un = [r for r in inp if r["Market"] and r["DUP_OF"] == "" and r["EVENT_ID_CANON"] == "" and r["SOURCE_SHEET"] and r["CONFERENCE"] in {
        "Cloud Security Awards - SaaS Awards family", "CRN Tech Innovator Awards (The Channel Company)", "Cybersecurity Excellence Awards (Cybersecurity Insiders / InfoSec Community)",
        "Fortress Cybersecurity Award (Business Intelligence Group)", "Globee Awards for Cybersecurity (22nd Annual)", "Fast Company Most Innovative Companies 2026"}]
    print("   un-labelled rows now live with a BLANK id:", len(un))
    raw = rd(fc.WK / "Awards_audited.csv")
    cols = list(csv.DictReader(open(fc.WK / "Awards_audited.csv", encoding="utf-8-sig")).fieldnames)
    tmpl = next(x for x in rd(fc.MK / "Awards_audited.final.csv") if x["STATUS"] == "Closed" and x["Market"] == "Cybersecurity")
    ident = rd(md / "Awards_audited.identity.csv")
    surv = {r["CONFERENCE"]: r for r in raw}
    for r in un:
        row = dict(tmpl)
        name = r["CONFERENCE"]
        out_name = name
        if collide and name.startswith("Fortress"):
            out_name = "Fortress Cybersecurity Award"                      # the research writes back the survivor's name
        slug = re.sub(r"-+", "-", re.sub(r"[\s_]+", "-", re.sub(r"[^a-z0-9\s-]", "", out_name.lower()))).strip("-")
        row.update({"CONFERENCE": out_name, "EVENT_ID": f"2026-{slug}-nan-awards", "EDITION": "2026", "Market": r["Market"], "SUBMISSION DEADLINE": "2027-02-01", "STATUS": "Upcoming",
                    "IS_PROJECTED": "false", "GROUNDING_CONFIDENCE": "Verified (2026)", "SUBMISSION URL": r["SUBMISSION URL"]})
        raw.append(row)
        ident.append({"OUTPUT_EVENT_ID": row["EVENT_ID"], "OUTPUT_CONFERENCE": out_name, "INPUT_CONFERENCE": name, "EVENT_ID_CANON": ""})
        if collide and name.startswith("Fortress"):
            # the survivor's own research row has the same output id (it was researched under the same name)
            sv = next((x for x in raw if x["CONFERENCE"] == "Fortress Cybersecurity Award"), None)
            if sv:
                ident.append({"OUTPUT_EVENT_ID": row["EVENT_ID"], "OUTPUT_CONFERENCE": out_name, "INPUT_CONFERENCE": "Fortress Cybersecurity Award",
                              "EVENT_ID_CANON": next(i["EVENT_ID_CANON"] for i in inp if i["CONFERENCE"] == "Fortress Cybersecurity Award")})
    with open(md / "Awards_audited.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL, extrasaction="ignore")
        w.writeheader()
        w.writerows(raw)
    with open(md / "Awards_audited.identity.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["OUTPUT_EVENT_ID", "OUTPUT_CONFERENCE", "INPUT_CONFERENCE", "EVENT_ID_CANON"], quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(ident)
    return db, md, un


def resolve(db, md, tag, on, ledger):
    work = N / ("work_" + tag)
    work.mkdir()
    log = []
    wi.run = fc.fake_run_factory(log, use_repaired=False)
    wi.gate = fc.real_gate_no_network
    return wi.resolve_market(wi.AWARDS, md, work, db, {}, log, None, {"enabled": on, "ledger": ledger}), log


def show(res, un_names):
    cand = rd(res["candidate"])
    print(f"   {res['status']}: {len(cand)} candidate rows, rounds {res['rounds']}, new events {[e['canonical'] for e in res['new_events']]}")
    for h in res["new_events_held"]:
        if h["conference"] in un_names or "same output id" in h["reason"]:
            print(f"   HELD {h['conference'][:52]:52s} | {h['reason'][:110]}")
    return cand


def main():
    ledger = N / "ledger.csv"
    print("SCENARIO A  all un-labelled, no ids yet, switch ON (nothing may be minted or dropped silently)")
    db, md, un = prep()
    names = {r["CONFERENCE"] for r in un}
    ledger.write_text("event_id,market,given_on,source\n", encoding="utf-8")
    res, log = resolve(db, md, "A", True, ledger)
    cand = show(res, names)
    print("   gate R8c passed, survivors still shipped:", all(any(c["CONFERENCE"] == s for c in cand) for s in ("Fortress Cybersecurity Award", "Globee Awards for Cybersecurity", "The Cloud Awards - Security Awards")))
    print("   an un-labelled award in the candidate (must be 0):", sum(1 for c in cand if c["CONFERENCE"] in names))

    print("\nSCENARIO B  the research names the Fortress row exactly like its survivor (one output id, two input rows)")
    db, md, un = prep(collide=True)
    res, log = resolve(db, md, "B", True, ledger)
    cand = show(res, names)
    print("   Fortress rows in the candidate:", [(c["CONFERENCE"][:40], c["EVENT_ID"][:44]) for c in cand if c["CONFERENCE"].startswith("Fortress")])

    print("\nSCENARIO C  upstream gave OWN ids to two (stand-ins), switch ON -> loaded as separate awards")
    db, md, un = prep()
    given = {"Cloud Security Awards - SaaS Awards family": "2026-cloud-security-awards-saas-awards-family-nan-awards", "Globee Awards for Cybersecurity (22nd Annual)": "2026-globee-awards-for-cybersecurity-22nd-annual-nan-awards"}
    ids = N / "ids.csv"
    ids.write_text("id,start,url\n" + "".join(f"{i},,{next(r['SUBMISSION URL'] for r in un if r['CONFERENCE'] == n)}\n" for n, i in given.items()), encoding="utf-8")
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "stamp_given_ids.py"), "--awards", "--ids-csv", str(ids), "--markets-dir", str(md), "--db", str(db), "--ledger", str(ledger), "--apply"],
                       capture_output=True, text=True, cwd=str(ROOT))
    print("   ", [l for l in p.stdout.splitlines() if "STAMP" in l or "NOTE" in l])
    # the identity file must now carry the stamped ids
    ident = rd(md / "Awards_audited.identity.csv")
    inp = {r["CONFERENCE"]: r["EVENT_ID_CANON"] for r in rd(md / "Awards_input.csv")}
    with open(md / "Awards_audited.identity.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ident[0]), quoting=csv.QUOTE_ALL)
        w.writeheader()
        for r in ident:
            if r["INPUT_CONFERENCE"] in given:
                r["EVENT_ID_CANON"] = inp[r["INPUT_CONFERENCE"]]
            w.writerow(r)
    res, log = resolve(db, md, "C", True, ledger)
    cand = show(res, names)
    gj = json.loads(Path(res["accept_json"]).read_text(encoding="utf-8"))
    for v in gj.values():
        for c in v:
            if not c.get("passed") and all(str(f).startswith("SKIPPED") for f in c.get("failures", [])):
                c["passed"], c["failures"] = True, []
    gp = Path(res["accept_json"]).with_name("rehearsal_gate.json")
    gp.write_text(json.dumps({Path(res["candidate"]).name: next(iter(gj.values()))}), encoding="utf-8")
    before = wi.award_ids(db)
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "import_awards.py"), res["candidate"], "--db", str(db), "--gate-json", str(gp), "--seed", res["input"], "--ids", res["ids_csv"],
                        "--source-list", "weekly-awards-rehearsal", "--apply"], capture_output=True, text=True, cwd=str(ROOT))
    print("   import_awards:", [l for l in p.stdout.splitlines() if l.startswith(("         ", "written", "reconciled", "REFUSED"))][:3], "exit", p.returncode)
    print("   read-back proof:", wi.prove_first_awards(res, before, db, True) or "OK")
    con = sqlite3.connect(db)
    print("   new records:", [(r[0], r[1][:44]) for r in con.execute("select event_id, name from award_grounding_facts where event_id in (?,?)", tuple(given.values()))])
    con.close()
    for mk in ("Cybersecurity", "Utility"):
        out = N / f"awards_2026-10-12_{mk}.html"
        q = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_review_page.py"), "-i", res["candidate"], "--kind", "awards", "--markets", mk, "-o", str(out), "--no-evidence", "--date", "2026-10-12",
                            "--customer-awards-dir", str(HERE / "work_snap")], capture_output=True, text=True, cwd=str(ROOT))
        txt = out.read_text(encoding="utf-8")
        print(f"   page {mk}: exit {q.returncode}; Cloud Security Awards - SaaS on page {txt.count('Cloud Security Awards - SaaS')}x, Globee ... 22nd Annual {txt.count('22nd Annual')}x, Fortress (Business Intelligence Group) {txt.count('Fortress Cybersecurity Award (Business')}x")


if __name__ == "__main__":
    main()
