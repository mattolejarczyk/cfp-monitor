"""Run the whole suite under pytest.

This used to execute each test_*.py as a plain script. Files that define test functions
but have no `if __name__ == "__main__"` block simply exited 0 without asserting anything,
so the runner reported them as passing -- 9 files and 112 tests were silently no-ops.
Collecting with pytest means a test counts only when it actually runs.
"""
import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
try:
    import pytest  # noqa: F401
except ImportError:
    sys.exit("pytest is required to run the suite:  uv run --with pytest python tests/run_all.py")

r = subprocess.run([sys.executable, "-m", "pytest", here, "-q"])
sys.exit(r.returncode)
