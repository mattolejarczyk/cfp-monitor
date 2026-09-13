"""LLM structured extraction per page (feat 4, 6, 7, 8, 9, 12).

Runs on markdown we've ALREADY crawled (no re-fetch — keeps the budget tight),
using LiteLLM directly with the same provider string crawl4ai would use. Returns a
validated `PageExtraction`, or None on failure. The instruction forbids guessing —
missing data must come back null so consolidation can mark it "unknown".
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Optional

from .models import PageExtraction
from .run_health import HEALTH
from .trace import Tracer

_INSTRUCTION = (
    "You extract speaking / submission opportunity facts from ONE conference or "
    "industry-event web page. An 'opportunity' includes a Call for Papers/Speakers/"
    "Proposals, propose-a-talk, abstract/poster/panel/workshop submission, AND "
    "awards-style calls for ENTRIES or NOMINATIONS (submit an entry, nominate, enter "
    "the awards, best of show). Treat 'submission deadline', 'entry deadline', and "
    "'nomination deadline' as the cfp_close_date. "
    "Set has_submission_form=true if a live submission/entry/proposal form (or a clear "
    "link/button to one) is present. Set closed_or_passed=true ONLY if the page "
    "explicitly says the opportunity is closed or the deadline has passed. Set "
    "other_editions if the page references a different event year/city than the main one. "
    "Return ONLY a JSON object matching the given schema. Rules: use null for anything "
    "the page does not clearly state; NEVER invent or infer dates, deadlines, or status; "
    "quote text verbatim where asked; for any non-verbatim text use plain ASCII "
    "punctuation only (standard hyphen and straight quotes, never em/en dashes or "
    "typographic punctuation); cfp_status must be one of open, closed, upcoming, "
    "unclear (or null) and set it to a value ONLY when the page states it explicitly."
)

_ALLOWED = set(PageExtraction.model_fields.keys())
_VALID_STATUS = {"open", "closed", "upcoming", "unclear"}


def _find_json(text: str) -> Optional[dict]:
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        obj = json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except Exception:
            return None
    if isinstance(obj, list):  # some models wrap in a list
        obj = next((x for x in obj if isinstance(x, dict)), {})
    return obj if isinstance(obj, dict) else None


def _coerce(data: dict) -> dict:
    clean = {k: v for k, v in data.items() if k in _ALLOWED}
    st = clean.get("cfp_status")
    if isinstance(st, str) and st.lower() not in _VALID_STATUS:
        clean["cfp_status"] = None
    elif isinstance(st, str):
        clean["cfp_status"] = st.lower()
    return clean


async def extract_from_markdown(
    markdown: str, url: str, settings, tracer: Tracer
) -> Optional[PageExtraction]:
    if not markdown or len(markdown.strip()) < 40:
        return None
    try:
        import litellm
    except Exception as e:  # pragma: no cover
        tracer.log("error", url, f"litellm unavailable: {e}")
        return None

    content = markdown[:16000]
    messages = [
        {"role": "system", "content": _INSTRUCTION},
        {
            "role": "user",
            "content": (
                f"JSON schema:\n{json.dumps(PageExtraction.model_json_schema())}\n\n"
                f"PAGE URL: {url}\n\nPAGE CONTENT:\n{content}\n\n"
                "Return ONLY the JSON object."
            ),
        },
    ]
    if settings.llm_proxy_url:
        # Customer build: route through the vendor's licensed proxy (OpenAI-compatible). The
        # license key is the credential; the proxy picks the model + holds the provider key.
        # If the license is revoked / expired / below the version floor, this call fails and
        # extraction stops — the kill switch.
        kwargs = dict(
            model="openai/cfp-extract",                       # nominal; the proxy chooses the real model
            messages=messages,
            api_base=settings.llm_proxy_url.rstrip("/") + "/v1",
            api_key=settings.license_key,
            extra_headers={"X-Client-Version": settings.client_version},
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
    else:
        kwargs = dict(
            model=settings.llm_provider,
            messages=messages,
            api_key=settings.provider_key(),      # OpenAI or OpenRouter, per the model prefix
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
    try:
        resp = await acomplete_with_retry(litellm, kwargs, url)
        text = resp.choices[0].message.content or ""
    except Exception as e:
        reason = "rate_limited" if is_retryable(e) and _is_rate_limit(e) else \
                 "provider_unavailable" if is_retryable(e) else "llm_error"
        HEALTH.fail("page_read", reason, f"{url}: {str(e)[:120]}")
        tracer.log("error", url, f"llm call failed ({reason}): {e}")
        return None

    data = _find_json(text)
    if not data:
        HEALTH.fail("page_read", "no_json", url)
        tracer.log("error", url, "llm returned no parseable JSON")
        return None
    try:
        pe = PageExtraction(**_coerce(data))
        HEALTH.ok("page_read")
        tracer.log("extracted", url, f"opportunity={pe.is_opportunity_page} cfp={pe.has_cfp}")
        return pe
    except Exception as e:
        HEALTH.fail("page_read", "schema_invalid", url)
        tracer.log("error", url, f"schema validation failed: {e}")
        return None


# ---- retries -------------------------------------------------------------------------------
# 2026-09-13: openrouter/deepseek/deepseek-chat answered 429 "temporarily rate-limited upstream"
# on nearly every page of a 14-site crawl. The old code caught ANY exception from the JSON-mode
# call and retried once without JSON mode - so a rate limit was taken for "model does not support
# JSON", a second request was spent on the same limit, and the page then counted as having
# nothing on it. A transient upstream limit needs a pause and another try; an unsupported
# parameter needs the plain call. They are different failures and get different handling.
RETRY_DELAYS = tuple(float(x) for x in os.getenv("CFP_LLM_RETRY_DELAYS", "5,15,30").split(","))
_RETRYABLE_NAMES = {"RateLimitError", "ServiceUnavailableError", "InternalServerError",
                    "Timeout", "APIConnectionError", "APITimeoutError"}
_RETRYABLE_TEXT = ("429", "rate-limited", "rate limit", "overloaded", "502", "503", "504",
                   "temporarily unavailable")
_JSON_MODE_TEXT = ("response_format", "json_object", "json mode", "unsupportedparams")


def _is_rate_limit(e: Exception) -> bool:
    s = f"{type(e).__name__} {e}".lower()
    return "ratelimit" in s or "429" in s or "rate-limited" in s or "rate limit" in s


def is_retryable(e: Exception) -> bool:
    """A failure that another try, after a pause, may not repeat."""
    if type(e).__name__ in _RETRYABLE_NAMES:
        return True
    s = str(e).lower()
    return any(t in s for t in _RETRYABLE_TEXT)


def _json_mode_unsupported(e: Exception) -> bool:
    s = f"{type(e).__name__} {e}".lower()
    return not is_retryable(e) and any(t in s for t in _JSON_MODE_TEXT)


async def acomplete_with_retry(litellm_mod, kwargs: dict, url: str = "",
                               delays: tuple | None = None, sleep=None):
    """JSON mode first; plain mode only if JSON mode is genuinely unsupported; transient
    failures retried after each delay in `delays`. Raises the last error if every try fails.

    Defaults resolve at CALL time, not import time, so RETRY_DELAYS and asyncio.sleep can be
    changed after import - a default bound at definition silently ignores both."""
    delays = RETRY_DELAYS if delays is None else delays
    sleep = sleep or asyncio.sleep
    json_mode = True
    for attempt in range(len(delays) + 1):
        try:
            if json_mode:
                return await litellm_mod.acompletion(**kwargs, response_format={"type": "json_object"})
            return await litellm_mod.acompletion(**kwargs)
        except Exception as e:                                           # noqa: BLE001
            if json_mode and _json_mode_unsupported(e):
                json_mode = False
                HEALTH.note("page_read", "json_mode_unsupported")
                continue
            if not is_retryable(e) or attempt == len(delays):
                raise
            HEALTH.note("page_read", "retried_rate_limit" if _is_rate_limit(e) else "retried_transient")
            await sleep(delays[attempt])
    raise RuntimeError("unreachable")
