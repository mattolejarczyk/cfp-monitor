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
        description="True only if this page is about submitting or speaking "
        "(call for papers/speakers, propose a talk, abstract/proposal submission)."
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
        default=None, description="External platform if used (e.g. Sessionize, PaperCall, EasyChair). null if absent."
    )
    key_snippet: Optional[str] = Field(
        default=None, description="Short verbatim quote (<200 chars) that best evidences the CFP or dates."
    )


# ---- Consolidated conference-level result -----------------------------------
class ConferenceResult(BaseModel):
    start_url: str
    canonical_url: Optional[str] = None
    name: Fact = Field(default_factory=Fact)
    description: Optional[str] = None
    location: Fact = Field(default_factory=Fact)
    conference_dates: Fact = Field(default_factory=Fact)
    audience_topics: Fact = Field(default_factory=Fact)

    has_cfp: Optional[bool] = None
    cfp_status: CFPStatus = CFPStatus.unclear
    cfp_open_date: Fact = Field(default_factory=Fact)
    cfp_close_date: Fact = Field(default_factory=Fact)
    submission_url: Fact = Field(default_factory=Fact)
    submission_platform: Optional[str] = None

    evidence: list[Evidence] = Field(default_factory=list)
    pages_crawled: int = 0
    pages_skipped: int = 0
    trace: list[dict] = Field(default_factory=list)
    error: Optional[str] = None
