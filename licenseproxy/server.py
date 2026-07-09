"""LLM proxy — the vendor-hosted service the customer build talks to instead of the LLM provider.

Speaks the OpenAI /v1/chat/completions shape so the client can point litellm at it. For every
request it: (1) reads the Bearer license key + X-Client-Version, (2) asks policy.authorize(),
(3) on allow, forwards to the REAL provider with the VENDOR's key and meters the returned tokens;
on deny, returns the policy's status + reason (e.g. 403 revoked, 426 upgrade-required).

The client never sees the provider key, and the model is chosen HERE (cost control) — the client's
requested model name is ignored.

Run (vendor side):
  pip install fastapi uvicorn litellm
  LICENSE_DB=licenses.db OPENROUTER_API_KEY=sk-... PROXY_MODEL=openrouter/deepseek/deepseek-chat \
      uvicorn licenseproxy.server:app --host 0.0.0.0 --port 8800

Requires fastapi + uvicorn + litellm (server-only deps; the core lib and tests don't need them).
"""
from __future__ import annotations

import os

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
except Exception as e:  # pragma: no cover - server-only dependency
    raise RuntimeError("licenseproxy.server needs fastapi + uvicorn: pip install fastapi uvicorn") from e

from .policy import LicenseStore

DB = os.getenv("LICENSE_DB", "licenses.db")
PROXY_MODEL = os.getenv("PROXY_MODEL", "openrouter/deepseek/deepseek-chat")
REQUIRED_FEATURE = os.getenv("PROXY_FEATURE") or None   # e.g. "crawl" to gate this endpoint


def _vendor_key() -> str | None:
    """Vendor provider key for the configured model — OpenAI or OpenRouter. litellm also reads
    these from the environment, but we pass explicitly so misconfig fails loudly."""
    if PROXY_MODEL.startswith("openai/"):
        return os.getenv("OPENAI_API_KEY")
    return os.getenv("OPENROUTER_API_KEY")

app = FastAPI(title="cfp-monitor license proxy")


def _bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    return auth[7:].strip() if auth.lower().startswith("bearer ") else ""


def _deny(status: int, reason: str) -> JSONResponse:
    # OpenAI-style error envelope so litellm surfaces a clean message to the client.
    return JSONResponse(status_code=status, content={"error": {"message": reason, "type": "license_error"}})


@app.get("/v1/license")
async def license_check(request: Request):
    store = LicenseStore(DB)
    try:
        d = store.authorize(_bearer(request), request.headers.get("x-client-version", ""), REQUIRED_FEATURE)
        lic = d.license or {}
        body = {"active": bool(d.allowed), "reason": d.reason,
                "plan": lic.get("plan"), "features": lic.get("features"),
                "version_floor": lic.get("version_floor"),
                "tokens_used": lic.get("used_tokens"), "quota_tokens": lic.get("quota_tokens")}
        return JSONResponse(status_code=(200 if d.allowed else d.status), content=body)
    finally:
        store.close()


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    key = _bearer(request)
    client_version = request.headers.get("x-client-version", "")
    store = LicenseStore(DB)
    try:
        decision = store.authorize(key, client_version, REQUIRED_FEATURE)
        if not decision.allowed:
            return _deny(decision.status, decision.reason)

        payload = await request.json()
        import litellm
        resp = await litellm.acompletion(
            model=PROXY_MODEL,                     # vendor picks the model, not the client
            messages=payload.get("messages", []),
            api_key=_vendor_key(),
            temperature=payload.get("temperature", 0.0),
            max_tokens=payload.get("max_tokens", 1400),
            response_format=payload.get("response_format"),
        )
        data = resp.model_dump()
        usage = data.get("usage") or {}
        store.record_usage(key, PROXY_MODEL,
                           usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
        return JSONResponse(content=data)
    except Exception as e:  # pragma: no cover - network/provider failures
        return _deny(502, f"upstream provider error: {e}")
    finally:
        store.close()
