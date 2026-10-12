"""One-off: add the ACT-67 customer-awards step to the LIVE Markets/run_monthly.ps1.

Uses the repo's own apply_unified() (same one the tests use) with the reviewed patch docs/control/patches/ACT-67-run_monthly.ps1.patch.
Makes its own backup first. Refuses if the step is already there, or if the live file has stray CR characters or does not match the patch context.
To undo: copy run_monthly.ps1.pre-customerawards-20261012 over run_monthly.ps1.
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\matts\cfp-monitor")
LIVE = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets\run_monthly.ps1")
BACKUP = LIVE.with_name("run_monthly.ps1.pre-customerawards-20261012")
PATCH = ROOT / "docs" / "control" / "patches" / "ACT-67-run_monthly.ps1.patch"

sys.path.insert(0, str(ROOT))
from tests.test_shadow_reader_hook import apply_unified  # noqa: E402

raw = LIVE.read_bytes()
if b"STEP 0a1b: CUSTOMER AWARDS" in raw:
    sys.exit("STOP: the customer-awards step is already in run_monthly.ps1. Nothing written.")
crlf = b"\r\n" in raw
text = raw.decode("utf-8").replace("\r\n", "\n")
if "\r" in text:
    sys.exit("STOP: stray CR characters in the live script. Nothing written.")
patch_text = PATCH.read_text(encoding="utf-8").replace("\r\n", "\n")
new = apply_unified(text, patch_text)
added = len(new.splitlines()) - len(text.splitlines())
if new.count("STEP 0a1b: CUSTOMER AWARDS") != 1 or added != 32:
    sys.exit(f"STOP: unexpected result after applying the patch (added {added} lines, expected 32). Nothing written.")
if not BACKUP.exists():
    shutil.copy2(LIVE, BACKUP)
out = (new.replace("\n", "\r\n") if crlf else new).encode("utf-8")
LIVE.write_bytes(out)
print("backup:", BACKUP.name)
print("written:", LIVE.name, len(raw), "->", len(out), "bytes", "(CRLF kept)" if crlf else "(LF)", "| lines added:", added)
