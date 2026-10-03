# Finding the right page without Google grounding: options to test (2026-10-03)

## Why look at this
Grounded Gemini does two jobs in one call: it FINDS a page and it READS it. The read-the-page experiment (experiments/read_the_page_pass/RESULT.md) showed that reading a given page with a cheap model and a code-checked quote is safe and costs fractions of a cent. That leaves the FINDING step. Today it costs about 6 cents a call, and in the 2026-09-30 test the page it cited was the same page as our verified one only 9 times in 24 (the same host 20 times in 24); about a third of citations name a site that was not among its own search sources.
A separate finder lets us choose the cheapest reliable one, and lets the finder and the reader be tested independently.

## What a finder must return
Given (event name, edition year, market, last year's URL if we have one): a short ranked list of candidate URLs for (a) the event's main page for that edition and (b) its call for speakers / papers / entries. We then render and read the pages with the read-the-page pass and the gate proves every quote.
**Score:** hit@1, hit@3, hit@5 (the operator-verified page or the benchmark evidence page, same URL, or same host and path stem), cost per query, seconds. Gold: the 13 pinned events' pages, the 40 benchmark events' evidence URLs.

## The options (prices checked 2026-10-03 unless marked)

### A. Search APIs, our code orchestrates (the model, if any, only reads)
| Option | Price | Notes |
|---|---|---|
| **Brave Search API** | $5 per 1,000 queries; the free tier ended Feb 2026, replaced by about $5 of credit a month (about 1,000 queries) | its own index; good on recent pages |
| **Tavily** | 1,000 free credits a month (a basic search is 1 credit); then $0.008 per credit | returns cleaned snippets; built for agents |
| **Serper.dev** (Google results) | 2,500 free queries, then $0.30 to $1.00 per 1,000 | cheapest Google results; scraping-based, a terms-of-service grey area to weigh |
| **Exa** (semantic search) | $7 per 1,000 searches, includes the text of 10 results; $20 free credit for new accounts, then $10 free a month | good at "find the CFP page for X" by meaning |
| **OpenRouter web plugin** (`:online` on any model, including DeepSeek) | $4 per 1,000 results (Exa-powered; 5 results by default, so up to $0.02 a request) plus the model's tokens | **no new account: we already have an OpenRouter key** |
| SerpAPI | $9 to $25 per 1,000 | works, expensive |
| Google Programmable Search JSON API | closed to new customers; discontinued 2027-01-01 | skip |
| DuckDuckGo through unofficial libraries; self-hosted SearXNG | free | rate limits and terms of use: experiments only |

### B. Language models with a search tool built in
| Option | Price / status | Notes |
|---|---|---|
| **Gemini + Google grounding** (today) | about 6 cents a narrow call (measured 09-30) | the baseline |
| **OpenAI web_search tool (Responses API)** | $10 per 1,000 calls with reasoning models ($25 with non-reasoning) plus tokens; one request can make several searches | pay-per-use |
| **Codex through the ChatGPT subscription** | no extra cost; draws on subscription limits (Plus: about 30 to 150 messages per 5 hours; Pro: 300 to 1,500) | **tested 10-03: with `-c features.standalone_web_search=true` Codex ran a real search and returned exactly Nullcon's verified call-for-papers URL, for about 12,500 tokens.** The feature is flagged "under development"; rate-limited; slow; fine for batch experiments, not yet a scheduled dependency |
| **Hermes (browser agent) with the free models** | $0 | already used for the benchmark; slow; uses a real browser, so mind search engines' terms |
| Anthropic web search tool; Perplexity Sonar API | not re-checked today | candidates if A and B above disappoint |
| **DeepSeek** | the standard API has NO built-in search (the consumer app does). Since 2026-05-26 its Anthropic-compatible endpoint documents a server-side web search tool, but that needs a DeepSeek API key (we reach DeepSeek through OpenRouter) | "DeepSeek with search" in practice = a DeepSeek model plus OpenRouter's `:online`, or plus our own search API as a tool |

### C. No search at all (free; possibly the best first step)
1. **Successor probing.** Last year's URL with the year bumped (`/2026/` to `/2027/`, `...-2026` to `...-2027`) and the site's own links from last year's page. One cheap request each. Test: how often does the next edition live at the predicted URL?
2. **Structured data already on the page.** Many event sites embed schema.org `Event` JSON-LD (`startDate`, `endDate`, `location`), iCal feeds or `sitemap.xml` dates: machine-readable, no model, no search. Test: the share of the 350 saved pages that carry it.
3. **Community lists as LEADS, never evidence** (the cfptime.org lesson): security-conference deadline lists, `ccfddl` (CCF deadlines), `confs.tech` (JSON on GitHub), WikiCFP. Free; good for discovering that an event exists and where its site is.
4. **Our page library and sitemap discovery** (360 pages, 70 sites) for events we already know.
5. **Wayback / Common Crawl** to learn a site's URL pattern across editions. Free; lags.

## Test plan (all in shadow; nothing reaches a customer)
1. **Finder benchmark:** for the 13 pinned events and the 40 benchmark events, ask each finder the same question; record hit@1/3/5, seconds and cost. Baseline for Gemini comes from the saved grounding logs.
2. **End to end:** best finder plus render plus read-the-page pass versus today's grounded call on the same events: facts right, facts blank, wrong claims (must stay 0), cost per event.
3. **Keep the safe part:** whatever finds the page, the code-checked quote and the gate decide what is accepted.

## What can start today, and what needs you
- **Can start now with what we have:** OpenRouter `:online` with DeepSeek and others (existing key); Codex with search on (subscription, small batches, mind the 5-hour window); successor probing; JSON-LD coverage over the saved pages; community lists as leads.
- **Needs an API key from you (free to create, I cannot create accounts):** Tavily (1,000 free a month), Serper (2,500 free), Brave (about 1,000 queries of monthly credit), Exa ($20 free). Each covers the 53-event benchmark many times over.

## Risks to keep in view
- A finder that returns an aggregator is a lead, not evidence. The page must be the event's own, and the gate must read the quote on it.
- Subscription capacity is shared with the operator's own use; run batches, not loops; no scheduled production job should depend on an under-development feature.
- Search engines' terms for automated queries differ; prefer the official APIs for anything that runs weekly.
