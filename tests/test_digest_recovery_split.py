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
    assert "Watch only" in out
    assert "Do not withdraw the citation" in out, (
        "absence is not disproof - the row keeps its citation and its deadline")


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
    assert 'f"## {g[\'title\']} ({len(items)})"' in src, (
        "the heading count must be len() of the rows it introduces, computed at render time")
    for n in ("(19)", "(13)", "(32)", "(80)"):
        assert f'"## Verified since last week {n}"' not in src
        assert f'"## Standing backlog {n}"' not in src


def test_the_two_halves_declare_their_scope():
    """Argus Biofuels and Decarb Connect NA appeared under both 'Recovered' and 'Standing
    backlog' and the report looked self-contradictory. Both entries were correct."""
    src = (ROOT / "scripts" / "weekly_verify.py").read_text(encoding="utf-8")
    assert "per CONFERENCE + URL" in src
    assert "can legitimately appear in" in src


def test_no_change_week_stays_quiet():
    out = digest({"e1": ("verified", "")}, {"e1": ("verified", "")}, still_cited={"e1"})
    assert "Nothing changed and nothing is outstanding" in out
    assert "No action from anyone" in out
    assert "## At a glance" not in out, "an empty action table is noise, not reassurance"


def test_every_category_states_a_meaning_an_action_an_owner_and_a_timeframe():
    """The ask behind this format: a reader should never have to work out what a heading
    means or whose job it is. 'Recovered since last week (19)' said none of that."""
    for key, g in wv.GUIDE.items():
        for field in ("title", "means", "action", "owner", "when"):
            assert g.get(field), f"{key} has no {field}"
        assert "actionable" in g, f"{key} must DECLARE whether it needs work"
        assert len(g["means"]) > 40, f"{key}: the definition must be a real sentence"


def test_the_action_column_does_not_cut_a_filename_in_half():
    """It split on '.', so 'scripts/audit_evidence.py must pass first' rendered as
    'Evidence it before disputing anything: scripts/audit_evidence.'"""
    before = {"e1": ("verified", "")}
    after = {"e1": ("contradicted", "page now shows a different date")}
    out = digest(before, after, still_cited={"e1"})
    assert "audit_evidence.py must pass first." in out
    assert "audit_evidence. |" not in out


def test_watch_only_rows_are_not_counted_as_work():
    """Owned is not the same as actionable. 'Evidence no longer found' belongs to us and needs
    nothing done this week; counting it printed '35 row(s) need someone to act' directly above
    three rows reading 'nothing to do now'."""
    out = digest({"e1": ("contradicted", "")}, {"e1": ("not_found", "")}, still_cited={"e1"})
    assert "## Evidence no longer found (1)" in out
    assert "Nothing needs anyone to act this week" in out
    assert wv.GUIDE["went_quiet"]["owner"] != "-", "it IS owned - just not due now"


def test_the_summary_counts_only_rows_someone_must_act_on():
    """A backlog line and a for-information line must not inflate the same number."""
    before = {"a": ("verified", ""), "b": ("contradicted", "")}
    after = {"a": ("contradicted", "a page now says otherwise"), "b": ("not_found", "")}
    out = digest(before, after, still_cited={"a"})
    assert "## At a glance" in out
    assert "**1 row(s) need someone to act.**" in out, (
        "the contradiction is actionable; the cleared citation is not")


def test_dead_link_sections_appear_in_the_summary_table():
    """They used to be spliced in AFTER the digest was built, so no overview could see them."""
    out, _ = wv.build_digest({}, {}, {}, TODAY, still_cited=set(),
                             new_dead=[("e1", "Dead Conf", "https://x.example/cfp")])
    assert "## At a glance" in out
    assert "NEW dead links since the last run" in out
    assert "https://x.example/cfp" in out
    assert "Matt to send" in out, "a hand-back with no named sender is nobody's job"
