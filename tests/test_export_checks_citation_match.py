"""A deadline verdict may only come from the page the row currently cites.

The badge on the customer page answers one question - did we open the page THIS ROW CITES and
find the deadline on it. Evidence gathered against a url the row has since stopped citing
answers a question about a different page.

Preferring the current citation was not enough, and the gap reached a customer page:
SecureWorld St. Louis shipped badged "Disputed" with no deadline to dispute, quoting scraped
table headings off an events index the row no longer cited, because it had NO evidence for its
current citation and the superseded row was the only candidate.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("ec", ROOT / "scripts" / "export_checks.py")
ec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ec)

CITE = "https://events.secureworld.io/details/st-louis-mo-2026/"


def test_the_same_page_is_the_same_page_despite_cosmetic_url_drift():
    """Measured 2026-09-14: one of 156 rows differed only cosmetically. A raw `==` would have
    discarded a real verdict as superseded."""
    for other in ("https://events.secureworld.io/details/st-louis-mo-2026",
                  "http://events.secureworld.io/details/st-louis-mo-2026/",
                  "https://www.events.secureworld.io/details/st-louis-mo-2026/",
                  "https://events.secureworld.io/details/st-louis-mo-2026/#speakers"):
        assert ec.same_page(CITE, other), other


def test_a_different_page_is_not_the_cited_page():
    assert not ec.same_page(CITE, "https://www.secureworld.io/events")
    assert not ec.same_page(CITE, "https://events.secureworld.io/details/twin-cities-mn-2026/")


def test_a_blank_never_counts_as_a_match():
    """Otherwise a row with no citation would collect every verdict recorded against a blank."""
    assert not ec.same_page("", "")
    assert not ec.same_page(None, None)
    assert not ec.same_page(CITE, "")


def test_precedence_is_still_worst_first():
    """Collapsing several claims to one badge must show the least reassuring thing we know."""
    assert ec.PRECEDENCE.index("contradicted") < ec.PRECEDENCE.index("no_quote")
    assert ec.PRECEDENCE.index("no_quote") < ec.PRECEDENCE.index("unreadable")
    assert ec.PRECEDENCE.index("unreadable") < ec.PRECEDENCE.index("verified")


def _select(rows: list[dict], cite: str) -> list[dict]:
    """The selection the export performs: keep only evidence against the cited page."""
    return [r for r in rows if ec.same_page(r["source_url"], cite)]


def test_a_superseded_contradiction_is_set_aside_not_merely_outranked():
    """The live defect. With no evidence for the current citation the row gets NO badge -
    silence is the honest answer when we have not opened the page it cites."""
    rows = [{"source_url": "https://www.secureworld.io/events", "verdict": "contradicted"}]
    assert _select(rows, CITE) == []


def test_a_verdict_against_the_cited_page_survives():
    """The inversion: the filter must not swallow the evidence it exists to protect."""
    rows = [{"source_url": CITE, "verdict": "verified"},
            {"source_url": "https://www.secureworld.io/events", "verdict": "contradicted"}]
    kept = _select(rows, CITE)
    assert [r["verdict"] for r in kept] == ["verified"]


def test_a_real_contradiction_on_the_cited_page_still_reaches_the_page():
    """Setting aside stale verdicts must not make contradictions unreportable - a dispute we
    can prove against the row's own citation is exactly what the badge is for."""
    rows = [{"source_url": CITE, "verdict": "contradicted"},
            {"source_url": CITE, "verdict": "verified"}]
    kept = _select(rows, CITE)
    assert min(ec.PRECEDENCE.index(r["verdict"]) for r in kept) == \
        ec.PRECEDENCE.index("contradicted")
