"""Hosts that can never be a citation, and hosts that only look like them.

Both rules here are STRUCTURAL - no amount of fetching reveals the problem, because the page
resolves and reads fine. A search redirect expires; a social post scrolls away. Either way the
citation quietly stops supporting the claim while still returning 200.
"""
from __future__ import annotations

import importlib.util
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
