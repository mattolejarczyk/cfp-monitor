"""Take in the customer's week, before we spend anything researching ours.

    python scripts/weekly_intake.py [--db DB] [--config PATH] [--snapshots DIR] [--dry-run]

WHY THIS RUNS FIRST
Their sheet is the most valuable input we have and the only one we do not generate. A real
person emails organisers, records what they heard in STATUS DETAILS, marks rows for us, and
acts on deadlines. Reading that before research is not courtesy, it is cost and correctness:

    2026-08-11   11 of 93 grounded requests went on conferences that had already happened
    2026-09-01   a day of citation remediation ran without reading the client layer once;
                 22 repaired rows had already been verified or acted on by their team, and
                 one was queued to be marked discontinued while they held an ACCEPTANCE to
                 it and were weighing a $12,500 sponsorship

IT CANNOT BE ALLOWED TO STOP THE RESEARCH
This is the front of the Saturday job. Research is the expensive, scheduled, hours-long part
of the week, and a missing credential or a flaky network must never cost a research window.
So EVERY step here is contained: nothing raises, nothing propagates, and the exit code is 0
even when the run is degraded. The Saturday job reads the banner, not the status.

WHAT "SELF-REPAIRING" MEANS HERE, AND WHAT IT CANNOT MEAN
It retries a fetch that failed transiently. It carries on with one client when the other
fails. It falls back to the newest snapshot already on disk and says how old it is. What it
cannot do is create a credential - if the service account key is missing, only a person can
fix that, so the honest behaviour is to say so in one clear line and keep going.

**THE NUMBER THAT MATTERS IS THE AGE OF THE CLIENT LAYER**, and it is always reported, on a
good week and a bad one. Silence about staleness is the failure: on 2026-09-15 the client
layer was 16 days old, merge decisions had been made against it, and nothing anywhere said so.

    exit 0 always. Read INTAKE HEALTH in the output, or intake_status.json.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PY = sys.executable
LIVE_DB = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor\cfp_monitor.db")
CONFIG = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor\customer_sheets.json")
SNAPSHOTS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets\customer_snapshots")
RUNS_OUT = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor\runs_out")

# config key -> how the database knows this client. Kept here rather than guessed from the
# config, because load_client_sheet writes these into `clients` and a typo would create a
# second client record rather than updating the one that exists.
CLIENTS = {
    "utility": {"key": "utility-global", "name": "Utility Global", "industry": "Utility"},
    "arnica":  {"key": "arnica",         "name": "Arnica",         "industry": "Cybersecurity"},
}

RETRY_DELAYS = (10, 30, 60)      # a sheet fetch is cheap; a lost research window is not
STALE_AFTER_DAYS = 9             # one cycle plus slack: a week plus two days

# FAILURES A RETRY CANNOT FIX, and what a person has to do about each. Matched against the fetch's
# own error text. Retrying these spent ~100 seconds proving the same thing four times, and the
# note that came out the other end did not even say what it was (see failure_reasons).
#
# Anything NOT listed is retried exactly as before. The list names only failures that are
# certain not to change between attempts; an unrecognised failure is cheap to retry, and giving
# up early on a transient one would be the expensive mistake.
PERMANENT = (
    ("No module named", "a library is missing from the project environment - run `uv sync` "
                        "in cfp-monitor"),
    ("Service account key not found", "the key file is missing - see WEEKLY-CYCLE.md step 0"),
    ("No config at", "customer_sheets.json is missing"),
    ("Unknown client", "customer_sheets.json does not name this client"),
    ("404 from the export endpoint", "wrong sheet_id, or the sheet is no longer shared with "
                                     "the service account"),
    ("401 from the export endpoint", "the sheet is not shared with the service account as Viewer"),
    ("403 from the export endpoint", "the sheet is not shared with the service account as "
                                     "Viewer, or the Google Drive API is disabled"),
    ("HTML page, not CSV", "a sign-in or permission redirect - check the sheet's sharing"),
    ("is missing column(s)", "wrong tab (gid), or the customer changed the sheet's columns"),
    ("has no rows", "the sheet came back empty - look at it before trusting any snapshot"),
    ("invalid_grant", "the key was deleted or disabled in Google Cloud - create a new one"),
)


def failure_reasons(output: str) -> list[str]:
    """The lines that say WHY a fetch failed.

    Not the last line of output. With --alert, the fetch always finishes by printing where it
    wrote the alert file, so until 2026-09-16 every failure was recorded in intake_status.json
    as "alert written: ...Desktop\\CUSTOMER-SHEET-FETCH-FAILED.txt" - true, and useless.
    """
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    failed = [ln for ln in lines if ": FAILED - " in ln]
    if failed:
        return failed
    # A failure before any client was tried (no key, no config) arrives as a bare message.
    return [ln for ln in lines if not ln.startswith(("alert written:", "Traceback"))][-1:]


def permanent_fix(reasons: list[str]) -> str | None:
    """What a person must do, if EVERY reason is one a retry cannot fix; otherwise None.

    All, not any: with two clients, one may fail on sharing while the other hit a timeout, and
    the timeout still deserves its retry.
    """
    if not reasons:
        return None
    fixes = []
    for reason in reasons:
        fix = next((f for sig, f in PERMANENT if sig in reason), None)
        if fix is None:
            return None
        if fix not in fixes:
            fixes.append(fix)
    return "; ".join(fixes)


def run(cmd: list[str], timeout: int = 600) -> tuple[int, str]:
    """Run a step. Never raises - a crash here is a finding, not an exception."""
    try:
        p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True,
                           timeout=timeout, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except Exception as exc:                                         # noqa: BLE001
        return 125, f"{type(exc).__name__}: {exc}"


def newest_snapshot(client: str, snapshots: Path) -> Path | None:
    """The most recent snapshot on disk for this client, whatever happened today."""
    d = snapshots / client
    if not d.is_dir():
        return None
    files = sorted(d.glob(f"{client}_*.csv"))
    return files[-1] if files else None


def snapshot_date(path: Path | None) -> date | None:
    """The date in the filename, which is what the snapshot asserts about itself.

    Read from the NAME, not the mtime: a file copied or restored keeps its name and loses its
    timestamp, and the name is what the snapshot store guarantees is unique.
    """
    if path is None:
        return None
    m = re.search(r"_(\d{8})-", path.name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def age_days(d: date | None, today: date) -> int | None:
    return None if d is None else (today - d).days


def loaded_snapshot_date(db: str, client_key: str) -> date | None:
    """What the DATABASE thinks it last ingested for this client.

    The disk and the database disagree more often than anyone expects: a snapshot can be taken
    and never loaded, which leaves a fresh file on disk and a stale client layer in the tables,
    with nothing anywhere reporting a problem. Found live on 2026-09-15 - snapshots from
    2026-09-01 sitting unloaded while the database still held 2026-08-30.
    """
    import sqlite3                                                   # noqa: PLC0415
    try:
        con = sqlite3.connect(db)
        row = con.execute("SELECT MAX(snapshot_file) FROM client_conferences WHERE client_key=?",
                          (client_key,)).fetchone()
        con.close()
    except Exception:                                                # noqa: BLE001
        return None
    return snapshot_date(Path(row[0])) if row and row[0] else None


def fetch_all(config: Path, snapshots: Path) -> tuple[bool, list[str]]:
    """Fetch both sheets, with retries. Returns (any_success, notes)."""
    notes: list[str] = []
    key = None
    try:
        key = Path(json.loads(config.read_text(encoding="utf-8"))["service_account_key"])
    except Exception as exc:                                         # noqa: BLE001
        notes.append(f"config unreadable ({type(exc).__name__}) - {config}")
        return False, notes
    if not key.exists():
        # The one thing this script cannot repair. Say it once, plainly, and carry on.
        notes.append(f"service account key missing: {key}. A person must download it from "
                     f"Google Cloud and share both sheets with its client_email as Viewer. "
                     f"Until then intake is manual - see WEEKLY-CYCLE.md step 0.")
        return False, notes

    for attempt, delay in enumerate((0, *RETRY_DELAYS)):
        if delay:
            time.sleep(delay)
        code, out = run([PY, ROOT / "scripts/fetch_customer_sheet.py", "--client", "all",
                         "--config", config, "--out-dir", snapshots, "--alert"], timeout=900)
        if code == 0:
            if attempt:
                notes.append(f"fetch succeeded on attempt {attempt + 1}")
            return True, notes
        reasons = failure_reasons(out) or [f"exit {code}"]
        notes.append(f"fetch attempt {attempt + 1} failed: {' | '.join(reasons)[:300]}")
        fix = permanent_fix(reasons)
        if fix:
            notes.append(f"not retried - a retry cannot fix this. A person must: {fix}")
            break
    return False, notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--config", default=str(CONFIG))
    ap.add_argument("--snapshots", default=str(SNAPSHOTS))
    ap.add_argument("--dry-run", action="store_true", help="report only; fetch nothing, load nothing")
    a = ap.parse_args()
    today = date.today()
    snapshots = Path(a.snapshots)

    print("=" * 78)
    print("WEEKLY INTAKE - the customer's week, before we research ours")
    print("=" * 78)

    before = {c: snapshot_date(newest_snapshot(c, snapshots)) for c in CLIENTS}
    notes: list[str] = []

    if a.dry_run:
        notes.append("dry run: nothing fetched, nothing loaded")
        fetched = False
    else:
        fetched, fetch_notes = fetch_all(Path(a.config), snapshots)
        notes += fetch_notes

    results = []
    for client, meta in CLIENTS.items():
        newest = newest_snapshot(client, snapshots)
        taken = snapshot_date(newest)
        is_new = taken is not None and taken != before.get(client)
        in_db = loaded_snapshot_date(a.db, meta["key"])
        # LOAD WHATEVER THE DATABASE HAS NOT SEEN, not merely what we fetched just now. This is
        # the self-repairing part: a snapshot taken on a week the load step failed, or was never
        # run, is picked up on the next pass instead of sitting on disk for ever while the
        # client layer quietly ages.
        behind = taken is not None and (in_db is None or taken > in_db)
        loaded, detail = False, ""
        if behind and not is_new:
            notes.append(f"{client}: snapshot {taken} was on disk but the database held "
                         f"{in_db or 'nothing'} - loading it now")

        if behind and not a.dry_run:
            code, out = run([PY, ROOT / "scripts/load_client_sheet.py", "--db", a.db,
                             "--csv", newest, "--client", meta["key"], "--name", meta["name"],
                             "--industry", meta["industry"]], timeout=900)
            loaded = code == 0
            if not loaded:
                detail = (out.strip().splitlines() or [f"exit {code}"])[-1][:160]
                notes.append(f"{client}: load failed - {detail}")

        results.append({"client": client, "snapshot": newest.name if newest else None,
                        "taken": taken.isoformat() if taken else None,
                        "in_db": in_db.isoformat() if in_db else None,
                        "age_days": age_days(taken, today), "new_this_run": is_new,
                        "loaded": loaded, "detail": detail})

    print(f"\n{'client':<10} {'snapshot taken':<16} {'age':>6}  {'new':<5} {'loaded':<6}")
    for r in results:
        age = "never" if r["age_days"] is None else f"{r['age_days']}d"
        print(f"{r['client']:<10} {r['taken'] or '(none)':<16} {age:>6}  "
              f"{'yes' if r['new_this_run'] else 'no':<5} {'yes' if r['loaded'] else '-':<6}")

    # THE VERDICT IS ABOUT THE AGE OF THE DATA, not about whether a command succeeded. A fetch
    # that failed on a week the sheet had not changed matters far less than a client layer
    # quietly drifting a month behind while every step reports success.
    ages = [r["age_days"] for r in results]
    worst = max((x for x in ages if x is not None), default=None)
    if any(x is None for x in ages):
        status, why = "DEGRADED", "a client has never been snapshotted"
    elif worst is not None and worst > STALE_AFTER_DAYS:
        status, why = "DEGRADED", f"client layer is {worst} days old (stale after {STALE_AFTER_DAYS})"
    elif notes and not fetched:
        status, why = "DEGRADED", "nothing was fetched this run"
    else:
        status, why = "HEALTHY", f"client layer is {worst} day(s) old"

    print(f"\nINTAKE HEALTH: {status} - {why}")
    for n in notes:
        print(f"  - {n}")
    if status == "DEGRADED":
        print("\n  Research will still run. Treat every row's STATUS as possibly out of date,")
        print("  and do not act on a contradiction with the customer until intake is current.")

    RUNS_OUT.mkdir(parents=True, exist_ok=True)
    out = RUNS_OUT / "intake_status.json"
    try:
        out.write_text(json.dumps(
            {"ran_at": datetime.now().isoformat(timespec="seconds"), "status": status,
             "why": why, "clients": results, "notes": notes}, indent=2), encoding="utf-8")
        print(f"\nwrote {out}")
    except Exception as exc:                                         # noqa: BLE001
        print(f"\ncould not write {out}: {exc}")

    # ALWAYS 0. The Saturday job must not lose a research window to an intake problem.
    return 0


if __name__ == "__main__":
    sys.exit(main())
