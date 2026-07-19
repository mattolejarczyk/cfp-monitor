"""Offline tests for the anti-bot / CDP reachability guard.

Regression cover for a real bug: the guard used to test whether CDP was *configured*
(`settings.cdp_url` truthy). Because the installer writes CFP_CDP_URL into every customer
.env, that was always true, so the "don't auto-crawl a hard anti-bot site" protection was
silently disabled whenever the debug Chrome wasn't actually running.
"""
import socket

from cfp_monitor.fetch import _force_fallback_domain, _will_use_cdp, cdp_reachable


class _S:
    def __init__(self, cdp_url=None):
        self.cdp_url = cdp_url


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_hard_antibot_domain_detection():
    assert _force_fallback_domain("https://events.reutersevents.com/energy-live")
    assert _force_fallback_domain("https://reutersevents.com/x")
    assert not _force_fallback_domain("https://www.robobusiness.com/")


def test_unset_cdp_is_not_reachable():
    assert cdp_reachable(None) is False
    assert cdp_reachable("") is False


def test_configured_but_dead_endpoint_is_not_reachable():
    """The core bug: a configured URL with nothing listening must NOT count as available."""
    dead = f"http://localhost:{_free_port()}"
    assert cdp_reachable(dead) is False


def test_reachable_when_something_is_actually_listening():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    try:
        assert cdp_reachable(f"http://localhost:{srv.getsockname()[1]}") is True
    finally:
        srv.close()


def test_will_use_cdp_requires_reachable_endpoint_not_just_config():
    dead = f"http://localhost:{_free_port()}"
    url = "https://events.reutersevents.com/energy-live"
    # configured but dead -> we must NOT claim the CDP path (that would expose the IP)
    assert _will_use_cdp(url, _S(dead)) is False
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    try:
        live = f"http://localhost:{srv.getsockname()[1]}"
        assert _will_use_cdp(url, _S(live)) is True
        # a normal site never uses CDP even when it's up
        assert _will_use_cdp("https://www.robobusiness.com/", _S(live)) is False
    finally:
        srv.close()


def test_malformed_cdp_url_is_not_reachable():
    for bad in ("not a url", "http://", "://nope"):
        assert cdp_reachable(bad) is False
