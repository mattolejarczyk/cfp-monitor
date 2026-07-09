# licenseproxy — licensed LLM proxy (kill switch + token metering)

Option D: the customer's local build never holds the LLM provider key. It sends extraction
requests to **this vendor-hosted proxy**, authenticated with a per-customer **license key**. The
proxy validates the license and only then forwards to the real provider using the **vendor's** key,
metering tokens.

**What this gives you**
- **Kill switch** — `revoke <key>` and that customer's crawling stops on the next extraction call.
- **Force-upgrade / kill old versions** — set a per-license `version_floor`; older clients get 426.
- **Feature gating** — entitlements ride in the key (`--features crawl,export`).
- **Token metering / billing** — every call is metered per key; enforce a `quota_tokens` cap.
- **Cost control** — the proxy chooses the model; the client can't request an expensive one.

## Pieces
- `policy.py` — enforcement core (SQLite key store + `authorize()` + metering). Pure stdlib, unit-tested.
- `server.py` — thin FastAPI shell speaking OpenAI `/v1/chat/completions`; forwards on allow.
- `admin.py` — issue / revoke / floor / quota / list / usage CLI.

## Vendor: run the proxy
1. `cp licenseproxy/.env.example licenseproxy/.env` and fill in the keys.
2. Windows: `scripts\run_proxy.bat` (loads `licenseproxy\.env`, starts on :8800).
   Any OS: `uv run uvicorn licenseproxy.server:app --host 0.0.0.0 --port 8800`.

**Both OpenAI and OpenRouter are supported** — set `PROXY_MODEL` and the matching key:
```
# OpenRouter
PROXY_MODEL=openrouter/deepseek/deepseek-chat
OPENROUTER_API_KEY=sk-or-...        # the VENDOR key, never shipped to customers
# ...or OpenAI
# PROXY_MODEL=openai/gpt-4o-mini
# OPENAI_API_KEY=sk-...
```
Issue a customer key:
```
python -m licenseproxy.admin issue --customer "PRIME|PR" --plan pro \
       --version-floor 1.0.0 --features crawl,export --quota 20000000
python -m licenseproxy.admin revoke  <key>      # kill switch
python -m licenseproxy.admin usage   <key>      # billing
```

## Customer: point the build at the proxy (no provider key on their machine)
In the customer's `.env`:
```
CFP_LLM_PROXY_URL=https://license.yourco.com    # your deployed proxy
CFP_LICENSE_KEY=cfp_xxx                          # their key
# OPENROUTER_API_KEY intentionally NOT set
```
`Settings.require_llm_key()` then requires the license (not a provider key), and every extraction
call routes through the proxy. Revoke the key → extraction fails → the monitor can't crawl.

## Notes / limits
- Enforcement is **server-side** (the capability lives on your side), so it can't be bypassed by
  patching the client the way a pure local check could.
- Deploy behind HTTPS. Rotate the vendor provider key independently of customer keys.
- `quota_tokens` is a period cap; reset it on billing with `admin quota <key> <n> --reset-used`.
- The client shows a friendly license banner at launch (`licensing.check_license` → `GET /v1/license`)
  and disables Run when the license is inactive; enforcement still also happens at the extraction
  call (fail-closed) in case the check is skipped or the server is briefly unreachable.
