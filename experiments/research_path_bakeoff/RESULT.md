# RESULT - T1 research path bake-off and T2 (2026-11-07, run 07:10 to 07:35, scored 07:50)

Question (docs/design/inspection-2026-11-07.md section 3): on the same 40 rows, the same morning, blind to the answer key, does a search, fetch,
extract, prove path beat the current grounded call on accuracy, provability, cost and time? Files: PLAN.md (budget stated before spending), rows.md
(the rows), rows.json (what the arms saw), key.json (scoring only), arm_a_serial.jsonl (+ .grounding.jsonl, .health.json, .summary.json), arm_b.jsonl,
arm_c.jsonl, arm_d.jsonl, calls.jsonl (every provider call of B, C, D), reader_llm_log.jsonl, scores.csv, tables.md (all the tables), what_if_finder.json,
the four arm_*.log files, raw/ (every raw provider response and Codex console, git-ignored).

## The rows and the key
40 rows: 19 person-confirmed events of docs/qa/answer-key.csv that are on an approved file and on the input list, then 21 live rows (16 with a deadline
ahead, 5 without). Key per row, used only by score.py after every arm had answered: 3 person-confirmed deadlines, 5 customer-verified deadlines that agree
with ours (hard keys, 8), 32 shipped values (soft keys: they came from the grounded path, so they favour arm A), of which 17 are blank (no key: a date
there can only be judged by whether the cited page states it). Arm A got the production input row as the Saturday job does (it carries last week's
deadline as a hint, same as production); arms B, C and D got the event name, edition year, site hosts and the pages we hold, never a date.

## The arms as run
| arm | what ran | note |
|---|---|---|
| A | `run_market_audit.audit_conference` on a copy (markets_copy/), narrow-first prompt, gemini-3-flash-preview, 16 s pacing, 120 s timeout, no citation verification: the Saturday call exactly | system Python (google.genai), 0 HTTP 504, 0 429, RUN HEALTH HEALTHY |
| B | one OpenRouter `openrouter:web_search` call (engine exa, 5 results, deepseek-chat asked for the official call page), candidates = the deadline page we hold, the answer URLs, the url_citation annotations, last year's URL with the year bumped; top 3 fetched by us (plain fetch, then the real Chrome over CDP when dateless); each page read alone by deepseek-chat (finder_reader_test.SYSTEM, 12,000-character window); code proof (`finder_reader_test.accept_deadline`: quote verbatim on the page, states day, month and year, call wording, not long past); `main_call.choose_main` | no Perplexity, DeepSeek, Brave or Exa key exists here, so the search is OpenRouter's Exa engine |
| C | OpenAI web_search relayed by OpenRouter (engine native, openai/gpt-5-mini, reasoning low), asked for deadline + URL + verbatim quote | no OpenAI key exists here, so NOT the Responses API; OpenRouter passed NO url_citation annotations through on any of the 40 calls, so C's URL is the model's report |
| D | `codex --search exec --ephemeral` on the ChatGPT subscription, model gpt-6-luna, effort low (the config default gpt-6.1-sol is refused on a ChatGPT account: raw/D_01_console_default_model_refused.txt) | prose JSON parsed in code; no citation contract |

## T1 numbers (40 rows; "right" = equals the key; "page states the date" = we fetched the URL the arm cited and dates_v2.find_target found that date on it)
| arm | dated | right | wrong | blank on a keyed row | cited page states the date | quote verbatim on the page | USD | searches | mean s a row | wall |
|---|---|---|---|---|---|---|---|---|---|---|
| A grounded (current) | 24 | 18 | 2 | 3 of 23 | 12 of 24 (11 no, 1 no URL) | 3 of 23 | 4.85 at paid rates (4.28 searches + about 0.57 tokens) | 306 (3 to 22 a call, median 7) | 23 | 15.4 min |
| B search, fetch, extract, prove | 14 | 12 | 1 | 10 of 23 | 14 of 14 | 14 of 14 | 0.38 | 40 (117 pages fetched, 114 reader calls) | 25 (median 19) | 16.7 min |
| C OpenAI web_search via OpenRouter | 18 | 15 | 2 | 6 of 23 | 15 of 18 | 11 of 18 | 0.82 | 72 | 8 | 5.6 min |
| D Codex CLI --search | 17 | 16 | 0 | 7 of 23 | 16 of 17 | 12 of 17 | 0 (773k subscription tokens, about 19k a row) | n/a | 17 | 11.1 min |

Hard keys only (8 rows, right / wrong / blank): A 6 / 1 / 1, B 5 / 1 / 2, C 6 / 1 / 1, D 8 / 0 / 0. Soft keys (15): A 12 / 1 / 2, B 7 / 0 / 8, C 9 / 1 / 5,
D 8 / 0 / 7. Per-row detail: tables.md.

