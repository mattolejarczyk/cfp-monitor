"""ACT-20 and ACT-22: the reviewer's patches for Markets/run_monthly.ps1 (docs/control/patches/ACT-20-run_monthly.ps1.patch, then ACT-22-run_monthly.ps1.patch, applied in that order) add the shadow
reader (Saturday) and the awards shadow run (Friday) to the post-research steps. The patches are applied to a COPY of the live script (never to the live one), $cfpDir is pointed at this worktree's
scripts, and the real step builder is run with -ListPostSteps. A patch whose block the live script already carries (the reviewer applied it) is skipped."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets\run_monthly.ps1")
P20 = ROOT / "docs" / "control" / "patches" / "ACT-20-run_monthly.ps1.patch"
P22 = ROOT / "docs" / "control" / "patches" / "ACT-22-run_monthly.ps1.patch"
LIVE_CFP = r"C:\Users\matts\cfp-monitor\scripts"


def apply_unified(text: str, patch: str) -> str:
    """Apply every hunk of a unified diff by exact match of its context and removed lines (which must be unique in the text)."""
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


def _patched_copy(tmp_path: Path) -> Path:
    text = LIVE.read_text(encoding="utf-8")
    if "shadow_reader.py" not in text:
        text = apply_unified(text, P20.read_text(encoding="utf-8"))
    if '"--markets", "Awards", "--max-minutes"' not in text:
        text = apply_unified(text, P22.read_text(encoding="utf-8"))
    text = text.replace(LIVE_CFP, str(ROOT / "scripts"))
    out = tmp_path / "run_monthly_patched.ps1"
    out.write_text(text, encoding="utf-8")
    return out


def _list(ps1: Path, markets: str):
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"& '{ps1}' -Markets {markets} -ListPostSteps"]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout
    steps = [line.split(": ", 1)[1].split(" | ") for line in out.splitlines() if line.startswith("STEP ")]
    assert f"STEPS: {len(steps)}" in out, out
    for line in out.splitlines():
        if line.startswith("STEP "):
            assert "[found]" in line, f"a step's script is missing: {line}"
    return steps


def test_saturday_lists_the_shadow_reader_before_the_finder_with_its_caps(tmp_path):
    steps = _list(_patched_copy(tmp_path), "'Cybersecurity','Utility'")
    names = [Path(s[0]).name for s in steps]
    assert names == ["weekend_import.py", "post_load_qa.py", "check_commitments.py", "weekend_recap.py", "shadow_reader.py", "shadow_finder.py", "luna_shadow.py"]   # check_commitments: ACT-58, applied live 2026-10-09   # luna: ACT-61, applied live 2026-10-06
    rd = steps[names.index("shadow_reader.py")]
    assert rd[1:4] == ["--markets", "Cybersecurity", "Utility"] and rd[-4:-2] == ["--max-minutes", "45"] and rd[-2] == "--run-log"
    assert "Awards" not in steps[names.index("shadow_finder.py")]                                                                  # Saturday's finder is the conference one
    assert all(len(tok) > 1 or tok.isdigit() for s in steps for tok in s), "flattened or malformed step"


def test_friday_lists_the_awards_shadow_run_last_with_its_caps(tmp_path):
    steps = _list(_patched_copy(tmp_path), "'Awards'")
    assert [Path(s[0]).name for s in steps] == ["weekend_import.py", "post_load_qa.py", "weekend_recap.py", "shadow_finder.py"]
    sh = steps[3]
    assert sh[1:3] == ["--markets", "Awards"] and "--max-minutes" in sh and sh[sh.index("--max-minutes") + 1] == "45" and sh[sh.index("--max-usd") + 1] == "0.30"
    assert sh[sh.index("--total-hours") + 1] == "14" and sh[-2] == "--run-log"
    assert all(len(tok) > 1 or tok.isdigit() for tok in sh)


def test_prospect_markets_get_no_shadow_step(tmp_path):
    ps1 = _patched_copy(tmp_path)
    out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"& '{ps1}' -Markets 'Robotics' -ListPostSteps"], capture_output=True, text=True, timeout=120).stdout
    assert "STEPS: 0" in out


def test_the_patches_only_add_lines():
    for p in (P20, P22):
        lines = p.read_text(encoding="utf-8").splitlines()
        assert not [l for l in lines if l.startswith("-") and not l.startswith("---")], f"{p.name} removes something"
        added = [l for l in lines if l.startswith("+") and not l.startswith("+++")]
        assert 4 <= len(added) <= 10 and any("shadow_" in l for l in added)
    assert re.search(r'--max-minutes", "45"', P20.read_text(encoding="utf-8")) and "saturday" in P20.read_text(encoding="utf-8")
    assert "'friday'" in P22.read_text(encoding="utf-8")
