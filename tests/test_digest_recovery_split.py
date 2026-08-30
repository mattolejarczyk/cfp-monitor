"""Leaving `contradicted` is three different events and the digest must not conflate them.

On 2026-08-30 the weekly digest announced "Recovered since last week (19)". Four rows had
actually verified. Thirteen were citations WE had cleared the day before - with no citation
there is nothing left to contradict, so the row falls to not_found mechanically - and three
were pages that went silent, which contract 2.1 says proves nothing.

The failure is not arithmetic. It is a report that reads as good news when nothing good
happened, which is the same shape as the acceptance gate printing ACCEPTED for checks it had
skipped.
"""
import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("_wv", ROOT / "scripts" / "weekly_verify.py")
wv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wv)

TODAY = date(2026, 8, 30)


def digest(before, after, still_cited, label=None):
    label = label or {k: k for k in after}
    text, _ = wv.build_digest(before, after, label, TODAY, still_cited=set(still_cited))
    return text


def test_a_real_recovery_is_still_reported_as_one():
    """GOOD INPUT MUST SURVIVE. The 2026-08-08 lesson: every test asserted the repair fixed
    broken input, none that it left good input alone, and 26 cities were corrupted."""
    out = digest({"e1": ("contradicted", "")}, {"e1": ("verified", "the page now agrees")},
                 still_cited={"e1"}, label={"e1": "Real Recovery Conf"})
    assert "## Verified since last week (1)" in out
    assert "Real Recovery Conf" in out
    assert "citation cleared" not in out.lower()


def test_a_cleared_citation_is_not_a_recovery():
    out = digest({"e1": ("contradicted", "")}, {"e1": ("not_found", "")},
                 still_cited=set(), label={"e1": "We Cleared This"})
    assert "## No longer evidenced - citation cleared (1)" in out
    assert "Verified since last week" not in out
    assert "We Cleared This" in out


def test_a_page_going_quiet_is_a_watch_item_not_a_win():
    out = digest({"e1": ("contradicted", "")}, {"e1": ("not_found", "")},
                 still_cited={"e1"}, label={"e1": "Went Quiet Conf"})
    assert "## Evidence no longer found (1)" in out
    assert "Verified since last week" not in out
    assert "not a recovery" in out


def test_the_three_buckets_do_not_leak_into_each_other():
    """The real 2026-08-30 shape: 4 verified, 3 quiet, 13 cleared - never 19 recoveries."""
    before = {f"v{i}": ("contradicted", "") for i in range(4)}
    after = {f"v{i}": ("verified", "") for i in range(4)}
    for i in range(3):
        before[f"q{i}"] = ("contradicted", "")
        after[f"q{i}"] = ("not_found", "")
    for i in range(13):
        before[f"c{i}"] = ("contradicted", "")
        after[f"c{i}"] = ("not_found", "")
    still = {f"v{i}" for i in range(4)} | {f"q{i}" for i in range(3)}

    out = digest(before, after, still_cited=still)
    assert "## Verified since last week (4)" in out
    assert "## Evidence no longer found (3)" in out
    assert "## No longer evidenced - citation cleared (13)" in out
    assert "(19)" not in out, "the three must never be added back together"


def test_still_cited_has_no_default():
    """Same reasoning as `fetched` in rules.withdrawal_changes: a default hides a decision
    the caller has to make, and that is how the stamp was skipped on four rows."""
    with pytest.raises(TypeError):
        wv.build_digest({}, {}, {}, TODAY)


def test_counts_are_derived_not_carried():
    """Contract: a reported number is computed at render time from the data it describes.
    make_handback.py hard-coded its counts in a header and reported cycle one's numbers
    to upstream for every cycle after."""
    src = (ROOT / "scripts" / "weekly_verify.py").read_text(encoding="utf-8")
    for n in ("(19)", "(13)", "(32)", "(80)"):
        assert f'f"## Verified since last week {n}"' not in src
    assert "len(verified_again)" in src or "len(recovered)" in src
    assert "len(went_quiet)" in src and "len(uncited)" in src


def test_the_two_halves_declare_their_scope():
    """Argus Biofuels and Decarb Connect NA appeared under both 'Recovered' and 'Standing
    backlog' and the report looked self-contradictory. Both entries were correct."""
    src = (ROOT / "scripts" / "weekly_verify.py").read_text(encoding="utf-8")
    assert "per CONFERENCE + URL" in src
    assert "can legitimately appear in" in src


def test_no_change_week_stays_quiet():
    out = digest({"e1": ("verified", "")}, {"e1": ("verified", "")}, still_cited={"e1"})
    assert "No CHANGE since the last sweep" in out
