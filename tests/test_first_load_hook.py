"""ACT-63: the reviewer's patch for Markets/run_monthly.ps1 (docs/control/patches/ACT-63-run_monthly.ps1.patch) switches the first load of new events ON for the Saturday import (weekend_import.py --new-events).
Applied to a COPY of the live script (never the live one); a live script that already carries it is used as is. Nothing is researched, loaded or emailed (-ListPostSteps).
Until the reviewer applies the patch, the live script must NOT carry the flag (the path is default OFF)."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets\run_monthly.ps1")
PATCH = ROOT / "docs" / "control" / "patches" / "ACT-63-run_monthly.ps1.patch"


def apply_unified(text: str, patch: str) -> str:
    hunks, cur = [], None
    for line in patch.splitlines():
        if line.startswith("@@"):
            cur = []
            hunks.append(cur)
        elif cur is not None and line[:1] in (" ", "+", "-") and not line.startswith(("+++", "---")):
            cur.append(line)
    for h in hunks:
        old = "\n".join(l[1:] for l in h if l[0] in " -")
        new = "\n".join(l[1:] for l in h if l[0] in " +")
        assert text.count(old) == 1, "a hunk's context is not unique in the live script: regenerate the patch"
        text = text.replace(old, new)
    return text


def patched_text() -> str:
    text = LIVE.read_text(encoding="utf-8").replace("\r\n", "\n")
    return text if "--new-events" in text else apply_unified(text, PATCH.read_text(encoding="utf-8"))


def _list(tmp_path, markets: str) -> str:
    f = tmp_path / "rm.ps1"
    f.write_text(patched_text(), encoding="utf-8")
    p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"& '{f}' -Markets {markets} -ListPostSteps"], capture_output=True, text=True, timeout=120)
    return p.stdout


def test_the_patch_changes_one_line_and_only_adds_the_flag():
    lines = PATCH.read_text(encoding="utf-8").splitlines()
    removed = [l for l in lines if l.startswith("-") and not l.startswith("---")]
    assert len(removed) == 1 and "weekend_import.py" in removed[0]
    added = "\n".join(l[1:] for l in lines if l.startswith("+") and not l.startswith("+++"))
    assert "--new-events" in added and "saturday" in added and "--apply" not in added


def test_patched_script_parses(tmp_path):
    f = tmp_path / "rm.ps1"
    f.write_text(patched_text(), encoding="utf-8")
    cmd = (f"$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('{f}',[ref]$null,[ref]$e); "
           "if ($e.Count -eq 0) { 'PARSE OK' } else { $e | ForEach-Object { $_.Message } }")
    out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd], capture_output=True, text=True, timeout=120).stdout
    assert "PARSE OK" in out, out


def test_saturday_import_gets_the_flag_after_the_report_argument(tmp_path):
    out = _list(tmp_path, "'Cybersecurity','Utility'")
    line = [l for l in out.splitlines() if "weekend_import.py" in l][0]
    assert "--new-events" in line and line.index("--report") < line.index("--new-events")


def test_friday_awards_import_does_not_get_the_flag(tmp_path):
    line = [l for l in _list(tmp_path, "'Awards'").splitlines() if "weekend_import.py" in l][0]
    assert "--new-events" not in line
