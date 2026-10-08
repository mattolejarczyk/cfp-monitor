"""ACT-58: the reviewer's patch for Markets/run_monthly.ps1 (docs/control/patches/ACT-58-run_monthly.ps1.patch) adds the promise check as a Saturday post-step, after the load and before the recap.
Applied to a COPY of the live script (never the live one); a live script that already carries it is used as is. Nothing is researched, loaded or emailed (-ListPostSteps)."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets\run_monthly.ps1")
PATCH = ROOT / "docs" / "control" / "patches" / "ACT-58-run_monthly.ps1.patch"


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
    return text if "check_commitments.py" in text else apply_unified(text, PATCH.read_text(encoding="utf-8"))


def _list(tmp_path, markets: str) -> str:
    f = tmp_path / "rm.ps1"
    f.write_text(patched_text(), encoding="utf-8")
    p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"& '{f}' -Markets {markets} -ListPostSteps"], capture_output=True, text=True, timeout=120)
    return p.stdout


def test_the_patch_only_adds_lines_and_never_sends_or_applies():
    lines = PATCH.read_text(encoding="utf-8").splitlines()
    assert not [l for l in lines if l.startswith("-") and not l.startswith("---")]
    added = "\n".join(l[1:] for l in lines if l.startswith("+") and not l.startswith("+++"))
    assert "check_commitments.py" in added and "saturday" in added and "--apply" not in added


def test_patched_script_parses(tmp_path):
    f = tmp_path / "rm.ps1"
    f.write_text(patched_text(), encoding="utf-8")
    cmd = (f"$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('{f}',[ref]$null,[ref]$e); "
           "if ($e.Count -eq 0) { 'PARSE OK' } else { $e | ForEach-Object { $_.Message } }")
    out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd], capture_output=True, text=True, timeout=120).stdout
    assert "PARSE OK" in out, out


def test_saturday_checks_the_promises_after_the_load_qa_and_before_the_recap(tmp_path):
    out = _list(tmp_path, "'Cybersecurity','Utility'")
    i_qa, i_cc, i_recap = out.index("post_load_qa.py"), out.index("check_commitments.py"), out.index("weekend_recap.py")
    assert i_qa < i_cc < i_recap
    assert "check_commitments.py" in out.splitlines()[[n for n, l in enumerate(out.splitlines()) if "check_commitments.py" in l][0]]


def test_friday_awards_run_does_not_get_the_step(tmp_path):
    assert "check_commitments.py" not in _list(tmp_path, "'Awards'")
