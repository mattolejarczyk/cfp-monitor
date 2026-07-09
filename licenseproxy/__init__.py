"""Vendor-controlled licensing + LLM proxy for cfp-monitor (Option D).

The customer's local build never holds the LLM provider key. Instead it sends extraction
requests to THIS proxy authenticated with a per-customer license key. The proxy validates the
license (active / not-revoked / version floor / entitlements / quota), and only then forwards to
the real LLM provider using the VENDOR's key — metering tokens for billing.

Consequences:
- Revoke a key  -> that customer's crawling stops immediately (hard kill switch).
- Raise a version floor -> old client versions are refused (force upgrade / kill old versions).
- Meter usage  -> the vendor pays the provider and bills the customer (resolves "who pays tokens").

`policy.py` is the pure, stdlib, fully-tested enforcement core. `server.py` is a thin HTTP shell
around it. `admin.py` is the issue/revoke/usage CLI.
"""
