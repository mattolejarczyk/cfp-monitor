"""Start/stop checks for the CDP Chrome the weekly sweep drives.

Batch is a poor language for "is this port answering yet" and "close only the browser I
started". This keeps that logic in one testable place.

    cdp_ctl.py check   exit 0 if a CDP endpoint answers on 9222, 1 if not
    cdp_ctl.py wait    poll until it answers (default 25s), exit 0 on success
    cdp_ctl.py stop    close ONLY a Chrome running the cfp-cdp-profile

WHY IT MATTERS THAT WE CLOSE THE RIGHT ONE
`fetch.py` deliberately DISCONNECTS from a CDP browser rather than closing it, because it may
be the operator's own signed-in Chrome. The weekly job may legitimately start one of its own,
and should tidy that up - but it must never close a window a human is using. So `stop` matches
on the dedicated profile directory, never on "chrome.exe".
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

URL = "http://localhost:9222/json/version"
PROFILE = "cfp-cdp-profile"


def check(timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(URL, timeout=timeout) as r:
            return bool(json.loads(r.read() or b"{}").get("Browser"))
    except Exception:
        return False


def wait(seconds: int = 25) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if check(1.5):
            print("CDP reachable on 9222")
            return True
        time.sleep(1.0)
    print(f"CDP did not come up within {seconds}s - continuing without it")
    return False


def stop() -> bool:
    """Close only Chrome processes started with OUR profile directory."""
    try:
        out = subprocess.run(
            ["wmic", "process", "where", "name='chrome.exe'", "get", "ProcessId,CommandLine",
             "/format:csv"],
            capture_output=True, text=True, timeout=20).stdout
    except Exception as exc:
        print(f"could not enumerate Chrome: {type(exc).__name__}")
        return False

    pids = []
    for line in out.splitlines():
        if PROFILE in line:
            parts = [p for p in line.strip().split(",") if p]
            if parts and parts[-1].isdigit():
                pids.append(parts[-1])
    if not pids:
        print("no Chrome running our profile - nothing to stop")
        return True
    for pid in pids:
        subprocess.run(["taskkill", "/PID", pid, "/T", "/F"],
                       capture_output=True, text=True)
    print(f"stopped {len(pids)} Chrome process(es) using {PROFILE}")
    return True


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        ok = check()
        print("reachable" if ok else "not reachable")
        raise SystemExit(0 if ok else 1)
    if cmd == "wait":
        raise SystemExit(0 if wait() else 1)
    if cmd == "stop":
        raise SystemExit(0 if stop() else 1)
    print(__doc__)
    raise SystemExit(2)
