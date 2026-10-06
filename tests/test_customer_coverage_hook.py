"""ACT-51 part 4: the reviewer's patch for Markets/run_monthly.ps1 (docs/control/patches/ACT-51-run_monthly.ps1.patch) runs scripts/customer_coverage.py right after the intake and BEFORE the
research. The patch is applied to a COPY of the live script (never the live one); a patch whose block the live script already carries (the reviewer applied it) is skipped."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets\run_monthly.ps1")
PATCH = ROOT / "docs" / "control" / "patches" / "ACT-51-run_monthly.ps1.patch"
LIVE_CFP = r"C:\Users\matts\cfp-monitor"


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
    if "customer_coverage.py" not in text:
        text = apply_unified(text, PATCH.read_text(encoding="utf-8"))
    return text


def ps(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass"] + args, capture_output=True, text=True, timeout=120)


def test_the_patch_only_adds_lines_and_names_the_script_and_the_log_line():
    lines = PATCH.read_text(encoding="utf-8").splitlines()
    assert not [l for l in lines if l.startswith("-") and not l.startswith("---")]
    added = "\n".join(l[1:] for l in lines if l.startswith("+") and not l.startswith("+++"))
    assert "customer_coverage.py" in added and "COVERAGE: UNKNOWN" in added and "-not $WhatIf" in added
    assert "--apply" not in added and "add_customer_rows" not in added.replace("# ", "").split("try")[1], "this week the step must only REPORT"


def test_patched_script_runs_the_coverage_check_after_the_intake_and_before_the_stamping_and_the_research():
    t = patched_text()
    i_intake, i_cov, i_stamp = t.index("INTAKE FAILED"), t.index("customer_coverage.py"), t.index("STEP 0a: PERMANENT IDS")
    assert i_intake < i_cov < i_stamp
    # everything that costs quota (the 5-row canary, then the archive step, then the audit) comes after STEP 0b
    assert i_cov < t.index("STEP 0b: CANARY") < t.index("Archive the previous cycle"), "the coverage check must come before the research starts"


def test_patched_script_still_parses_with_no_errors(tmp_path):
    f = tmp_path / "rm.ps1"
    f.write_text(patched_text(), encoding="utf-8")
    cmd = (f"$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('{f}',[ref]$null,[ref]$e); "
           "if ($e.Count -eq 0) { 'PARSE OK' } else { $e | ForEach-Object { $_.Message } }")
    out = ps(["-Command", cmd]).stdout
    assert "PARSE OK" in out, out


def _block() -> str:
    """The added step, lifted from the patch, with $liveMarkets and $WhatIf set the way the script has them."""
    added = [l[1:] for l in PATCH.read_text(encoding="utf-8").splitlines() if l.startswith("+") and not l.startswith("+++")]
    return "\n".join(added)


def _run_block(tmp_path, py: str, script: str, what_if: bool = False, markets: str = "'Utility'"):
    body = _block().replace(LIVE_CFP + r"\.venv\Scripts\python.exe", py).replace(LIVE_CFP + r"\scripts\customer_coverage.py", script)
    f = tmp_path / "block.ps1"
    f.write_text(f"$liveMarkets = @({markets}); $WhatIf = ${str(what_if).lower()}\n" + body + "\nWrite-Host 'AFTER-BLOCK'\n", encoding="utf-8")
    return ps(["-File", str(f)])


def test_block_passes_the_coverage_lines_through_to_the_log(tmp_path):
    stub = tmp_path / "stub.py"
    stub.write_text('print("COVERAGE: 17 of 20 customer rows ahead of 2026-10-10 are in the research queue; 3 are NOT")\n', encoding="utf-8")
    p = _run_block(tmp_path, sys.executable, str(stub))
    assert "COVERAGE: 17 of 20 customer rows ahead of 2026-10-10 are in the research queue; 3 are NOT" in p.stdout and "AFTER-BLOCK" in p.stdout


def test_block_can_never_stop_the_research_whatever_the_tool_does(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("import sys\nprint('boom')\nsys.exit(7)\n", encoding="utf-8")
    p = _run_block(tmp_path, sys.executable, str(bad))
    assert "AFTER-BLOCK" in p.stdout and p.returncode == 0
    p = _run_block(tmp_path, str(tmp_path / "no-such-python.exe"), str(bad))
    assert "COVERAGE: UNKNOWN - interpreter or script not found" in p.stdout and "AFTER-BLOCK" in p.stdout


def test_block_is_skipped_for_whatif_and_for_an_awards_only_run(tmp_path):
    stub = tmp_path / "stub.py"
    stub.write_text('print("COVERAGE: ran")\n', encoding="utf-8")
    assert "COVERAGE: ran" not in _run_block(tmp_path, sys.executable, str(stub), what_if=True).stdout
    assert "COVERAGE: ran" not in _run_block(tmp_path, sys.executable, str(stub), markets="").stdout
