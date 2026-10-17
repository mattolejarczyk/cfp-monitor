"""One command for the Saturday patches (ACT-64 sponsor prefill, ACT-63 new events, ACT-22 Friday awards shadow step): checks, backs up, applies, proves the result, restores on any doubt.

    python experiments\\saturday_apply\\apply_saturday_patches.py            DRY RUN: does every check on the live files in memory, writes nothing
    python experiments\\saturday_apply\\apply_saturday_patches.py --apply    does it

What each patch is (reviewed patches in docs/control/patches/):
  ACT-64  Markets\\run_overnight.ps1  +3 lines  copies last week's settled sponsorship answer into the new research file before the sponsor pass (saves about 35 USD a week).
  ACT-63  Markets\\run_monthly.ps1    +4/-1 lines  lets Saturday's import load a brand-new event itself when upstream has given its id (Saturday only).
  ACT-22  Markets\\run_monthly.ps1    +6 lines     adds a LAST, read-only, capped (45 min, 0.30 USD) awards shadow step to FRIDAY's run; it never fails the run; it first runs the Friday after it is applied.
Two patches for the same file are applied one after the other IN MEMORY and the file is written once, so the second can never overwrite the first.
Safety, per file: refuses if a scheduled CFP task is running; refuses if the patch is already in; applies with the repo's own apply_unified() (the one the tests use) and requires the exact
line count and exactly one marker; the new text must PARSE as PowerShell (0 errors) before anything is written; a backup named *.pre-act64-20261013 / *.pre-act63-20261013 is made first; after writing
the file is read back, parsed and compared byte for byte with what was prepared, and the backup is put back automatically if any of that fails.
To undo by hand: copy the backup over the script. --markets-dir lets the reviewer rehearse on a copy of the Markets folder.
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(r"C:\Users\matts\cfp-monitor")
LIVE_MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
sys.path.insert(0, str(ROOT))
from tests.test_shadow_reader_hook import apply_unified  # noqa: E402

TARGETS = [
    {"name": "ACT-64", "file": "run_overnight.ps1", "patch": "ACT-64-run_overnight.ps1.patch", "marker": '--apply } catch { Write-Host "SPONSOR-PREFILL', "present": "sponsor_prefill.py", "delta": 3,
     "backup": "run_overnight.ps1.pre-act64-20261013"},
    {"name": "ACT-63", "file": "run_monthly.ps1", "patch": "ACT-63-run_monthly.ps1.patch", "marker": "$newEvents = if ($kind -eq 'saturday')", "present": "$newEvents = if ($kind -eq", "delta": 3,
     "backup": "run_monthly.ps1.pre-act63-20261013"},
    {"name": "ACT-22", "file": "run_monthly.ps1", "patch": "ACT-22-run_monthly.ps1.patch", "marker": "# 2026-10-05 (ACT-22): AWARDS SHADOW RUN", "present": "(ACT-22): AWARDS SHADOW RUN", "delta": 6,
     "backup": "run_monthly.ps1.pre-act22-20261016"},
]


def parse_errors(text: str) -> int:
    """Number of PowerShell parse errors in `text` (Windows PowerShell 5.1's own parser)."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "check.ps1"
        p.write_bytes(text.encode("utf-8"))
        cmd = ("$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('%s',[ref]$null,[ref]$e); $e.Count" % str(p))
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True)
        return int((r.stdout or "999").strip().splitlines()[-1])


# The one-time task that RUNS this wrapper is itself named 'CFP Saturday Patch Apply (one-time)'. Without this exclusion the wrapper always found a running CFP task (itself) and waited for ever:
# on 2026-10-16 it waited 18 times, 10:00 to 18:30, and applied nothing. Every other CFP task still blocks the apply.
RUNNER_TASK = "CFP Saturday Patch Apply*"


def running_tasks() -> list[str]:
    cmd = ("Get-ScheduledTask | Where-Object { $_.TaskName -like 'CFP*' -and $_.TaskName -notlike '%s' -and $_.State -eq 'Running' } | ForEach-Object { $_.TaskName }" % RUNNER_TASK)
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True)
    return [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]


