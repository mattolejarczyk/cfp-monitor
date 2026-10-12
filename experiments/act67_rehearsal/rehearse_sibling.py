"""ACT-67 follow-up rehearsal (git-ignored): ONE AWARD UNDER TWO MARKETS - Fast Company Most Innovative Companies 2027 (Utility row on our list, on Arnica's sheet at High priority).

Copies only: the live awards sheets (live/), Markets/Awards_input.csv, the real 2026-10-09 research. Steps: auto-add (apply on the copy) adds the sibling row; the Friday import
(resolve_market with the REAL accept_delivery --no-network gate) ships the researched row under BOTH markets; import_awards lands ONE record and TWO award_markets rows; the page builder and
qa_build see both."""
import csv
import json
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

N = HERE / "work_sib"
FC = "Fast Company Most Innovative Companies 2027"


def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig", newline="")))


def main():
    if N.exists():
        shutil.rmtree(N)
    (N / "markets").mkdir(parents=True)
    fc.W = N
    db = fc.build()
    md = N / "markets"
    print("STEP 1  auto-add on the copy")
    lines, _ = ca.run("2026-10-12", HERE / "live", md, ca.NOT_RESEARCHED, N / "qa", 30, True)
    print("\n".join(l for l in lines if l.startswith("AWARDS AUTOADD:") or "WRONG" in l))
    inp = rd(md / "Awards_input.csv")
    for r in inp:
        if r["CONFERENCE"].startswith("Fast Company Most Innovative"):
            print("   input row:", r["CONFERENCE"][:60], "|", r["Market"], "| DUP_OF=", r["DUP_OF"][:30], "| canon=", r["EVENT_ID_CANON"][:55])
    lines, _ = ca.run("2026-10-12", HERE / "live", md, ca.NOT_RESEARCHED, N / "qa2", 30, True)
    print("   after:", lines[0])

    print("\nSTEP 2  Friday import resolve (real gate, no network): researched row shipped under both markets?")
    work = N / "work"
    work.mkdir()
    log = []
    wi.run = fc.fake_run_factory(log)
    wi.gate = fc.real_gate_no_network
    res = wi.resolve_market(wi.AWARDS, md, work, db, {}, log, None, {"enabled": False})
    cand = rd(res["candidate"])
    fcr = [r for r in cand if r["CONFERENCE"].startswith("Fast Company Most Innovative")]
    print(f"   {res['status']}, {len(cand)} candidate rows, rounds {res['rounds']}, siblings {res['market_siblings']}")
    for r in fcr:
        print("   candidate:", r["CONFERENCE"][:55], "|", r["Market"], "|", r["EVENT_ID"][:50], "|", r["SUBMISSION DEADLINE"], r["STATUS"])
    gj = json.loads(Path(res["accept_json"]).read_text(encoding="utf-8"))
    print("   gate R8c:", [(c["check"], c["passed"]) for v in gj.values() for c in v if c["check"] in ("R8c", "6")])

    print("\nSTEP 3  import_awards on the reconstructed DB copy")
    for v in gj.values():
        for c in v:
            if not c.get("passed") and all(str(f).startswith("SKIPPED") for f in c.get("failures", [])):
                c["passed"], c["failures"] = True, []
    gp = Path(res["accept_json"]).with_name("rehearsal_gate.json")
    gp.write_text(json.dumps({Path(res["candidate"]).name: next(iter(gj.values()))}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "import_awards.py"), res["candidate"], "--db", str(db), "--gate-json", str(gp), "--seed", res["input"], "--ids", res["ids_csv"],
                        "--source-list", "weekly-awards-rehearsal", "--apply"], capture_output=True, text=True, cwd=str(ROOT))
    print("  ", [l for l in r.stdout.splitlines() if l.startswith(("delivery", "         ", "written", "reconciled", "REFUSED", "RECON", "  -"))][:9], "exit", r.returncode)
    con = sqlite3.connect(db)
    key = "2027-fast-company-most-innovative-companies-tbd-awards"
    print("   award records:", con.execute("select count(*), max(deadline) from award_grounding_facts where event_id=?", (key,)).fetchone(),
          "| memberships:", con.execute("select market from award_markets where award_key=?", (key,)).fetchall())
    con.close()
    inv = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_invariants.py"), "--db", str(db), "--seed-dir", str(ROOT / "market_sheets"), "--awards-delivery", res["candidate"], "--awards-seed", res["input"]],
                         capture_output=True, text=True, cwd=str(ROOT))
    print("   invariants (awards half):", [l.strip()[:100] for l in inv.stdout.splitlines() if l.strip().startswith(("[ok", "[FAIL", "[warn", "RESULT")) and ("award" in l.lower() or l.startswith("RESULT") or l.strip()[6:8] in ("10", "11", "12", "13", "14", "15"))][:12])

    print("\nSTEP 4  page build per market (build_review_page --kind awards) and qa_build old vs new")
    for mk in ("Cybersecurity", "Utility"):
        out = N / f"page_{mk}.html"
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_review_page.py"), "--input", res["candidate"], "--kind", "awards", "--markets", mk, "--output", str(out), "--no-evidence"],
                           capture_output=True, text=True, cwd=str(ROOT))
        txt = out.read_text(encoding="utf-8") if out.exists() else ""
        print(f"   {mk}: exit {p.returncode}, 'Most Innovative Companies 2027' on the page: {txt.count('Most Innovative Companies 2027')}x;", (p.stdout + p.stderr).strip().splitlines()[-1][:100] if (p.stdout + p.stderr).strip() else "")
    q = subprocess.run([sys.executable, str(ROOT / "scripts" / "qa_build.py"), "--help"], capture_output=True, text=True, cwd=str(ROOT))
    print("   qa_build usage:", q.stdout.strip().splitlines()[0][:140] if q.stdout else q.stderr[:140])


if __name__ == "__main__":
    main()
