"""The controls for Matt's 2026-11-13 rule (D66 = B): "If the customer sheets don't load I do NOT want to proceed."

What these prove, in the order the weekend meets them:
  - a failing sheet load makes the intake return 6 (HELD) and a good one does not (weekly_intake.py);
  - exit 6 is never "usable research" and the recap, the importer's reason and the Sunday gate say HELD in plain words;
  - run_monthly.ps1 (patches ACT-75 and ACT-76) really STOPS at exit 6 and really CONTINUES on 0: the patched PowerShell blocks are run with stub programs
    that return a chosen exit code or verdict line, and the process exit code and the text are read back (nothing is researched, nothing is spent);
  - the customer-context hold (ACT-76) holds on a crash, FAILED, UNKNOWN or 0 rows, and does NOT hold on a good or DEGRADED-with-rows verdict, with
    its two off switches;
  - the three patches apply in order to the live Markets script, whichever of them is already in, and the result parses.
The live script lives outside this repo: the PowerShell tests skip when it is not on the machine."""
from __future__ import annotations

import os
import subprocess
import shutil
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.cfp_monitor import research_usable                     # noqa: E402
from src.cfp_monitor.unified_patch import PatchDoesNotApply, apply_unified   # noqa: E402

PATCHES = ROOT / "docs" / "control" / "patches"
LIVE_RM = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets\run_monthly.ps1")
PS = shutil.which("powershell")


# ------------------------------------------------------------------ the hold only promises what the run script enforces
def test_the_hold_is_on_only_when_the_live_script_carries_act_75(monkeypatch, tmp_path):
    """These scripts are live when saved; the stop in run_monthly.ps1 only when Matt applies ACT-75. Until then a HELD email would be a false promise."""
    import customer_sheet_load as csl
    real = csl._real_hold_wired
    md = tmp_path / "Markets"
    md.mkdir()
    assert real(md) is False, "no script at all: the 11-10 behaviour"
    (md / "run_monthly.ps1").write_text("# STEP 0a4\n", encoding="utf-8")
    assert real(md) is False
    (md / "run_monthly.ps1").write_text('if ($LASTEXITCODE -eq 6) { Write-Host "RESEARCH HELD (ACT-75): x"; exit 6 }\n', encoding="utf-8")
    assert real(md) is True
    monkeypatch.setattr(csl, "hold_wired", lambda markets=None: False)
    assert csl.on_fail_mode({}) == "proceed", "not wired: a failed load goes ahead on old copies, DEGRADED, as before"
    assert csl.on_fail_mode({"CFP_SHEETS_ON_FAIL": "hold"}) == "hold" and csl.on_fail_mode({"CFP_SHEETS_ON_FAIL": "PROCEED"}) == "proceed"
    monkeypatch.setattr(csl, "hold_wired", lambda markets=None: True)
    assert csl.on_fail_mode({}) == "hold" and csl.on_fail_mode({"CFP_SHEETS_ON_FAIL": "proceed"}) == "proceed"


def test_the_acts_patch_text_carries_the_marker_the_check_looks_for():
    import customer_sheet_load as csl
    assert csl.HOLD_MARKER in (PATCHES / "ACT-75-run_monthly.ps1.patch").read_text(encoding="utf-8")


# ------------------------------------------------------------------ the intake (Saturday)
def test_the_intake_returns_6_when_the_sheets_did_not_load_and_stops_before_touching_the_database(monkeypatch, tmp_path, capsys):
    import weekly_intake as wi
    monkeypatch.setattr(wi, "fetch_all", lambda *a, **k: (False, ["SHEET LOAD: HELD - 1 of 4 sheet(s) still not loaded"], 6))
    monkeypatch.setattr(wi, "match_client", lambda *a, **k: pytest.fail("the intake went on to the database after a HELD load"))
    monkeypatch.setattr(wi, "run", lambda *a, **k: pytest.fail("the intake ran another step after a HELD load"))
    monkeypatch.setattr(sys, "argv", ["weekly_intake.py", "--db", str(tmp_path / "x.db"), "--config", str(tmp_path / "c.json"), "--snapshots", str(tmp_path)])
    assert wi.main() == 6
    out = capsys.readouterr().out
    assert "INTAKE HEALTH: HELD" in out and "Nothing was loaded into the database" in out and "still not loaded" in out


