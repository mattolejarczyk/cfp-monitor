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


def _run(monkeypatch, rows, code=404, browser=None):
    """`browser` is what a real browser gets for a link the plain fetch saw as 403. The default
    - still 403 - is the pre-2026-09-16 behaviour, so these tests never launch Chromium."""
    monkeypatch.setattr(ad, "link_status", lambda u: (code(u) if callable(code) else code, ""))
    monkeypatch.setattr(ad, "fetch_text", lambda u: ("", ""))
    monkeypatch.setattr(ad, "browser_second_opinion",
                        browser or (lambda urls: {u: 403 for u in urls}))
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


# ---------------------------------------------------------------------------------------------
# 2026-09-16 - THE TWO BLIND SPOTS. Measured on the live deliveries that day: 19 of 95 distinct
# links sat in columns check 2 never read, and 1 of 12 links behind a plain 403 was a real 404.

def _notes(g_notes, num):
    return [n for n in g_notes if n[0] == num]


def _gate(monkeypatch, rows, code=404, browser=None):
    monkeypatch.setattr(ad, "link_status", lambda u: (code(u) if callable(code) else code, ""))
    monkeypatch.setattr(ad, "fetch_text", lambda u: ("", ""))
    monkeypatch.setattr(ad, "browser_second_opinion",
                        browser or (lambda urls: {u: 403 for u in urls}))
    g = ad.Gate.__new__(ad.Gate)
    g.rows, g.results, g.notes, g.network, g.today = rows, [], [], True, TODAY
    g.check_citations()
    return next(r for r in g.results if r[0] == "2"), g.notes


def test_a_404_hiding_behind_a_403_fails_a_live_call(monkeypatch):
    """Black Hat USA, 2026-09-16: 403 to a plain fetch, 404 to a browser, in all three columns."""
    c2, _ = _run(monkeypatch, [_row("Black Hat USA", "2027-03-01", "https://bh.test/cfb")],
                 code=403, browser=lambda urls: {u: 404 for u in urls})
    assert c2[2] is False
    assert "a browser says 404" in c2[3][0]


def test_a_403_a_browser_can_read_stays_exempt(monkeypatch):
    """The inversion: 6 of 12 blocked links opened fine in a browser. The second opinion may
    FIND a dead link; it must never turn a live, bot-blocked one into a failure."""
    c2, note = _run(monkeypatch, [_row("Gartner IAM", "2027-03-01")],
                    code=403, browser=lambda urls: {u: 200 for u in urls})
    assert c2[2] is True and note is None


def test_a_browser_that_cannot_start_is_reported_not_silent(monkeypatch):
    """If Chromium will not launch, 'nothing found' and 'nothing checked' look identical unless
    the gate says which one happened."""
    def boom(urls):
        raise RuntimeError("no browser")
    c2, notes = _gate(monkeypatch, [_row("Blocked", "2027-03-01")], code=403, browser=boom)
    assert c2[2] is True
    assert any("did NOT run" in n[1] and "1 link(s) behind a 403" in n[1] for n in notes)


def test_a_dead_submission_link_is_reported(monkeypatch):
    """SecureWorld: evidence page alive, the form the customer clicks returns 404."""
    row = {**_row("SecureWorld Seattle", "2027-03-01", "https://sw.test/event"),
           "SUBMISSION URL": "https://sw.test/call-for-speakers"}
    c2, notes = _gate(monkeypatch, [row], code=lambda u: 404 if "call-for" in u else 200)
    sub = _notes(notes, "2s")
    assert sub and "SUBMISSION URL" in sub[0][2][0] and "LIVE" in sub[0][1]


def test_a_dead_submission_link_is_advisory_until_upstream_agrees(monkeypatch):
    """Criterion 2 as AGREED covers cited pages. Rejecting a delivery on a link upstream never
    agreed was in scope is a change for the two parties, not for this file."""
    row = {**_row("SecureWorld Seattle", "2027-03-01", "https://sw.test/event"),
           "SUBMISSION URL": "https://sw.test/call-for-speakers"}
    c2, _ = _gate(monkeypatch, [row], code=lambda u: 404 if "call-for" in u else 200)
    assert c2[2] is True


def test_a_passed_deadline_submission_link_is_decay(monkeypatch):
    row = {**_row("SecureWorld Detroit", "2026-08-03", "https://sw.test/event"),
           "SUBMISSION URL": "https://sw.test/call-for-speakers",
           "CFP_SUBMISSION_URL": "https://sw.test/call-for-speakers"}
    _, notes = _gate(monkeypatch, [row], code=lambda u: 404 if "call-for" in u else 200)
    sub = _notes(notes, "2s")
    assert len(sub) == 1 and "passed" in sub[0][1]
    assert "SUBMISSION URL + CFP_SUBMISSION_URL" in sub[0][2][0], "one link, reported once"


def test_the_evidence_link_is_not_reported_twice(monkeypatch):
    """Troopers cites one pretalx URL in all three columns. Criterion 2 already judges it."""
    u = "https://pretalx.test/cfp"
    row = {**_row("Troopers", "2027-03-01", u), "SUBMISSION URL": u, "CFP_SUBMISSION_URL": u}
    c2, notes = _gate(monkeypatch, [row])
    assert c2[2] is False and not _notes(notes, "2s")
