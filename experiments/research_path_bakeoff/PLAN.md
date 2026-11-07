# T1 / T2 plan: research path bake-off (written 2026-11-07, before any paid call)

Question (docs/design/inspection-2026-11-07.md, section 3): on the same 40 rows, same day, does a search, fetch, extract, prove path beat the current
grounded call on accuracy, provability, cost and time, and does the grounded call go faster in parallel without hitting the daily grounding quota?

## Rows (select_rows.py, rows.md)
40 rows: the 19 person-confirmed events of docs/qa/answer-key.csv that are on an approved file and on the input list (Nullcon is on neither), then 21 live
rows (16 with a deadline ahead, soonest first, then 5 with no deadline held). Key per row, scoring only: person-confirmed deadline (3), customer-verified
deadline agreeing with ours (5), else the shipped value (32, of which 17 are blank). The arms read rows.json, which carries no key value; arm A gets the
production input row exactly as the Saturday job does (it carries last week's deadline as a hint, as in production); arms B, C and D get the event name,
edition year, site hosts and the pages we hold (never a date).

## Arms and budget (stated before spending; keys from the user environment only)
| arm | what | unit cost | 40 rows, planned | cap |
|---|---|---|---|---|
| A | current grounded call, narrow-first, serial, 16 s pacing (arm_a_worker.py on a copy of run_market_audit.py) | 14 USD per 1,000 searches, about 7 searches a call (inspection), plus tokens | 2.4 USD measured (6 cents a narrow call, 09-30) to 3.9 USD worst case at the paid rate; the month's free 5,000 searches may cover it (about 2,400 used this month) | stops at the first 429 |
| B | OpenRouter web_search server tool (Exa, 5 results) on deepseek-chat + 3 pages fetched by us + deepseek-chat reader + code proof | 0.007 USD a search request + about 0.001 a reader call | about 0.5 USD | 0.60 USD |
| C | OpenAI web_search through OpenRouter (engine native, openai/gpt-5-mini, reasoning low) | 0.01 USD a search call + tokens; the smoke row ran 2 searches, 0.024 USD | about 1.0 USD | 1.00 USD (raised from 0.60 after the smoke test) |
| D | Codex CLI `codex exec --search` (ChatGPT subscription) | 0 USD marginal, subscription tokens | 0 USD | 75 minutes |
| T1 total | | | about 4.2 USD at paid rates (A 2.8 at the smoke row's 7 cents, B 0.45, C 1.0; smoke test 0.13) | 5 USD |
| T2 | arm A again, 4 workers, 0 s pacing, 60 s timeout | as A | about 2.4 to 3.9 USD at paid rates | run only if T1 actuals leave room, else ask |

No OpenAI, Perplexity, DeepSeek, Brave or Exa key exists on this PC, so B uses the OpenRouter key and C is OpenAI's search relayed by OpenRouter (recorded as such).

## Scoring (score.py, in code, after all arms answered)
Per arm and row: deadline equals the key (right / wrong / blank / no-key); the page the arm cited, fetched by US (plain fetch then the real Chrome over CDP),
states that date (dates_v2.find_target); the quote it gave is on that page; USD; seconds; searches. Then totals, a hard-key / soft-key split, agreement
between arms, and a per-row table.

## Guarantees
Read-only against live data: no write to the database, the approved files, the input lists, the Markets working files or the live build. The audit script
runs from a copy in markets_copy/ (git-ignored). Every provider call is one line in calls.jsonl (B, C, D) or in the row record and the grounding trail (A).
Smoke test with --limit 1 per arm first, then the full run; A, B+C and D run as three separate processes (different providers).
