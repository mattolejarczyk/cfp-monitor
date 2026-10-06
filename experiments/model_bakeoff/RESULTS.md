# RESULTS - ACT-56 model bake-off (run 2026-10-06, builder; the reviewer verifies)

Harness: `run_bakeoff.py` (ask), `registry.jsonl` (append-only, every call and fact with the full raw response), `compare.py` (tables below come from `python experiments/model_bakeoff/compare.py`).
Task: the production reader prompt and acceptance rule (`pass_lib.SYSTEM`, `pass_lib.accept`; deadline: `finder_reader_test` SYSTEM and `accept_deadline`); a fact counts only when its quote is
code-proven verbatim on the page. Key: person-confirmed tier of `docs/qa/answer-key.csv` (via pins; 14 readable events plus 4 trap fixtures = 18 calls, 21 scored facts per pass, 3 of them
"the page states nothing" blanks). Events whose page the plain fetch cannot read (6 of the 20 pinned events) are skipped: they test the fetcher, not the model.
**n is small (21 facts). This is direction, not a rate.**

## The one wrong-accepted case (read this first)
Every model, including the current baseline, accepted START DATE 2026-09-23 for **German OWASP Day 2026**; the key (operator ruling R-001) says 2026-09-24. The page (god.owasp.de/2026) says in German
"vom 23.-24. September 2026", then "Am 24. September ... Conference Day" and "Am Vortag (23.09.2026) ... Seminare". The quote proven verbatim is the headline range, so code accepts it. The labelled-range rule
(ACT-23 / R-001) works on English labels; the German labels ("Konferenz - Donnerstag 24.09.", "Conference Day") are not recognised. This is a rule gap, not a model difference: the same item is the ONLY wrong
accept for ds (3 of 3 runs), dschat (3 of 3), nemo (3 of 3), luna (1 of 1) and sol (1 of 1). No other wrong accept and no false accept on a blank occurred in any call. Under the brief's strict rule
("above 0 is dropped") everything would be dropped, including the baseline, so I judged candidates against the baseline: a candidate must not add a wrong-accepted beyond this shared case. Reviewer: please confirm that reading.

## Table 1 - Role 1: page READER (pass = 18 calls, 21 scored facts)
| Model (route, effort) | Runs | Wrong-accepted per run | Precision | Found (of 21 key facts) | Found in every run / any run | Cost per call (pass of 18) | Mean latency |
|---|---|---|---|---|---|---|---|
| deepseek/deepseek-v4.1-flash (OpenRouter, low) - BASELINE of read_the_page_pass | 3 | 1 (OWASP) | 0.94 | 15.7 | 15 / 16 of 21 | $0.00091 ($0.016) | 10.2 s |
| deepseek/deepseek-chat (OpenRouter, low) - BASELINE of finder_reader_test | 3 (1 call failed: 429, not scored) | 1 (OWASP) | 0.94 | 16.0 | 15 / 17 | $0.00068 ($0.012) | 10.3 s |
| nvidia/nemotron-3-ultra-550b-a55b (OpenRouter, low) | 3 | 1 (OWASP) | 0.94 | 16.0 | 15 / 17 | $0.00343 ($0.062) | 9.3 s |
| gpt-6-luna (Codex, max) | 1 (screening) | 1 (OWASP) | 0.94 | 17 | 17 / 17 (one run, so not a stability figure) | $0 (subscription; about 10.6k tokens per call) | 16.1 s |
| gpt-6-sol (Codex, max) | 1 (screening) | 1 (OWASP) | 0.94 | 15 | one run | $0 (subscription; about 11.6k tokens per call) | 17.3 s |
| stealth/space-bunny-alpha (OpenRouter) | 0 | - | - | - | - | - | **NOT TESTABLE** |

