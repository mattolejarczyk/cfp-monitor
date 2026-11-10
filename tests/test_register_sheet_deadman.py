"""The operator-run registration of 'CFP Sheet Load Check' (the customer sheet dead-man check, 2026-11-09) and patch ACT-73.

Nothing is registered while these tests run: only -WhatIf is executed. The patch is only read here; applying it was proven on a copy of the
Markets scripts with agentos tools\apply-markets-patches.ps1 -Patches ACT-73-run_monthly.ps1.patch (dry run, apply, second run, parse)."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import release_gate as rg                                     # noqa: E402

SCRIPT = ROOT / "scripts" / "register_sheet_deadman.ps1"
TEXT = SCRIPT.read_text(encoding="utf-8")
PATCH = ROOT / "docs" / "control" / "patches" / "ACT-73-run_monthly.ps1.patch"
PS = shutil.which("powershell")
needs_ps = pytest.mark.skipif(PS is None or sys.platform != "win32", reason="Windows PowerShell is needed")


def test_the_script_is_ascii_and_registers_only_inside_should_process():
    TEXT.encode("ascii")
    assert TEXT.count("Register-ScheduledTask -TaskName") == 1
    assert TEXT.index("ShouldProcess($TaskName") < TEXT.index("Register-ScheduledTask -TaskName")
    assert "[CmdletBinding(SupportsShouldProcess = $true)]" in TEXT


def test_the_task_runs_the_deadman_check_friday_and_saturday_at_0300_and_wakes_the_pc():
    assert "[string]$TaskName = 'CFP Sheet Load Check'" in TEXT and "[string]$At       = '03:00'" in TEXT
    assert "-Weekly -DaysOfWeek Friday, Saturday -At $At" in TEXT
    assert "--deadman auto" in TEXT and "scripts\\customer_sheet_load.py" in TEXT
    assert "$settings.WakeToRun = $true" in TEXT, "the one difference from the other CFP tasks, on purpose: a sleeping PC must wake for it"
    assert "-StartWhenAvailable" in TEXT and "-MultipleInstances IgnoreNew" in TEXT and "-LogonType Interactive -RunLevel Limited" in TEXT


def test_it_refuses_a_second_registration():
    assert "REFUSED: a task named '$TaskName' is already registered" in TEXT


@needs_ps
def test_whatif_registers_nothing():
    before = subprocess.run([PS, "-NoProfile", "-Command", "[bool](Get-ScheduledTask -TaskName 'CFP Sheet Load Check' -ErrorAction SilentlyContinue)"],
                            capture_output=True, text=True).stdout.strip()
    out = subprocess.run([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), "-WhatIf"], capture_output=True, text=True)
    if "REFUSED: a task named" in out.stdout:
        pytest.skip("the task is already registered on this PC")
    assert out.returncode == 0 and "(-WhatIf: nothing was registered.)" in out.stdout and "--deadman auto" in out.stdout
    after = subprocess.run([PS, "-NoProfile", "-Command", "[bool](Get-ScheduledTask -TaskName 'CFP Sheet Load Check' -ErrorAction SilentlyContinue)"],
                           capture_output=True, text=True).stdout.strip()
    assert before == after


# ------------------------------------------------------------------ patch ACT-73
PATCH_TEXT = PATCH.read_text(encoding="utf-8")
def test_act73_is_plain_ascii_lf_and_names_no_customer_detail():
    PATCH_TEXT.encode("ascii")
    assert "\r" not in PATCH.read_bytes().decode("ascii")
    assert not re.search(r"docs\.google\.com|spreadsheets/d/|[\w.-]+@[\w-]+\.\w+", PATCH_TEXT)


def test_act73_adds_the_guarded_awards_load_and_the_hold_exit_in_both_places():
    added = [ln[1:] for ln in PATCH_TEXT.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    removed = [ln[1:] for ln in PATCH_TEXT.splitlines() if ln.startswith("-") and not ln.startswith("---")]
    assert sum("if ($LASTEXITCODE -eq 6)" in a and "exit 6" in a for a in added) == 2
    assert any("--clients 'arnica-awards,utility-awards' --context friday" in a for a in added)
    assert any("foreach ($awClient" in r for r in removed), "the old unguarded per-sheet fetch is replaced"
    assert not any(re.search(r"STEP\s+\w+:", a) for a in added), "no STEP marker: the pre-flight recognises it by its added line"


def test_the_thursday_preflight_recognises_act73_by_its_added_line():
    sig = rg.patch_signature(PATCH_TEXT)
    assert sig["kind"] == "line" and sig["target"] == "run_monthly.ps1" and "RESEARCH HELD (ACT-73)" in sig["line"]
