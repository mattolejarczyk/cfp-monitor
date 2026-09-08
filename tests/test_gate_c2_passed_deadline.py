"""Criterion 2 after amendment v2.2 - a dead link on a passed deadline is decay, not a defect.

Ruled by upstream 2026-09-08, on the measurement from the first awards delivery: all 14
dead cited pages belonged to rows whose deadline had already passed, and
`rules.may_withdraw_citation` refused every one of them. The check was rejecting a
delivery for a condition neither side had an action for.

The narrowness is the point and is pinned below. Check 3 excuses a BLANK deadline because
there is no claim to verify; check 2 does not, because a dead link sends the reader
nowhere whether or not the row claims a date.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("ad_c2", ROOT / "scripts" / "accept_delivery.py")
ad = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ad)

TODAY = date(2026, 9, 8)


def _row(name, deadline, url="https://dead.test/entry"):
    return {"CONFERENCE": name, "SUBMISSION DEADLINE": deadline,
            "DEADLINE_EVIDENCE_URL": url, "DEADLINE_QUOTE": ""}


def _run(monkeypatch, rows, code=404):
    monkeypatch.setattr(ad, "link_status", lambda u: (code, ""))
    monkeypatch.setattr(ad, "fetch_text", lambda u: ("", ""))
    g = ad.Gate.__new__(ad.Gate)
    g.rows, g.results, g.notes, g.network, g.today = rows, [], [], True, TODAY
    g.check_citations()
    c2 = next(r for r in g.results if r[0] == "2")
    note = next((n for n in g.notes if n[0] == "2"), None)
    return c2, note


def test_a_404_on_a_passed_deadline_is_a_note_not_a_failure(monkeypatch):
    """The Earthshot Prize, verbatim from the 2026-09-06 delivery: deadline 2024-12-11."""
    c2, note = _run(monkeypatch, [_row("The Earthshot Prize", "2024-12-11")])
    assert c2[2] is True, "a passed-deadline 404 must not fail criterion 2"
    assert note and len(note[2]) == 1, "it must still be REPORTED, not silently dropped"
    assert "deadline passed" in note[2][0]


def test_a_404_on_a_live_call_still_fails(monkeypatch):
    """The case the criterion exists for. Nothing about v2.2 lowers this bar."""
    c2, _ = _run(monkeypatch, [_row("Some Live Award", "2027-01-31")])
    assert c2[2] is False and len(c2[3]) == 1


def test_a_blank_deadline_still_fails_check_2(monkeypatch):
    """DELIBERATELY narrower than check 3's exemption.

    Check 3 excuses a blank because a row that claims no date evidences nothing. A dead
    LINK is a defect either way - the reader clicks through to a 404 regardless.
    """
    c2, note = _run(monkeypatch, [_row("No Deadline Award", "")])
    assert c2[2] is False, "a blank deadline must NOT inherit the passed-deadline exemption"
    assert note is None


def test_410_is_treated_the_same_as_404(monkeypatch):
    c2, note = _run(monkeypatch, [_row("Japan Prize", "2025-01-31")], code=410)
    assert c2[2] is True and note and "HTTP 410" in note[2][0]


def test_403_is_still_not_a_disproof(monkeypatch):
    """5.2 is untouched: only 404 and 410 disprove. A block is not an absence."""
    c2, note = _run(monkeypatch, [_row("Blocked Award", "2027-01-31")], code=403)
    assert c2[2] is True and note is None


def test_a_mixed_delivery_separates_the_two(monkeypatch):
    c2, note = _run(monkeypatch, [
        _row("Past One", "2025-01-31", "https://a.test"),
        _row("Past Two", "2026-04-03", "https://b.test"),
        _row("Live One", "2027-02-01", "https://c.test"),
    ])
    assert c2[2] is False and len(c2[3]) == 1 and "Live One" in c2[3][0]
    assert note and len(note[2]) == 2


def test_the_amendment_is_named_in_the_gate():
    """So the next reader of a NOTE line can find the ruling that put it there."""
    src = (ROOT / "scripts" / "accept_delivery.py").read_text(encoding="utf-8")
    assert "AMENDMENT v2.2" in src
