"""End-to-end test of the license proxy via FastAPI TestClient (no network, provider mocked).

Proves the real HTTP path: license check, allow -> forward -> meter, and the kill switch
(revoked / unknown keys are denied WITHOUT ever calling the provider).
"""
import os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Env must be set before importing the server (module reads it at import).
_DB = os.path.join(tempfile.mkdtemp(), "lic.db")
os.environ["LICENSE_DB"] = _DB
os.environ["PROXY_MODEL"] = "openrouter/deepseek/deepseek-chat"
os.environ["OPENROUTER_API_KEY"] = "test-vendor-key"

from fastapi.testclient import TestClient
import litellm
from licenseproxy import server as srv
from licenseproxy.policy import LicenseStore

client = TestClient(srv.app)


def _issue(**kw):
    s = LicenseStore(_DB); k = s.issue("Cust", **kw); s.close(); return k


class _FakeResp:
    def model_dump(self):
        return {"choices": [{"message": {"content": '{"conference_name":"X"}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


def _mock_llm():
    calls = {"n": 0}
    async def fake(**kw):
        calls["n"] += 1
        return _FakeResp()
    return calls, fake


def _hdr(key, version="1.0.0"):
    return {"Authorization": f"Bearer {key}", "X-Client-Version": version}


def test_license_check_active_and_inactive():
    k = _issue()
    r = client.get("/v1/license", headers=_hdr(k))
    assert r.status_code == 200 and r.json()["active"] is True
    LicenseStore(_DB).revoke(k)
    r = client.get("/v1/license", headers=_hdr(k))
    assert r.status_code == 403 and r.json()["active"] is False


def test_completions_allow_and_meter():
    k = _issue(quota_tokens=1000)
    calls, fake = _mock_llm()
    orig = litellm.acompletion; litellm.acompletion = fake
    try:
        r = client.post("/v1/chat/completions", headers=_hdr(k),
                        json={"messages": [{"role": "user", "content": "hi"}]})
    finally:
        litellm.acompletion = orig
    assert r.status_code == 200
    assert calls["n"] == 1                                   # provider was called once
    assert r.json()["choices"][0]["message"]["content"]
    assert LicenseStore(_DB).usage_summary(k)["tokens"] == 15   # metered for billing


def test_revoked_key_is_denied_without_calling_provider():
    k = _issue()
    LicenseStore(_DB).revoke(k)                              # the kill switch
    calls, fake = _mock_llm()
    orig = litellm.acompletion; litellm.acompletion = fake
    try:
        r = client.post("/v1/chat/completions", headers=_hdr(k),
                        json={"messages": [{"role": "user", "content": "hi"}]})
    finally:
        litellm.acompletion = orig
    assert r.status_code == 403
    assert calls["n"] == 0                                   # provider NEVER called -> no cost


def test_unknown_key_denied():
    r = client.post("/v1/chat/completions", headers=_hdr("cfp_nope"),
                    json={"messages": []})
    assert r.status_code == 401


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
