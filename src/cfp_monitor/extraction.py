"""LLM structured extraction per page (feat 4, 6, 7, 8, 9, 12).

Runs on markdown we've ALREADY crawled (no re-fetch — keeps the budget tight),
using LiteLLM directly with the same provider string crawl4ai would use. Returns a
validated `PageExtraction`, or None on failure. The instruction forbids guessing —
missing data must come back null so consolidation can mark it "unknown".
"""
from __future__ import annotations

import json
import re
from typing import Optional

from .models import PageExtraction
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
    "quote text verbatim where asked; cfp_status must be one of open, closed, upcoming, "
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
    kwargs = dict(
        model=settings.llm_provider,
        messages=messages,
        api_key=settings.openrouter_api_key,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
    try:
        try:
            resp = await litellm.acompletion(**kwargs, response_format={"type": "json_object"})
        except Exception:
            resp = await litellm.acompletion(**kwargs)  # model may not support json mode
        text = resp.choices[0].message.content or ""
    except Exception as e:
        tracer.log("error", url, f"llm call failed: {e}")
        return None

    data = _find_json(text)
    if not data:
        tracer.log("error", url, "llm returned no parseable JSON")
        return None
    try:
        pe = PageExtraction(**_coerce(data))
        tracer.log("extracted", url, f"opportunity={pe.is_opportunity_page} cfp={pe.has_cfp}")
        return pe
    except Exception as e:
        tracer.log("error", url, f"schema validation failed: {e}")
        return None
