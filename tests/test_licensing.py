"""Offline tests for the license enforcement core (policy.py) + the client proxy-mode gate.
No network, no web framework — the HTTP server is a thin shell over these decisions."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from licenseproxy.policy import (
    LicenseStore, version_lt,
    OK, UNAUTHORIZED, PAYMENT_REQUIRED, FORBIDDEN, UPGRADE_REQUIRED,
)
from cfp_monitor.config import Settings


def test_version_compare():
    assert version_lt("1.0.0", "1.2.0") is True
    assert version_lt("1.10.0", "1.9.0") is False        # numeric, not lexical
    assert version_lt("1.2.0", "1.2.0") is False


def test_active_key_allows():
    s = LicenseStore()
    k = s.issue("Acme", features=["crawl"], quota_tokens=1000)
    d = s.authorize(k, client_version="1.0.0", feature="crawl")
    assert d.allowed and d.status == OK


def test_unknown_key_denied():
    d = LicenseStore().authorize("cfp_nope")
    assert not d.allowed and d.status == UNAUTHORIZED


def test_revoke_is_a_kill_switch():
    s = LicenseStore()
    k = s.issue("Acme")
    assert s.authorize(k).allowed is True
    s.revoke(k)
    d = s.authorize(k)
    assert not d.allowed and d.status == FORBIDDEN
    # …and reactivation restores service.
    s.reactivate(k)
    assert s.authorize(k).allowed is True


def test_version_floor_forces_upgrade():
    s = LicenseStore()
    k = s.issue("Acme", version_floor="1.3.0")
    old = s.authorize(k, client_version="1.0.0")
    assert not old.allowed and old.status == UPGRADE_REQUIRED
    assert s.authorize(k, client_version="1.3.0").allowed is True


def test_feature_gate():
    s = LicenseStore()
    k = s.issue("Acme", features=["crawl"])
    assert not s.authorize(k, feature="export").allowed          # not entitled
    assert s.authorize(k, feature="crawl").allowed


def test_quota_and_metering():
    s = LicenseStore()
    k = s.issue("Acme", quota_tokens=100)
    s.record_usage(k, "m", prompt_tokens=60, completion_tokens=30)   # 90 used
    assert s.authorize(k).allowed is True
    s.record_usage(k, "m", prompt_tokens=10, completion_tokens=5)    # 105 used > 100
    d = s.authorize(k)
    assert not d.allowed and d.status == PAYMENT_REQUIRED
    assert s.usage_summary(k)["tokens"] == 105


def test_billing_report():
    s = LicenseStore()
    a = s.issue("Acme"); b = s.issue("Beta")
    s.record_usage(a, "m", 1_000_000, 500_000)     # 1.5M tokens
    s.record_usage(a, "m", 0, 500_000)             # +0.5M -> 2.0M total
    # Beta has no usage but must still appear.
    rows = s.billing(rate_per_mtok=0.20)
    by_cust = {r["customer"]: r for r in rows}
    assert by_cust["Acme"]["tokens"] == 2_000_000
    assert by_cust["Acme"]["cost"] == 0.40         # 2M * $0.20/M
    assert by_cust["Beta"]["tokens"] == 0 and by_cust["Beta"]["cost"] == 0.0


def test_client_requires_license_in_proxy_mode():
    # Proxy configured but no license key -> refuse to run (no silent fallback).
    s = Settings(); s.llm_proxy_url = "https://license.example.com"; s.license_key = None
    try:
        s.require_llm_key(); assert False, "should have raised"
    except RuntimeError as e:
        assert "license" in str(e).lower()
    # With a license key, proxy mode is satisfied even without an OpenRouter key.
    s.license_key = "cfp_abc"; s.openrouter_api_key = None
    s.require_llm_key()


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for fn in fns:
        try:
            fn(); print(f"PASS {fn.__name__}")
        except Exception as e:
            bad += 1; print(f"FAIL {fn.__name__}: {e!r}")
    print(f"--- {len(fns)-bad}/{len(fns)} passed ---")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    _run()
