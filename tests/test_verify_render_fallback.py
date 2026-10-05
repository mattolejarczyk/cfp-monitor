"""ACT-12: the weekly verifier reads a walled page through the real-Chrome render, and changes nothing for pages the plain fetch reads."""
from src.cfp_monitor import verify
from src.cfp_monitor.verify import (NOT_FOUND, VERIFIED, fetch_page_text, needs_render, verify_against_page)

# Saved fixtures: what blackhat.com answered a plain fetch (2026-10-02, trap case T03) and what the same page shows in a real browser.
WALL = "Request unsuccessful. Incapsula incident ID: 260000060773792091-441289197983367596"
RENDERED = ("Black Hat Asia 2027 Call for Summits. Submit your proposal. Close date: 12 October 2026 (23:59 Singapore Time GMT/UTC +8). "
            "Summits are held on the first day of the briefings. Submissions are reviewed by the Black Hat Asia review board. " * 2)


def _reset():
    verify._renders_used[0] = 0


def test_needs_render_only_for_walls():
    assert needs_render("", "HTTP 403") and needs_render(WALL, "ok") and needs_render("tiny shell", "ok")
    assert not needs_render("", "HTTP 404") and not needs_render("", "HTTP 410") and not needs_render("", "TimeoutError")
    assert not needs_render("A real page " * 100, "ok")


def test_a_403_page_verifies_through_the_render_path():
    _reset()
    calls = []
    text, note = fetch_page_text("https://www.blackhat.com/asia-27/call-for-summits.html", plain=lambda u: ("", "HTTP 403"),
                                 render=lambda u: (calls.append(u) or RENDERED, "rendered via cdp, status 200"))
    assert calls and text == RENDERED and note.startswith("rendered after HTTP 403")
    assert verify_against_page(text, "2026-10-12", "Open").state == VERIFIED
    # without the fallback the same page reads as unconfirmed, which is the defect
    assert verify_against_page("", "2026-10-12", "Open").state == NOT_FOUND


def test_an_anti_bot_notice_is_rendered_and_a_still_walled_render_keeps_the_plain_answer():
    _reset()
    assert fetch_page_text("u", plain=lambda u: (WALL, "ok"), render=lambda u: (RENDERED, "x"))[0] == RENDERED
    _reset()
    assert fetch_page_text("u", plain=lambda u: ("", "HTTP 403"), render=lambda u: (WALL, "x")) == ("", "HTTP 403")     # hard anti-bot host: skipped by design
    assert fetch_page_text("u", plain=lambda u: ("", "HTTP 403"), render=lambda u: ("", "no chrome")) == ("", "HTTP 403")


def test_a_page_the_plain_fetch_reads_never_touches_the_render():
    _reset()
    page = "Call for papers. Deadline: October 12, 2026. " * 20
    def boom(u):
        raise AssertionError("render must not run")
    assert fetch_page_text("u", plain=lambda u: (page, "ok"), render=boom) == (page, "ok")
    assert fetch_page_text("u", plain=lambda u: ("", "HTTP 404"), render=boom) == ("", "HTTP 404")    # a dead page stays dead


def test_the_render_is_capped_per_run():
    _reset()
    n = []
    for _ in range(verify.MAX_RENDERS_PER_RUN + 5):
        fetch_page_text("u", plain=lambda u: ("", "HTTP 403"), render=lambda u: (n.append(1) or RENDERED, "x"))
    assert len(n) == verify.MAX_RENDERS_PER_RUN
    _reset()


def test_the_weekly_verifier_uses_the_fallback():
    import inspect
    from scripts import verify_grounding
    assert "fetch_page_text(candidate)" in inspect.getsource(verify_grounding.main)
