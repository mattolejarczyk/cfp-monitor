"""ACT-33: the reviewer's patch for Markets/run_monthly.ps1 (docs/control/patches/ACT-33-run_monthly.ps1.patch) runs scripts/refresh_plan.py for Cybersecurity and Utility BEFORE the canary and the
research, on the Saturday run only, as a DRY RUN unless the environment variable CFP_REFRESH_APPLY is 1. Applied to a COPY of the live script, never the live one; a live script that already carries
the block (the reviewer applied it) is used as is."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_customer_coverage_hook import LIVE, LIVE_CFP, apply_unified, ps   # noqa: E402

PATCH = ROOT / "docs" / "control" / "patches" / "ACT-33-run_monthly.ps1.patch"


def patched_text() -> str:
    text = LIVE.read_text(encoding="utf-8").replace("\r\n", "\n")
    return text if "STEP 0a3: CONFERENCE REFRESH PLAN" in text else apply_unified(text, PATCH.read_text(encoding="utf-8"))


def _added() -> str:
    return "\n".join(l[1:] for l in PATCH.read_text(encoding="utf-8").splitlines() if l.startswith("+") and not l.startswith("+++"))


def test_patch_only_adds_lines_and_applies_only_when_the_environment_switch_is_on():
    lines = PATCH.read_text(encoding="utf-8").splitlines()
    assert not [l for l in lines if l.startswith("-") and not l.startswith("---")]
    added = _added()
    assert "refresh_plan.py" in added and "REFRESH-PLAN" in added and "-not $WhatIf" in added
    assert "CFP_REFRESH_APPLY -eq '1'" in added, "marking is a switch, off by default"
    assert added.count("'--apply'") == 1 and "$rfArgs = @()" in added
    assert "--clear" not in "
".join(l for l in added.splitlines() if not l.lstrip().startswith("#"))      # the fallback is plain PowerShell; --clear is the operator's command


def test_the_step_is_for_the_saturday_run_only_never_the_friday_awards_run():
    added = _added()
    assert "$liveMarkets.Count -gt 0 -and $Markets -notcontains 'Awards'" in added
    t = patched_text()
    assert t.count("--market Awards --apply") == 1               # the awards step is the one it was


def test_patched_script_runs_the_plan_after_the_awards_plan_and_the_stamping_and_before_the_canary_and_the_archive():
    t = patched_text()
    i_stamp, i_awards, i_conf, i_canary = t.index("STEP 0a: PERMANENT IDS"), t.index("STEP 0a2: AWARDS REFRESH PLAN"), t.index("STEP 0a3: CONFERENCE REFRESH PLAN"), t.index("STEP 0b: CANARY")
    assert i_stamp < i_awards < i_conf < i_canary < t.index("Archive the previous cycle")
    assert t.count("STEP 0a3: CONFERENCE REFRESH PLAN") == 1


def test_patched_script_still_parses_with_no_errors(tmp_path):
    f = tmp_path / "rm.ps1"
    f.write_text(patched_text(), encoding="utf-8")
    cmd = (f"$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('{f}',[ref]$null,[ref]$e); "
           "if ($e.Count -eq 0) { 'PARSE OK' } else { $e | ForEach-Object { $_.Message } }")
    assert "PARSE OK" in ps(["-Command", cmd]).stdout


STUB = "import sys\nprint('REFRESH-PLAN stub: args=' + ' '.join(sys.argv[1:]))\n"


def _run_block(tmp_path, markets: str, py: str, script: str, apply_env: str = "", what_if: bool = False, input_marked: bool = False):
    body = _added().replace(LIVE_CFP + r"\.venv\Scripts\python.exe", py).replace(LIVE_CFP + r"\scripts\refresh_plan.py", script)
    f = tmp_path / "block.ps1"
    for m in ("Cybersecurity", "Utility"):
        (tmp_path / f"{m}_input.csv").write_text('"CONFERENCE","REFRESH_SKIP"\n"A","G2 dormant"\n"B",""\n' if input_marked else '"CONFERENCE"\n"A"\n', encoding="utf-8")
    env_line = f"$env:CFP_REFRESH_APPLY = '{apply_env}'\n" if apply_env else "Remove-Item Env:CFP_REFRESH_APPLY -ErrorAction SilentlyContinue\n"
    f.write_text(f"$Markets = @({markets}); $liveMarkets = @($Markets | Where-Object {{ $_ -in @('Cybersecurity','Utility') }}); $WhatIf = ${str(what_if).lower()}\n{env_line}" + body + "\nWrite-Host 'AFTER-BLOCK'\n", encoding="utf-8")
    return ps(["-File", str(f)])


def test_saturday_run_plans_each_live_market_as_a_dry_run_by_default_and_applies_only_with_the_switch(tmp_path):
    stub = tmp_path / "stub.py"
    stub.write_text(STUB, encoding="utf-8")
    out = _run_block(tmp_path, "'Cybersecurity','Utility'", sys.executable, str(stub)).stdout
    assert "REFRESH-PLAN stub: args=--market Cybersecurity" in out and "REFRESH-PLAN stub: args=--market Utility" in out
    assert "--apply" not in out and out.index("--market Cybersecurity") < out.index("--market Utility")
    out = _run_block(tmp_path, "'Cybersecurity','Utility'", sys.executable, str(stub), apply_env="1").stdout
    assert "args=--market Cybersecurity --apply" in out and "args=--market Utility --apply" in out
    out = _run_block(tmp_path, "'Cybersecurity','Utility'", sys.executable, str(stub), apply_env="0").stdout
    assert "--apply" not in out and "REFRESH-PLAN stub" in out                              # anything but 1 is a dry run


def test_only_the_saturday_run_gets_it(tmp_path):
    stub = tmp_path / "stub.py"
    stub.write_text(STUB, encoding="utf-8")
    for markets, what_if in (("'Awards'", False), ("'Awards','Cybersecurity'", False), ("'Robotics'", False), ("'Cybersecurity'", True)):
        out = _run_block(tmp_path, markets, sys.executable, str(stub), apply_env="1", what_if=what_if).stdout
        assert "REFRESH-PLAN" not in out and "AFTER-BLOCK" in out, (markets, what_if)


def test_a_planner_fault_never_stops_the_research_and_a_dry_run_never_clears_anything(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("import sys\nprint('boom')\nsys.exit(7)\n", encoding="utf-8")
    p = _run_block(tmp_path, "'Cybersecurity'", sys.executable, str(bad), input_marked=True)
    assert "AFTER-BLOCK" in p.stdout and p.returncode == 0
    assert "G2 dormant" in (tmp_path / "Cybersecurity_input.csv").read_text(encoding="utf-8")      # switch off: the input list is not touched, even when the planner failed
    p = _run_block(tmp_path, "'Cybersecurity'", str(tmp_path / "no-such-python.exe"), str(bad))
    assert "REFRESH-PLAN Cybersecurity: UNKNOWN - interpreter or script not found" in p.stdout and "AFTER-BLOCK" in p.stdout


def test_with_the_switch_on_a_planner_that_cannot_start_clears_the_previous_marks_in_plain_powershell(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("import sys\nprint('boom')\nsys.exit(7)\n", encoding="utf-8")
    p = _run_block(tmp_path, "'Cybersecurity','Utility'", sys.executable, str(bad), apply_env="1", input_marked=True)
    assert "AFTER-BLOCK" in p.stdout and "previous marks were cleared" in p.stdout
    for m in ("Cybersecurity", "Utility"):
        text = (tmp_path / f"{m}_input.csv").read_text(encoding="utf-8-sig")
        assert "G2 dormant" not in text and '"A"' in text and '"B"' in text and "REFRESH_SKIP" in text      # rows and columns intact, marks gone
    # a planner that ran and printed its own REFRESH-PLAN line (even UNKNOWN: it cleared the marks itself) is not second-guessed
    ok = tmp_path / "ok.py"
    ok.write_text("print('REFRESH-PLAN Cybersecurity: UNKNOWN - x; nothing skipped')\n", encoding="utf-8")
    p = _run_block(tmp_path, "'Cybersecurity'", sys.executable, str(ok), apply_env="1", input_marked=True)
    assert "previous marks were cleared" not in p.stdout and "G2 dormant" in (tmp_path / "Cybersecurity_input.csv").read_text(encoding="utf-8")
