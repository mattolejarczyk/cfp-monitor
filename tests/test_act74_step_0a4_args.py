"""Regression for Friday 2026-11-13: step 0a4 of run_monthly.ps1 crashed and the research ran with no customer context.

ROOT CAUSE. `$ccArgs = if (...) { @('--apply') } else { @('--clear') }` : PowerShell unwraps a ONE-element array returned by an
if-expression into a plain string, and splatting a string passes its characters one at a time, so the writer received
`- - a p p l y` and exited with an argparse error. The step is wrapped (it can never stop the research), so nothing else noticed.

These tests run the REAL argument line from the two patch files in Windows PowerShell and count what a splat delivers. They read
only the patch files in this repo; the live Markets script is outside it and is checked by the Thursday pre-flight and by
`apply-markets-patches.ps1` (ACT-74 is the one-line patch that fixes the live copy)."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

PATCHES = Path(__file__).resolve().parents[1] / "docs" / "control" / "patches"
ACT72 = PATCHES / "ACT-72-run_monthly.ps1.patch"
ACT74 = PATCHES / "ACT-74-run_monthly.ps1.patch"
PS = shutil.which("powershell") or shutil.which("pwsh")


def _added(path: Path) -> list[str]:
    return [ln[1:] for ln in path.read_text(encoding="utf-8").splitlines() if ln.startswith("+") and not ln.startswith("+++")]


def _arg_line(path: Path) -> str:
    hit = [ln.strip() for ln in _added(path) if re.match(r"\s*\$ccArgs\s*=", ln)]
    assert len(hit) == 1, f"{path.name}: expected exactly one added $ccArgs line, found {len(hit)}"
    return hit[0]


def _splat(line: str, switch_off: bool) -> list[str]:
    """What the writer would receive for `--markets Awards @ccArgs`, as PowerShell really passes it."""
    env = "$env:CFP_CUSTOMER_CONTEXT = '0'; " if switch_off else "$env:CFP_CUSTOMER_CONTEXT = $null; "
    cmd = env + line + "; function Show { ($args | ForEach-Object { $_ }) -join '|' }; Show --markets Awards @ccArgs"
    out = subprocess.run([PS, "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip().split("|")


@pytest.mark.skipif(PS is None, reason="PowerShell not available")
@pytest.mark.parametrize("patch", [ACT72, ACT74], ids=lambda p: p.name)
@pytest.mark.parametrize("switch_off,expected", [(False, "--apply"), (True, "--clear")])
def test_the_switch_reaches_the_writer_as_one_argument(patch, switch_off, expected):
    assert _splat(_arg_line(patch), switch_off) == ["--markets", "Awards", expected]


@pytest.mark.skipif(PS is None, reason="PowerShell not available")
def test_the_broken_form_really_splats_characters():
    """The test above would pass vacuously if PowerShell ever stopped unwrapping; prove the old line still shows the bug."""
    broken = "$ccArgs = if ($env:CFP_CUSTOMER_CONTEXT -eq '0') { @('--clear') } else { @('--apply') }"
    got = _splat(broken, switch_off=False)
    assert got[:2] == ["--markets", "Awards"] and len(got) > 3, got      # '-', '-', 'a', 'p', 'p', 'l', 'y'


@pytest.mark.parametrize("patch", [ACT72, ACT74], ids=lambda p: p.name)
def test_no_patch_splats_a_variable_built_by_an_if_expression(patch):
    """A lint for the whole class: `$x = if (...) {...}` followed by `@x` in the same added text is the unwrap trap."""
    added = "\n".join(_added(patch))
    for var in re.findall(r"(?m)^\s*\$(\w+)\s*=\s*if\s*\(", added):
        assert not re.search(r"(?<![\w$])@" + re.escape(var) + r"\b", added), f"{patch.name}: ${var} is built by an if-expression and splatted"


def test_the_two_patches_agree_on_the_corrected_line():
    assert _arg_line(ACT72) == _arg_line(ACT74)