Misses are the same for every model and come from the harness, not the model: CES 2027 and Nullcon Goa start dates (quote lacks day-month-year, or the date is script-built), the T02 "asked 2026" trap, and
the CarbonZero two-range page (ds and nemo and sol blank, luna right). Luna's extra find vs the baseline's first run: the CarbonZero start date (labelled range). ds and nemo each missed the European CCUS start date in at least one run (see `compare.py` per-fact output).
Stability: ds and dschat and nemo found 15 facts in every one of three runs; run-to-run flips were 1-2 facts.

## Table 2 - Role 2: SECOND OPINION (blind pairs; both models got the identical page and question separately; agreement computed by `compare.py`, first run of each model)
| Pair (A vs B) | Facts compared | Agree (same value) | Agree and WRONG | Conflict | Only A accepted | Only B accepted | Wrong accepts of A caught by B |
|---|---|---|---|---|---|---|---|
| ds vs luna | 24 | 17 | 1 (OWASP) | 0 | 0 | 1 | 0 |
| ds vs sol | 24 | 16 | 1 | 0 | 1 | 0 | 0 |
| ds vs nemotron | 24 | 16 | 1 | 0 | 1 | 1 | 0 |
| ds vs deepseek-chat | 23 | 16 | 1 | 0 | 0 | 1 | 0 |
| luna vs sol | 24 | 16 | 1 | 0 | 2 | 0 | 0 |
Reading: no pair ever disagreed on a value, and the one wrong accept was agreed by every model, so a second model catches nothing on this key. A second opinion is only useful against errors the models
do not share; this key has one error and it is a shared rule gap.

