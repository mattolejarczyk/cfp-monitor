"""Render a script-built page in the real Chrome (CDP) and return its visible text. For pages the plain fetch cannot read: Global Energy Show Canada returned no text, Nullcon's
timeline is built by script, CES prints no dates in its static HTML (2026-10-03 read-the-page experiment). Reuses fetch._render_with_consent, the same renderer the page library
uses (scripts/page_library.py). Needs Chrome with remote debugging on 127.0.0.1:9222 (scripts/launch_chrome_cdp.bat); without it this returns ("", reason) and the caller keeps the plain text."""
from __future__ import annotations

import asyncio
import os

CDP_DEFAULT = "http://127.0.0.1:9222"


class _Q:
    def log(self, *a, **k):
        pass


async def _render(url: str, timeout: int) -> tuple[str, str]:
    from src.cfp_monitor import fetch as _f
    from src.cfp_monitor.config import Settings
    settings = Settings()
    try:
        _html, _anchors, status, body, used_cdp = await asyncio.wait_for(_f._render_with_consent(url, settings, _Q(), prefer_cdp=True), timeout)
        return (body or ""), f"rendered via {'cdp' if used_cdp else 'headless browser'}, status {status}"
    finally:
        try:
            await _f.close_fallback_browser()
        except Exception:                                                  # noqa: BLE001
            pass


def render_text(url: str, timeout: int = 90) -> tuple[str, str]:
    """(visible text, note). Never raises: a failure is ("", reason)."""
    os.environ.setdefault("CFP_CDP_URL", CDP_DEFAULT)
    try:
        return asyncio.run(_render(url, timeout))
    except Exception as e:                                                  # noqa: BLE001
        return "", f"render failed: {type(e).__name__}"
