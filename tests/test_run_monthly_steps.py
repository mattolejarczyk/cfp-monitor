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
    assert "New-Object System.Collections.ArrayList" in t and "function New-PostSteps" in t and "return ,$steps" in t and "New-PostSteps -Mkts $Markets" in t
    # the buggy form: an array literal whose elements are '+' sums joined by a comma
    assert not re.search(r"foreach\s*\(\s*\$step\s+in\s+@\(\s*@\(", t), "steps flattened again (comma binds tighter than +)"


def test_load_qa_runs_after_the_import_and_before_the_recap():
    t = _text()
    assert t.index("weekend_import.py") < t.index("post_load_qa.py") < t.index('weekend_recap.py", $kind')


def test_a_stray_python_prompt_cannot_hang_the_job():
    t = _text()
    assert "$null | & $cfpPy @step" in t and "Test-Path -LiteralPath $step[0]" in t


def test_the_shadow_run_is_last_saturday_only_and_time_boxed():
    t = _text()
    assert t.index('weekend_recap.py", $kind') < t.index("shadow_finder.py")             # after the load and the recap: it can delay neither
    block = t[t.index("SHADOW RUN of the real-URL"):]
    assert "$kind -eq 'saturday'" in block[:900] and '"--run-log", $RunLog' in block[:900]   # Saturday conference markets only; time budget tied to the job's log


def test_the_awards_refresh_plan_runs_before_the_canary_and_cannot_stop_the_run():
    t = _text()
    assert t.index("STEP 0a: PERMANENT IDS") < t.index("AWARDS REFRESH PLAN") < t.index("STEP 0b: CANARY")
    block = t[t.index("AWARDS REFRESH PLAN"):t.index("STEP 0b: CANARY")]
    assert "$Markets -contains 'Awards'" in block and "refresh_plan.py" in block and "try {" in block and "catch {" in block and "every award will be researched" in block


def test_the_awards_load_gets_its_own_load_qa_step_before_the_recap():
    t = _text()
    assert t.index('"--markets", "Awards"))') < t.index('weekend_recap.py", $kind')


def test_the_audit_skips_refresh_marked_rows_in_the_pending_count_and_in_the_row_loop():
    a = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets\run_market_audit.py").read_text(encoding="utf-8")
    assert "def is_refresh_skip" in a and "and not is_refresh_skip(r)]" in a and "if is_refresh_skip(row):" in a


# --- 2026-10-05: -ListPostSteps runs the REAL step builder and prints every step (nothing is researched, loaded, emailed or written) ---
import subprocess


def _list_steps(markets: str) -> list[list[str]]:
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"& '{PS1}' -Markets {markets} -ListPostSteps"]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout
    steps = [line.split(": ", 1)[1].split(" | ") for line in out.splitlines() if line.startswith("STEP ") and "[" in line]
    assert f"STEPS: {len(steps)}" in out, out
    for line in out.splitlines():
        if line.startswith("STEP "):
            assert "[found]" in line, f"a step's script is missing: {line}"
    return steps


def test_the_saturday_steps_are_whole_real_commands_in_the_right_order():
    steps = _list_steps("'Cybersecurity','Utility'")
    names = [Path(s[0]).name for s in steps]
    # ACT-20: once the reviewer applies docs/control/patches/ACT-20-run_monthly.ps1.patch the shadow reader sits before the finder (tests/test_shadow_reader_hook.py guards that list)
    assert names in (["weekend_import.py", "post_load_qa.py", "weekend_recap.py", "shadow_finder.py"],
                     ["weekend_import.py", "post_load_qa.py", "weekend_recap.py", "shadow_reader.py", "shadow_finder.py"])
    for s in steps:
        assert s[0].lower().endswith(".py") and all(len(tok) > 1 or tok.isdigit() for tok in s), f"flattened or malformed step: {s}"           # the 10-03 bug made single-character arguments
    assert steps[0][1:3] == ["--markets", "Cybersecurity"] and "Utility" in steps[0] and steps[2][1] == "saturday"
    assert steps[-1][-2] == "--run-log"                                    # the finder is last


def test_the_friday_awards_steps_include_the_awards_load_qa_and_no_shadow_run():
    steps = _list_steps("'Awards'")
    # ACT-22: once the reviewer applies docs/control/patches/ACT-22-run_monthly.ps1.patch Friday also ends with the awards shadow run (tests/test_shadow_reader_hook.py guards that list)
    names = [Path(s[0]).name for s in steps]
    assert names in (["weekend_import.py", "post_load_qa.py", "weekend_recap.py"], ["weekend_import.py", "post_load_qa.py", "weekend_recap.py", "shadow_finder.py"])
    assert steps[1][-2:] == ["--markets", "Awards"] and steps[2][1] == "friday"


def test_a_market_with_no_customer_page_has_no_post_steps():
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"& '{PS1}' -Markets 'Robotics' -ListPostSteps"]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout
    assert "STEPS: 0" in out                                      # the monthly prospect sweep reports through its own branch
