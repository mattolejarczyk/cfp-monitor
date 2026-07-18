"""Offline tests for the coarse opportunity-TRACK mapping (tracks.py).

TRACK is a read-only label derived from already-extracted opportunity_types; it must
never invent a track from missing data and must not depend on anything else.
"""
from cfp_monitor.tracks import opportunity_tracks, track_label


def test_empty_is_blank_never_guessed():
    assert opportunity_tracks(None) == []
    assert opportunity_tracks([]) == []
    assert opportunity_tracks(["", "  "]) == []
    assert track_label(None) == ""


def test_speaking_types():
    for t in ("cfp", "call_for_speakers", "speaker_proposal", "abstract",
              "poster", "panel", "workshop", "presentation"):
        assert opportunity_tracks([t]) == ["Speaking"], t


def test_awards_types():
    assert opportunity_tracks(["awards_entry"]) == ["Awards"]
    assert opportunity_tracks(["nomination"]) == ["Awards"]


def test_mixed_tracks_ordered_and_deduped():
    assert opportunity_tracks(["awards_entry", "cfp", "call_for_speakers"]) == ["Speaking", "Awards"]
    assert track_label(["cfp", "awards_entry"]) == "Speaking; Awards"


def test_unmapped_but_real_signal_is_other():
    # showcase is a genuine opportunity type we don't grade finely yet -> Other, not Speaking.
    assert opportunity_tracks(["showcase"]) == ["Other"]


def test_case_and_whitespace_insensitive():
    assert opportunity_tracks(["  CFP ", "Awards_Entry"]) == ["Speaking", "Awards"]
