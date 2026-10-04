"""Markets/run_monthly.ps1 builds the post-research steps (import, load QA, recap) correctly (2026-10-03: they were flattened into one array of strings,
python was started with single characters and hung at a prompt, and Saturday's load never ran). PowerShell has no unit tests here, so this guards the
script's shape: whole steps added to a list, the empty-input pipe, the missing-script guard, and the load QA step before the recap."""
import re
from pathlib import Path

PS1 = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets\run_monthly.ps1")


def _text() -> str:
    return PS1.read_text(encoding="utf-8")


def test_steps_are_built_whole_and_added_to_a_list():
    t = _text()
    assert "New-Object System.Collections.ArrayList" in t and "[void]$steps.Add($importStep)" in t and "[void]$steps.Add($recapStep)" in t
    # the buggy form: an array literal whose elements are '+' sums joined by a comma
    assert not re.search(r"foreach\s*\(\s*\$step\s+in\s+@\(\s*@\(", t), "steps flattened again (comma binds tighter than +)"


def test_load_qa_runs_after_the_import_and_before_the_recap():
    t = _text()
    assert t.index("[void]$steps.Add($importStep)") < t.index("post_load_qa.py") < t.index("[void]$steps.Add($recapStep)")


def test_a_stray_python_prompt_cannot_hang_the_job():
    t = _text()
    assert "$null | & $cfpPy @step" in t and "Test-Path -LiteralPath $step[0]" in t


def test_the_shadow_run_is_last_saturday_only_and_time_boxed():
    t = _text()
    assert t.index("[void]$steps.Add($recapStep)") < t.index("shadow_finder.py")             # after the load and the recap: it can delay neither
    block = t[t.index("SHADOW RUN of the real-URL"):]
    assert "$recapKind -eq 'saturday'" in block[:900] and '"--run-log", $env:CFP_RUN_LOG' in block[:900]   # Saturday conference markets only; time budget tied to the job's log
