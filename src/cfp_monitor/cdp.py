"""Ensure a real-Chrome CDP endpoint is available for LIVE runs.

Hard anti-bot sites (e.g. Reuters Events) only crawl through a REAL signed-in-capable Chrome
driven over CDP - the automated browser path meets a CAPTCHA and, hit repeatedly, gets the
residential IP flagged. The desktop UI (`scripts/launch_ui.bat`) already starts this Chrome and
sets CFP_CDP_URL; this module gives the command-line scripts (coverage, scheduler) the same
guarantee so a live run can never silently fall onto the IP-burning path.

Uses a DEDICATED profile so the user's normal Chrome is untouched. No login needed - a
signed-out real Chrome already beats the anti-bot fingerprint check.
"""
from __future__ import annotations

import os
import socket
import subprocess
import time

from .fetch import _FALLBACK_FIRST_DOMAINS, _force_fallback_domain

CDP_PORT = 9222
_CHROME_PATHS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


def _port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _chrome_exe() -> str | None:
    return next((p for p in _CHROME_PATHS if os.path.exists(p)), None)


def ensure_cdp(port: int = CDP_PORT, start: bool = True, wait_s: int = 20) -> str | None:
    """Return a CDP url if a debug Chrome is (or can be) running on `port`, else None.

    If nothing is listening and start=True, launch a dedicated-profile Chrome (as the UI does)
    and wait for the port to come up. Returns None only if Chrome can't be found/started.
    """
    url = f"http://localhost:{port}"
    if _port_listening(port):
        return url
    if not start:
        return None
    exe = _chrome_exe()
    if not exe:
        return None
    profile = os.path.join(os.path.expanduser("~"), "cfp-cdp-profile")
    subprocess.Popen(
        [exe, f"--remote-debugging-port={port}", "--remote-allow-origins=*",
         f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if _port_listening(port):
            return url
        time.sleep(0.5)
    return None


def hard_antibot_urls(urls: list[str]) -> list[str]:
    """The subset of `urls` on known hard anti-bot domains (need the CDP real-Chrome path)."""
    return [u for u in urls if _force_fallback_domain(u)]


def hard_antibot_domains() -> tuple[str, ...]:
    return _FALLBACK_FIRST_DOMAINS
