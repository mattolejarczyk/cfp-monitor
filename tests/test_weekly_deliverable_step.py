"""scripts/weekly_deliverable.py step(): a step that outlives its limit is stopped for real, with everything it started.

2026-11-09: the Monday evidence step timed out. step() used subprocess.run(timeout=), which kills the child only; on Windows the child is the
venv launcher, and the interpreter or a browser it started may live on and keep writing to the database while the later steps read it. The
same defect was fixed in weekend_import on 2026-11-07 and never carried over. The kill now goes through src/cfp_monitor/proc.kill_tree.
"""
from __future__ import annotations

import importlib.util
import sys
import textwrap
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("wd_step", ROOT / "scripts" / "weekly_deliverable.py")
wd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wd)


def test_a_timed_out_step_kills_the_grandchild_too_and_keeps_the_log(tmp_path):
    beat = tmp_path / "beat.txt"
    grandchild = tmp_path / "grandchild.py"
    grandchild.write_text(textwrap.dedent(f"""
        import time
        from pathlib import Path
        p = Path(r"{beat}")
        for _ in range(100):          # about 25 s, then it leaves on its own: a failed test leaves nothing behind
            p.write_text(str(time.time()))
            time.sleep(0.25)
    """), encoding="utf-8")
    child = tmp_path / "child.py"
    child.write_text(textwrap.dedent(f"""
        import subprocess, sys, time
        print("child start", flush=True)
        subprocess.Popen([sys.executable, r"{grandchild}"])
        time.sleep(60)
    """), encoding="utf-8")
    log = tmp_path / "1_evidence.log"
    before = wd.HEALTH.snapshot("weekly_step")["timed_out"]
    result = {}

    def go():
        result["ok"] = wd.step("evidence re-read", [sys.executable, child], log, timeout=2)

    t = threading.Thread(target=go, daemon=True)
    t.start()
    t.join(15)
    assert not t.is_alive(), "step() did not return within 15 s of a 2 s timeout"
    assert result["ok"] is False
    assert wd.HEALTH.snapshot("weekly_step")["timed_out"] == before + 1, "the timeout is recorded in the run health"
    text = log.read_text(encoding="utf-8")
    assert "child start" in text, "what the step printed before the kill is kept"
    assert "TIMEOUT after 2s - process tree killed" in text, "the log says the step was killed, and how"
    time.sleep(1.5)
    m1 = beat.stat().st_mtime
    time.sleep(1.5)
    assert beat.stat().st_mtime == m1, "the grandchild is still running: the process tree was not killed"


# --- D5 on Daily Review (Matt, 2026-11-09): "Do not publish; the email says NO-GO and how many pages were not read." ---
KILLED_LOG = """804 claim(s) across 6 page(s)
one visit per page; the ladder is climbed on failure

[1/6] https://a.example/cfp  (1 claim(s))
        ok deadline         grounding page states 2027-01-31
[2/6] https://b.example/cfp
        unreadable - page could not be read [HTTP 403]
[3/6] https://c.example/cfp
        unreadable - page could not be read [TimeoutError]
[4/6] https://d.example/cfp
        unreadable - page returned almost no text (0 chars)
[5/6] https://e.example/cfp  (1 claim(s))
        -- deadline         grounding nothing claimed for this field

--- escalating 3 unreadable page(s) through the ladder ---
  [1/3] https://b.example/cfp -> playwright-fallback (8268c)
  [2/3] https://c.example/cfp -> still unreadable (playwright-fallback)
"""


def test_a_killed_evidence_pass_counts_the_pages_it_never_read():
    """The 2026-11-09 shape: no verdict line. Page 6 was never visited; of 3 unreadable, the browser read 1. 1 + 2 = 3 of 6."""
    s = wd.evidence_shortfall(KILLED_LOG)
    assert s.startswith("3 of 6 cited pages were not read"), s
    assert "5 of 6 pages tried once; 1 of 3 unreadable pages read in a browser" in s


def test_the_budget_verdict_is_quoted_and_a_finished_pass_is_silent():
    budget = KILLED_LOG + ("\nEVIDENCE PASS: DEGRADED - the time budget (105 min) ended with 2 of 3 unreadable page(s) never tried in a browser; "
                           "their claims read 'unreadable' because we did not look.\n")
    assert wd.evidence_shortfall(budget) == "2 of 6 cited pages were never tried in a browser: the evidence re-read's time budget (105 min) ended first"
    assert wd.evidence_shortfall(KILLED_LOG + "\nEVIDENCE PASS: HEALTHY - every page was read or tried through the ladder\n") == ""
    assert wd.evidence_shortfall("") == "the evidence re-read did not finish and its log does not say how far it got"


def test_an_incomplete_evidence_pass_alone_makes_the_run_degraded():
    """As a rate it was 1 failed step in 9 and the run said HEALTHY. It is a hard failure now, so nothing publishes."""
    from src.cfp_monitor.run_health import RunHealth
    h = RunHealth("t")
    for _ in range(8):
        h.ok("weekly_step")
    h.fail("weekly_step", "timed_out", "evidence re-read after 7200s")
    assert h.verdict()[0] == "HEALTHY", "the old rate rule alone lets it through"
    h.fail("evidence_pass", "evidence_incomplete", "292 of 748 cited pages were not read")
    status, reasons = h.verdict()
    assert status == "DEGRADED" and any("evidence_incomplete" in r for r in reasons)
    assert "- evidence_pass / evidence_incomplete: 292 of 748 cited pages were not read" in h.report_lines()


def test_a_step_that_finishes_is_ok_and_one_that_fails_is_recorded(tmp_path):
    ok_before = wd.HEALTH.snapshot("weekly_step")["ok"]
    bad_before = wd.HEALTH.snapshot("weekly_step")["step_failed"]
    assert wd.step("fine", [sys.executable, "-c", "print('done')"], tmp_path / "a.log", timeout=30) is True
    assert wd.step("broken", [sys.executable, "-c", "import sys; print('no'); sys.exit(2)"], tmp_path / "b.log", timeout=30) is False
    assert (tmp_path / "a.log").read_text(encoding="utf-8").strip() == "done"
    assert wd.HEALTH.snapshot("weekly_step")["ok"] == ok_before + 1
    assert wd.HEALTH.snapshot("weekly_step")["step_failed"] == bad_before + 1
