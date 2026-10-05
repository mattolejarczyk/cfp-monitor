"""ACT-20: the reviewer's patch for Markets/run_monthly.ps1 (docs/control/patches/ACT-20-run_monthly.ps1.patch) adds the shadow reader to Saturday's steps.
The patch is applied to a COPY of the live script (never to the live one), $cfpDir is pointed at this worktree's scripts, and the real step builder is run with -ListPostSteps.
If the live script already carries the step (the patch was applied), the copy is just the live script."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets\run_monthly.ps1")
PATCH = ROOT / "docs" / "control" / "patches" / "ACT-20-run_monthly.ps1.patch"
LIVE_CFP = r"C:\Users\matts\cfp-monitor\scripts"


def _patched_copy(tmp_path: Path) -> Path:
    text = LIVE.read_text(encoding="utf-8")
    if "shadow_reader.py" not in text:
        lines = PATCH.read_text(encoding="utf-8").splitlines()
        added = [l[1:] for l in lines if l.startswith("+") and not l.startswith("+++")]
        context = next(l[1:] for l in lines if l.startswith(" ") and "weekend_recap.py" in l)       # the line the block goes right after
        assert text.count(context) == 1, "the patch's anchor line is not unique in the live script: regenerate the patch"
        text = text.replace(context, context + "\n" + "\n".join(added))
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
    assert names == ["weekend_import.py", "post_load_qa.py", "weekend_recap.py", "shadow_reader.py", "shadow_finder.py"]
    rd = steps[3]
    assert rd[1:4] == ["--markets", "Cybersecurity", "Utility"] and rd[-4:-2] == ["--max-minutes", "45"] and rd[-2] == "--run-log"
    assert all(len(tok) > 1 or tok.isdigit() for s in steps for tok in s), "flattened or malformed step"


def test_friday_awards_and_prospect_markets_do_not_get_the_shadow_reader(tmp_path):
    ps1 = _patched_copy(tmp_path)
    assert [Path(s[0]).name for s in _list(ps1, "'Awards'")] == ["weekend_import.py", "post_load_qa.py", "weekend_recap.py"]
    out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"& '{ps1}' -Markets 'Robotics' -ListPostSteps"], capture_output=True, text=True, timeout=120).stdout
    assert "STEPS: 0" in out


def test_the_patch_adds_only_the_one_block_and_touches_nothing_else():
    lines = PATCH.read_text(encoding="utf-8").splitlines()
    assert not [l for l in lines if l.startswith("-") and not l.startswith("---")]                    # nothing removed
    added = [l for l in lines if l.startswith("+") and not l.startswith("+++")]
    assert 4 <= len(added) <= 8 and any("shadow_reader.py" in l for l in added) and any("saturday" in l for l in added)
    assert re.search(r'--max-minutes", "45"', "\n".join(added))
