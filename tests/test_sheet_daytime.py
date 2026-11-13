"""D67 (Matt, 2026-11-13: "we should proceed if the copies of the customer sheet data are 24 hours or less ... if tonight tries to load the customer data and it
fails, we should STILL PROCEED because we have updated data less than 24 hours old"), the daytime load (07:30 and 18:15, Thursday and Friday), and plan step
1.20 (the customer-context step is RUN before the night, and watched at 03:00).

The three controls Matt asked for, by name: a failing load plus a 10 hour old copy PROCEEDS (YELLOW); a failing load plus a 30 hour old copy HOLDS; a healthy
load proceeds (GREEN). Nothing here sends mail, reads Task Scheduler or touches a live file."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import customer_sheet_load as csl                                        # noqa: E402
import sheet_daytime_check as sdc                                        # noqa: E402
import step_0a4_rehearsal as rh                                          # noqa: E402
from test_customer_sheet_load import World, Clock, NOW, FAKE_PASS, deadman   # noqa: E402

SHARING = "403 from the export endpoint."          # a failure no retry can fix: one try, so no sleeping in the test


@pytest.fixture
def w(tmp_path, monkeypatch):
    monkeypatch.setattr(csl.fcs, "alert_paths", lambda: [tmp_path / "desk" / "CUSTOMER-SHEET-FETCH-FAILED.txt"])
    monkeypatch.setenv("CFP_SMTP_PASS", FAKE_PASS)
    return World(tmp_path)


def status(w, kind="saturday"):
    return json.loads(w.status.read_text(encoding="utf-8"))[kind]


# ------------------------------------------------------------------ D67: the freshness rule at the 02:00 load
def test_a_failing_load_with_a_10_hour_old_copy_PROCEEDS_yellow(w):
    w.copy("utility", NOW - timedelta(hours=10))
    code, res, lines, clock = w.load([{"utility": SHARING}], env={})
    assert code == 0 and res["failed"] == ["utility"], "exit 0: the research starts, on that copy"
    assert clock.slept == [] and len(w.calls) == 1, "no wait: a fix cannot make the copy fresher than it is"
    assert [s[0] for s in w.sent] == ["CFP customer sheets YELLOW - load failed, research proceeding on copies up to 10 hours old"]
    body = w.sent[0][1]
    assert "is NOT held. It proceeds" in body and "10.0 hours old" in body and "YELLOW, not green" in body and "HOW TO FIX IT" in body and body.isascii()
    assert "D67" in body and csl.SUBJECT not in [s[0] for s in w.sent], "the CRITICAL email is not sent for a covered failure"
    assert lines[-1].startswith("SHEET LOAD: YELLOW - 1 of 4 sheet(s) did not load (utility; cause: sharing); the research PROCEEDS on copies up to 10.0 hours old (limit 24 h)")
    st = status(w)
    assert st["verdict"] == "COPIES" and st["failed"] == ["utility"] and "10.0 h old" in st["note"]


def test_a_failing_load_with_a_30_hour_old_copy_HOLDS(w):
    w.copy("utility", NOW - timedelta(hours=30))
    code, res, lines, clock = w.load([{"utility": SHARING}], env={})
    assert code == csl.HELD_EXIT == 6 and res["failed"] == ["utility"]
    assert [s[0] for s in w.sent] == [csl.SUBJECT, csl.SUBJECT_HELD], "the CRITICAL email, the 2 hour wait, then HELD"
    assert "A failed sheet does NOT hold the research if its newest copy is no older than 24 hours (your rule, D67). That is not the case here" in w.sent[0][1]
    assert "Utility Global conferences sheet: 30.0 hours old" in w.sent[0][1]
    assert clock.now() == NOW + timedelta(hours=2) and len(w.calls) == 13
    assert status(w)["verdict"] == "HELD" and lines[-1].startswith("SHEET LOAD: HELD")


def test_a_healthy_load_proceeds_green_and_sends_nothing(w):
    code, res, lines, clock = w.load([{}], env={})
    assert code == 0 and not res["failed"] and not w.sent and lines[-1].startswith("SHEET LOAD: HEALTHY")
    assert status(w)["verdict"] == "HEALTHY"


def test_no_copy_at_all_holds(w):
    code, *_ = w.load([{"utility": SHARING}], env={})
    assert code == 6


def test_every_failed_sheet_needs_a_fresh_copy_not_just_one_of_them(w):
    w.copy("utility", NOW - timedelta(hours=5))                # covered
    w.copy("arnica", NOW - timedelta(hours=40))                # not covered
    code, res, _l, _c = w.load([{"utility": SHARING, "arnica": SHARING}], env={})
    assert code == 6 and sorted(res["failed"]) == ["arnica", "utility"]


def test_the_limit_is_a_setting_clamped_to_48_and_zero_switches_the_fallback_off(w):
    assert csl.max_age_hours({}) == 24 and csl.max_age_hours({"CFP_SHEETS_MAX_AGE_HOURS": "6"}) == 6 and csl.max_age_hours({"CFP_SHEETS_MAX_AGE_HOURS": "x"}) == 24
    assert csl.max_age_hours({"CFP_SHEETS_MAX_AGE_HOURS": "500"}) == 48, "never above 2 days: the context step calls an older copy stale"
    assert csl.max_age_hours({"CFP_SHEETS_MAX_AGE_HOURS": "-3"}) == 0
    w.copy("utility", NOW - timedelta(hours=10))
    assert w.load([{"utility": SHARING}], env={"CFP_SHEETS_MAX_AGE_HOURS": "6"})[0] == 6, "a 10 h copy is too old for a 6 h limit"
    assert w.load([{"utility": SHARING}], env={"CFP_SHEETS_MAX_AGE_HOURS": "0"})[0] == 6, "limit 0: always hold"
    w.copy("arnica", NOW - timedelta(hours=40))
    assert w.load([{"arnica": SHARING}], env={"CFP_SHEETS_MAX_AGE_HOURS": "500"})[0] == 0, "500 is clamped to 48: a 40 h copy is within it"


def test_a_60_hour_copy_is_over_the_48_hour_clamp_even_when_the_setting_asks_for_500(w):
    w.copy("arnica-awards", NOW - timedelta(hours=60))
    assert w.load([{"arnica-awards": SHARING}], env={"CFP_SHEETS_MAX_AGE_HOURS": "500"})[0] == 6


def test_the_48_hour_clamp_matches_the_two_day_stale_rule_of_the_context_step():
    import customer_row_context as crc
    assert csl.MAX_AGE_CAP_H == crc.STALE_AFTER_DAYS * 24, "if these ever differ, a copy the load accepts could be called stale by the context step"


def test_a_sheet_that_loads_during_the_wait_leaves_only_covered_sheets_and_the_wait_ends_yellow(w):
    w.copy("arnica", NOW - timedelta(hours=30))               # stale: holds the run at first
    w.copy("utility", NOW - timedelta(hours=8))               # covered
    script = [{"arnica": SHARING, "utility": SHARING}, {"arnica": SHARING, "utility": SHARING}, {"utility": SHARING}]
    code, res, lines, clock = w.load(script, env={})
    assert code == 0 and res["failed"] == ["utility"], "arnica loaded during the wait; utility is covered by its 8 h copy"
    assert clock.now() < NOW + timedelta(hours=2), "it stopped waiting as soon as only covered sheets were left"
    subjects = [s[0] for s in w.sent]
    assert subjects[0] == csl.SUBJECT and subjects[-1].startswith("CFP customer sheets YELLOW") and csl.SUBJECT_HELD not in subjects
    assert lines[-1].startswith("SHEET LOAD: YELLOW") and status(w)["verdict"] == "COPIES"


def test_the_freshness_rule_applies_only_when_the_hold_is_wired(w, monkeypatch):
    """Before ACT-75 is in the live script (hold_wired False) a failed load behaves as on 11-10: 2 h wait, then the old copy, DEGRADED."""
    monkeypatch.setattr(csl, "hold_wired", lambda markets=None: False)
    w.copy("utility", NOW - timedelta(hours=10))
    code, res, lines, clock = w.load([{"utility": SHARING}], env={})
    assert code == 1 and clock.now() == NOW + timedelta(hours=2) and lines[-1].startswith("SHEET LOAD: DEGRADED")
    assert not any("YELLOW" in s[0] for s in w.sent)


def test_the_yellow_email_does_not_use_up_the_one_critical_email_a_day_but_covers_the_dead_man(w):
    w.copy("utility", NOW - timedelta(hours=10))
    w.load([{"utility": SHARING}], env={})
    (code, lines), _c = deadman(w, task={"state": "Ready", "last_run": NOW}, status_path=w.status)
    assert code == 0 and lines[0].startswith("SHEET DEADMAN: YELLOW") and "Nothing sent" in lines[0]
    assert len(w.sent) == 1, "the 03:00 check sends nothing after a YELLOW proceed"


def test_the_dead_man_still_sends_the_critical_email_when_no_yellow_was_recorded(w):
    logs = w.tmp / "logs"
    logs.mkdir()
    log = logs / "run_monthly_20261114-020001.log"
    log.write_text("nothing about sheets\n", encoding="utf-8")
    old = (NOW - timedelta(hours=2)).timestamp()
    os.utime(log, (old, old))
    for c in ("arnica", "arnica-awards", "utility-awards"):
        w.copy(c, NOW)
    (code, lines), _c = deadman(w, task={"state": "Ready", "last_run": NOW}, status_path=w.status)
    assert code == 1 and "the research ran but today's copies are missing" in lines[0]


def test_the_recap_and_the_gate_say_yellow():
    from scripts.weekend_recap import saturday_recap
    from scripts import release_gate as rg
    log = ("=== run_monthly exit code: 0 ===\nSHEET LOAD: YELLOW - 1 of 4 sheet(s) did not load (utility; cause: sharing); the research PROCEEDS on copies up to 9.8 hours "
           "old (limit 24 h): utility 9.8 h; email sent; evidence: x.json\n")
    subject, text, _ = saturday_recap(log, None, Path("."), "saturday", None)
    assert "YELLOW: customer sheets did not load, research used copies up to 10 hours old" in subject and "DEGRADED" not in subject and "HELD" not in subject
    assert "Customer sheets: YELLOW - 1 of 4" in text
    o = SimpleNamespace(on=date(2026, 11, 15))
    c = rg.check_sheet_load(o, {"saturday": {"date": "2026-11-14", "verdict": "COPIES", "failed": ["utility"], "note": "proceeding on copies up to 9.8 h old (limit 24 h)"}})
    assert c["status"] == "WARN" and c["summary"].startswith("YELLOW: Saturday's load failed") and any("9.8 h old" in r for r in c["rows"])


# ------------------------------------------------------------------ the daytime check
THU_0730 = datetime(2026, 11, 12, 7, 30)
FRI_1815 = datetime(2026, 11, 13, 18, 15)
GOOD = {"verdict": "GREEN", "reason": "CUSTOMER CONTEXT: HEALTHY - 82 of 86 research rows carry the customer's row", "line": "HEALTHY - 82 of 86", "lint": []}


def run_daytime(w, kind, at, script, rehearsal=GOOD, env=None):
    clock = Clock(at)
    return sdc.daytime(kind, now=clock.now, snapshots=w.snaps, config=w.config, env={} if env is None else env, mailer=w.mailer, state=w.state, qa_root=w.qa,
                       runner=w.runner(script, clock), sleep=clock.sleep, rehearse_fn=lambda k: rehearsal, status_path=w.tmp / "daytime.json", alert_files=w.desk), clock


def test_the_window_is_the_next_0200_of_the_research_it_protects():
    assert sdc.next_window("friday", THU_0730) == datetime(2026, 11, 13, 2, 0)
    assert sdc.next_window("saturday", FRI_1815) == datetime(2026, 11, 14, 2, 0)
    assert sdc.next_window("friday", datetime(2026, 11, 13, 3, 0)) == datetime(2026, 11, 20, 2, 0), "after Friday's window: next week's"
    assert sdc.next_window("saturday", datetime(2026, 11, 14, 1, 0)) == datetime(2026, 11, 14, 2, 0)
    assert sdc.KIND_BY_WEEKDAY == {3: "friday", 4: "saturday"}


def test_daytime_green_sends_nothing_saves_the_copies_and_clears_an_old_alert(w):
    w.desk[0].parent.mkdir(exist_ok=True)
    w.desk[0].write_text("old alert", encoding="utf-8")
    (code, lines), _c = run_daytime(w, "friday", THU_0730, [{}])
    assert code == 0 and not w.sent and lines[-1].startswith("SHEET DAYTIME: GREEN - all 4 sheet(s) loaded; context rehearsal GREEN; 18.5 h before the Fri 02:00 research")
    assert not w.desk[0].exists()
    assert all(csl.newest_copy(c, w.snaps) for c in csl.ALL_CLIENTS), "a real load: the copies are saved"
    assert json.loads((w.tmp / "daytime.json").read_text(encoding="utf-8"))["overall"] == "GREEN"


def test_daytime_a_needed_sheet_failing_with_a_copy_that_will_still_be_fresh_at_0200_is_yellow(w):
    w.copy("arnica-awards", THU_0730 - timedelta(hours=4))      # 4 h now, 22.5 h at Friday 02:00
    (code, lines), _c = run_daytime(w, "friday", THU_0730, [{"arnica-awards": SHARING}])
    assert code == 2 and lines[-1].startswith("SHEET DAYTIME: YELLOW")
    subj, body = w.sent[0][0], w.sent[0][1]
    assert subj.startswith("CFP customer sheets 07:30 check: YELLOW - ") and "18.5 h before 02:00" in subj
    assert "22.5 h old at 02:00, within the 24 h limit" in body and "would still proceed on the copy" in body and body.isascii()


def test_daytime_a_needed_sheet_whose_copy_will_be_too_old_at_0200_is_red_with_the_deadline(w):
    taken = THU_0730 - timedelta(hours=10)                      # 10 h now, 28.5 h at 02:00: too old
    w.copy("arnica-awards", taken)
    (code, lines), _c = run_daytime(w, "friday", THU_0730, [{"arnica-awards": SHARING}])
    assert code == 1 and lines[-1].startswith("SHEET DAYTIME: RED")
    body = w.sent[0][1]
    assert "28.5 h old at 02:00, over the 24 h limit" in body and "would be HELD unless its own 02:00 load succeeds" in body
    assert f"too old after {taken + timedelta(hours=24):%a %H:%M}" in body and "HOW TO FIX IT" in body and "--clients arnica-awards --once" in body


def test_daytime_no_copy_at_all_for_a_needed_sheet_is_red(w):
    (code, _l), _c = run_daytime(w, "friday", THU_0730, [{"utility-awards": SHARING}])
    assert code == 1 and "there is no copy" in w.sent[0][1]


def test_daytime_a_failed_sheet_tomorrow_does_not_need_is_only_yellow(w):
    """Thursday protects Friday's awards: a failing conference sheet matters for Saturday, so it is a note, not a red."""
    (code, lines), _c = run_daytime(w, "friday", THU_0730, [{"utility": SHARING}])
    assert code == 2 and "tomorrow's research does not need it" in w.sent[0][1]


