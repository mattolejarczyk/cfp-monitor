"""ACT-67: the reviewer's patch for Markets/run_monthly.ps1 (docs/control/patches/ACT-67-run_monthly.ps1.patch) runs scripts/customer_awards.py before the research on every customer run (Friday
awards and Saturday), dry-run unless CFP_AWARDS_AUTOADD_APPLY=1, and never stops the research. Applied to a COPY of the live script (never the live one); skipped if the live script already carries it."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_customer_auto_add_hook import patched_text as base_text   # noqa: E402
from test_customer_coverage_hook import apply_unified, ps          # noqa: E402

PATCH = ROOT / "docs" / "control" / "patches" / "ACT-67-run_monthly.ps1.patch"


def patched_text() -> str:
    text = base_text()
    return text if "customer_awards.py" in text else apply_unified(text, PATCH.read_text(encoding="utf-8"))


def _added() -> str:
    return "\n".join(l[1:] for l in PATCH.read_text(encoding="utf-8").splitlines() if l.startswith("+") and not l.startswith("+++"))


def test_patch_only_adds_lines_and_applies_only_when_switched_on_by_the_environment():
    lines = PATCH.read_text(encoding="utf-8").splitlines()
    assert not [l for l in lines if l.startswith("-") and not l.startswith("---")]
    added = _added()
    assert "customer_awards.py" in added and "AWARDS COVERAGE: UNKNOWN" in added and "-not $WhatIf" in added
    assert "CFP_AWARDS_AUTOADD_APPLY -eq '1'" in added and "$awArgs = @()" in added, "applying is a switch, off by default"
    assert added.count("--apply") == 1
    assert "--client $awClient" in added and "arnica-awards" in added and "utility-awards" in added, "an Awards run fetches the two awards sheets itself"


def test_the_block_runs_on_awards_runs_and_on_customer_runs_and_every_call_is_wrapped():
    added = _added()
    assert "$liveMarkets.Count -gt 0 -or $Markets -contains 'Awards'" in added
    # every call into Python sits inside a try { } so a fault is a log line, never a stopped research
    assert added.count("try {") >= 2 and "catch {" in added and added.count("catch {") >= 2


def test_patched_script_runs_the_awards_step_after_the_conference_steps_and_before_stamping_and_research():
    t = patched_text()
    i_auto, i_aw, i_stamp = t.index("customer_auto_add.py"), t.index("customer_awards.py"), t.index("STEP 0a: PERMANENT IDS")
    assert i_auto < i_aw < i_stamp < t.index("STEP 0b: CANARY") < t.index("Archive the previous cycle")


def test_patched_script_still_parses_with_no_errors(tmp_path):
    f = tmp_path / "rm.ps1"
    f.write_text(patched_text(), encoding="utf-8")
    cmd = (f"$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('{f}',[ref]$null,[ref]$e); "
           "if ($e.Count -eq 0) { 'PARSE OK' } else { $e | ForEach-Object { $_.Message } }")
    assert "PARSE OK" in ps(["-Command", cmd]).stdout


def test_the_awards_block_alone_runs_and_prints_unknown_when_the_script_is_missing(tmp_path):
    """The block as it would run, with $liveMarkets/$Markets/$WhatIf set, in a throw-away script: with the interpreter path absent it must print the UNKNOWN line and fall through, exit 0."""
    added = _added()
    start = added.index("if (($liveMarkets.Count")
    block = added[start:].replace("C:\\Users\\matts\\cfp-monitor\\", str(tmp_path / "nowhere") + "\\")
    f = tmp_path / "blk.ps1"
    f.write_text("$Markets = @('Awards'); $liveMarkets = @(); $WhatIf = $false\n" + block + "\nWrite-Host 'AFTER THE BLOCK'\n", encoding="utf-8")
    p = ps(["-File", str(f)])
    assert p.returncode == 0 and "AWARDS COVERAGE: UNKNOWN - interpreter or script not found" in p.stdout and "AFTER THE BLOCK" in p.stdout
    f.write_text("$Markets = @('Awards'); $liveMarkets = @(); $WhatIf = $true\n" + block + "\nWrite-Host 'AFTER THE BLOCK'\n", encoding="utf-8")
    p = ps(["-File", str(f)])
    assert "AWARDS COVERAGE" not in p.stdout and "AFTER THE BLOCK" in p.stdout, "-WhatIf runs nothing"
    f.write_text("$Markets = @('Utility_prospects'); $liveMarkets = @(); $WhatIf = $false\n" + block + "\nWrite-Host 'AFTER THE BLOCK'\n", encoding="utf-8")
    assert "AWARDS COVERAGE" not in ps(["-File", str(f)]).stdout, "a run with no customer does not run it"
