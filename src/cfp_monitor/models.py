"""Typed data models for the CFP monitor.

Two layers:
- `PageExtraction`  — what the LLM pulls from ONE crawled page (feat 4,6,7,8,9).
- `ConferenceResult` — the consolidated, evidence-backed conference-level result
  (feat 10,12,13). Every important fact is a `Fact` carrying its confidence and
  the source URLs/snippets it came from.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Confidence(str, Enum):
    confirmed = "confirmed"   # stated plainly on a crawled page
    inferred = "inferred"     # derived/guessed from indirect signals
    unknown = "unknown"       # not found — do NOT fabricate


class CFPStatus(str, Enum):
    open = "open"
    closed = "closed"
    upcoming = "upcoming"     # announced but not yet open
    unclear = "unclear"       # opportunity exists but timing ambiguous
    none = "none"             # no speaking/submission opportunity found


class Evidence(BaseModel):
    """A single source-backed proof for a fact."""
    field: str                # which fact this supports, e.g. "cfp_close_date"
    source_url: str
    snippet: str              # short verbatim quote from the page


class Fact(BaseModel):
    """A value plus its provenance. `value is None` + unknown = genuinely not found."""
    value: Optional[str] = None
    confidence: Confidence = Confidence.unknown
    evidence: list[Evidence] = Field(default_factory=list)


# ---- Per-page LLM extraction schema (fed to LLMExtractionStrategy) -----------
class PageExtraction(BaseModel):
    """Fields the LLM extracts from a single page. Use null when the page does not
    state something — never guess."""
    is_opportunity_page: bool = Field(
        default=False,
        description="True only if this page is about submitting or speaking "
        "(call for papers/speakers, propose a talk, abstract/proposal submission).",
    )
    conference_name: Optional[str] = None
    conference_dates: Optional[str] = Field(
        default=None, description="When the conference happens, verbatim. null if not on this page."
    )
    location: Optional[str] = Field(default=None, description="City/venue/online. null if absent.")
    audience_topics: Optional[str] = Field(
        default=None, description="Who it's for and the topic area. null if absent."
    )
    has_cfp: Optional[bool] = Field(
        default=None, description="Whether a speaking/submission opportunity exists. null if this page doesn't say."
    )
    cfp_status: Optional[str] = Field(
        default=None, description="One of: open, closed, upcoming, unclear. null if not stated."
    )
    cfp_open_date: Optional[str] = Field(default=None, description="When submissions open, verbatim. null if absent.")
    cfp_close_date: Optional[str] = Field(
        default=None, description="Submission deadline, verbatim. null if absent."
    )
    submission_url: Optional[str] = Field(
        default=None, description="The actual page/URL where one submits, if named or linked here. null if absent."
    )
    submission_platform: Optional[str] = Field(
        default=None, description="External platform if used (e.g. Sessionize, PaperCall, EasyChair, HubSpot). null if absent."
    )
    opportunity_type: Optional[str] = Field(
        default=None,
        description="Kind of opportunity if any: one of cfp, call_for_speakers, speaker_proposal, "
        "abstract, poster, panel, workshop, awards_entry, nomination, presentation, showcase. null if none.",
    )
    has_submission_form: Optional[bool] = Field(
        default=None, description="True if a live submission/entry/proposal FORM (or a link to one) is present on this page."
    )
    closed_or_passed: Optional[bool] = Field(
        default=None,
        description="True ONLY if the page explicitly says the opportunity is closed or the deadline has passed. "
        "null if it doesn't say.",
    )
    other_editions: Optional[str] = Field(
        default=None,
        description="If the page references OTHER event editions (different year/city) than the main one, list them briefly. null otherwise.",
    )
    key_snippet: Optional[str] = Field(
        default=None, description="Short verbatim quote (<200 chars) that best evidences the CFP or dates."
    )


# ---- Consolidated conference-level result -----------------------------------
class ConferenceResult(BaseModel):
    start_url: str
    canonical_url: Optional[str] = None
    # Input-side metadata (NOT extracted from the page): which industry list this URL came
    # from, for filtering/grouping in the review UI. Set by the caller, never by the crawl.
    industry: Optional[str] = None
    name: Fact = Field(default_factory=Fact)
    description: Optional[str] = None
    location: Fact = Field(default_factory=Fact)
    conference_dates: Fact = Field(default_factory=Fact)
    audience_topics: Fact = Field(default_factory=Fact)

    has_cfp: Optional[bool] = None
    cfp_status: CFPStatus = CFPStatus.unclear
    # WHY the status was assigned, e.g. "explicit_open", "inferred_from_live_submission_form",
    # "explicit_closed", "no_opportunity_found" — so inferred is never mistaken for confirmed.
    status_basis: Optional[str] = None
    # Plain-English one-liner synthesizing status_basis + key evidence, so a reviewer
    # can trust the verdict at a glance without assembling the detail layers themselves.
    # This is a human-readable SUMMARY of the other trust layers, not a replacement for them.
    reason: Optional[str] = None
    cfp_open_date: Fact = Field(default_factory=Fact)
    cfp_close_date: Fact = Field(default_factory=Fact)
    submission_url: Fact = Field(default_factory=Fact)
    submission_platform: Optional[str] = None

    # Opportunity detail
    opportunity_types: list[str] = Field(default_factory=list)   # e.g. ["awards_entry", "call_for_speakers"]
    submission_form_found: bool = False
    submission_forms: list[dict] = Field(default_factory=list)   # [{url, platform, context}]

    # Multi-edition caution (feat 10)
    possible_multi_edition_site: bool = False
    competing_event_mentions: list[str] = Field(default_factory=list)

    evidence: list[Evidence] = Field(default_factory=list)
    pages_crawled: int = 0
    pages_skipped: int = 0
    # How the (final) start page was fetched: crawl4ai | playwright-fallback | cdp | "" (failed).
    resolution_path: str = ""
    # True when we navigated from a directory/org page to the specific event (aggregator hop).
    aggregator_hop: bool = False
    trace: list[dict] = Field(default_factory=list)
    error: Optional[str] = None