def test_daytime_friday_needs_all_four_sheets_for_saturday(w):
    w.copy("utility", FRI_1815 - timedelta(hours=20))           # 20 h now + 7.75 h = 27.75 h at Saturday 02:00
    (code, lines), _c = run_daytime(w, "saturday", FRI_1815, [{"utility": SHARING}])
    assert code == 1 and "7.8 hours from now" in w.sent[0][1] and "27.8 h old at 02:00, over the 24 h limit" in w.sent[0][1]


def test_daytime_a_failed_context_rehearsal_is_red_even_when_every_sheet_loaded(w):
    bad = {"verdict": "RED", "reason": "the writer was started with arguments it does not accept (a usage error): usage:", "line": None, "lint": ["line 414: $ccArgs ..."]}
    (code, lines), _c = run_daytime(w, "friday", THU_0730, [{}], rehearsal=bad)
    assert code == 1 and "context rehearsal RED" in lines[-1]
    body = w.sent[0][1]
    assert "THE CUSTOMER CONTEXT STEP" in body and "usage error" in body and "line 414" in body and "WITHOUT it" in body
    assert "the context step would fail" in w.sent[0][0] and w.sent[0][0].startswith("CFP customer sheets 07:30 check: RED - ")


def test_daytime_a_degraded_context_rehearsal_is_yellow(w):
    (code, _l), _c = run_daytime(w, "friday", THU_0730, [{}], rehearsal={"verdict": "YELLOW", "reason": "CUSTOMER CONTEXT: DEGRADED - x", "line": "DEGRADED - x", "lint": []})
    assert code == 2 and "the context step is degraded" in w.sent[0][0]