def test_a_guard_that_crashed_holds_in_hold_mode_and_goes_on_with_the_override(monkeypatch, tmp_path):
    """Codex review 2026-11-13: fetch_all turned a crash of the guarded load into a quiet 1, and the intake then returned 0 and the research started."""
    import customer_sheet_load as csl
    import weekly_intake as wi
    cfg = tmp_path / "cfg.json"
    cfg.write_text('{"service_account_key": "k", "clients": {"utility": {}}}', encoding="utf-8")

    def boom(*a, **k):
        raise RuntimeError("the guard fell over")
    monkeypatch.setattr(csl, "guarded_load", boom)
    monkeypatch.delenv("CFP_SHEETS_ON_FAIL", raising=False)
    ok, notes, code = wi.fetch_all(cfg, tmp_path)
    assert not ok and code == 6 and "could not run (RuntimeError" in notes[0]
    monkeypatch.setenv("CFP_SHEETS_ON_FAIL", "proceed")
    assert wi.fetch_all(cfg, tmp_path)[2] == 1


def test_the_first_email_does_not_say_the_research_is_held_while_it_is_still_waiting(monkeypatch, tmp_path):
    """Codex review 2026-11-13: the first alert (sent when the wait starts) said 'it is held; it will not start by itself again'."""
    import customer_sheet_load as csl
    from datetime import datetime, timedelta
    res = {"clients": ["utility"], "failed": ["utility"], "attempts": [],
           "outcomes": {"utility": {"ok": False, "cause": "sharing", "tries": 1, "at": "2026-11-14T02:00:05", "reason": "403 from the export endpoint."}}}
    now = datetime(2026, 11, 14, 2, 0, 5)
    cfg = tmp_path / "customer_sheets.json"
    waiting = csl.compose(res, "saturday", csl.config_info(cfg), tmp_path, (2.0, "", now + timedelta(hours=2)), None, now.date(), mode="hold")[1]
    assert "it will not start by itself again" not in waiting and "it is held" not in waiting.split("EVIDENCE")[0].lower().replace("research is held", "")
    assert "IF THE SHEETS STILL DO NOT LOAD AT THE END OF THE WAIT, THE RESEARCH IS HELD" in waiting and "starts by itself the moment the sheets load" in waiting
    assert "Start-ScheduledTask -TaskName 'CFP Weekly Re-Research (live markets)'" in waiting
    nowait = csl.compose(res, "saturday", csl.config_info(cfg), tmp_path, (0.0, "no wait", now), None, now.date(), mode="hold")[1]
    assert "THEN START THE RESEARCH (it is held; it will not start by itself again)" in nowait


# ------------------------------------------------------------------ what a held run looks like downstream
def test_exit_6_is_never_usable_research_and_says_held(tmp_path):
    c = research_usable.check("Cybersecurity", tmp_path, research_exit=6)
    assert not c.usable and "exited 6" in c.why and "HELD" in c.why and "never started" in c.why
    (tmp_path / "Cybersecurity_audited.csv").write_text("CONFERENCE\nx\n", encoding="utf-8")        # even with an output file lying about, 6 is not usable
    assert not research_usable.check("Cybersecurity", tmp_path, research_exit=6).usable


