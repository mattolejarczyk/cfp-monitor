# Grounding reliability - investigation and test plan

Drafted 2026-09-30. **Status: PLAN ONLY. Nothing has been run and nothing is wired into the pipeline.**
Follows the standing rule for `experiments/`: theory and isolated tests first, wired in only once proven.

## 1. Why this exists

Two finished prospect-market runs on 2026-09-30 (Robotics, Semiconductor) made 192 Gemini calls and got
51 usable, searched answers (27%). 98 calls were Google 504 DEADLINE_EXCEEDED, 43 were answers that came
back with NO search behind them, 0 were quota (429). Per-row outcomes look independent (about 30% of
first attempts succeed, and retries do no better), so failures do not look tied to particular conferences.
The cost is real: each grounded call ran about 4.5 searches and each search is billed.

Measured from `Markets/*_audited.grounding.jsonl`. NOT known: how long each call ran before failing, the
thinking setting in effect, time-of-day pattern. The trail carries no timestamps.

## 2. Facts established (with source)

| Fact | Source |
|---|---|
| Runs use `gemini-3-flash-preview`, via API key on the Gemini Developer API (`generativelanguage.googleapis.com`), not Vertex | `run_market_audit.py` DEFAULT_MODEL, `genai.Client(api_key=...)` |
| That model IS listed by Google, marked **preview**: "more restrictive rate limits", deprecated with 2 weeks notice | ai.google.dev/gemini-api/docs/models |
| The key sees 61 models incl. `gemini-3.1-flash-lite` (stable), `3.5-flash-lite`, `3.6/3.7/3.8-flash` | `client.models.list()` run 2026-09-30, read-only |
| Google gives NO way to force the model to search; it decides per prompt | ai.google.dev/gemini-api/docs/google-search |
| Gemini 3 grounding: billed per search query the model runs. Listed at 5,000 free/month then $14 per 1,000. Gemini 2.5 is $35 per 1,000 grounded PROMPTS | ai.google.dev/gemini-api/docs/pricing |
| Preview models have more restrictive rate limits; no separate grounding limit | ai.google.dev/gemini-api/docs/rate-limits |
| Cloud Billing: set Group by = SKU and Service = Gemini API. Per-model attribution is not promised for every charge | ai.google.dev/gemini-api/docs/billing |
| Third-party test (24 queries, small): smaller flash-lite grounded more often (19/24) than larger models (11/24) | caseywest.com (July 2026) - weak evidence, NOT our model |
| Our own 2026-09-19 note: 3.5-flash grounded 0/4, 3-flash-preview 3/6, 3.8-flash 0/3 | comment above DEFAULT_MODEL - tiny sample |

## 3. Open questions - each answered by a measurement, not an opinion

Q1. Why are the console charges "not specific to a model", and does the total reconcile to usage?
Q2. Is the 504 a call-length problem (many searches + big JSON answer), a thinking-time problem, a
    preview-capacity problem, or time-of-day?
Q3. Why does the model skip search on a call that asked for it, and does prompt or model change that?
Q4. Which setup gives the best USABLE ROWS PER DOLLAR, judged against known answers?

## 4. Workstream A - billing reconciliation (free, no API calls)

1. AI Studio > Usage (aistudio.google.com/usage): requests, tokens and grounding count by model, last 30 days.
2. Cloud Console > Billing > Reports: Service = Gemini API, Group by = SKU, same dates. Note which SKU carries
   "Grounding with Google Search" and its unit count.
3. Reconcile: units x listed rate = charge? Tokens x model rate = charge? Record any gap.
4. Confirm the project behind the key, its tier, and whether the 5,000 free monthly grounding allowance is
   already consumed. Expected, not yet confirmed: grounding is its own SKU, hence "not specific to a model".
5. Note: $35 per 1,000 is the Gemini 2.5 prompt rate; Gemini 3 is listed at $14 per query. 3,000+ calls at ~4.5
   queries each is ~13,000+ queries. The arithmetic can be consistent with more than one story - the SKU
   report decides which.

### Workstream A - RESULTS (2026-09-30, read from Cloud Billing, Service = Gemini API, Group by SKU)

