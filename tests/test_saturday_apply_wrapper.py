"""The Saturday patches wrapper (experiments/saturday_apply/apply_saturday_patches.py): ACT-64, ACT-63 and ACT-22 together on a COPY of the live Markets scripts. Two patches go into
run_monthly.ps1 and both must be there afterwards (the second must not overwrite the first), the files must parse, a second run must say everything is already in, and a dry run must write
nothing. The live folder is only READ (copied); skipped when the live scripts are not on this machine."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "experiments" / "saturday_apply" / "apply_saturday_patches.py"
LIVE = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
pytestmark = pytest.mark.skipif(not (LIVE / "run_monthly.ps1").exists() or not (LIVE / "run_overnight.ps1").exists(), reason="the live Markets scripts are not on this machine")


def copy_markets(tmp_path: Path) -> Path:
    d = tmp_path / "Markets"
    d.mkdir()
    for n in ("run_monthly.ps1", "run_overnight.ps1"):
        shutil.copy2(LIVE / n, d / n)
    return d


def run(d: Path, apply: bool):
    r = subprocess.run([sys.executable, str(WRAPPER), "--markets-dir", str(d)] + (["--apply"] if apply else []), capture_output=True, text=True, encoding="utf-8")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def test_a_dry_run_writes_nothing(tmp_path):
    d = copy_markets(tmp_path)
    before = {n: (d / n).read_bytes() for n in ("run_monthly.ps1", "run_overnight.ps1")}
    code, out = run(d, False)
    if "already applied" in out and "ACT-22: patch fits" not in out:
        pytest.skip("the live scripts already have the patches")
    assert code == 0 and "DRY RUN OK" in out
    assert {n: (d / n).read_bytes() for n in before} == before
    assert sorted(p.name for p in d.iterdir()) == ["run_monthly.ps1", "run_overnight.ps1"]


def test_all_three_patches_land_both_in_one_file_and_a_second_run_is_a_no_op(tmp_path):
    d = copy_markets(tmp_path)
    live_now = (d / "run_monthly.ps1").read_text(encoding="utf-8")
    if "(ACT-22): AWARDS SHADOW RUN" in live_now:
        pytest.skip("the live scripts already have the patches")
    code, out = run(d, True)
    assert code == 0 and "DONE." in out, out
    monthly = (d / "run_monthly.ps1").read_text(encoding="utf-8")
    assert "(ACT-22): AWARDS SHADOW RUN" in monthly and "$newEvents = if ($kind -eq 'saturday')" in monthly, "both patches for run_monthly.ps1 are in, the second did not overwrite the first"
    assert "sponsor_prefill.py" in (d / "run_overnight.ps1").read_text(encoding="utf-8")
    assert len(list(d.glob("run_monthly.ps1.pre-*"))) == 1 and len(list(d.glob("run_overnight.ps1.pre-*"))) == 1
    backup = next(d.glob("run_monthly.ps1.pre-*")).read_text(encoding="utf-8")
    assert backup == live_now, "the backup is the script as it was before any patch"
    code2, out2 = run(d, True)
    assert code2 == 0 and "Nothing to apply" in out2


def test_the_apply_task_does_not_count_itself_as_a_running_cfp_task(monkeypatch):
    """2026-10-16: the one-time task that runs the wrapper is named 'CFP Saturday Patch Apply (one-time)'; the wrapper's 'is a CFP task running?' check saw that task (itself) Running and waited 18 times
    without ever applying. The check must leave the runner out and keep blocking on every other CFP task."""
    sys.path.insert(0, str(WRAPPER.parent))
    import apply_saturday_patches as w
    seen = []

    class R:
        stdout = "CFP Weekly Awards Research\n"

    def fake_run(cmd, **kw):
        seen.append(cmd[-1])
        return R()

    monkeypatch.setattr(w.subprocess, "run", fake_run)
    assert w.running_tasks() == ["CFP Weekly Awards Research"], "another running CFP task still blocks"
    assert "-notlike 'CFP Saturday Patch Apply*'" in seen[0] and "-like 'CFP*'" in seen[0]