def test_the_recap_subject_says_held_for_both_reasons():
    from scripts.weekend_recap import saturday_recap
    sheets = ("=== run_monthly exit code: 6 ===\n"
              "SHEET LOAD: HELD - 1 of 4 sheet(s) still not loaded (utility; cause: sharing) after waiting 120 min; the Saturday 02:00 conference research did NOT start: "
              "nothing researched, nothing spent. After the fix, start it: Start-ScheduledTask -TaskName 'CFP Weekly Re-Research (live markets)'\n")
    subject, text, _ = saturday_recap(sheets, None, Path("."), "saturday", None)
    assert "HELD - research did NOT start: customer sheets did not load" in subject and "WORKED" not in subject
    assert "Customer sheets: HELD - 1 of 4" in text
    context = "=== run_monthly exit code: 6 ===\nRESEARCH HELD (ACT-76): the customer context did not build (CUSTOMER CONTEXT: FAILED - x). Nothing researched.\n"
    subject, _t, _ = saturday_recap(context, None, Path("."), "saturday", None)
    assert "HELD - research did NOT start: customer context did not build" in subject
    broke = "=== run_monthly exit code: 6 ===\nINTAKE SKIPPED: interpreter or script not found\nRESEARCH HELD (ACT-75): the customer sheet intake could not run. Nothing researched.\n"
    assert "HELD - research did NOT start: customer sheets did not load" in saturday_recap(broke, None, Path("."), "saturday", None)[0]
    unknown = "=== run_monthly exit code: 6 ===\nsomething else printed 6\n"
    assert "HELD - research did NOT start (exit 6): see the run log" in saturday_recap(unknown, None, Path("."), "saturday", None)[0]
    ok = "=== run_monthly exit code: 0 ===\nSHEET LOAD: HEALTHY - all 4 sheet(s) loaded at 02:03\n"
    assert "HELD" not in saturday_recap(ok, None, Path("."), "saturday", None)[0]


def test_the_sunday_gate_warns_held_and_a_later_recovery_replaces_it():
    from scripts import release_gate as rg
    o = SimpleNamespace(on=date(2026, 11, 15))
    held = {"saturday": {"date": "2026-11-14", "verdict": "HELD", "failed": ["utility"], "waited_min": 120}}
    c = rg.check_sheet_load(o, held)
    assert c["status"] == "WARN" and c["summary"].startswith("HELD: Saturday's research did NOT start") and any("HELD - utility did not load after waiting 120 min" in r for r in c["rows"])
    both = {"saturday": held["saturday"], "friday": {"date": "2026-11-13", "verdict": "DEGRADED", "failed": ["arnica-awards"], "copies": {}}}
    s = rg.check_sheet_load(o, both)["summary"]
    assert "HELD: Saturday's research did NOT start" in s and "DEGRADED: Friday's research ran on old copies" in s
    recovered = {"saturday": {"date": "2026-11-14", "verdict": "RECOVERED", "failed": [], "waited_min": 40}}
    assert rg.check_sheet_load(o, recovered)["status"] == "PASS"


def test_the_context_held_email_has_the_commands_and_no_secret(monkeypatch, tmp_path):
    import customer_sheet_load as csl
    monkeypatch.setenv("CFP_SMTP_PASS", "s3cret-smtp-pass-DO-NOT-PRINT")
    subject, body = csl.compose_context_held("saturday", 'CUSTOMER CONTEXT: FAILED - the context could not be built (KeyError: "x"); lists not changed')
    assert subject == csl.SUBJECT_CONTEXT_HELD and body.startswith(subject)
    assert "is HELD: it did NOT start" in body and "customer_row_context.py" in body and "--markets Cybersecurity,Utility" in body
    assert "Start-ScheduledTask -TaskName 'CFP Weekly Re-Research (live markets)'" in body and "CFP_CONTEXT_ON_FAIL" in body and "s3cret" not in body and body.isascii()
    friday = csl.compose_context_held("friday", "x")[1]
    assert "--markets Awards" in friday and "Start-ScheduledTask -TaskName 'CFP Weekly Awards Research'" in friday
    sent = []
    monkeypatch.setattr(csl, "send", lambda subj, b, today, now, **kw: (sent.append((subj, kw)), "sent")[1])
    monkeypatch.setattr(csl, "write_alert_file", lambda b, paths=None: ["desk.txt"])
    assert csl.main(["--held-notice", "context", "--context", "saturday", "--detail", "no CUSTOMER CONTEXT line"]) == 0
    assert sent and sent[0][0] == csl.SUBJECT_CONTEXT_HELD and sent[0][1] == {"once_a_day": False}, "a different alert from the sheet-load one: it must not use up that one"


# ------------------------------------------------------------------ the patches: order, parse, and what the PowerShell really does
def _chain(text: str) -> str:
    """ACT-74, ACT-75, ACT-76 onto the live script, whichever of them is already in (an applied patch's lines are checked, not re-applied)."""
    for name in ("ACT-74", "ACT-75", "ACT-76"):
        patch = (PATCHES / f"{name}-run_monthly.ps1.patch").read_text(encoding="utf-8")
        try:
            text = apply_unified(text, patch)
        except PatchDoesNotApply:
            added = [ln[1:] for ln in patch.splitlines() if ln.startswith("+") and not ln.startswith("+++") and ln[1:].strip() and not ln[1:].strip().startswith("#")]
            assert all(a.rstrip() in text for a in added), f"{name} neither applies to the live script nor is already in it"
    return text


