"""The unattended Saturday-patches apply (experiments/saturday_apply/auto_apply_saturday_patches.py): waits while a CFP task runs, reminds every 4th wait, applies and e-mails once, goes quiet when done,
sends one final note when the window closes, e-mails an unexpected refusal once, and a dry run sends and writes nothing. Mailer, runner and state are stubs; no live file is read or written."""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "saturday_apply"))
import auto_apply_saturday_patches as aa  # noqa: E402

BEFORE = dt.datetime(2026, 10, 16, 18, 0)
AFTER = dt.datetime(2026, 10, 17, 1, 30)


class Box:
    def __init__(self, applied=False, out="", code=0):
        self.mails, self.applied, self.out, self.code, self.calls = [], applied, out, code, []

    def mailer(self, subject, body):
        self.mails.append(subject)
        return True

    def runner(self, markets, apply):
        self.calls.append(apply)
        return self.code, self.out

    def isapplied(self, markets):
        return self.applied


def go(box, tmp_path, now=BEFORE, dry=False):
    return aa.once("X", now, dry, box.mailer, state_path=tmp_path / "s.json", runner=box.runner, applied=box.isapplied)


def test_waiting_reminds_every_fourth_wait_only(tmp_path):
    b = Box(out="STOP: a CFP task is running right now (['CFP Weekly Awards Research']). Nothing written.", code=1)
    counts = []
    for _ in range(9):
        go(b, tmp_path)
        counts.append(len(b.mails))
    assert counts == [0, 0, 0, 1, 1, 1, 1, 2, 2]      # a reminder on the 4th and 8th wait only
    assert all("still waiting" in m for m in b.mails)
    assert b.calls and all(b.calls)                   # it tried to apply each time (the wrapper itself refuses while a task runs)


def test_applies_once_and_goes_quiet(tmp_path):
    b = Box(out="ACT-64 ... written\nDONE. Tell Claude;", code=0)
    go(b, tmp_path)
    assert b.mails == ["CFP Saturday patches APPLIED: ACT-64 and ACT-63 are in"]
    b.applied = True
    go(b, tmp_path)
    go(b, tmp_path)
    assert len(b.mails) == 1              # no second e-mail once it is done


def test_window_closed_sends_one_final_note(tmp_path):
    b = Box()
    go(b, tmp_path, now=AFTER)
    go(b, tmp_path, now=AFTER)
    assert b.mails == ["CFP Saturday patches: NOT applied, the window has closed"]
    assert b.calls == []                  # it never touches the scripts after the window closes


def test_an_unexpected_refusal_is_mailed_once_per_distinct_message(tmp_path):
    b = Box(out="STOP ACT-64: the patch does not fit the live script (ValueError: x). Nothing written.", code=1)
    go(b, tmp_path)
    go(b, tmp_path)
    assert len(b.mails) == 1 and "needs a look" in b.mails[0]
    b.out = "STOP ACT-63: the patched script would have 2 PowerShell parse error(s). Nothing written."
    go(b, tmp_path)
    assert len(b.mails) == 2


def test_dry_run_sends_nothing_and_writes_no_state(tmp_path):
    b = Box(out="DRY RUN OK: both patches fit and parse.", code=0)
    acts = go(b, tmp_path, dry=True)
    assert b.mails == [] and not (tmp_path / "s.json").exists()
    assert b.calls == [False]             # the wrapper is run in ITS dry-run mode
    assert acts


def test_the_registration_script_parses_and_names_the_one_time_task():
    import subprocess
    p = ROOT / "experiments" / "saturday_apply" / "register_saturday_patch_task.ps1"
    text = p.read_text(encoding="utf-8")
    assert "CFP Saturday Patch Apply (one-time)" in text and "-DeleteExpiredTaskAfter" in text and "SupportsShouldProcess" in text
    cmd = "$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('%s',[ref]$null,[ref]$e); $e.Count" % str(p)
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True)
    assert r.stdout.strip().splitlines()[-1] == "0"
