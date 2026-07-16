"""Evidence-backed consolidation into one conference result (feat 8, 9, 10, 12, 13).

Merges every page's extraction (plus discovered forms / external submission links)
into a single ConferenceResult. Key rules:
- FIELD-SPECIFIC evidence: each fact quotes its OWN value's source text, not a
  generic CFP snippet reused everywhere.
- LABELED status: distinguish explicit ("page says open/closed") from inferred
  ("a live submission form exists, no closed language") via `status_basis`.
- Never fabricate: unknown stays unknown.
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


# Plain-English words/phrases for the human-readable `reason` summary. These MIRROR
# the machine `status_basis` tag — the tag stays for filtering/analytics, this is prose.
_STATUS_WORD = {
    CFPStatus.open: "Open",
    CFPStatus.closed: "Closed",
    CFPStatus.upcoming: "Upcoming",
    CFPStatus.unclear: "Unclear",
    CFPStatus.none: "No opportunity",
}
_BASIS_PHRASE = {
    "explicit_open": "the page states the call is open",
    "explicit_closed": "the page states the call is closed or the deadline has passed",
    "explicit_upcoming": "the page states the call is announced but not yet open",
    "inferred_from_live_submission_form": "a live submission form was found and nothing says it's closed",
    "opportunity_signals_no_live_form": "a call/speakers page exists but no live form or explicit status was found",
    "no_opportunity_found": "the pages checked state there is no speaking/submission opportunity",
    "insufficient_evidence": "not enough evidence was found on the crawled pages to judge",
}


def _build_reason(res: ConferenceResult) -> str:
    """One trustworthy sentence: verdict + why + the key evidence backing it.
    A readable summary of status_basis / evidence / trace — those layers stay intact."""
    word = _STATUS_WORD.get(res.cfp_status, res.cfp_status.value.title())
    why = _BASIS_PHRASE.get(res.status_basis or "", res.status_basis or "reason unrecorded")
    parts = [f"{word} - {why}."]
    if res.submission_form_found and res.submission_url.value:
        plat = f"{res.submission_platform} form " if res.submission_platform else ""
        via = "Submit via " + (plat or "").strip()
        parts.append(f"{via}: {res.submission_url.value}.".replace("  ", " "))
    if res.cfp_close_date.value:
        parts.append(f'Deadline "{res.cfp_close_date.value}" ({res.cfp_close_date.confidence.value}).')
    if res.conference_dates.value:
        parts.append(f'Event dates "{res.conference_dates.value}" ({res.conference_dates.confidence.value}).')
    if res.possible_multi_edition_site:
        parts.append("Caution: crawled pages disagree on dates — facts may span multiple editions.")
    return " ".join(parts)


def _fact(field: str, pairs: list[tuple[str, PageExtraction]], get: Callable[[PageExtraction], Optional[str]]) -> Fact:
    """Field-specific evidence: the snippet is the field's OWN value (verbatim from
    the page), never the page's generic opportunity snippet."""
    ev: list[Evidence] = []
    value: Optional[str] = None
    for url, pe in pairs:
        v = get(pe)
        if v:
            v = str(v).strip()
            if value is None:
                value = v
            ev.append(Evidence(field=field, source_url=url, snippet=v[:200]))
            if len(ev) >= 3:
                break
    return Fact(value=value, confidence=Confidence.confirmed, evidence=ev) if value is not None else Fact()


