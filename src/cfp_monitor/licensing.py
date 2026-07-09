"""Client-side license status check — a friendly launch-time signal so a revoked / expired
customer sees a clear message instead of silently-empty crawls. Enforcement still happens at the
extraction call (fail-closed); this is purely for UX. Stdlib only (urllib), no extra deps.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional


def check_license(settings, timeout: float = 6.0) -> dict:
    """Return a status dict:
      mode:   "direct" (no proxy) | "proxy"
      ok:     True (active) | False (inactive/revoked) | None (couldn't reach the server)
      status: short label · detail: human explanation · info: raw server payload
    """
    if not settings.llm_proxy_url:
        return {"mode": "direct", "ok": True, "status": "direct provider mode",
                "detail": "No license server configured (developer / vendor build).", "info": {}}

    url = settings.llm_proxy_url.rstrip("/") + "/v1/license"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {settings.license_key or ''}",
        "X-Client-Version": settings.client_version,
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        active = bool(data.get("active"))
        return {"mode": "proxy", "ok": active,
                "status": "active" if active else "inactive",
                "detail": data.get("reason", ""), "info": data}
    except urllib.error.HTTPError as e:
        data = _safe_json(e)
        reason = data.get("reason") or (data.get("error") or {}).get("message") or f"HTTP {e.code}"
        return {"mode": "proxy", "ok": False, "status": "inactive", "detail": reason,
                "info": data, "code": e.code}
    except Exception as e:
        return {"mode": "proxy", "ok": None, "status": "unreachable",
                "detail": f"Could not reach the license server ({e}). It will be re-checked when you run.",
                "info": {}}


def _safe_json(resp) -> dict:
    try:
        return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}