- **The "not specific to a model" report was a filter, not a fact.** The URL's empty `modelNames=` parameter made the
  console apply "[Charges not specific to a model]" only (Model names 1 of 7). Removing those parameters shows every
  SKU. The dropdown is Google's fixed billing taxonomy (2.5 Flash, 3.0 Pro, 3.0 Pro Image, 3.1 Flash Image, 3.8 Flash,
  "3 Flash", plus the not-specific bucket), not a list of every API model ID.
- **Our model is billed, under the name "gemini 3 flash"** (`gemini-3-flash-preview`). Output $3.00/M and input $0.50/M
  reproduce exactly from the Sept SKUs (3,432,792 output tokens = $10.30). Reconciled.
- **Searches are one SKU: "Generate content search query gemini 3 paid one", exactly $14 per 1,000.**
  Aug: 3,340 paid ($46.76) + 5,400 free. Sept: 7,032 paid ($98.45) + 5,000 free. The 5,000 free allowance is used up
  in the first days of each month.
- **Spend:** Aug $72.79 (mostly on gemini 3.5 flash tokens + searches), Sept $134.06 through 9/30. Sept: searches
  $98.45 = 73% of the bill; tokens are minor. Tokens moved from "3.5 flash" to "3 flash" after 2026-09-19 as the code says.
- **Failed calls do not appear to be billed for searches.** 9/27: billed 1,871 paid search queries; our trails logged
  1,817 searches (successful responses only) across both markets and both sponsorship passes. ~3% gap, unexplained.
  A 504 or a no-search answer therefore costs almost nothing in search fees - the waste is TIME and retries, not money.
- **The money is in the sponsorship passes.** They average ~14 searches per call (593/42 and 678/49) against ~4.5 for
  the main research call (Robotics 90/20, Semiconductor 151/31). 9/27 cost $30.93, of which searches $26.19.
- **Output tokens are large:** 1.39M output tokens on 9/27 for ~250 successful calls. Thinking tokens bill as output, so
  this supports testing arm B (thinking level) - but it is not yet measured per call.
- **Unexplained:** the ~54-search gap on 9/27; whether the 9/30 run's ~241 logged searches match billing (billing lags).

### Sponsorship pass review (2026-09-30) - read from the 9/27 trails and final files

- **It is reliable where the main call is not.** 43/44 Cybersecurity and 49/50 Utility sponsorship calls succeeded (1 timeout,
  1 504, 0-2 no-search) on the same day and model where the main research call succeeded ~30% of the time. The sponsor
  prompt is narrow (one question, three fields, same scaffold). Strong lead for arms E/F (shorter prompt / split call).
  Confound: it ran later the same day, so time-of-day is not excluded.
- **It is the biggest search cost.** ~14 searches per call (max 59 and 76) vs ~4.5 for the main call. 9/27: 1,271 of ~1,817
  logged searches (about 70%) came from sponsorship, ~$18 that day, from about a quarter of the calls.
- **It re-asks nearly every row every weekend.** 44 of 59 Cybersecurity and 50 of 54 Utility rows were pending. The research
  input (`<Market>_input.csv`) has no SPONSOR_* columns, so the main audit restarts every row at Unknown and the pass
  re-buys answers already settled. The "cost shrinks over time" design (settled rows written through free) is not working
  in the weekly chain because nothing carries answers forward.
- **The answer barely discriminates.** 106 of 113 rows come back "Yes". Only 25 carry a real money figure; ~53 say
  contact / tailored / on request; 10 have a blank cost. All 106 Yes rows carry a URL (not yet verified that they resolve).
- **AI Studio (project "Gemini Solomon", Tier 2)** shows Google's own server-side 504 GatewayTimeout and 503 counts, so the
  504s are counted by Google, not our client timeout. ~640 requests on 9/19 with ~229 504s; ~410 on 9/27. Success rate is
  100% on quiet days and dips on heavy run days. Daily tables would not load through the browser tool; read from charts only.
- **Candidate savings, NOT yet decided:** carry SPONSOR_* forward from last week's final file (writes through free), and
  re-ask only Unknown rows or on a slow schedule (sponsorship packages change yearly, not weekly). Would remove most of the
  ~70% search share. Needs operator approval - it changes weekly-chain behaviour and the customer-visible sponsor fields.

