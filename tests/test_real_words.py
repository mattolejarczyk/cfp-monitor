"""Length is not content.

Added 2026-08-12 after a page of 4,512 characters was judged substantial and turned out to be
twenty-five words of German error text wrapped around one base64 logo. Every check we had -
status code, byte length, soft-404 wording - passed it, and the conclusion drawn from that was
about to reach the customer as "here is the call page".
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_s = importlib.util.spec_from_file_location("_ae", ROOT / "scripts" / "audit_evidence.py")
ae = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ae)

# The real thing, trimmed: a logo data URI and a short error message.
LOGO = "![Logo](data:image/svg+xml,%3c?xml%20version='1.0'%3e" + "%3cpath%20d='M460" * 200 + ")"
ERROR_PAGE = LOGO + " Ups! Etwas ist schiefgelaufen. Keine Sorge, es liegt nicht an dir."


def test_a_logo_blob_is_not_content():
    assert len(ERROR_PAGE) > 3000, "the fixture must be long, that is the whole point"
    ok, why = ae.readable(ERROR_PAGE)
    assert ok is False
    assert "readable text" in why
    assert ae.real_words(ERROR_PAGE) < 20


def test_a_wall_of_urls_is_not_content():
    page = "Links " + " ".join(f"https://example.org/page-{i}/deep/path" for i in range(400))
    assert len(page) > 10000
    assert ae.real_words(page) < 40
    assert ae.readable(page)[0] is False


def test_a_genuine_page_passes():
    """Floor calibrated against pages we actually measured: the error page scored 25, the
    thinnest legitimate one (SEMICON China navigation) scored 136. 40 sits in that gap with
    room either side - close enough to catch empty shells, far enough not to reject a real
    page that happens to be terse."""
    page = ("Call for Papers. The programme committee invites submissions of original work "
            "across all tracks of the conference. Abstracts should describe the problem, the "
            "approach taken, and the results obtained, and must be submitted through the "
            "online system before the published deadline. Accepted authors will be notified "
            "by email and asked to prepare a full manuscript for the proceedings. Topics "
            "include architecture, verification, security, tooling and industrial "
            "experience reports from production deployments.")
    assert ae.real_words(page) >= 40
    assert ae.readable(page)[0] is True


def test_the_floor_sits_between_the_pages_we_measured():
    """Guards the calibration itself, so a later tweak has to face these numbers."""
    assert ae.readable(" ".join(["wort"] * 25))[0] is False    # embedded world error page
    assert ae.readable(" ".join(["chrome"] * 136))[0] is True  # thinnest legitimate page


def test_the_soft_404_reason_still_wins_when_both_apply():
    """A short 'Page not found' is both empty AND a soft 404. The more specific reason is more
    useful to whoever reads the verdict, so the ordering is deliberate."""
    page = "Page not found. " + "The requested document could not be located here. " * 6
    ok, why = ae.readable(page)
    assert ok is False
    assert "soft 404" in why


@pytest.mark.parametrize("n_words,expected", [(10, False), (39, False), (60, True)])
def test_the_floor_is_where_we_put_it(n_words, expected):
    page = " ".join(["submission"] * n_words)
    assert ae.readable(page)[0] is expected


# --- raw HTML must not be counted as words --------------------------------------------------

RAW_HTML_SHELL = """
<!doctype html><html><head><style>.a{color:red}.b{margin:0}</style>
<script>function initialiseApplicationBootstrap(){var configuration={};return configuration;}</script>
</head><body><div class="container wrapper header navigation">
<img src="data:image/svg+xml,%3csvg%20viewBox='0 0 10 10'%3e%3cpath%20d='M4'/%3e%3c/svg%3e">
<span class="error-illustration">Ups! Etwas ist schiefgelaufen.</span>
</div></body></html>
"""


def test_markup_is_not_content():
    """Upstream built the same check over requests.get(...).text and counted tag names, class
    names and script identifiers as words. This shell scored 246 on that counter, over a
    threshold of 120. A filter that measures markup passes everything, which is worse than no
    filter because it looks like a control."""
    # The point is the RATIO: plenty of characters, almost no readable words.
    assert len(RAW_HTML_SHELL) > 400
    assert ae.real_words(RAW_HTML_SHELL) < 10
    assert ae.readable(RAW_HTML_SHELL)[0] is False


def test_a_real_page_still_passes_when_given_as_html():
    html = ("<html><body><h1>Call for Papers</h1><div class='content'><p>" +
            ("The committee invites original submissions describing research results, "
             "industrial experience and tooling. Abstracts must reach the programme chair "
             "through the online system before the published deadline. ") * 3 +
            "</p></div></body></html>")
    assert ae.real_words(html) >= 40
    assert ae.readable(html)[0] is True


def test_script_bodies_do_not_inflate_the_count():
    page = "<script>" + "var someLongVariableName = anotherLongIdentifier; " * 80 + "</script><p>Hi</p>"
    assert ae.real_words(page) < 10
