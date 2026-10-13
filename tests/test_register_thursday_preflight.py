"""The operator-run registration script for 'CFP Thursday Pre-flight' (ACT-70): it parses, it builds the same task shape as the Sunday recap and the weekly pages (dev interpreter, dev script, working
directory the dev repo), it supports -WhatIf, it refuses a second registration and an unmerged script, and nothing registers anything while these tests run (only -WhatIf and refusals are executed)."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "experiments" / "act70_rehearsal" / "register_thursday_preflight.ps1"
PS = shutil.which("powershell")
TEXT = SCRIPT.read_text(encoding="utf-8")
needs_ps = pytest.mark.skipif(PS is None or sys.platform != "win32", reason="Windows PowerShell is needed")


def test_the_script_is_plain_ascii_and_registers_in_exactly_one_guarded_place():
    TEXT.encode("ascii")
    assert TEXT.count("Register-ScheduledTask -TaskName") == 1
    assert TEXT.index("ShouldProcess($TaskName") < TEXT.index("Register-ScheduledTask -TaskName"), "registration only inside the ShouldProcess branch (so -WhatIf registers nothing)"
    assert "[CmdletBinding(SupportsShouldProcess = $true)]" in TEXT


def test_the_task_has_the_agreed_name_day_time_and_the_dev_repo_command_like_the_weekly_pages_task():
    assert "[string]$TaskName = 'CFP Thursday Pre-flight'" in TEXT
    assert "-Weekly -DaysOfWeek Thursday -At $At" in TEXT and "[string]$At       = '18:00'" in TEXT
    assert "[string]$Repo     = 'C:\\Users\\matts\\cfp-monitor'" in TEXT
    # the same action shape as 'CFP Weekly Customer Pages': powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '<dev python>' '<dev script>'" with the dev repo as the working directory
    assert "New-ScheduledTaskAction -Execute 'powershell.exe'" in TEXT and "-WorkingDirectory $Repo" in TEXT
    assert "-NoProfile -ExecutionPolicy Bypass -Command `\"& '$py' '$script' --thursday`\"" in TEXT
    assert "$py     = Join-Path $Repo '.venv\\Scripts\\python.exe'" in TEXT and "$script = Join-Path $Repo 'scripts\\release_gate.py'" in TEXT


def test_the_settings_are_the_other_cfp_tasks_and_it_never_wakes_the_computer():
    assert "-StartWhenAvailable" in TEXT and "-MultipleInstances IgnoreNew" in TEXT
    assert "$settings.WakeToRun = $false" in TEXT, "as every other CFP task: WakeToRun is off"
    assert "-LogonType Interactive -RunLevel Limited" in TEXT


def test_it_refuses_a_second_registration_and_an_unmerged_script_before_it_builds_anything():
    i_exists = TEXT.index("Get-ScheduledTask -TaskName $TaskName")
    i_refuse = TEXT.index("REFUSED: a task named")
    i_build = TEXT.index("New-ScheduledTaskAction")
    assert i_exists < i_refuse < i_build
    assert TEXT.index("'--thursday' -Quiet") < i_build


@needs_ps
def test_it_parses_with_the_powershell_parser():
    cmd = ("$e = $null; $t = $null; [void][System.Management.Automation.Language.Parser]::ParseFile('" + str(SCRIPT) + "', [ref]$t, [ref]$e); "
           "if ($e.Count -gt 0) { $e | ForEach-Object { $_.Message }; exit 1 } else { 'PARSE OK' }")
    r = subprocess.run([PS, "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "PARSE OK" in r.stdout, r.stdout + r.stderr


def _fake_repo(tmp_path: Path, merged: bool) -> Path:
    repo = tmp_path / "repo"
    (repo / ".venv" / "Scripts").mkdir(parents=True)
    (repo / ".venv" / "Scripts" / "python.exe").write_bytes(b"")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "release_gate.py").write_text("ap.add_argument('--thursday')\n" if merged else "ap.add_argument('--preflight')\n", encoding="utf-8")
    return repo


def _run(tmp_path, merged, name="CFP Thursday Pre-flight TEST (never registered)", whatif=True):
    args = [PS, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), "-Repo", str(_fake_repo(tmp_path, merged)), "-TaskName", name]
    return subprocess.run(args + (["-WhatIf"] if whatif else []), capture_output=True, text=True, timeout=90)


@needs_ps
def test_whatif_prints_the_exact_task_and_registers_nothing(tmp_path):
    r = _run(tmp_path, merged=True)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert "every Thursday at 18:00" in out and "release_gate.py' --thursday" in out and "WakeToRun OFF" in out
    assert "nothing was registered" in out
    check = subprocess.run([PS, "-NoProfile", "-NonInteractive", "-Command", "Get-ScheduledTask -TaskName 'CFP Thursday Pre-flight TEST (never registered)' -ErrorAction SilentlyContinue | Measure-Object | Select-Object -ExpandProperty Count"],
                           capture_output=True, text=True, timeout=60)
    assert check.stdout.strip() == "0"


@needs_ps
def test_it_refuses_a_script_without_the_thursday_mode(tmp_path):
    r = _run(tmp_path, merged=False, whatif=False)
    assert r.returncode == 2 and "no --thursday mode yet" in (r.stdout + r.stderr)


@needs_ps
def test_it_refuses_a_second_registration_of_an_existing_task(tmp_path):
    # any task that exists will do: the refusal comes before anything is built. Use a Windows built-in.
    existing = subprocess.run([PS, "-NoProfile", "-NonInteractive", "-Command", "(Get-ScheduledTask | Select-Object -First 1).TaskName"], capture_output=True, text=True, timeout=60).stdout.strip()
    if not existing or not re.fullmatch(r"[\w .\-]+", existing):
        pytest.skip("no scheduled task with a plain name to use")
    r = _run(tmp_path, merged=True, name=existing, whatif=False)
    assert r.returncode == 1 and "already registered" in (r.stdout + r.stderr) and "Nothing was changed" in (r.stdout + r.stderr)
