"""Hosts that can never be a citation, and hosts that only look like them.

Both rules here are STRUCTURAL - no amount of fetching reveals the problem, because the page
resolves and reads fine. A search redirect expires; a social post scrolls away. Either way the
citation quietly stops supporting the claim while still returning 200.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("_ar", ROOT / "scripts" / "apply_resolutions.py")
ar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ar)


@pytest.mark.parametrize("url", [
    "https://www.facebook.com/cleanenergycouncil/",
    "https://facebook.com/AGRITECHNICA/",
    "https://www.facebook.com/adipecofficialpage/videos/as-the-global-energy",
    "https://x.com/someconf/status/12345",
    "https://www.linkedin.com/company/someconf/",
    "https://t.me/someconf",
])
def test_social_pages_are_not_citations(url):
    assert ar._is_social(url) is True


@pytest.mark.parametrize("url", [
    "https://pretalx.com/fwd-cloudsec-2026/",              # a real CFP platform
    "https://www.interphex.com/en-us/education/conference-overview.html",
    "https://informaconnect.com/bioeurope/",
    "https://x.company.org/cfp",
])
def test_hosts_that_merely_contain_a_social_name_are_fine(url):
    """A substring check reported EIGHT social citations when there were five: 'x.com/' is
    inside 'pretalx.com/' and 'interphex.com/'. One is the submission system itself and the
    other is the event's own site - rejecting either would discard good evidence."""
    assert ar._is_social(url) is False


def test_proxy_and_social_are_separate_rules():
    assert ar._is_proxy("https://vertexaisearch.cloud.google.com/grounding-api-redirect/AB")
    assert not ar._is_social("https://vertexaisearch.cloud.google.com/grounding-api-redirect/AB")
    assert ar._is_social("https://www.facebook.com/x/")
    assert not ar._is_proxy("https://www.facebook.com/x/")


# --- deliberate clears must survive the merge -----------------------------------------------

_rd = importlib.util.spec_from_file_location("_rd", ROOT / "scripts" / "refresh_delivery.py")
rd = importlib.util.module_from_spec(_rd)
_rd.loader.exec_module(rd)


@pytest.mark.parametrize("detail", [
    "[retired] 2026-08-11 no source for the date",
    "[R1 withdrawal] 2026-08-12 cited page returns HTTP 404",
])
def test_every_deliberate_clear_marker_is_recognised(detail):
    """A blank in the database must reach the delivery when we emptied the field ON PURPOSE.
    This test exists because the check was too narrow twice: cfp_model=='Not Announced' missed
    closed calls, then '[retired]' alone missed R1 withdrawals - leaving four dead 404 links in
    the customer file while the database said they were gone."""
    assert rd._is_deliberate_clear(detail) is True


@pytest.mark.parametrize("detail", [
    "", "   ", "[L2] deadline not stated on the page - grounding value stands",
    "[merge] quote confirmed on the cited page at merge time",
    "[upgraded 2026-08-12] replaced with the live page",     # sets a URL, does not clear one
])
def test_ordinary_details_do_not_clear_anything(detail):
    assert rd._is_deliberate_clear(detail) is False


def test_every_marker_written_anywhere_is_in_the_set():
    """Guards the guard: if a writer starts emitting a new bracketed clear-marker, it has to be
    registered here or the blank will silently fail to carry."""
    src = (ROOT / "scripts" / "apply_resolutions.py").read_text(encoding="utf-8")
    written = set(re.findall(r'f"(\[[A-Za-z0-9 ]+\])', src))
    clearing = {m for m in written if "retired" in m.lower() or "withdrawal" in m.lower()}
    assert clearing <= set(rd.CLEAR_MARKERS), (
        f"apply_resolutions writes {clearing - set(rd.CLEAR_MARKERS)} but refresh_delivery "
        f"does not recognise it as a deliberate clear")