@pytest.fixture(scope="module")
def patched() -> str:
    if not LIVE_RM.exists() or PS is None:
        pytest.skip("the live Markets script or PowerShell is not on this machine")
    return _chain(LIVE_RM.read_text(encoding="utf-8").replace("\r\n", "\n"))


def test_the_three_patches_chain_onto_the_live_script_and_it_parses(patched, tmp_path):
    p = tmp_path / "run_monthly.ps1"
    p.write_text(patched, encoding="utf-8")
    cmd = ("$e=$null;$t=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('" + str(p) + "',[ref]$t,[ref]$e);"
           "if($e.Count){$e|ForEach-Object{$_.Message};exit 1}")
    r = subprocess.run([PS, "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    for needle in ("ACT-74", "ACT-75", "ACT-76", "-ne 0 -and $env:CFP_SHEETS_ON_FAIL -ne 'proceed') { Write-Host \"RESEARCH HELD (ACT-75)", "RESEARCH HELD (ACT-76)"):
        assert needle in patched
    assert patched.index("STEP 0a4") < patched.index("RESEARCH HELD (ACT-76)") < patched.index("STEP 0b: CANARY")
    assert patched.index("RESEARCH HELD (ACT-75): the customer sheets were not shown to be loaded") < patched.index("STEP 0a0: CUSTOMER COVERAGE"), \
        "the Saturday hold must come right after the intake, before coverage, the refresh plan, the archive and the canary"
    assert patched.count("RESEARCH HELD (ACT-75)") == 5, "Saturday: after the intake, intake missing, intake threw; Friday: loader missing, load ended not clean"


STUB = ("@echo off\r\n"
        "echo %* | findstr /c:\"--held-notice\" >nul && (echo NOTICE-SENT & exit /b 0)\r\n"
        "if defined STUB_LINE echo %STUB_LINE%\r\n"
        "exit /b %STUB_EXIT%\r\n")


def _run_region(tmp_path: Path, region: str, prelude: str, env: dict) -> subprocess.CompletedProcess:
    stub = tmp_path / "stub.cmd"
    stub.write_text(STUB, encoding="ascii")
    dummy = tmp_path / "dummy.py"
    dummy.write_text("x\n", encoding="ascii")
    script = tmp_path / "harness.ps1"
    body = prelude + "\r\n" + region + "\r\nWrite-Host 'CONTINUED-AFTER-THE-STEP'\r\n"
    script.write_text(body.replace("@STUB@", str(stub)).replace("@DUMMY@", str(dummy)).replace("@MISSING@", str(tmp_path / "no-such-file.py")), encoding="utf-8")
    e = {**os.environ, **{k: v for k, v in env.items() if v is not None}}
    for k, v in env.items():
        if v is None:
            e.pop(k, None)
    return subprocess.run([PS, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)], capture_output=True, text=True, timeout=120, env=e)


def _saturday_region(text: str, intake_missing: bool = False) -> str:
    a, b = text.index("if ($SkipIntake) {"), text.index("# ------------------------------------------------- STEP 0a0")
    return (text[a:b].replace(r'C:\Users\matts\cfp-monitor\scripts\weekly_intake.py', "@MISSING@" if intake_missing else "@DUMMY@")
            .replace(r'C:\Users\matts\cfp-monitor\.venv\Scripts\python.exe', "@STUB@"))


def _friday_region(text: str) -> str:
    """From ACT-75's pre-check (the loader must exist) through the end of the awards load block."""
    a = text.index("if ($Markets -contains 'Awards' -and $env:CFP_SHEETS_ON_FAIL -ne 'proceed'")
    return (text[a:text.index("        if ((Test-Path $awPy) -and (Test-Path $awPy_)) {", a)]
            .replace(r'C:\Users\matts\cfp-monitor\scripts\customer_sheet_load.py', "@DUMMY@"))


