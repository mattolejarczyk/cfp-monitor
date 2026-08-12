"""Weekly discovery for the handful of rows whose call has not opened yet.

WHY THIS EXISTS AND WHY IT IS SEPARATE
`weekly_verify.py` re-checks claims we already hold and spends no API quota. Finding a call
that has NEWLY OPENED on a page we never cited is a different question, and it was deliberately
left to the monthly grounded audit on 2026-08-08 because re-researching the whole database
weekly is ~400 requests and had just exhausted quota.

That reasoning applies to the whole database. It does not apply to nine rows. Discovery scoped
to rows that are BOTH unconfirmed AND still have a future deadline costs roughly nine requests
a week, and it is the only way to notice a 2027 call the week it opens rather than the month
after. Decided 2026-08-12, and the customer briefing now promises it.

THE SCOPE IS THE COST CONTROL. A row qualifies only if:

    the deadline is in the FUTURE      a passed deadline has no page left to find (rule 1)
    it is not already verified         a confirmed citation needs no discovery
    it was not deliberately retired    [R1 withdrawal] / [retired] are decisions, not gaps

That set is currently 9. `--max-rows` is a hard ceiling on top, so a data problem that suddenly
qualifies 300 rows cannot quietly spend 300 requests.

WHAT IT DOES NOT DO
It does not call the grounding API itself - discovery is upstream's half of the contract and
their script holds the key. This builds the queue, optionally invokes that script, then runs
OUR extraction and gate over whatever comes back. Without --run-discovery it just writes the
queue and reports, which is the safe default.

    python scripts/weekly_discovery.py --db <live.db> [--run-discovery] [--apply]
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import shutil
import sqlite3
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor.verify import _parse_date          # noqa: E402

# Markers meaning "we decided this, do not keep looking". Mirrors refresh_delivery.CLEAR_MARKERS
# plus the upgrade path; a row carrying one is answered, not open.
ANSWERED = ("[R1 withdrawal]", "[retired]", "[upgraded")


def open_rows(db: str, source_csv: Path, today: date) -> tuple[list[dict], list[str], dict]:
    """Rows still worth asking upstream about, with the reason each other row was excluded."""
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    _s = importlib.util.spec_from_file_location("_ar", ROOT / "scripts" / "apply_resolutions.py")
    _ar = importlib.util.module_from_spec(_s)
    _s.loader.exec_module(_ar)

    class _S:
        path = db
    up_to_canon, _roots = _ar._seed_map(_S())
    if not up_to_canon:
        raise SystemExit("REFUSING: no EVENT_ID map beside the database - nothing would match.")

    facts = {r["event_id"]: r for r in con.execute("select * from grounding_facts")}
    with open(source_csv, encoding="utf-8-sig", newline="") as fh:
        src = list(csv.DictReader(fh))
    cols = list(src[0].keys()) if src else []

    keep, why = [], {"verified": 0, "answered": 0, "passed": 0, "no date": 0, "unmatched": 0}
    for r in src:
        raw = (r.get("EVENT_ID") or "").strip()
        f = facts.get(up_to_canon.get(raw, raw))
        if not f:
            why["unmatched"] += 1
            continue
        if f["verify_state"] == "verified":
            why["verified"] += 1
            continue
        if (f["verify_detail"] or "").startswith(ANSWERED):
            why["answered"] += 1
            continue
        d = _parse_date(f["deadline"] or "")
        if not d:
            why["no date"] += 1
            continue
        if d < today:
            why["passed"] += 1
            continue
        # Hand upstream what we hold NOW, not what we held when the list was first built.
        r["DEADLINE YOU SENT"] = f["deadline"]
        r["URL YOU CITED"] = f["deadline_evidence_url"] or ""
        keep.append((d, r))
    keep.sort(key=lambda x: x[0])
    return [r for _, r in keep], cols, why


def main() -> int:
    ap = argparse.ArgumentParser(description="Weekly discovery for rows whose call is still shut.")
    ap.add_argument("--db", required=True)
    ap.add_argument("--source", required=True,
                    help="the original unconfirmed-citations CSV; the queue is derived from it")
    ap.add_argument("--out-dir", required=True, help="where the queue and results are written")
    ap.add_argument("--max-rows", type=int, default=25,
                    help="hard ceiling on rows sent for discovery. Guards against a data "
                         "problem suddenly qualifying hundreds and spending hundreds.")
    ap.add_argument("--discovery-script",
                    help="upstream's extract_candidate_urls.py. Given with --run-discovery, it "
                         "is invoked on the queue; otherwise the queue is only written.")
    ap.add_argument("--run-discovery", action="store_true",
                    help="SPENDS API QUOTA - roughly one grounded request per queued row")
    ap.add_argument("--apply", action="store_true",
                    help="merge anything that survives the gate. Reports only without it.")
    a = ap.parse_args()

    today = date.today()
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")

    print("=" * 84)
    print(f"WEEKLY DISCOVERY  {datetime.now():%Y-%m-%d %H:%M}   "
          f"{'APPLY' if a.apply else 'REPORT ONLY'}")
    print("=" * 84)

    rows, cols, why = open_rows(a.db, Path(a.source), today)
    print(f"\nfrom {sum(why.values()) + len(rows)} audited rows:")
    for k, v in why.items():
        if v:
            print(f"   {v:>4}  excluded - {k}")
    print(f"   {len(rows):>4}  OPEN - unconfirmed with a future deadline")

    if not rows:
        print("\nNothing to discover. Every audited row is verified, answered or past its date.")
        return 0

    if len(rows) > a.max_rows:
        print(f"\nREFUSING: {len(rows)} rows qualify but --max-rows is {a.max_rows}.")
        print("  That many usually means a data problem, not a real spike in open calls.")
        print("  Inspect the queue before raising the ceiling.")
        return 2

    queue = out_dir / f"weekly_discovery_queue_{stamp}.csv"
    with open(queue, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"\nqueue: {queue}")
    for r in rows:
        print(f"   {r['DEADLINE YOU SENT']}  {r['CONFERENCE'][:56]}")

    if not a.run_discovery:
        print(f"\nQueue written. {len(rows)} grounded request(s) would be spent with "
              f"--run-discovery.")
        return 0

    if not a.discovery_script or not Path(a.discovery_script).exists():
        print("\nERROR: --run-discovery needs --discovery-script pointing at "
              "extract_candidate_urls.py")
        return 2

    ds = Path(a.discovery_script)
    found = out_dir / f"weekly_discovery_out_{stamp}.csv"
    if found.exists():
        found.unlink()          # its resume logic refuses to overwrite, so start clean
    print(f"\n--- discovery: {len(rows)} row(s), ~{len(rows)} grounded request(s) ---")
    rc = subprocess.run([sys.executable, "-u", str(ds.name), "-i", str(queue.resolve()),
                         "-o", str(found.resolve())],
                        cwd=str(ds.parent), text=True).returncode
    if rc != 0 or not found.exists():
        print(f"discovery failed (rc={rc}) - nothing to gate")
        return 1

    print("\n--- our gate: extract citations from whatever it returned ---")
    extracted = out_dir / f"weekly_discovery_citations_{stamp}.csv"
    rc = subprocess.run([sys.executable, str(ROOT / "scripts" / "extract_citations.py"),
                         "-i", str(found), "-o", str(extracted)],
                        cwd=str(ROOT), text=True).returncode
    if rc != 0 or not extracted.exists():
        print(f"extraction failed (rc={rc})")
        return 1

    print("\n--- merge guard ---")
    cmd = [sys.executable, str(ROOT / "scripts" / "apply_resolutions.py"),
           "--db", a.db, "--citations", str(extracted)]
    if a.apply:
        cmd.append("--apply")
    subprocess.run(cmd, cwd=str(ROOT), text=True)

    print(f"\nqueue     {queue.name}")
    print(f"discovery {found.name}")
    print(f"citations {extracted.name}")
    if not a.apply:
        print("\nREPORT ONLY - nothing merged. Re-run with --apply once the gate output reads "
              "correctly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