def test_daytime_emails_never_use_up_the_critical_email_of_the_02_load(w):
    run_daytime(w, "friday", THU_0730, [{"arnica-awards": SHARING}])
    run_daytime(w, "friday", THU_0730 + timedelta(hours=10, minutes=45), [{"arnica-awards": SHARING}])
    assert len(w.sent) == 2, "a second daytime alert the same day is sent"
    assert csl.already_sent(THU_0730.date(), w.state) is None, "and the once-a-day CRITICAL state is untouched"
    for _s, b, _k in w.sent:
        assert FAKE_PASS not in b


def test_daytime_auto_does_nothing_off_thursday_and_friday(monkeypatch, capsys):
    class Mon(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 9, 7, 30)
    monkeypatch.setattr(sdc, "datetime", Mon)
    assert sdc.main(["--kind", "auto"]) == 0
    assert "nothing to check today" in capsys.readouterr().out


# ------------------------------------------------------------------ step 1.20: the context step is RUN, linted, and watched at 03:00
def test_the_lint_flags_a_variable_built_by_an_if_expression_and_then_splatted():
    bad = "$ccArgs = if ($x) { @('--clear') } else { @('--apply') }\n& $py $s @ccArgs\n"
    assert len(rh.lint_splat(bad)) == 1 and "line 1" in rh.lint_splat(bad)[0]
    assert not rh.lint_splat("$ccArgs = @(if ($x) { '--clear' } else { '--apply' })\n& $py $s @ccArgs\n")
    assert not rh.lint_splat("$kind = if ($m) { 'friday' } else { 'saturday' }\nWrite-Host $kind\n"), "an if-expression that is never splatted is fine"
    assert not rh.lint_splat("$awArgs = @()\nif ($e) { $awArgs = @('--apply') }\n& $py @awArgs\n")


