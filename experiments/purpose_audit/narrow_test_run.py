"""Small real test of CFP_PROMPT_MODE=narrow-first through the PRODUCTION script (2026-10-02). Writes only under narrow_test/.

    python experiments/purpose_audit/narrow_test_run.py            # runs it (about 7 Gemini calls, roughly $0.50)
    python experiments/purpose_audit/narrow_test_run.py --report   # summarise an existing run, no calls

Conference rows: two NEW events (almost no input data: the hard case for carrying other fields) and two established rows with rich
input data. Award rows: two NEW awards and one established. Cost cap: --limit on each run. Nothing outside narrow_test/ is written."""
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "narrow_test"
M = Path("C:/Users/matts/Desktop/Nicolia-PR-Prime/Markets")
CONF = ["TROOPERS27", "SANS Cyber Threat Intelligence Summit and OSINT Summit", "ShmooCon 2027", "CyberTech Global Tel Aviv 2027"]
AW = ["Climate Change Emerging Scholar Awards", "ACT Expo Fleet Awards", "Tech Trailblazers Awards"]


def subset(src: Path, names: list[str], dst: Path) -> int:
    with open(src, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        cols, rows = rd.fieldnames, [r for r in rd if r["CONFERENCE"].strip() in names]
    with open(dst, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def run(tag: str, src: Path, names: list[str]) -> None:
    inp, out = OUT / f"{tag}_in.csv", OUT / f"{tag}_out.csv"
    n = subset(src, names, inp)
    for f in OUT.glob(f"{tag}_out*"):
        f.unlink()
    env = {**os.environ, "CFP_PROMPT_MODE": "narrow-first", "PYTHONIOENCODING": "utf-8"}
    t0 = time.time()
    p = subprocess.run([sys.executable, str(M / "run_market_audit.py"), "-i", str(inp), "-o", str(out), "--delay", "5", "--limit", str(n)],
                       capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(M), timeout=1500)
    (OUT / f"{tag}_log.txt").write_text(p.stdout + "\n--STDERR--\n" + p.stderr, encoding="utf-8")
    print(f"{tag}: {n} rows, exit {p.returncode}, {time.time() - t0:.0f}s")


def report(tag: str) -> None:
    inp = {r["CONFERENCE"].strip(): r for r in csv.DictReader(open(OUT / f"{tag}_in.csv", encoding="utf-8-sig"))}
    out_path = OUT / f"{tag}_out.csv"
    log = (OUT / f"{tag}_log.txt").read_text(encoding="utf-8") if (OUT / f"{tag}_log.txt").exists() else ""
    print(f"\n=== {tag}: log mentions narrow {log.count('[prompt: narrow]')}x, full {log.count('[prompt: full]')}x, "
          f"'no Google Search ran' {log.count('no Google Search ran')}x, 504 {log.count('504')}x")
    if not out_path.exists():
        print("  no output file")
        return
    for r in csv.DictReader(open(out_path, encoding="utf-8-sig")):
        i = inp.get(r["CONFERENCE"].strip(), {})
        stub = "Audit Exception" in r.get("STATUS DETAILS", "")
        kept = {c: bool(i.get(c, "").strip()) and r.get(c, "") == i.get(c, "") for c in ("OVERVIEW", "CATEGORIES", "ORGANIZER", "TRACK", "COORDINATOR EMAIL")}
        had = [c for c, v in kept.items() if i.get(c, "").strip()]
        print(f"- {r['CONFERENCE'][:46]} {'STUB' if stub else ''}\n    deadline {r['SUBMISSION DEADLINE'] or '(blank)'} | status {r['STATUS']} | projected {r['IS_PROJECTED']} | "
              f"opens {r.get('SUBMISSION_OPENS') or '-'} | announce {r.get('ANNOUNCEMENT_DATE') or '-'}\n    evidence {r['DEADLINE_EVIDENCE_URL'][:70] or '(none)'}\n"
              f"    quote {r['DEADLINE_QUOTE'][:90] or '(none)'}\n    FORMAT {r.get('FORMAT') or '(blank)'} | venue evidence {r.get('VENUE_EVIDENCE_URL', '')[:50] or '(blank)'} | "
              f"name unchanged {r['CONFERENCE'].strip() in inp} | input fields the input HAD and kept unchanged: "
              f"{sum(1 for c in had if kept[c])} of {len(had)}")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    if "--report" not in sys.argv:
        run("conf", M / "Cybersecurity_input.csv", CONF)
        run("awards", M / "Awards_input.csv", AW)
    report("conf")
    report("awards")
