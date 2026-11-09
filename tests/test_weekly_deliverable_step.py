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


def test_a_step_that_finishes_is_ok_and_one_that_fails_is_recorded(tmp_path):
    ok_before = wd.HEALTH.snapshot("weekly_step")["ok"]
    bad_before = wd.HEALTH.snapshot("weekly_step")["step_failed"]
    assert wd.step("fine", [sys.executable, "-c", "print('done')"], tmp_path / "a.log", timeout=30) is True
    assert wd.step("broken", [sys.executable, "-c", "import sys; print('no'); sys.exit(2)"], tmp_path / "b.log", timeout=30) is False
    assert (tmp_path / "a.log").read_text(encoding="utf-8").strip() == "done"
    assert wd.HEALTH.snapshot("weekly_step")["ok"] == ok_before + 1
    assert wd.HEALTH.snapshot("weekly_step")["step_failed"] == bad_before + 1