@pytest.mark.parametrize("out,code,verdict", [
    ("CUSTOMER CONTEXT: HEALTHY - 82 of 86 research rows carry the customers row", 0, "GREEN"),
    ("CUSTOMER CONTEXT: OFF - the switch is off", 0, "GREEN"),
    ("CUSTOMER CONTEXT: DEGRADED - 100 of 187 research rows carry the customers row", 0, "YELLOW"),
    ("CUSTOMER CONTEXT: HEALTHY - 0 of 187 research rows carry the customers row", 0, "RED"),
    ("CUSTOMER CONTEXT: FAILED - the context could not be built", 0, "RED"),
    ("CUSTOMER CONTEXT: UNKNOWN - interpreter or script not found", 0, "RED"),
    ("CUSTOMER CONTEXT: BROKEN - 3 of 4 research rows carry the customers row", 0, "RED"),        # Codex 2026-11-13: an unrecognised verdict word used to be GREEN
    ("CUSTOMER CONTEXT: HEALTHY - 0 of 0 research rows carry the customers row", 0, "YELLOW"),     # nothing to research: not provable, not a failure
    ("CUSTOMER CONTEXT: HEALTHY - all fine", 0, "YELLOW"),                                         # no row count to check
    ("usage: customer_row_context.py [-h]\ncustomer_row_context.py: error: unrecognized arguments: - - a p p l y", 0, "RED"),
    ("", 0, "RED"),
    ("RESEARCH HELD (ACT-76): x\nCUSTOMER CONTEXT: FAILED - x", 6, "RED"),
])
def test_the_rehearsal_classifies_what_the_block_printed(out, code, verdict):
    assert rh.classify(out, code)[0] == verdict