def _context_region(text: str) -> str:
    m = text.index("STEP 0a4: CUSTOMER CONTEXT")
    a, b = text.index("if (($liveMarkets.Count -gt 0 -or $Markets -contains 'Awards') -and -not $WhatIf) {", m), text.index("STEP 0b: CANARY", m)
    return (text[a:b].replace(r'C:\Users\matts\cfp-monitor\scripts\customer_row_context.py', "@DUMMY@")
            .replace(r'C:\Users\matts\cfp-monitor\.venv\Scripts\python.exe', "@STUB@"))


SAT = "$SkipIntake = $false; $WhatIf = $false; $Markets = @('Cybersecurity','Utility'); $liveMarkets = @('Cybersecurity','Utility')"
FRI = "$Markets = @('Awards'); $awPy = '@STUB@'; $awFetch = '@DUMMY@'"
CTX_SAT = "$WhatIf = $false; $Markets = @('Cybersecurity','Utility'); $liveMarkets = @('Cybersecurity','Utility')"
CTX_FRI = "$WhatIf = $false; $Markets = @('Awards'); $liveMarkets = @()"


# Codex review 2026-11-13: the stop used to fire on exit 6 ONLY. The rule now is Matt's own: if the sheets cannot be SHOWN to be loaded, the research does not
# start. Anything but a clean exit 0 holds (6 = did not load after the wait; 1 or 2 = the intake or loader itself broke), and so does a missing script or
# interpreter; only a person's CFP_SHEETS_ON_FAIL = 'proceed' lets it go on.
EXIT_CASES = [("6", None, True), ("1", None, True), ("2", None, True), ("0", None, False),
              ("1", "proceed", False), ("2", "proceed", False), ("0", "hold", False)]


@pytest.mark.skipif(PS is None, reason="PowerShell not available")
@pytest.mark.parametrize("stub_exit,on_fail,held", EXIT_CASES, ids=[f"exit{c[0]}-{c[1] or 'default'}" for c in EXIT_CASES])
def test_saturday_the_run_stops_unless_the_intake_ended_clean(patched, tmp_path, stub_exit, on_fail, held):
    r = _run_region(tmp_path, _saturday_region(patched), SAT, {"STUB_EXIT": stub_exit, "STUB_LINE": None, "CFP_SHEETS_ON_FAIL": on_fail})
    assert (r.returncode == 6) is held, r.stdout + r.stderr
    assert ("RESEARCH HELD (ACT-75)" in r.stdout) is held and ("CONTINUED-AFTER-THE-STEP" in r.stdout) is (not held)
    if held:
        assert f"exit code {stub_exit}" in r.stdout


@pytest.mark.skipif(PS is None, reason="PowerShell not available")
@pytest.mark.parametrize("on_fail,held", [(None, True), ("proceed", False)])
def test_saturday_a_missing_intake_holds_instead_of_researching_with_no_load(patched, tmp_path, on_fail, held):
    r = _run_region(tmp_path, _saturday_region(patched, intake_missing=True), SAT, {"STUB_EXIT": "0", "STUB_LINE": None, "CFP_SHEETS_ON_FAIL": on_fail})
    assert (r.returncode == 6) is held, r.stdout + r.stderr
    assert "INTAKE SKIPPED" in r.stdout and ("RESEARCH HELD (ACT-75)" in r.stdout) is held and ("CONTINUED-AFTER-THE-STEP" in r.stdout) is (not held)


@pytest.mark.skipif(PS is None, reason="PowerShell not available")
@pytest.mark.parametrize("stub_exit,on_fail,held", EXIT_CASES, ids=[f"exit{c[0]}-{c[1] or 'default'}" for c in EXIT_CASES])
def test_friday_the_run_stops_unless_the_awards_load_ended_clean(patched, tmp_path, stub_exit, on_fail, held):
    r = _run_region(tmp_path, _friday_region(patched), FRI, {"STUB_EXIT": stub_exit, "STUB_LINE": None, "CFP_SHEETS_ON_FAIL": on_fail})
    assert (r.returncode == 6) is held, r.stdout + r.stderr
    assert ("RESEARCH HELD (ACT-75)" in r.stdout) is held and ("CONTINUED-AFTER-THE-STEP" in r.stdout) is (not held)