def prepare(t: dict, markets: Path, cache: dict):
    """Check one patch against the file's CURRENT in-memory text (so two patches for one file build on each other). Returns (state or None, message)."""
    st = cache.get(t["file"])
    if st is None:
        live = markets / t["file"]
        raw = live.read_bytes()
        text = raw.decode("utf-8").replace("\r\n", "\n")
        if "\r" in text:
            sys.exit(f"STOP {t['name']}: stray CR characters in {t['file']}. Nothing written.")
        st = cache[t["file"]] = {"live": live, "raw": raw, "crlf": b"\r\n" in raw, "text": text, "applied": [], "backup": None}
    if t["present"] in st["text"]:
        return None, f"{t['name']}: already applied ({t['present']!r} is in {t['file']}). Nothing to do."
    patch = (ROOT / "docs" / "control" / "patches" / t["patch"]).read_text(encoding="utf-8").replace("\r\n", "\n")
    try:
        new = apply_unified(st["text"], patch)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"STOP {t['name']}: the patch does not fit the live script ({type(e).__name__}: {e}). Nothing written.")
    added = len(new.splitlines()) - len(st["text"].splitlines())
    if new.count(t["marker"]) != 1 or added != t["delta"]:
        sys.exit(f"STOP {t['name']}: unexpected result (marker count {new.count(t['marker'])}, line delta {added}, expected 1 and {t['delta']}). Nothing written.")
    errs = parse_errors(new)
    if errs != 0:
        sys.exit(f"STOP {t['name']}: the patched script would have {errs} PowerShell parse error(s). Nothing written.")
    st["text"] = new
    st["applied"].append(t)
    st["backup"] = st["backup"] or t["backup"]
    return st, f"{t['name']}: patch fits {t['file']}: +{added} lines, 0 parse errors, {'CRLF' if st['crlf'] else 'LF'} kept"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--markets-dir", default=str(LIVE_MARKETS), help="a copy of the Markets folder for a rehearsal")
    a = ap.parse_args()
    markets = Path(a.markets_dir)
    live_run = markets == LIVE_MARKETS
    print(f"== Saturday patches (ACT-64, ACT-63, ACT-22): {'APPLY' if a.apply else 'DRY RUN (writes nothing)'} on {markets}")
    if live_run:
        busy = running_tasks()
        if busy:
            sys.exit(f"STOP: a CFP task is running right now ({busy}). Run this when none is running. Nothing written.")
        print("no CFP scheduled task is running")
    cache = {}
    for t in TARGETS:
        _st, msg = prepare(t, markets, cache)
        print(" ", msg)
    plans = [st for st in cache.values() if st["applied"]]
    if not plans:
        print("\nNothing to apply: all the patches are already in.")
        return
    if not a.apply:
        print("\nDRY RUN OK: every pending patch fits and parses. Run again with --apply to do it.")
        return
    for st in plans:
        names = ", ".join(t["name"] for t in st["applied"])
        out = (st["text"].replace("\n", "\r\n") if st["crlf"] else st["text"]).encode("utf-8")
        backup = st["live"].with_name(st["backup"])
        if not backup.exists():
            shutil.copy2(st["live"], backup)
        st["live"].write_bytes(out)
        back = st["live"].read_bytes()
        ok = back == out and parse_errors(back.decode("utf-8")) == 0 and all(t["marker"].encode("utf-8") in back for t in st["applied"])
        if not ok:
            shutil.copy2(backup, st["live"])
            sys.exit(f"STOP {names}: the file written did not verify, so the backup was put back. Tell Claude. Nothing is changed.")
        print(f"  {names}: written {len(st['raw'])} -> {len(back)} bytes in {st['live'].name}, read back, parsed (0 errors); backup {backup.name}")
    print("\nDONE. Tell Claude; it re-verifies the files. The Saturday task reads them when it starts.")


if __name__ == "__main__":
    main()