MINI_SCRIPT = ("# header\n# ---- STEP 0a4: CUSTOMER CONTEXT (ACT-72) ----\n" + rh.START + "\n"
               "    $ccPy  = \"C:\\Users\\matts\\cfp-monitor\\.venv\\Scripts\\python.exe\"\n"
               "    $ccPy_ = \"" + rh.WRITER + "\"\n"
               "    & $ccPy \"" + rh.ANSWERS + "\" | Out-Null\n"
               "    & $ccPy \"" + rh.NOTICE + "\" --held-notice context\n"
               "}\n\n# ---- STEP 0b: CANARY ----\nwork\n")


def test_the_rehearsal_runs_a_copy_of_the_block_against_scratch_and_cleans_up(tmp_path):
    md = tmp_path / "Markets"
    (md / "customer_snapshots").mkdir(parents=True)
    (md / "run_monthly.ps1").write_text(MINI_SCRIPT, encoding="utf-8")
    (md / "Awards_input.csv").write_text("CONFERENCE\nx\n", encoding="utf-8")
    db = tmp_path / "live.db"
    db.write_text("db", encoding="utf-8")
    seen = {}

    def fake_run(cmd, **kw):
        harness = Path(cmd[-1])
        seen["text"] = harness.read_text(encoding="utf-8")
        seen["dir"] = harness.parent
        return SimpleNamespace(returncode=0, stdout="CUSTOMER CONTEXT: HEALTHY - 5 of 6 research rows carry the customers row\nREHEARSAL-CONTINUED\n", stderr="")
    tmp_root = Path(tempfile.gettempdir())
    before = set(tmp_root.glob("step0a4_*"))
    res = rh.rehearse("friday", markets=md, db=db, run=fake_run)
    assert res["verdict"] == "GREEN" and res["exit"] == 0 and res["line"].startswith("HEALTHY - 5 of 6")
    t = seen["text"]
    assert "$Markets = @('Awards'); $liveMarkets = @()" in t and "writer_shim.py" in t and "answers_shim.py" in t and "notice_stub.py" in t
    assert rh.WRITER not in t and rh.NOTICE not in t and rh.ANSWERS not in t, "the block must never point at the live writer or the real email sender"
    assert not seen["dir"].exists() and set(tmp_root.glob("step0a4_*")) == before, "the scratch copies of the customer's text are deleted"
    assert (md / "run_monthly.ps1").read_text(encoding="utf-8") == MINI_SCRIPT, "the live script is never changed"
    res = rh.rehearse("saturday", markets=md, db=db, run=lambda cmd, **kw: SimpleNamespace(returncode=0, stdout="usage: x\nerror: unrecognized arguments: - - a p p l y", stderr=""))
    assert res["verdict"] == "RED" and "usage error" in res["reason"]


def test_the_rehearsal_is_red_not_a_crash_when_the_script_has_no_step_0a4(tmp_path):
    md = tmp_path / "Markets"
    md.mkdir()
    (md / "run_monthly.ps1").write_text("# nothing\n", encoding="utf-8")
    (tmp_path / "db").write_text("x", encoding="utf-8")
    res = rh.rehearse("friday", markets=md, db=tmp_path / "db")
    assert res["verdict"] == "RED" and "no STEP 0a4 marker" in res["reason"]


