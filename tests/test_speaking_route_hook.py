"""The speaking route check is wired into Monday's build as the LAST, advisory step (2026-10-19): after the pages are published and the gate has spoken, never counted in the run health, switchable off."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "scripts" / "weekly_deliverable.py").read_text(encoding="utf-8")


def test_the_step_runs_after_the_gate_and_before_the_exit_code():
    assert "scripts/speaking_route.py" in SRC
    assert SRC.index("run_release_gate(stamp") < SRC.index("scripts/speaking_route.py") < SRC.index('return 0 if HEALTH.failures("weekly_step") == 0 else 1')


def test_the_step_is_advisory_bounded_and_switchable():
    start = SRC.index("# 8. SPEAKING ROUTES, LAST")
    block = SRC[start:SRC.index("if status != \"HEALTHY\":", start)]
    assert '"--limit", "40", "--max-minutes", "25"' in block                      # a weekly slice, never the whole list
    assert "except Exception" in block and "HEALTH.fail" not in block and "HEALTH.note" not in block   # a fault is one printed line, never a failed step
    assert "--no-routes" in SRC and "if not a.no_routes:" in SRC


def test_the_production_script_is_advisory_too():
    s = (ROOT / "scripts" / "speaking_route.py").read_text(encoding="utf-8")
    assert "except (Exception, SystemExit)" in s and "return 0" in s.split("def main")[1]
