"""ACT-68: the release gate is the LAST step of the Monday build and can never change a publish."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("wd", ROOT / "scripts" / "weekly_deliverable.py")
wd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wd)


class Done:
    def __init__(self, out, code=0):
        self.stdout, self.returncode = out, code


def test_the_gate_line_is_returned_and_the_command_is_the_gate_with_the_build_folders(tmp_path):
    seen = []

    def runner(cmd, **kw):
        seen.append(cmd)
        return Done("noise\nGATE: GO WITH NOTES - CFP weekly pages: GO WITH NOTES - Conferences 204, Awards 128\nreport: x\n")
    line = wd.run_release_gate("2026-10-19", tmp_path / "work", "weekly", "markets", "db.sqlite", runner=runner)
    assert line.startswith("GATE: GO WITH NOTES")
    cmd = seen[0]
    assert cmd[1].endswith("release_gate.py") and cmd[cmd.index("--on") + 1] == "2026-10-19" and "--dry-run" not in cmd
    assert cmd[cmd.index("--work-dir") + 1] == str(tmp_path / "work") and cmd[cmd.index("--weekly-dir") + 1] == "weekly"
    wd.run_release_gate("2026-10-19", tmp_path, "w", "m", "d", dry_run=True, runner=runner)
    assert "--dry-run" in seen[1]


def test_a_gate_fault_is_reported_not_raised():
    def boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 900)
    assert wd.run_release_gate("2026-10-19", Path("."), "w", "m", "d", runner=boom).startswith("GATE: UNKNOWN - TimeoutExpired")
    assert wd.run_release_gate("2026-10-19", Path("."), "w", "m", "d", runner=lambda c, **k: Done("", 3)).startswith("GATE: UNKNOWN - the gate printed no verdict (exit 3)")


def test_the_gate_runs_after_the_publish_and_both_pages_ask_for_provisional_rows():
    src = (ROOT / "scripts" / "weekly_deliverable.py").read_text(encoding="utf-8")
    assert src.index("shutil.copy2(page, published / page.name)") < src.index("run_release_gate(stamp, work")
    assert '"--provisional-dir", md' in src
    conf = src[src.index('cmd = [PY, ROOT / "scripts/build_review_page.py", "-i", combined'):src.index('step("conferences page"')]
    assert '"--provisional-dir", md' in conf, "ACT-70: the conference page shows held rows as Provisional, with the failing field blanked"
