"""Run every canary through the rules layer.

This is the gate the process needs: any change to crawling, gating or delivery logic runs
against these eleven records before it runs against 406. Each canary names the incident it
came from, so a failure here tells you which mistake you are about to repeat.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from canaries import CANARIES, TODAY            # noqa: E402
from src.cfp_monitor import rules               # noqa: E402


def _named(key):
    return [c for c in CANARIES if key in c]


def _id(c):
    return c["name"]


@pytest.mark.parametrize("c", _named("expect_withdraw"), ids=_id)
def test_withdrawal_decision(c):
    ok, why = rules.may_withdraw_citation(
        c["row"], quote_found=c["quote_found"], pages_read=c["pages_read"], today=TODAY)
    assert ok is c["expect_withdraw"], f"{c['name']}\n  incident: {c['incident']}\n  said: {why}"
    assert why, "a decision must come with a reason"


@pytest.mark.parametrize("c", _named("expect_stamp_advances"), ids=_id)
def test_withdrawal_decides_the_stamp(c):
    """`fetched` is mandatory, so a withdrawal cannot be written without deciding this."""
    changes = rules.withdrawal_changes(c["row"], fetched=c["fetched"], today=TODAY)
    advanced = "SOURCE_AS_OF" in changes
    assert advanced is c["expect_stamp_advances"], (
        f"{c['name']}\n  incident: {c['incident']}")
    if advanced:
        assert changes["SOURCE_AS_OF"] == TODAY.isoformat()


def test_withdrawal_changes_refuses_to_guess_whether_a_page_was_read():
    """No default for `fetched`. The 2026-08-29 miss was a caller not asking the question."""
    import inspect
    sig = inspect.signature(rules.withdrawal_changes)
    p = sig.parameters["fetched"]
    assert p.default is inspect.Parameter.empty, (
        "fetched must have no default - a caller has to decide whether a page was read")


@pytest.mark.parametrize("c", _named("expect_confidence_after_withdrawal"), ids=_id)
def test_withdrawal_binds_confidence(c):
    changes = rules.withdrawal_changes(c["row"], fetched=True, today=TODAY)
    assert changes["GROUNDING_CONFIDENCE"] == c["expect_confidence_after_withdrawal"], (
        f"{c['name']}\n  incident: {c['incident']}")
    assert changes["IS_PROJECTED"] == "true"


@pytest.mark.parametrize("c", _named("expect_deadline_untouched"), ids=_id)
def test_withdrawal_leaves_the_deadline(c):
    changes = rules.withdrawal_changes(c["row"], fetched=True, today=TODAY)
    assert "SUBMISSION DEADLINE" not in changes, (
        f"{c['name']}\n  incident: {c['incident']}")


@pytest.mark.parametrize("c", _named("expect_may_advance"), ids=_id)
def test_source_as_of_discipline(c):
    ok, why = rules.may_advance_source_as_of(fetch_succeeded=c["fetch_succeeded"])
    assert ok is c["expect_may_advance"], f"{c['name']}\n  incident: {c['incident']}\n  {why}"


@pytest.mark.parametrize("c", _named("expect_dead"), ids=_id)
def test_only_404_410_disprove(c):
    dead, why = rules.link_is_dead(c["status"])
    assert dead is c["expect_dead"], f"{c['name']}\n  incident: {c['incident']}\n  {why}"


@pytest.mark.parametrize("c", _named("expect_duplicate"), ids=_id)
def test_event_id_uniqueness_is_per_market(c):
    keys = [rules.r8c_key(r) for r in c["rows"]]
    has_dupe = len(keys) != len(set(keys))
    assert has_dupe is c["expect_duplicate"], f"{c['name']}\n  incident: {c['incident']}"


@pytest.mark.parametrize("c", _named("expect_fields"), ids=_id)
def test_a_fix_reaches_every_field_carrying_the_url(c):
    got = rules.urls_to_update(c["row"], c["old_url"])
    assert sorted(got) == sorted(c["expect_fields"]), (
        f"{c['name']}\n  incident: {c['incident']}\n  found: {got}")


@pytest.mark.parametrize("c", _named("expect_check3_applies"), ids=_id)
def test_v14_check3_scope(c):
    """Amendment v1.4: check 3 evaluates ACTIVE deadline claims only.

    Mirrors the gate's own two skips - blank deadline, and passed deadline - so a change to
    either is caught here before it is discovered on 314 rows.
    """
    row = c["row"]
    claimed = bool((row.get("SUBMISSION DEADLINE") or "").strip())
    applies = claimed and not rules.deadline_has_passed(row, TODAY)
    assert applies is c["expect_check3_applies"], (
        f"{c['name']}\n  incident: {c['incident']}")


def test_every_canary_names_its_incident():
    """A canary without a story becomes a rule nobody dares delete and nobody understands."""
    for c in CANARIES:
        assert c.get("incident"), f"{c['name']} has no incident recorded"
        assert any(y in c["incident"] for y in ("2026-", "Contract", "R1")), (
            f"{c['name']}: incident should cite a date or a rule")


def test_the_set_covers_the_repeat_offenders():
    """The three defects introduced twice or more on 2026-08-29 must each have a canary."""
    names = " ".join(c["name"] for c in CANARIES).lower()
    for shape in ("confidence", "source_as_of", "every field"):
        assert shape in names, f"no canary covers {shape!r}"