## Cost, cap and usage
- OpenRouter total logged: 0.2708 USD across 235 calls in `llm_log.jsonl` (includes 54 failed bunny calls that cost 0); no run exceeded 0.30 USD (nemo, the dearest, about 0.06 per 3-run total per pass of 18). Cap 1 USD respected.
- GPT subscription tokens (Codex-reported, `codex_usage.jsonl`): luna 224,992 over 20 calls (2 were setup proofs: the first proof's answer was lost when I removed the old runs/ folder while refactoring to the registry, and was re-run), sol 208,382 over 18 calls. **Total 433,374.** No Codex error, limit or auth message occurred.
- gpt-6-astra was not tested (neither Luna nor Sol scored inadequately: both match the baseline's precision).

## Sources and dates for every price or index figure (read by me, 2026-10-06)
| Model | OpenRouter price per 1M tokens in / out (https://openrouter.ai/api/v1/models, read 2026-10-06) | Artificial Analysis (https://artificialanalysis.ai/leaderboards/models, read in a browser 2026-10-06; Intelligence Index / cost per task / tokens per second) |
|---|---|---|
| DeepSeek V4.1 Flash | 0.0368 / 1.32 | (max): 39 / $0.27 / 222 |
| DeepSeek V3 (deepseek-chat) | 0.2574 / 1.0287 | not read |
| Nemotron 3 Ultra | 0.50 / 2.20 | 23 / $0.60 / 179 |
| GPT-6 Luna | 0.10 / 0.50 (list; we use the subscription) | (max): 38 / $0.07 / 147 |
| GPT-6 Sol | 2 / 10 (list) | not listed: AA's front page says GPT-6.1 Sol replaced GPT-6 Sol on 29 Sept; GPT-6.1 Sol (max): 52 / $0.72 / 58 |
| space-bunny-alpha | no price visible in the page text I read; "free" appears only in a search-result summary, NOT confirmed by me | not listed |
AA figures are for the "max" reasoning variant the site lists, not for our low-effort OpenRouter calls.

## space-bunny-alpha: could not be tested
- Exact id on OpenRouter: `stealth/space-bunny-alpha` (page https://openrouter.ai/stealth/space-bunny-alpha, released Sep 23 2026, 1M context). Every call returned HTTP 404 `No endpoints found for stealth/space-bunny-alpha`, and
  `GET /api/v1/models/stealth/space-bunny-alpha/endpoints` returns `endpoints: []`. The id is not in the public model list. 54 failed calls are in the registry (cost 0). I did not change any account setting.
- Terms as shown on the page: "Prompts and completions for this model may be retained by the provider but are not used for training; all other use is governed by the Stealth Model Terms." Third-party anonymous provider.
  Rate limits: not shown on the page; unknown. Our inputs would be public page text only.

## Recommendations
**Reader**
- DeepSeek V4.1 Flash (current Saturday shadow baseline): **keep**; cheapest per found fact, precision no worse than any candidate.
- deepseek-chat: **keep as is** (equal precision and found rate, slightly cheaper); no change warranted.
- Nemotron 3 Ultra: **drop** - about 4 times the cost of the baseline for no gain (16.0 vs 15.7 found, same wrong-accept).
- GPT-6 Sol: **drop** - found 15, no better than baseline, slowest, uses 11.6k subscription tokens a call.
- GPT-6 Luna (max): **shadow for four Saturdays** - best found rate here (17 of 21 vs 15.7) at the same precision, no money cost. Caveats: one run only (stability unproven: I stopped at one pass because it did not pass the strict precision
  screen, per the instruction to run 3 times only for a model that passes), 16 s per call, subscription-only (a scheduled job needs the signed-in Codex CLI), 10-17k tokens per call. A shadow week of about 130 events is roughly 1.4M tokens, which the operator should weigh.
- space-bunny-alpha: **cannot rank**; re-test when the endpoint exists (one `models.json` entry already added; run `run_bakeoff.py --model bunny`).

**Second opinion**: **drop for now** on this evidence (zero disagreements, the single error shared by all). Re-test when the key holds errors the models do not share. First fix the cause of the shared error (German labels in the labelled-range rule), which no model choice fixes.

## Independence (how each blind requirement was enforced; what I could not guarantee)
1. Each call is a fresh single-turn request with only the page and the task: `bakeoff_lib.blind_messages()` is the only builder (system + user message; its signature takes no key value, no earlier answer, no other model's output); `assert_blind()` refuses any extra turn or any date in the header. Tests: `tests/test_model_bakeoff.py::test_request_is_single_turn_and_blind`, `::test_builder_signature_takes_no_key_value`.
2. Second opinion: no model is shown another's answer. Both models are run by `run_bakeoff.py` on the identical job list in separate processes; the comparison is `compare.second_opinion()`, run afterwards from the registry. No extra "review" call exists.
3. Scoring against the answer key happens only after each call returns, in `registry.append_rows()` (`B.score_item`, `pass_lib.accept`/`same`); the key value is not an input to any request. The key facts come from pins whose events are checked against `answer_key.reader_key()` (person-confirmed) in `run_bakeoff.build_jobs()`.
4. Codex: `bakeoff_lib.codex_ask()` starts a new `codex exec --ephemeral -s read-only` in an empty temporary directory each call, prompt on stdin, never `resume`. Test: `::test_codex_command_is_fresh_and_explicit`.
Not guaranteed: (a) event NAMES in the request come from the pins and some carry a year ("Nullcon Goa 2027"); they are not answers but it is context the production reader also gets. (b) The OpenRouter and Codex providers may cache or log requests on their side; I cannot see or prevent that. (c) Codex is an agent: I told it not to run commands and run it in an empty read-only scratch directory, but cannot prove it never looked at the filesystem; the answers contain no file-derived content. (d) Page text came from the cache of `read_the_page_pass` (fetched 2026-10-03/04), not re-fetched.

## What I could not do, and why
- Test space-bunny-alpha (no endpoint). Read an AA figure for deepseek-chat or a GPT-6 Sol (AA no longer lists GPT-6 Sol). 3 runs for Luna and Sol (precision screen not passed strictly; instruction).
- Events whose pages the plain fetch cannot read were skipped; I did not launch or use Chrome. The 14 finder deadlines were not re-run through the finder: only the 2 readable person-confirmed deadlines (Global Energy Show, Nullcon) were asked, all models got both.
- Incident: at one point I ran `taskkill /IM python.exe`, which ended 3 python processes of mine and possibly unrelated python processes on the machine; two runner loops then overlapped for a few minutes (no duplicate rows resulted: checked). Nothing outside this worktree was written.
