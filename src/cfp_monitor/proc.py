"""Stopping a child process for real. One place, because two schedulers need it and one already got it wrong.

2026-11-06: `subprocess.run(timeout=...)` kills the child and nothing the child started. A browser grandchild (Playwright) outlived a
gate pass by 2 h 17 min and held its output pipe open (inspection 2026-11-07, defect 2, fixed in scripts/weekend_import.py).
2026-11-09: scripts/weekly_deliverable.py still used the same call for the Monday pages. Its evidence step timed out and the kill
happened to be clean; nothing made it so. Both now call kill_tree.
"""
from __future__ import annotations

import os
import subprocess


def kill_tree(p: subprocess.Popen) -> str:
    """Kill the child AND everything it spawned. On Windows `taskkill /T /F`; elsewhere the process group
    (the child is started in its own session). Returns one line saying what happened, for the log."""
    if os.name == "nt":
        r = subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, text=True,
                           errors="replace", timeout=60)
        return " ".join((r.stdout + r.stderr).split())[:300] or f"taskkill exit {r.returncode}"
    import signal
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        return f"killed process group of pid {p.pid}"
    except Exception as e:                                                   # noqa: BLE001
        p.kill()
        return f"killed pid {p.pid} only ({type(e).__name__})"
