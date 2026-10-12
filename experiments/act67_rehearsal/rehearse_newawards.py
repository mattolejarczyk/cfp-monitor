"""ACT-67 rehearsal (git-ignored): the whole awards path on COPIES - coverage -> auto-add (apply on a copy) -> ids given (stand-in ledger) -> stamp -> Friday import with the first-load switch.

READ-ONLY inputs: the live customer awards sheets (copies in live/), Markets/Awards_input.csv, the 2026-10-09 weekend folder, Markets/Awards_20261002_out.csv. Everything written lives in work_new/.
THE IDS BELOW ARE FABRICATED STAND-INS for what upstream would give (this rehearsal has no upstream); they exist only in work_new/ledger.csv, never in docs/operations/given_ids.csv.
The database is the reconstruction from rehearse_fastcompany.py; the gate is the real accept_delivery.py --no-network."""
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
from scripts import first_load as fl                   # noqa: E402

N = HERE / "work_new"
LIVE = HERE / "live"


def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig", newline="")))


def main():
    if N.exists():
        shutil.rmtree(N)
    (N / "markets").mkdir(parents=True)
    fc.W = N                                                   # reuse its builders against this folder
    db = fc.build()
    md = N / "markets"
    before = rd(md / "Awards_input.csv")
    print("STEP 1  dry run, then --apply on the copy")
    out = N / "qa"
    lines, _ = ca.run("2026-10-12", LIVE, md, ca.NOT_RESEARCHED, out, 30, False)
    print("\n".join(lines))
    assert rd(md / "Awards_input.csv") == before, "dry run changed the list"
    lines, _ = ca.run("2026-10-12", LIVE, md, ca.NOT_RESEARCHED, out, 30, True)
    print("\n".join(l for l in lines if l.startswith("AWARDS AUTOADD")))
    after = rd(md / "Awards_input.csv")
    assert after[:len(before)] == before and len(after) == len(before) + 30
    blank = [r for r in after[len(before):] if not r["EVENT_ID_CANON"]]
    print(f"   input list {len(before)} -> {len(after)} rows; old rows byte-for-byte equal as values; {len(blank)} new rows all with a BLANK id; backup:",
          [p.name for p in md.glob("Awards_input.pre-customerrows-*")])
    lines, _ = ca.run("2026-10-12", LIVE, md, ca.NOT_RESEARCHED, out, 30, True)
    print("   second apply:", [l for l in lines if l.startswith("AWARDS AUTOADD:")][0])

    print("\nSTEP 2  stand-in ids 'given by upstream' for 3 awards (+1 with an edition that disagrees); stamp with stamp_given_ids --awards")
    new = {r["CONFERENCE"]: r for r in after[len(before):]}
    given = {"AI Breakthrough Awards": "2026-ai-breakthrough-awards-nan-awards", "BIG Innovation Awards": "2026-big-innovation-awards-nan-awards",
             "TIME Best Inventions Award": "2026-time-best-inventions-award-nan-awards", "The AI Awards": "2027-the-ai-awards-nan-awards"}
    ids_csv = N / "ids.csv"
    with open(ids_csv, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "start", "url"])
        for n, i in given.items():
            w.writerow([i, "", new[n]["SUBMISSION URL"]])
    ledger = N / "ledger.csv"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "stamp_given_ids.py"), "--awards", "--ids-csv", str(ids_csv), "--markets-dir", str(md), "--db", str(db), "--ledger", str(ledger), "--apply"],
                       capture_output=True, text=True, cwd=str(ROOT))
    print(r.stdout.strip() or r.stderr.strip())
    stamped = {x["CONFERENCE"]: x["EVENT_ID_CANON"] for x in rd(md / "Awards_input.csv") if x["CONFERENCE"] in given}
    print("   stamped on the list:", stamped)

    print("\nSTEP 3  Friday research output = the real 2026-10-09 file + researched rows for 5 new awards (one has no id, one has an edition that disagrees)")
    raw = rd(fc.WK / "Awards_audited.csv")
    cols = list(csv.DictReader(open(fc.WK / "Awards_audited.csv", encoding="utf-8-sig")).fieldnames)
    tmpl = next(x for x in rd(fc.MK / "Awards_audited.final.csv") if x["Market"] == "Cybersecurity" and x["STATUS"] == "Closed")
    ident = rd(md / "Awards_audited.identity.csv")
    researched = {"AI Breakthrough Awards": ("2026", "Cybersecurity"), "BIG Innovation Awards": ("2026", "Cybersecurity"), "TIME Best Inventions Award": ("2026", "Utility"),
                  "The AI Awards": ("2026", "Cybersecurity"),                      # id says 2027, edition 2026: held for a person
                  "Minsky Awards for Excellence in AI": ("2026", "Cybersecurity")}   # no id given at all: HELD, named
    for k, (name, (ed, mk)) in enumerate(researched.items()):
        row = dict(tmpl)
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        row.update({"CONFERENCE": name, "EVENT_ID": f"{ed}-{slug}-nan-awards", "EDITION": ed, "Market": mk, "SUBMISSION DEADLINE": "2026-06-01", "STATUS": "Closed",
                    "SUBMISSION URL": new[name]["SUBMISSION URL"], "CONFERENCE URL": "", "MAIN_INFO_URL": new[name]["SUBMISSION URL"]})
        raw.append(row)
        ident.append({"OUTPUT_EVENT_ID": row["EVENT_ID"], "OUTPUT_CONFERENCE": name, "INPUT_CONFERENCE": name, "EVENT_ID_CANON": stamped.get(name, "")})
    with open(md / "Awards_audited.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL, extrasaction="ignore")
        w.writeheader()
        w.writerows(raw)
    with open(md / "Awards_audited.identity.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["OUTPUT_EVENT_ID", "OUTPUT_CONFERENCE", "INPUT_CONFERENCE", "EVENT_ID_CANON"], quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(ident)

    for label, on in (("switch OFF (default)", False), ("switch ON (--new-awards)", True)):
        work = N / ("work_" + ("on" if on else "off"))
        work.mkdir()
        log = []
        wi.run = fc.fake_run_factory(log, use_repaired=False)
        wi.gate = fc.real_gate_no_network
        shutil.copy2(N / "markets" / "Awards_audited.csv", N / "markets" / "Awards_audited.csv.keep")
        res = wi.resolve_market(wi.AWARDS, md, work, db, {}, log, None, {"enabled": on, "ledger": ledger})
        print(f"\n== {label}: {res['status']}, candidate rows {res['shipped']}, new events {[e['canonical'] for e in res['new_events']]}")
        for h in res["new_events_held"]:
            if h["conference"] in researched or h["conference"].startswith(("Minsky",)):
                print(f"   HELD {h['conference'][:46]:46s} | {h['reason'][:130]}")
        print(f"   all HELD new awards named: {len(res['new_events_held'])}; waiting (id given, switch off): {res['new_events_waiting']}; held for a person: {res['new_events_held_for_person']}")
        if on:
            before_ids = wi.award_ids(db)
            shutil.copy2(db, N / "db_before.sqlite")
            gj = json.loads(Path(res["accept_json"]).read_text(encoding="utf-8"))          # rehearsal only: the two network checks were SKIPPED (no network here); treat them as passed so the importer runs
            for checks in gj.values():
                for c in checks:
                    if not c.get("passed") and all(str(f).startswith("SKIPPED") for f in c.get("failures", [])):
                        c["passed"], c["failures"] = True, []
            gj_path = Path(res["accept_json"]).with_name("rehearsal_gate.json")
            gj_path.write_text(json.dumps({Path(res["candidate"]).name: next(iter(gj.values()))}), encoding="utf-8")
            r = subprocess.run([sys.executable, str(ROOT / "scripts" / "import_awards.py"), res["candidate"], "--db", str(db), "--gate-json", str(gj_path), "--seed", res["input"],
                                "--ids", res["ids_csv"], "--source-list", "weekly-awards-rehearsal", "--apply"], capture_output=True, text=True, cwd=str(ROOT))
            print("   import_awards:", [l for l in r.stdout.splitlines() if l.startswith(("delivery", "         ", "written", "reconciled", "REFUSED", "RECON"))][:6], "exit", r.returncode)
            print("   read-back proof:", wi.prove_first_awards(res, before_ids, db, True) or "OK (exactly the expected awards, names match, on a market list)")
            con = sqlite3.connect(db)
            print("   award_grounding_facts rows now:", con.execute("select count(*) from award_grounding_facts").fetchone()[0], "| the new ones:",
                  [r_[0] for r_ in con.execute("select event_id from award_grounding_facts where event_id in (%s)" % ",".join("?" * 3), [given[n] for n in list(given)[:3]])])
            print("   their markets:", con.execute("select award_key, market from award_markets where award_key in (%s)" % ",".join("?" * 3), [given[n] for n in list(given)[:3]]).fetchall())
            con.close()
            # second run adds nothing
            work2 = N / "work_on2"
            work2.mkdir()
            res2 = wi.resolve_market(wi.AWARDS, md, work2, db, {}, [], None, {"enabled": True, "ledger": ledger})
            print("   second run: new events", len(res2["new_events"]), "(already in the database)")


if __name__ == "__main__":
    main()
