"""D13 (Matt, Daily Review 2026-11-09): the pages job moves to Sunday 01:00, when no person's Chrome is open. The real-Chrome rung is
mandatory (TROUBLESHOOTING.md), and until now only step 5 had it: steps 1 and 2a never did. These tests pin the conditions Home base
set: start it through start_cdp_chrome, close ONLY what the job opened on every exit path (normal end, error, a step killed at its
time limit, the task's 6 h limit), carry on and say so in plain words when Chrome will not start, and count each fetch method."""
from __future__ import annotations

import importlib.util
import os
import sys
import textwrap
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("wd_chrome", ROOT / "scripts" / "weekly_deliverable.py")
wd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wd)


class Chrome:
    """A fake Chrome: start() says whether WE started it; stop() is counted."""
    def __init__(self, started: bool, up: bool | None = None):
        self.started, self.up, self.stops = started, (started if up is None else up), 0

    def start(self):
        return self.started

    def is_up(self):
        return self.up

    def stop(self):
        self.stops += 1


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("CFP_CDP_URL", raising=False)


def test_a_chrome_we_started_is_offered_to_every_step_and_closed_once_at_the_end():
    c = Chrome(started=True)
    seen = {}

    def run():
        seen["env"] = os.environ.get("CFP_CDP_URL")
        seen["stops_during_run"] = c.stops
        return 0

    assert wd.with_real_chrome(run, c.start, c.stop, c.is_up, stop_after_s=None) == 0
    assert seen == {"env": "http://localhost:9222", "stops_during_run": 0}, "every step's environment carries the debug port"
    assert c.stops == 1 and wd.REAL_CHROME["state"] == "started"


def test_an_error_still_closes_the_chrome_we_started():
    c = Chrome(started=True)

    def run():
        raise RuntimeError("a step blew up")

    with pytest.raises(RuntimeError):
        wd.with_real_chrome(run, c.start, c.stop, c.is_up, stop_after_s=None)
    assert c.stops == 1


def test_a_step_killed_at_its_time_limit_does_not_leave_our_chrome_open(tmp_path):
    """The step's own kill_tree ends the step's process tree only; this run's Chrome is closed by with_real_chrome afterwards."""
    c = Chrome(started=True)
    slow = tmp_path / "slow.py"
    slow.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")

    def run():
        ok = wd.step("slow step", [sys.executable, slow], tmp_path / "slow.log", timeout=2)
        assert ok is False and "TIMEOUT after 2s" in (tmp_path / "slow.log").read_text(encoding="utf-8")
        return 2

    assert wd.with_real_chrome(run, c.start, c.stop, c.is_up, stop_after_s=None) == 2
    assert c.stops == 1


def test_the_timer_closes_our_chrome_before_the_task_limit_and_only_once():
    """A Task Scheduler kill runs no `finally`, so the close cannot wait for the end of the run."""
    c = Chrome(started=True)
    seen = {}

    def run():
        time.sleep(0.6)
        seen["stops_during_run"] = c.stops
        return 0

    wd.with_real_chrome(run, c.start, c.stop, c.is_up, stop_after_s=0.1)
    assert seen["stops_during_run"] == 1, "closed by the timer while the run was still going"
    assert c.stops == 1, "and not closed a second time at the end"


def test_a_chrome_someone_else_started_is_used_and_left_open():
    c = Chrome(started=False, up=True)
    assert wd.with_real_chrome(lambda: os.environ.get("CFP_CDP_URL") and 0, c.start, c.stop, c.is_up, stop_after_s=0.01) == 0
    time.sleep(0.05)
    assert c.stops == 0 and wd.REAL_CHROME["state"] == "already-running"


def test_no_chrome_the_run_carries_on_and_says_so_in_plain_words():
    c = Chrome(started=False, up=False)
    seen = {}

    def run():
        seen["env"] = os.environ.get("CFP_CDP_URL")
        return 0

    assert wd.with_real_chrome(run, c.start, c.stop, c.is_up, stop_after_s=None) == 0, "no Chrome never fails the run"
    assert seen["env"] is None and c.stops == 0
    assert wd.REAL_CHROME["note"].startswith("not available - Chrome could not be started")


def test_a_start_that_raises_counts_as_no_chrome():
    def boom():
        raise OSError("no chrome.exe")

    c = Chrome(started=False, up=False)
    assert wd.with_real_chrome(lambda: 0, boom, c.stop, c.is_up, stop_after_s=None) == 0
    assert wd.REAL_CHROME["state"] == "not-available" and c.stops == 0


EVIDENCE_LOG = textwrap.dedent("""\
    804 claim(s) across 6 page(s)
    [1/6] https://a.example/cfp  (1 claim(s))
            ok deadline         grounding page states 2027-01-31
    [2/6] https://b.example/cfp
            unreadable - page could not be read [HTTP 403]
    [3/6] https://c.example/cfp
            unreadable - page could not be read [TimeoutError]
    [4/6] https://d.example/cfp
            unreadable - page returned almost no text (0 chars)
    [5/6] https://e.example/cfp
    [6/6] https://f.example/cfp

    --- escalating 3 unreadable page(s) through the ladder ---
      [1/3] https://b.example/cfp -> cdp (8268c)
      [2/3] https://c.example/cfp -> still unreadable (playwright-fallback)
      [3/3] https://d.example/cfp -> crawl4ai (512c)
    EVIDENCE PASS: HEALTHY - every page was read or tried through the ladder
    """)
AWARDS_LOG = textwrap.dedent("""\
    136 cited award deadline(s) across 129 page(s)
      flat fetch read 83 of 129 page(s)
      escalating 3 page(s) the flat fetch did not settle
      [1/3] https://a.example/awards -> crawl4ai (21134c)
      [2/3] https://b.example/awards -> still unreadable (playwright-fallback)
      [3/3] https://c.example/awards -> still unreadable (cdp)
    """)


def test_fetch_methods_are_counted_for_the_evidence_re_read():
    rows = wd.fetch_method_rows("evidence re-read", EVIDENCE_LOG, "evidence")
    assert rows[0] == ("evidence re-read", "plain fetch", "6", "3", "3")
    assert rows[1] == ("evidence re-read", "browser ladder (all rungs)", "3", "2", "1")
    assert ("evidence re-read", "  read by cdp", "-", "1", "-") in rows
    assert ("evidence re-read", "  still unreadable at playwright-fallback", "-", "-", "1") in rows


def test_fetch_methods_are_counted_for_the_awards_check_and_a_missing_log_is_said():
    rows = wd.fetch_method_rows("awards check", AWARDS_LOG, "awards")
    assert rows[0] == ("awards check", "plain fetch", "129", "83", "46")
    assert rows[1] == ("awards check", "browser ladder (all rungs)", "3", "1", "2")
    assert ("awards check", "  still unreadable at cdp", "-", "-", "1") in rows
    assert wd.fetch_method_rows("awards check", "", "awards") == [("awards check", "log not found or empty", "-", "-", "-")]


def test_the_run_summary_carries_the_table_and_the_chrome_line(tmp_path):
    (tmp_path / "1_evidence.log").write_text(EVIDENCE_LOG, encoding="utf-8")
    wd.REAL_CHROME.update(state="not-available", note="not available - Chrome could not be started on port 9222")
    lines = wd.fetch_methods_lines(tmp_path)
    assert lines[0] == "## Fetch methods (steps 1 and 2a)"
    assert "Real Chrome: not available - Chrome could not be started on port 9222" in lines
    assert "| evidence re-read | plain fetch | 6 | 3 | 3 |" in lines
    assert "| awards check | log not found or empty | - | - | - |" in lines