def consolidate(
    start_url: str,
    pairs: list[tuple[str, PageExtraction]],
    forms: list[dict],
    external_submissions: list[dict],
    tracer: Tracer,
    pages_crawled: int,
    pages_skipped: int,
) -> ConferenceResult:
    pairs = sorted(pairs, key=lambda kv: (not kv[1].is_opportunity_page,))
    res = ConferenceResult(start_url=start_url, pages_crawled=pages_crawled, pages_skipped=pages_skipped)

    res.name = _fact("name", pairs, lambda pe: pe.conference_name)
    res.conference_dates = _fact("conference_dates", pairs, lambda pe: pe.conference_dates)
    res.location = _fact("location", pairs, lambda pe: pe.location)
    res.audience_topics = _fact("audience_topics", pairs, lambda pe: pe.audience_topics)
    res.cfp_open_date = _fact("cfp_open_date", pairs, lambda pe: pe.cfp_open_date)
    res.cfp_close_date = _fact("cfp_close_date", pairs, lambda pe: pe.cfp_close_date)

    # --- opportunity types ---
    res.opportunity_types = sorted({pe.opportunity_type for _, pe in pairs if pe.opportunity_type})

    # --- forms / submission evidence ---
    res.submission_forms = list(forms or [])
    form_present = bool(forms) or bool(external_submissions) or any(pe.has_submission_form for _, pe in pairs)

    # --- CFP existence & LABELED status (feat 9) ---
    explicit_closed = any((pe.closed_or_passed is True) or (pe.cfp_status == "closed") for _, pe in pairs)
    explicit_open = any(pe.cfp_status == "open" for _, pe in pairs)
    upcoming = any(pe.cfp_status == "upcoming" for _, pe in pairs)
    opportunity = (
        any((pe.has_cfp is True) or pe.is_opportunity_page for _, pe in pairs)
        or form_present
        or bool(res.opportunity_types)
    )
    any_false = any(pe.has_cfp is False for _, pe in pairs)

    if explicit_closed:
        res.has_cfp = True
        res.cfp_status, res.status_basis = CFPStatus.closed, "explicit_closed"
    elif explicit_open:
        res.has_cfp = True
        res.cfp_status, res.status_basis = CFPStatus.open, "explicit_open"
    elif upcoming:
        res.has_cfp = True
        res.cfp_status, res.status_basis = CFPStatus.upcoming, "explicit_upcoming"
    elif form_present:
        # Inferred open: a live submission form exists and nothing says it's closed.
        res.has_cfp = True
        res.cfp_status = CFPStatus.open
        res.status_basis = "inferred_from_live_submission_form"
    elif opportunity:
        # Opportunity signals (e.g. a speakers/CFP page) but NO live form and no
        # explicit status — stay cautious rather than claiming it's open.
        res.has_cfp = True
        res.cfp_status = CFPStatus.unclear
        res.status_basis = "opportunity_signals_no_live_form"
    elif any_false:
        res.has_cfp = False
        res.cfp_status, res.status_basis = CFPStatus.none, "no_opportunity_found"
    else:
        res.has_cfp = None
        res.cfp_status, res.status_basis = CFPStatus.unclear, "insufficient_evidence"

    # --- submission path (feat 9) ---
    sub = _fact("submission_url", pairs, lambda pe: pe.submission_url)
    platform = next((pe.submission_platform for _, pe in pairs if pe.submission_platform), None)
    if not sub.value and external_submissions:
        s = external_submissions[0]
        sub = Fact(value=s["url"], confidence=Confidence.confirmed,
                   evidence=[Evidence(field="submission_url", source_url=s["url"], snippet=f"{s['platform']}: {s.get('text','')}"[:200])])
        platform = platform or s["platform"]
    if not sub.value and forms:
        f0 = forms[0]
        sub = Fact(value=f0["url"], confidence=Confidence.confirmed,
                   evidence=[Evidence(field="submission_url", source_url=f0["url"], snippet=f"{f0['platform']}: {f0.get('context','')}"[:200])])
        platform = platform or (f0["platform"] if f0["platform"] != "on-page form" else None)
    if not sub.value and res.has_cfp:
        opp = next((url for url, pe in pairs if pe.is_opportunity_page), None)
        if opp:
            sub = Fact(value=opp, confidence=Confidence.inferred,
                       evidence=[Evidence(field="submission_url", source_url=opp, snippet="best opportunity page (no explicit submit link found)")])
    res.submission_url = sub
    res.submission_platform = platform
    res.submission_form_found = bool(form_present or sub.value)

    # --- multi-edition caution (feat 10) ---
    # Flag only when pages genuinely DISAGREE on the conference dates (the real
    # ABLC-style ambiguity), not merely because a stray past year is mentioned.
    date_vals = sorted({(pe.conference_dates or "").strip() for _, pe in pairs if (pe.conference_dates or "").strip()})
    other_eds = sorted({pe.other_editions.strip() for _, pe in pairs if pe.other_editions and pe.other_editions.strip()})
    if len(date_vals) >= 2:
        res.possible_multi_edition_site = True
        res.competing_event_mentions = date_vals + [e for e in other_eds if e not in date_vals]

    for f in (res.name, res.conference_dates, res.location, res.audience_topics,
              res.cfp_open_date, res.cfp_close_date, res.submission_url):
        res.evidence.extend(f.evidence)

    # Human-readable summary line (layer 4) — synthesizes the tag + evidence above.
    res.reason = _build_reason(res)

    tracer.log(
        "consolidated", start_url,
        f"has_cfp={res.has_cfp} status={res.cfp_status.value} basis={res.status_basis} "
        f"forms={len(res.submission_forms)} multi_edition={res.possible_multi_edition_site}",
    )
    return res
