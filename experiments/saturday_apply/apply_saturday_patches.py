"""One command for the two Saturday patches (ACT-64 sponsor prefill, ACT-63 new events): checks, backs up, applies, proves the result, restores on any doubt.

    python experiments\\saturday_apply\\apply_saturday_patches.py            DRY RUN: does every check on the live files in memory, writes nothing
    python experiments\\saturday_apply\\apply_saturday_patches.py --apply    does it

What each patch is (reviewed patches in docs/control/patches/):
  ACT-64  Markets\\run_overnight.ps1  +3 lines  copies last week's settled sponsorship answer into the new research file before the sponsor pass (saves about 35 USD a week).
  ACT-63  Markets\\run_monthly.ps1    +4/-1 lines  lets Saturday's import load a brand-new event itself when upstream has given its id (Saturday only).
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
]


def parse_errors(text: str) -> int:
    """Number of PowerShell parse errors in `text` (Windows PowerShell 5.1's own parser)."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "check.ps1"
        p.write_bytes(text.encode("utf-8"))
        cmd = ("$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('%s',[ref]$null,[ref]$e); $e.Count" % str(p))
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True)
        return int((r.stdout or "999").strip().splitlines()[-1])


def running_tasks() -> list[str]:
    cmd = "Get-ScheduledTask | Where-Object { $_.TaskName -like 'CFP*' -and $_.State -eq 'Running' } | ForEach-Object { $_.TaskName }"
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True)
    return [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]


def prepare(t: dict, markets: Path):
    live = markets / t["file"]
    raw = live.read_bytes()
    if t["present"].encode("utf-8") in raw:
        return None, f"{t['name']}: already applied ({t['present']!r} is in {t['file']}). Nothing to do."
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if "\r" in text:
        sys.exit(f"STOP {t['name']}: stray CR characters in {t['file']}. Nothing written.")
    patch = (ROOT / "docs" / "control" / "patches" / t["patch"]).read_text(encoding="utf-8").replace("\r\n", "\n")
    try:
        new = apply_unified(text, patch)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"STOP {t['name']}: the patch does not fit the live script ({type(e).__name__}: {e}). Nothing written.")
    added = len(new.splitlines()) - len(text.splitlines())
    if new.count(t["marker"]) != 1 or added != t["delta"]:
        sys.exit(f"STOP {t['name']}: unexpected result (marker count {new.count(t['marker'])}, line delta {added}, expected 1 and {t['delta']}). Nothing written.")
    errs = parse_errors(new)
    if errs != 0:
        sys.exit(f"STOP {t['name']}: the patched script would have {errs} PowerShell parse error(s). Nothing written.")
    out = (new.replace("\n", "\r\n") if crlf else new).encode("utf-8")
    return {"live": live, "raw": raw, "out": out, "added": added, "crlf": crlf}, f"{t['name']}: patch fits {t['file']}: +{added} lines, 0 parse errors, {'CRLF' if crlf else 'LF'} kept"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--markets-dir", default=str(LIVE_MARKETS), help="a copy of the Markets folder for a rehearsal")
    a = ap.parse_args()
    markets = Path(a.markets_dir)
    live_run = markets == LIVE_MARKETS
    print(f"== Saturday patches (ACT-64, ACT-63): {'APPLY' if a.apply else 'DRY RUN (writes nothing)'} on {markets}")
    if live_run:
        busy = running_tasks()
        if busy:
            sys.exit(f"STOP: a CFP task is running right now ({busy}). Run this when none is running. Nothing written.")
        print("no CFP scheduled task is running")
    plans = []
    for t in TARGETS:
        plan, msg = prepare(t, markets)
        print(" ", msg)
        if plan:
            plans.append((t, plan))
    if not plans:
        print("\nNothing to apply: both patches are already in.")
        return
    if not a.apply:
        print("\nDRY RUN OK: both patches fit and parse. Run again with --apply to do it.")
        return
    for t, p in plans:
        backup = p["live"].with_name(t["backup"])
        if not backup.exists():
            shutil.copy2(p["live"], backup)
        p["live"].write_bytes(p["out"])
        back = p["live"].read_bytes()
        ok = back == p["out"] and parse_errors(back.decode("utf-8")) == 0 and t["marker"].encode("utf-8") in back
        if not ok:
            shutil.copy2(backup, p["live"])
            sys.exit(f"STOP {t['name']}: the file written did not verify, so the backup was put back. Tell Claude. Nothing is changed.")
        print(f"  {t['name']}: written {len(p['raw'])} -> {len(back)} bytes, read back, parsed (0 errors); backup {backup.name}")
    print("\nDONE. Tell Claude; it re-verifies both files. The Saturday task reads them when it starts.")


if __name__ == "__main__":
    main()