Agreement (rows where both gave a date): A-B 12 of 13 agree, all 11 keyed ones right; A-D 14 of 16 agree, 13 right, the 2 disagreements both went to D;
B-D 10 of 10 agree and right; C-D 14 of 16 agree, 13 right, both disagreements to D; A-C 14 of 16, 12 right and 1 agreed-and-wrong (CODASPY, both
chose the paper round). The 10-04 pattern held: when two paths agree the date was right every time except that one shared round choice.

The wrong answers, read: CODASPY 2027 (key 2026-11-16, the abstract round by the operator's ruling): A and C gave the paper round 2026-11-23, B gave
2026-11-24 from hotcrp "Tuesday Nov 24, 2026, 6:59:59 AM EST" (that is Nov 23 anywhere on earth), D gave 11-16. Every quote is real; the disagreement is
which round and which clock, not the page. IEEE S&P (shipped 2026-11-17): A gave 11-18 citing the cycle-2 hotcrp page with a registration-deadline
quote; C and D gave 11-17 proven on cfpapers.html; B blank. RAAI (shipped 2026-11-10): C gave 2026-08-01 from a 2026 CFP PDF (a passed round); A, B, D
agree on 11-10 proven on raai.net/sub.html. On the 17 no-key rows A produced 3 dates nobody else did, none stated on the page it cited (a yutori.io page,
a starbridge.org aggregator page, a passed 2026 HITB call); B stayed blank on all 17.

Arm A's provability, this morning: 22 of its 40 citations are on a host it never searched (the grounding trail's citation-host-not-in-sources, the
inspection's 42 percent reproduced at 55 percent), 11 of its 24 dated rows cite a page that does not state the date when we fetch it (four of them are
404 pages: Global Energy Show, CES, World of Concrete, AAIML), and only 3 of its 23 quotes are on the cited page verbatim. Right answers, mostly unprovable.

Arm B's gap, read (what_if_finder.py, about 1 cent, pages already fetched): of the 10 keyed rows B left blank, handing B's own reader the page another
arm cited proved 1 more (Global Energy Show: our held page is now a 404, the search returned the 2025 call, D and C found the 2027 page). On 3 pages that
DO state the date the reader missed: IEEE S&P cfpapers.html is 50,000 characters and the reader sees the first 12,000 (it reported the passed cycle-1 date,
which the code refused), FEW's quote was a paraphrase (refused), GC&E's quote had no day-month-year (refused). The refusals are the design working (no
wrong date shipped), but on this set the finder missed about 6 pages and the reader 3. The 10-04 finding "finding is the hard step, reading is not" is
only half true here.

## Cost and quota
Spend at paid rates: A 4.85, B 0.38, C 0.82, smoke test 0.13, what-if 0.01: about 6.2 USD, over the 5 USD plan. The overrun is arm A: 7.65 searches a call,
not the 7 planned, and tokens (the token figure uses an ASSUMED gemini-3-flash-preview price of 0.50 / 3.00 USD per million; the 4,000 output tokens a call
are mostly thinking). Google bills searches at 14 USD per 1,000 only beyond 5,000 free a month; this month's count was about 2,418 before today and 310
were added here, so the search part is probably free this month, which would make the cash spend about 1.9 USD (OpenRouter 1.21 plus Gemini tokens).
Not verifiable from here; the paid-rate figure is the honest ceiling. Per row at paid rates: A 0.12, B 0.0096, C 0.020, D 0. For the weekly 300 rows:
A about 36 USD (what the weekend costs today), B about 3, C about 6.

Daily grounding quota: the Saturday job ran 1,514 searches from 02:05 and this run 310 at 07:15, 1,824 in one Pacific day, with 0 HTTP 429 and 0 504 in
the 40 serial calls (last night: 4 of 188). The 1,500-a-day default the inspection names did not bite, so the ceiling for T2 is not the daily quota.

## T2 (grounded path, 4 workers, 0 s pacing, 60 s timeout): run 09:07 to 09:12 on Matt's go-ahead
Same 40 rows, same copy of the audit script, same prompt, the only change the pacing and the worker count. Files: arm_a_parallel.jsonl (+ .grounding.jsonl,
.health.json, .summary.json, .log).

| | serial (T1 arm A, 16 s pacing, 120 s timeout) | parallel (4 workers, 0 s pacing, 60 s timeout) |
|---|---|---|
| wall clock, 40 rows | 922 s (23 s a row) | 295 s (7.4 s a row): 3.1 times faster |
| per-call seconds, min / median / max | 9.8 / 24.8 / 45.0 | 8.9 / 22.2 / 104.8 (the one retried row) |
| attempts, HTTP 504, HTTP 429, timeouts, stubs | 40, 0, 0, 0, 0 | 41, 1 (retried, recovered), 0, 0, 0 |
| RUN HEALTH | HEALTHY | HEALTHY |
| searches, USD at the paid rate | 306, 4.28 + about 0.57 tokens | 300, 4.20 + about 0.54 tokens |
| citation host not in sources | 22 of 40 | 19 of 40 |
| same deadline as the serial run | | 36 of 40 (right 18, wrong 1, blank 4 against the key; the serial run 18 / 2 / 3) |
| same evidence URL as the serial run | | 20 of 40 |