CTX_LOG = "Step 1: Cost preview\nCUSTOMER CONTEXT: {line}\nCANARY PASSED\n"


@pytest.mark.parametrize("line,problem", [
    ("HEALTHY - 138 of 187 research rows carry the customer's row", False),
    ("DEGRADED - 100 of 187 research rows carry the customer's row", False),
    ("OFF - the switch is off", False),
    ("FAILED - the context could not be built", True),
    ("UNKNOWN - interpreter or script not found", True),
    ("HEALTHY - 0 of 187 research rows carry the customer's row", True),
    ("BROKEN - 3 of 4 research rows carry the customer's row", True),
    ("HEALTHY - 0 of 0 research rows carry the customer's row", False),
])
def test_the_0300_context_watch_reads_the_verdict_line(line, problem):
    assert bool(csl.context_problem(CTX_LOG.format(line=line))) is problem


def test_the_0300_context_watch_stays_quiet_when_the_step_has_not_had_its_turn_or_the_run_was_held():
    assert csl.context_problem("SHEET WAIT: try at 02:20 - 1 still failing\n") is None, "still waiting for the sheets"
    assert csl.context_problem("RESEARCH HELD (ACT-75): x\nStep 1: Cost preview\n") is None, "a held run has its own email"
    assert "no CUSTOMER CONTEXT line" in csl.context_problem("Step 1: Cost preview\nCANARY PASSED\n")


def test_the_0300_context_watch_sends_one_critical_email_and_nothing_when_fine(w):
    logs = w.tmp / "logs"
    logs.mkdir()
    (logs / "run_monthly_20261114-020001.log").write_text("Step 1: Cost preview\nCANARY PASSED\n", encoding="utf-8")
    clock = Clock(NOW.replace(hour=3, minute=0))
    code, lines = csl.context_watch("saturday", logs, now=clock.now, mailer=w.mailer, state=w.state)
    assert code == 1 and "CONTEXT FAILED" in lines[0] and [s[0] for s in w.sent] == [csl.SUBJECT_CONTEXT_RUNNING]
    body = w.sent[0][1]
    assert "RUNNING, but WITHOUT the customer context" in body and "customer_row_context.py" in body and "--markets Cybersecurity,Utility" in body and body.isascii()
    (logs / "run_monthly_20261114-020001.log").write_text(CTX_LOG.format(line="HEALTHY - 138 of 187 research rows carry the customer's row"), encoding="utf-8")
    code, lines = csl.context_watch("saturday", logs, now=clock.now, mailer=w.mailer, state=w.state)
    assert code == 0 and "CONTEXT OK" in lines[0] and len(w.sent) == 1
    assert csl.context_watch("friday", w.tmp / "no-logs", now=clock.now, mailer=w.mailer)[0] == 0, "no run today: the three-case check says so"


# ------------------------------------------------------------------ the Codex review of 2026-11-13: boundaries, a missing config entry, the rehearsal's isolation
def test_the_age_limit_is_compared_unrounded_to_the_second(w):
    """A copy 24 h and 10 s old used to be rounded to 24.00 and pass; 23 h 59 min passes."""
    w.copy("utility", NOW - timedelta(hours=24, seconds=10))
    assert w.load([{"utility": SHARING}], env={})[0] == 6
    w.copy("arnica", NOW - timedelta(hours=23, minutes=59))
    assert w.load([{"arnica": SHARING}], env={})[0] == 0


def test_a_copy_dated_in_the_future_never_counts_as_fresh(w):
    w.copy("utility", NOW + timedelta(hours=10))                 # still in the future after the 2 hour wait: the test clock advances while it waits
    assert w.load([{"utility": SHARING}], env={})[0] == 6


def test_judge_sheets_compares_unrounded_and_rejects_future_copies():
    ages = {"a": {"age_h": 5.0, "taken": datetime(2026, 11, 12, 2, 30), "copy": "a.csv"}}
    hours_left = 19.04                                           # 5.0 + 19.04 = 24.04 h at 02:00: over the 24 h limit although it displays as 24.0
    r = sdc.judge_sheets(["a"], ["a"], ["a"], ages, hours_left, 24.0)["a"]
    assert r["level"] == "RED" and r["age_at_window"] == 24.0
    assert sdc.judge_sheets(["a"], ["a"], ["a"], ages, 18.99, 24.0)["a"]["level"] == "YELLOW", "23.99 h at 02:00 is within the limit"
    future = {"a": {"age_h": -3.0, "taken": datetime(2026, 11, 12, 12, 0), "copy": "a.csv"}}
    r = sdc.judge_sheets(["a"], ["a"], ["a"], future, 10.0, 24.0)["a"]
    assert r["level"] == "RED" and "dated in the future" in r["why"]


