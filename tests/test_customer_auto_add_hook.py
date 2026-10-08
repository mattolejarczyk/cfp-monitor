"""ACT-51 phase 2: the reviewer's patch for Markets/run_monthly.ps1 (docs/control/patches/ACT-51-phase2-run_monthly.ps1.patch) runs scripts/customer_auto_add.py after the coverage check and
BEFORE the stamping and the research, dry-run unless CFP_AUTOADD_APPLY=1. Applied to a COPY of the live script, never the live one; skipped if the live script already carries the block."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_customer_coverage_hook import LIVE, LIVE_CFP, apply_unified, ps   # noqa: E402

PATCH = ROOT / "docs" / "control" / "patches" / "ACT-51-phase2-run_monthly.ps1.patch"
PHASE1 = ROOT / "docs" / "control" / "patches" / "ACT-51-run_monthly.ps1.patch"


def patched_text() -> str:
    text = LIVE.read_text(encoding="utf-8").replace("\r\n", "\n")
    if "customer_coverage.py" not in text:
        text = apply_unified(text, PHASE1.read_text(encoding="utf-8"))
    if "customer_auto_add.py" not in text:
        text = apply_unified(text, PATCH.read_text(encoding="utf-8"))
    return text


def _added() -> str:
    return "\n".join(l[1:] for l in PATCH.read_text(encoding="utf-8").splitlines() if l.startswith("+") and not l.startswith("+++"))


def test_patch_only_adds_lines_and_applies_only_when_apply_is_switched_on_by_the_environment():
    lines = PATCH.read_text(encoding="utf-8").splitlines()
    assert not [l for l in lines if l.startswith("-") and not l.startswith("---")]
    added = _added()
    assert "customer_auto_add.py" in added and "AUTOADD: UNKNOWN" in added and "-not $WhatIf" in added
    assert "CFP_AUTOADD_APPLY -eq '1'" in added, "applying is a switch, off by default"
    assert added.count("--apply") == 1 and "$aaArgs = @()" in added


def test_patched_script_runs_the_add_step_after_the_coverage_check_and_before_stamping_and_research():
    t = patched_text()
    i_cov, i_add, i_stamp = t.index("customer_coverage.py"), t.index("customer_auto_add.py"), t.index("STEP 0a: PERMANENT IDS")
    assert i_cov < i_add < i_stamp < t.index("STEP 0b: CANARY") < t.index("Archive the previous cycle")


def test_patched_script_still_parses_with_no_errors(tmp_path):
    f = tmp_path / "rm.ps1"
    f.write_text(patched_text(), encoding="utf-8")
    cmd = (f"$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('{f}',[ref]$null,[ref]$e); "
           "if ($e.Count -eq 0) { 'PARSE OK' } else { $e | ForEach-Object { $_.Message } }")
    assert "PARSE OK" in ps(["-Command", cmd]).stdout


def _run_block(tmp_path, py: str, script: str, apply_env: str = "", what_if: bool = False):
    body = _added().replace(LIVE_CFP + r"\.venv\Scripts\python.exe", py).replace(LIVE_CFP + r"\scripts\customer_auto_add.py", script)
    f = tmp_path / "block.ps1"
    env_line = f"$env:CFP_AUTOADD_APPLY = '{apply_env}'\n" if apply_env else "Remove-Item Env:CFP_AUTOADD_APPLY -ErrorAction SilentlyContinue\n"
    f.write_text(f"$liveMarkets = @('Utility'); $WhatIf = ${str(what_if).lower()}\n{env_line}" + body + "\nWrite-Host 'AFTER-BLOCK'\n", encoding="utf-8")
    return ps(["-File", str(f)])


def test_block_is_dry_run_by_default_and_passes_only_with_the_switch(tmp_path):
    stub = tmp_path / "stub.py"
    stub.write_text("import sys\nprint('AUTOADD: args=' + ','.join(sys.argv[1:]))\n", encoding="utf-8")
    assert "AUTOADD: args=" in _run_block(tmp_path, sys.executable, str(stub)).stdout
    assert "--apply" not in _run_block(tmp_path, sys.executable, str(stub)).stdout
    assert "AUTOADD: args=--apply,--live" in _run_block(tmp_path, sys.executable, str(stub), apply_env="1").stdout
    assert "AUTOADD: args" not in _run_block(tmp_path, sys.executable, str(stub), what_if=True).stdout


def test_block_can_never_stop_the_research(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("import sys\nprint('boom')\nsys.exit(7)\n", encoding="utf-8")
    p = _run_block(tmp_path, sys.executable, str(bad))
    assert "AFTER-BLOCK" in p.stdout and p.returncode == 0
    p = _run_block(tmp_path, str(tmp_path / "no-such-python.exe"), str(bad))
    assert "AUTOADD: UNKNOWN - interpreter or script not found" in p.stdout and "AFTER-BLOCK" in p.stdout