@pytest.mark.skipif(PS is None, reason="PowerShell not available")
@pytest.mark.parametrize("on_fail,held", [(None, True), ("proceed", False)])
def test_friday_a_missing_fetch_script_or_loader_holds(patched, tmp_path, on_fail, held):
    missing_fetch = "$Markets = @('Awards'); $awPy = '@STUB@'; $awFetch = '@MISSING@'"
    r = _run_region(tmp_path, _friday_region(patched), missing_fetch, {"STUB_EXIT": "0", "STUB_LINE": None, "CFP_SHEETS_ON_FAIL": on_fail})
    assert (r.returncode == 6) is held, r.stdout + r.stderr
    assert ("RESEARCH HELD (ACT-75)" in r.stdout) is held and ("CONTINUED-AFTER-THE-STEP" in r.stdout) is (not held)
    r = _run_region(tmp_path, _friday_region(patched).replace("@DUMMY@", "@MISSING@"), FRI, {"STUB_EXIT": "0", "STUB_LINE": None, "CFP_SHEETS_ON_FAIL": on_fail})
    assert (r.returncode == 6) is held, "the loader itself (customer_sheet_load.py) missing must hold too: " + r.stdout + r.stderr


CTX_CASES = [
    # (verdict line the writer prints, extra env, held?)
    ("CUSTOMER CONTEXT: HEALTHY - 138 of 187 research rows carry the customers row", {}, False),
    ("CUSTOMER CONTEXT: DEGRADED - 100 of 187 research rows carry the customers row; 1 cell dropped", {}, False),
    ("CUSTOMER CONTEXT: HEALTHY - 0 of 187 research rows carry the customers row", {}, True),
    ("CUSTOMER CONTEXT: FAILED - the context could not be built (KeyError: x); the research lists were not changed", {}, True),
    ("CUSTOMER CONTEXT: UNKNOWN - interpreter or script not found", {}, True),
    ("CUSTOMER CONTEXT: BROKEN - 3 of 4 research rows carry the customers row", {}, True),      # Codex 2026-11-13: a verdict word nobody has seen is not good
    ("", {}, True),                                                                              # the writer crashed: no verdict line at all
    ("CUSTOMER CONTEXT: FAILED - x", {"CFP_CONTEXT_ON_FAIL": "proceed"}, False),                  # the by-hand override
    ("CUSTOMER CONTEXT: OFF - the switch is off", {"CFP_CUSTOMER_CONTEXT": "0"}, False),          # context switched off on purpose: never holds
    ("", {"CFP_CUSTOMER_CONTEXT": "0"}, False),
]


@pytest.mark.skipif(PS is None, reason="PowerShell not available")
@pytest.mark.parametrize("line,extra,held", CTX_CASES, ids=[f"{i}-{'held' if c[2] else 'goes'}" for i, c in enumerate(CTX_CASES)])
def test_the_context_step_holds_on_a_crash_failed_unknown_or_zero_rows_and_not_otherwise(patched, tmp_path, line, extra, held):
    env = {"STUB_EXIT": "0", "STUB_LINE": line or None, "CFP_CONTEXT_ON_FAIL": None, "CFP_CUSTOMER_CONTEXT": None, **extra}
    r = _run_region(tmp_path, _context_region(patched), CTX_SAT, env)
    assert (r.returncode == 6) is held, r.stdout + r.stderr
    assert ("RESEARCH HELD (ACT-76)" in r.stdout) is held and ("CONTINUED-AFTER-THE-STEP" in r.stdout) is (not held)
    assert ("NOTICE-SENT" in r.stdout) is held, "a hold sends its CRITICAL email through --held-notice; a pass sends nothing"


@pytest.mark.skipif(PS is None, reason="PowerShell not available")
def test_the_context_hold_also_applies_to_fridays_awards_run(patched, tmp_path):
    env = {"STUB_EXIT": "0", "STUB_LINE": "CUSTOMER CONTEXT: FAILED - x", "CFP_CONTEXT_ON_FAIL": None, "CFP_CUSTOMER_CONTEXT": None}
    r = _run_region(tmp_path, _context_region(patched), CTX_FRI, env)
    assert r.returncode == 6 and "RESEARCH HELD (ACT-76)" in r.stdout and "NOTICE-SENT" in r.stdout
