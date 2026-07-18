"""Coarse opportunity-TRACK labels for the customer sheet.

This is a deliberately SEPARATE component. It reads only the fine-grained
``opportunity_types`` the extractor already captures (with evidence) and maps them to
a coarse track label (Speaking / Awards / Other). It does NOT run any extraction, does
NOT look at the page, and does NOT influence conference identification or CFP status in
any way — so folding in awards/other tracks cannot regress the quality of conference
detection. It is also conservative: it labels ONLY tracks that were actually detected and
never infers a track from missing/absent data (no opportunity types -> no track).

Fine-grained types come from ``PageExtraction.opportunity_type`` /
``ConferenceResult.opportunity_types``:
    cfp, call_for_speakers, speaker_proposal, abstract, poster, panel, workshop,
    presentation, awards_entry, nomination, showcase
"""
from __future__ import annotations

from typing import Iterable

# Evidence-backed opportunity types the extractor emits, grouped into coarse tracks.
_SPEAKING = {"cfp", "call_for_speakers", "speaker_proposal", "abstract", "poster",
             "panel", "workshop", "presentation"}
_AWARDS = {"awards_entry", "nomination"}
# "showcase" is intentionally left unmapped: it is ambiguous (demo/exhibit/talk), so it
# falls through to "Other" rather than being asserted as Speaking. New tracks (e.g. a
# real Exhibitor signal) get added here when the extractor learns to detect them.


def opportunity_tracks(opportunity_types: Iterable[str] | None) -> list[str]:
    """Distinct coarse tracks present, in priority order (Speaking, Awards, Other).

    Returns ``[]`` when nothing was detected — an empty track is the honest signal that
    no opportunity type was found, never a guess. "Other" is emitted only when a real but
    unmapped opportunity type is present (a genuine signal we simply don't grade finely yet).
    """
    types = {str(t).strip().lower() for t in (opportunity_types or []) if t and str(t).strip()}
    if not types:
        return []
    out: list[str] = []
    if types & _SPEAKING:
        out.append("Speaking")
    if types & _AWARDS:
        out.append("Awards")
    if not out:
        # A recognized opportunity exists but isn't a speaking/awards type we grade yet.
        out.append("Other")
    return out


def track_label(opportunity_types: Iterable[str] | None) -> str:
    """Single customer-sheet cell value, e.g. "Speaking" or "Speaking; Awards".

    Empty string when no opportunity type was detected (matches our "leave blank rather
    than assert" rule for missing information)."""
    return "; ".join(opportunity_tracks(opportunity_types))