What it says: the 16 s limiter, not the API, is most of the weekly wall clock (a call takes about 22 s either way); four workers cut 40 rows from 15 to 5
minutes with one transient 504 and no 429, at the same cost. 1,824 searches had already run today when T2 started, and it added 300 more with no 429,
so the daily grounding quota did not bite at 2,124 searches in one Pacific day. The weekly 182 rows would take about 22 minutes instead of 90. The two
runs also show the grounded call's run-to-run variance: the same prompt on the same day returned a different deadline on 4 rows (IEEE S&P moved from
the wrong 11-18 to the right 11-17; ZTW's 11-09 and two unprovable past dates vanished) and a different evidence URL on half the rows. Caveats: one
parallel run of 40 rows, all in one five-minute window; a 504 rate under sustained load for 300 rows is not measured; the 60 s timeout never fired here.

Budget after T2: about 11.0 USD at paid rates (T1 6.2 + T2 4.74), approved by Matt in chat at 09:05 for T2; probably about 2.0 USD cash if the month's
free 5,000 searches cover the 3,028 counted so far this month.

## What this proves and does not
- Proves, on 40 rows, one morning, one run each: the grounded call finds the most dates (18 of 23 keyed) but proves the fewest (12 of 24 cited pages
  state the date; 3 of 23 quotes verbatim; 22 of 40 citations on hosts it never searched) at 12 times B's cost. B's 14 dates are all proven on a page we
  fetched, at under a cent a row and the same speed as the grounded call (the 10-04 finder's 2.5 minutes a row is gone: CDP renders, 3 pages, no sitemap
  walk), but it leaves 10 of 23 keyed rows blank. Codex search is the most accurate arm (16 right, 0 wrong, 8 of 8 hard keys) for 0 USD but has no citation
  contract and runs on a subscription. Agreement between any two paths is a reliable signal of a right date.
- Does not prove: a rate (n = 40, 8 hard keys; 32 keys are our own shipped values, which favour A; the input row A sees carries last week's deadline);
  anything about awards rows (none here); the Responses API's url_citation behaviour (C ran through OpenRouter, which returned no annotations); B's
  behaviour with a second search, more pages or a longer reader window (not tested); reader variance (one read per page, deepseek-chat).

## Recommendation
Not yet as the weekly row's primary path. B as run finds too few dates (12 of 23 keyed, against 18 for the grounded call) because one Exa search plus
three pages misses the call page and the reader's 12,000-character window loses long pages. What B returns is exactly what the inspection asked for:
every shipped deadline backed by a verbatim quote on a page we fetched, at a twelfth of the cost, in the same time.

Next, in order, each its own experiment:
1. T1b (about 1 USD, same 40 rows, same key): B with the finder widened (the home page and the year-bumped URL always fetched, up to 5 pages, a second
   search phrased for "call for papers" when the first finds no call page) and the reader given the whole page in windows (or the window around a
   dated call sentence first). Target: B's recall at or above the grounded call's 18 with its proof rate kept at 100 percent. If it gets there, make B the
   primary source for the weekly conference row and demote the grounded call to the fallback for rows B leaves blank, after two shadow Saturdays agree.
2. Keep D (Codex search, gpt-6-luna) as a Saturday shadow second opinion where it is free: agreement with B or A is the strongest right-date signal seen
   here; never a scheduled dependency (subscription limits, no citations).
3. T2 says the weekly research can run 4 wide with a 60 s timeout: 3.1 times faster, same cost, no quota stop at 2,124 searches a day. Worth a patch
   to run_market_audit.py (a worker pool in main(), the RateLimiter kept as a floor of 0 to 4 s) with a 5-row canary first; not done here.
4. Do not spend on C through OpenRouter again: no annotations came back, so it adds nothing B or D does not give cheaper.

Worklog line: `2026-11-07 - T1 bake-off (experiments/research_path_bakeoff, 40 rows, 4 arms) and T2 (4 workers), about 11 USD at paid rates, probably 2 cash: grounded 18 right / 12 of 24 pages prove it / 22 of 40 citations on unsearched hosts / 4.85 USD; search-fetch-prove 12 right / 14 of 14 proven / 0.38 USD; Codex 16 right, 0 wrong, free; OpenAI-via-OpenRouter 15 right, no citations. Not adopted yet: widen the finder and the reader window (T1b) first. T2: 4 workers 3.1x faster (295 s vs 922 s), 1 transient 504, 0 429 at 2,124 searches a day.`