def test_daytime_a_needed_sheet_missing_from_the_settings_file_is_red_not_skipped(w):
    cfg = json.loads(w.config.read_text(encoding="utf-8"))
    del cfg["clients"]["arnica-awards"]
    w.config.write_text(json.dumps(cfg), encoding="utf-8")
    (code, lines), _c = run_daytime(w, "friday", THU_0730, [{}])
    assert code == 1 and lines[-1].startswith("SHEET DAYTIME: RED")
    assert "Arnica awards sheet" in w.sent[0][1] and "not in the sheet settings file" in w.sent[0][1]


def test_the_rehearsal_refuses_to_run_a_block_that_names_a_script_it_cannot_redirect(tmp_path):
    md = tmp_path / "Markets"
    (md / "customer_snapshots").mkdir(parents=True)
    (tmp_path / "db").write_text("x", encoding="utf-8")
    ran = []
    other = MINI_SCRIPT.replace(rh.NOTICE, r"C:\Users\matts\somewhere-else\send_mail.py")
    (md / "run_monthly.ps1").write_text(other, encoding="utf-8")
    res = rh.rehearse("friday", markets=md, db=tmp_path / "db", run=lambda *a, **k: ran.append(a))
    assert res["verdict"] == "RED" and "unsafe to rehearse" in res["reason"] and "send_mail.py" in res["reason"] and not ran, "nothing may run"
    (md / "run_monthly.ps1").write_text(MINI_SCRIPT.replace(rh.WRITER, r"C:\other\writer.py"), encoding="utf-8")
    res = rh.rehearse("friday", markets=md, db=tmp_path / "db", run=lambda *a, **k: ran.append(a))
    assert res["verdict"] == "RED" and "unsafe to rehearse" in res["reason"] and not ran


def test_a_scratch_folder_that_cannot_be_deleted_is_said_not_hidden(tmp_path, monkeypatch):
    md = tmp_path / "Markets"
    (md / "customer_snapshots").mkdir(parents=True)
    (md / "run_monthly.ps1").write_text(MINI_SCRIPT, encoding="utf-8")
    (tmp_path / "db").write_text("x", encoding="utf-8")
    monkeypatch.setattr(rh.shutil, "rmtree", lambda *a, **k: None)
    good = lambda cmd, **kw: SimpleNamespace(returncode=0, stdout="CUSTOMER CONTEXT: HEALTHY - 5 of 6 research rows carry the customers row\n", stderr="")
    res = rh.rehearse("friday", markets=md, db=tmp_path / "db", run=good)
    left = Path(res["leftover"])
    try:
        assert res["verdict"] == "YELLOW" and "could not be deleted" in res["reason"] and "delete it by hand" in res["reason"] and left.exists()
    finally:
        shutil.rmtree(left, ignore_errors=True)

# ------------------------------------------------------------------ Codex second pass, 2026-11-13
def test_judge_sheets_uses_the_unrounded_hours_left():
    ages = {"a": {"age_h": 23.0, "taken": datetime(2026, 11, 12, 8, 30), "copy": "a.csv"}}
    assert sdc.judge_sheets(["a"], ["a"], ["a"], ages, 1.004, 24.0)["a"]["level"] == "RED", "23.0 + 1.004 = 24.004 h at 02:00"
    assert sdc.judge_sheets(["a"], ["a"], ["a"], ages, 0.996, 24.0)["a"]["level"] == "YELLOW"


def test_a_stray_file_name_in_a_snapshot_folder_does_not_hide_a_valid_fresh_copy(w):
    good = w.copy("utility", NOW - timedelta(hours=5))
    (good.parent / "utility_bad.csv").write_text("x\n", encoding="utf-8")        # sorts after the dated name, carries no load time
    assert csl.newest_copy("utility", w.snaps) == good
    code, res, _l, _c = w.load([{"utility": SHARING}], env={})
    assert code == 0 and res["failed"] == ["utility"], "covered by the 5 h copy: YELLOW, not held"


def test_a_context_watch_that_cannot_run_exits_1_and_says_so(w, monkeypatch):
    logs = w.tmp / "logs"
    logs.mkdir()
    (logs / "run_monthly_20261114-020001.log").write_text("Step 1: Cost preview\n", encoding="utf-8")
    monkeypatch.setattr(csl, "context_problem", lambda text: (_ for _ in ()).throw(PermissionError("log is locked")))
    clock = Clock(NOW.replace(hour=3, minute=0))
    code, lines = csl.context_watch("saturday", logs, now=clock.now, mailer=w.mailer, state=w.state)
    assert code == 1 and "CONTEXT UNKNOWN" in lines[0] and "PermissionError" in lines[0]
    assert [s[0] for s in w.sent] == ["CFP customer context watch could not run - CRITICAL ERROR"]

