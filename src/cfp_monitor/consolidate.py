"""Evidence-backed consolidation into one conference result (feat 10, 12, 13).

Merges every page's extraction into a single ConferenceResult. Each fact records
where it came from (URL + snippet) and a confidence: confirmed (stated on a page),
inferred (derived), or unknown (never found — left blank, never guessed).
"""
from __future__ import annotations

from typing import Callable, Optional

from .models import (
    ConferenceResult,
    Fact,
    Evidence,
    Confidence,
    CFPStatus,
    PageExtraction,
)
from .trace import Tracer

# Report priority when pages disagree on status (prefer "opportunity available").
_STATUS_ORDER = ["open", "upcoming", "unclear", "closed"]


def _fact(field: str, pairs: list[tuple[str, PageExtraction]], get: Callable[[PageExtraction], Optional[str]]) -> Fact:
    ev: list[Evidence] = []
    value: Optional[str] = None
    for url, pe in pairs:
        v = get(pe)
        if v:
            v = str(v).strip()
            if value is None:
                value = v
            ev.append(Evidence(field=field, source_url=url, snippet=(pe.key_snippet or v)[:200]))
            if len(ev) >= 3:
                break
    if value is None:
        return Fact()
    return Fact(value=value, confidence=Confidence.confirmed, evidence=ev)


def consolidate(
    start_url: str,
    pairs: list[tuple[str, PageExtraction]],
    submission_links: list[dict],
    tracer: Tracer,
    pages_crawled: int,
    pages_skipped: int,
) -> ConferenceResult:
    # Opportunity pages first — they hold the most authoritative CFP facts.
    pairs = sorted(pairs, key=lambda kv: (not kv[1].is_opportunity_page,))

    res = ConferenceResult(start_url=start_url, pages_crawled=pages_crawled, pages_skipped=pages_skipped)
    res.name = _fact("name", pairs, lambda pe: pe.conference_name)
    res.conference_dates = _fact("conference_dates", pairs, lambda pe: pe.conference_dates)
    res.location = _fact("location", pairs, lambda pe: pe.location)
    res.audience_topics = _fact("audience_topics", pairs, lambda pe: pe.audience_topics)
    res.cfp_open_date = _fact("cfp_open_date", pairs, lambda pe: pe.cfp_open_date)
    res.cfp_close_date = _fact("cfp_close_date", pairs, lambda pe: pe.cfp_close_date)

    # --- CFP existence & status ---
    any_true = any((pe.has_cfp is True) or pe.is_opportunity_page for _, pe in pairs) or bool(submission_links)
    any_false = any(pe.has_cfp is False for _, pe in pairs)
    statuses = {pe.cfp_status for _, pe in pairs if pe.cfp_status in _STATUS_ORDER}

    if any_true:
        res.has_cfp = True
        res.cfp_status = CFPStatus(next((s for s in _STATUS_ORDER if s in statuses), "unclear"))
    elif any_false:
        res.has_cfp = False
        res.cfp_status = CFPStatus.none
    else:
        res.has_cfp = None
        res.cfp_status = CFPStatus.unclear

    # --- Submission path (feat 9) ---
    sub = _fact("submission_url", pairs, lambda pe: pe.submission_url)
    platform = next((pe.submission_platform for _, pe in pairs if pe.submission_platform), None)
    if not sub.value and submission_links:
        sl = submission_links[0]
        sub = Fact(
            value=sl["url"],
            confidence=Confidence.confirmed,
            evidence=[Evidence(field="submission_url", source_url=sl["url"], snippet=f"{sl['platform']} link")],
        )
        platform = platform or sl["platform"]
    if not sub.value and res.has_cfp:
        opp = next((url for url, pe in pairs if pe.is_opportunity_page), None)
        if opp:
            sub = Fact(
                value=opp,
                confidence=Confidence.inferred,
                evidence=[Evidence(field="submission_url", source_url=opp, snippet="best opportunity page")],
            )
    res.submission_url = sub
    res.submission_platform = platform

    # Aggregate all evidence for a quick audit trail.
    for f in (
        res.name,
        res.conference_dates,
        res.location,
        res.audience_topics,
        res.cfp_open_date,
        res.cfp_close_date,
        res.submission_url,
    ):
        res.evidence.extend(f.evidence)

    tracer.log(
        "consolidated",
        start_url,
        f"has_cfp={res.has_cfp} status={res.cfp_status.value} facts={len(res.evidence)}",
    )
    return res
