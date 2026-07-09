# LLM model & cost reference

**Added 2026-07-09.** What model the monitor uses for extraction, how its cost compares to the
frontier models, and how to change it. Prices move — treat the tables as order-of-magnitude and
re-check the sources before quoting exact figures to a customer.

## What we use, and why
- **Extraction model:** DeepSeek-V3 (`deepseek-chat`) via OpenRouter (`openrouter/deepseek/deepseek-chat`).
- **Why cheap is right here:** the crawler hands the LLM already-cleaned page markdown and asks for a
  small structured-JSON object (name, dates, deadline, submission URL, status). That's an extraction
  task, not a reasoning task — a frontier model adds little. Our *misses* come from **crawling**
  (blocked sites, JS shells, budget timeouts), not from the extractor's intelligence.
- **A real LLM still does the work** — without it you'd have raw HTML, not structured facts.

## Price per 1M tokens
| Model | Input $/1M | Output $/1M |
|---|--:|--:|
| **DeepSeek-V3 — what we use** | ~$0.14–0.27 | ~$0.28–1.10 |
| GPT-5 | $1.25 | $10.00 |
| Claude Sonnet 5 | $3.00 (~$2 intro to 2026-08-31) | $15.00 (~$10 intro) |
| Claude Opus 4.8 | $5.00 | $25.00 |

## What it costs in practice
Extraction is **input-heavy** (page markdown + JSON schema in, a small object out) — roughly
**~25K input + ~1.5K output tokens per conference** at the tuned batch settings.

| Model | ≈ per conference | ≈ per 100-conference run | Relative cost |
|---|--:|--:|--:|
| **DeepSeek-V3 (current)** | **~$0.005–0.01** | **~$0.50–1.00** | **1× (baseline)** |
| GPT-5 | ~$0.05 | ~$5 | ~5–10× |
| Claude Sonnet 5 | ~$0.07–0.10 | ~$7–10 | ~10–20× |
| Claude Opus 4.8 | ~$0.16 | ~$16 | ~20–30× |

**Takeaway:** moving extraction to a frontier model multiplies token cost ~10–30× for marginal
quality gain on this task. Reserve the pricier models for a targeted "hard cases" re-pass if we ever
find rows the cheap model genuinely can't parse. (All four support prompt caching, which trims the
repeated-schema prefix for the pricier models — but page content varies per call, so it only offsets
part.)

## Money flow (recap)
Customer crawls locally → their build calls the **vendor proxy** with a license key → the proxy
calls the LLM with **your** provider key and **meters tokens** → you bill the customer
(`admin billing --rate <$/M tokens>`). You front the token cost and recover it per customer. This is
why the provider key lives only on the proxy, never on customer machines.

## Changing the model (single lever, all customers)
The model is set **once**, on the VPS, in `licenseproxy/.env` as `PROXY_MODEL` (+ the matching
`OPENROUTER_API_KEY` / `OPENAI_API_KEY`). To switch:
```bash
# on the VPS, in the app dir
nano .env                                   # edit PROXY_MODEL (and key if switching provider)
PM2_HOME=$HOME/.pm2 pm2 restart cfp-proxy
```
One edit changes the model for **every** customer — no client-side change. Both OpenAI (`openai/...`)
and OpenRouter (`openrouter/...`) model strings are supported.

## ⚠️ Deprecation to action
DeepSeek is **deprecating the `deepseek-chat` / `deepseek-reasoner` model names on 2026-07-24**
(they become compatibility aliases for the newer V4 Flash tier). Our `PROXY_MODEL` points at
`openrouter/deepseek/deepseek-chat`, so it keeps working via the alias — but plan to update it to the
successor model id. It's the one-line `.env` + `pm2 restart` change above.

## Sources (re-verify before quoting)
- DeepSeek: <https://api-docs.deepseek.com/quick_start/pricing/>, <https://pricepertoken.com/pricing-page/provider/deepseek>
- OpenAI / GPT-5: <https://developers.openai.com/api/docs/pricing>, <https://pricepertoken.com/pricing-page/model/openai-gpt-5>
- Claude: bundled `claude-api` reference (cached 2026-06-24) — Sonnet 5 $3/$15, Opus 4.8 $5/$25.