# ------------------------------------------------------------------ the Thursday pre-flight (t7) runs the step
def test_the_thursday_preflight_t7_runs_the_step_and_fails_loudly(tmp_path):
    from test_release_gate_thursday import thursday_world, THU, THU_NOW, ENV_ALL, chk
    from scripts import release_gate as rg
    w = thursday_world(tmp_path)

    def t7(r):
        o = rg.Opts(THU, THU_NOW, True, w.md, w.db, w.snaps, None, w.weekly, None, w.qa, w.commit, w.given, w.ledger)
        return chk(rg.evaluate_thursday(o, ENV_ALL, w.patches, step_rehearsal=(lambda o: r) if r is not None else None), "t7")
    ok = {"verdict": "GREEN", "reason": "CUSTOMER CONTEXT: HEALTHY - 82 of 86 research rows"}
    assert t7({"friday": ok, "saturday": ok})["status"] == "PASS"
    red = {"verdict": "RED", "reason": "the writer was started with arguments it does not accept (a usage error): usage:"}
    c = t7({"friday": red, "saturday": ok})
    assert c["status"] == "FAIL" and "would NOT build the customer context" in c["summary"] and "usage error" in c["summary"] and "WITHOUT it" in c["summary"]
    assert t7({"friday": ok, "saturday": {"verdict": "YELLOW", "reason": "DEGRADED - x"}})["status"] == "WARN"
    assert t7(None)["status"] == "PASS" and "not tested" in t7(None)["summary"]


# ------------------------------------------------------------------ the registration script (operator-run; only -DryRun and -WhatIf are executed)
SCRIPT = ROOT / "scripts" / "register_sheet_daytime.ps1"
TEXT = SCRIPT.read_text(encoding="utf-8")
PS = shutil.which("powershell")
needs_ps = pytest.mark.skipif(PS is None or sys.platform != "win32", reason="Windows PowerShell is needed")


def test_the_registration_script_is_ascii_and_registers_only_inside_should_process():
    TEXT.encode("ascii")
    assert TEXT.count("Register-ScheduledTask -TaskName") == 1
    assert TEXT.index("ShouldProcess($TaskName") < TEXT.index("Register-ScheduledTask -TaskName")
    assert "[CmdletBinding(SupportsShouldProcess = $true)]" in TEXT


def test_the_task_runs_thursday_and_friday_at_0730_and_1815_and_wakes_the_pc():
    assert "[string]$TaskName = 'CFP Sheet Daytime Load'" in TEXT and "[string]$Morning  = '07:30'" in TEXT and "[string]$Evening  = '18:15'" in TEXT
    assert TEXT.count("-Weekly -DaysOfWeek Thursday, Friday -At") == 2 and "-Trigger @($triggerA, $triggerB)" in TEXT
    assert "sheet_daytime_check.py" in TEXT and "--kind auto" in TEXT
    assert "$settings.WakeToRun = $true" in TEXT and "-ExecutionTimeLimit (New-TimeSpan -Minutes 45)" in TEXT
    assert "-StartWhenAvailable" in TEXT and "-MultipleInstances IgnoreNew" in TEXT and "-LogonType Interactive -RunLevel Limited" in TEXT
    assert "REFUSED: a task named '$TaskName' is already registered" in TEXT


@needs_ps
def test_dryrun_and_whatif_register_nothing():
    def exists():
        return subprocess.run([PS, "-NoProfile", "-Command", "[bool](Get-ScheduledTask -TaskName 'CFP Sheet Daytime Load' -ErrorAction SilentlyContinue)"],
                              capture_output=True, text=True).stdout.strip()
    before = exists()
    for flag, marker in (("-DryRun", "(-DryRun: nothing was registered.)"), ("-WhatIf", "(-WhatIf: nothing was registered.)")):
        out = subprocess.run([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), flag], capture_output=True, text=True)
        if "REFUSED: a task named" in out.stdout:
            pytest.skip("the task is already registered on this PC")
        assert out.returncode == 0 and marker in out.stdout and "07:30 and at 18:15" in out.stdout and "--kind auto" in out.stdout
        assert "0 GREEN, 2 YELLOW, 1 RED" in out.stdout
    assert exists() == before


def test_the_manifest_entry_exists_and_is_flagged_for_verdict_exit_codes():
    man = Path(r"C:\Users\matts\agentos\tools\scheduled-tasks.manifest.json")
    if not man.exists():
        pytest.skip("the agentos manifest is not on this machine")
    entry = next((t for t in json.loads(man.read_text(encoding="utf-8"))["tasks"] if t["name"] == "CFP Sheet Daytime Load"), None)
    assert entry and entry["usesVerdictExitCodes"] is True and entry["needsPcOn"] is True and "07:30 and 18:15" in entry["schedule"]