### Arm E RESULT (2026-09-30) - see `experiments/grounding_reliability/RESULT.md`
Narrow prompt: 24 of 24 grounded, 0 timeouts, 0 no-search, median 16 s. Full prompt: 9 of 24 grounded, 8 hit the 120 s
deadline, 7 skipped the search. Deadlines matched the known answer in every grounded call of both arms. Quote quality is
NOT measured (simple fetch finds our own verified quotes on only 4 of 12 pages). The "504" is our own 120 s timeout being
enforced by Google. Recommendation: adopt as direction, not yet wired; next test hard cases and field coverage.

## 5. Workstream B - controlled experiment

**Sample.** 12 rows from the LIVE markets (Cybersecurity/Utility) whose deadline is already verified with a
verbatim quote on a page, so a right answer is known. Not prospect markets.

**Baseline (Arm A).** Exactly today's call: gemini-3-flash-preview, current prompt, JSON mime type, google_search.

**One variable per arm, everything else as baseline:**

| Arm | Change | Tests |
|---|---|---|
| B | thinking level low (confirm the parameter exists in google-genai 2.14 first, free) | Q2 thinking time |
| C1 | model = gemini-3.1-flash-lite (stable) | Q2, Q3 preview / model size |
| C2 | model = gemini-3.8-flash | Q2, Q3 |
| C3 | model = gemini-3.5-flash-lite | Q2, Q3 |
| D | drop `response_mime_type` from the grounded call | JSON-with-tools effect |
| E | shorter prompt: minimal facts asked, standing rules moved to a second step | prompt size, Q3 |
| F | split: call 1 grounded, short, plain text ("find sources for X"); call 2 no tools, formats JSON from call 1's text | Q2 call length |
| G | streaming (`generate_content_stream`) | 504 vs long-held request |

**Design rules.**
- Log per call: outcome (grounded / 504 / no-search / other), wall-clock latency, search count, source hosts,
  usage metadata incl. thinking tokens, finish reason, hour of day. This is the timing the current trail lacks.
- Arms interleaved in random order, and baseline repeated at three different times of day, so a bad Google hour
  cannot masquerade as an effect.
- Noise: at ~30% base success, 24 calls per arm gives roughly +/-18 points. Only large effects (say 30% to 80%)
  are detectable. Stage 1 = 6 rows x all arms to prune; Stage 2 = 12 rows x 2 repeats on survivors and baseline.
- Quality judged against known truth: deadline correct, link resolves (HTTP, then browser), quote present
  verbatim on the page. A grounded call with a wrong or composed link is a failure, not a success.

**Decision criteria, fixed before running.** An arm is adopted only if: >=90% of first attempts grounded,
<=5% 504, quality >= baseline, and lower cost per usable row. Otherwise the answer is "Gemini grounding is not
fit for this job" and we move to Workstream C.

## 6. Workstream C - only if B fails

Search done by a search API, Gemini only reads results and writes the answer (the parked Firecrawl head-to-head:
~20 rows with known answers, scored on deadline / working link / verbatim quote). NOT set up until the operator
asks. The consumer Gemini app that works manually has no API and cannot be automated, so it is not an option.

## 7. Guardrails

- Never overlap another Gemini job. Quota is account-level. Run Wed/Thu, clear of Fri 02:00 and Sat 02:00.
- Hard cap on requests (`--max-requests`), stop on the first 429, no auto-retry inside the harness beyond what
  an arm is testing.
- Rough cost ceiling, an ESTIMATE: ~$0.06 per grounded call at 4.5 searches -> Stage 1 about $3, Stage 2
  about $8. Confirm against Workstream A before spending.
- Before any run, state `USING EXISTING: <script>` or `NEW CODE: searched TOOLING.md ... found nothing` per
  the working rules. The harness will be new code and belongs in `experiments/grounding_reliability/` with a test.
- Nothing here changes the Friday / Saturday / Sunday / Monday jobs.

## 8. Order of work

1. Workstream A (free) and the thinking-parameter check (free).
2. Build the timing harness; dry-run with no API calls.
3. Stage 1, then Stage 2.
4. Write results into this file, decide, and only then touch `DEFAULT_MODEL` or the prompt.
