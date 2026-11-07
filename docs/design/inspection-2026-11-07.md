# Conference Monitor inspection, Saturday 2026-11-07 (read-only review, 02:00 to 04:05)

Scope: the weekly process, runbooks, scheduled tasks, logs and the research code, with a close look at the Friday
and Saturday runs of this weekend and at the question "why is the automated research slower and less reliable than
a manual Google AI search, and what should replace it". Nothing was changed, loaded, sent or committed. The Saturday
job was still in its automatic import when this was written (gate round 2 for Cybersecurity started 03:55).

## 1. What actually happened last night (Sat 2026-11-07 02:00, CFP Weekly Re-Research)

| Step | Time | Result |
|---|---|---|
| Intake of the customer sheets | 02:00 to 02:01 | DEGRADED: Arnica fetched and loaded; Utility fetch FAILED ("missing column CONFERENCE"), so the Utility client layer is still the 2026-10-17 copy, 21 days old |
| Canary (5 rows) | 02:01 to 02:04 | PASSED, 5 of 5 grounded |
| Research Cybersecurity | 02:05 to 02:55 | 108 of 139 rows (28 dormant by the refresh plan, 3 duplicates skipped); RUN HEALTH HEALTHY; 112 calls, 107 ok, 3 HTTP 504, 2 disconnects; 1 stub (FIRST Annual Conference 2027 Bangkok failed all 4 attempts: SSL EOF, disconnect, 504, 504) |
| Research Utility | 02:56 to 03:34 | 74 of 87 rows; HEALTHY; 76 calls, 74 ok, 1 504, 1 disconnect |
| Format check (validate_market_output) | after each market | "RESULT: FAIL" on both: IS_PROJECTED=false without a quote (7 + 12 rows), CFP MODEL TYPE blank (70 + 26 rows), placeholders ("To Be Announced"), one series row (Climate Week NYC) |
| Wrapper exit | 03:35 | "Monthly re-research finished (exit 0)" although both markets reported exit 1 |
| weekend_import | 03:35 onward | mechanical repairs 03:44; gate round 1 Cybersecurity 03:44 to 03:55 REJECTED (4 dead links 404, 2 quotes without a date, 4 STATUS_DETAILS claims, Nullcon deadline past but Open); round 2 started 03:55 |

Cost of the research: Cybersecurity 819 Google searches, Utility 695, about 21 USD at 14 USD per 1,000; Friday awards 904
searches, about 12.7 USD. Weekend total about 34 USD before the sponsor and shadow steps. Searches per call ranged from
0 to 30 (median about 7). One call that fires 24 searches costs 0.34 USD.

### The "failed codes" you were seeing, decoded

| Where | Code / text | Meaning |
|---|---|---|
| Task Scheduler, CFP Weekly Awards Research | 3221225786 = 0xC000013A | the Friday process was killed by the 06:23 reboot during the gate (STATUS_CONTROL_C_EXIT). Research itself was HEALTHY; the load was finished by hand at 12:46. Shows FAILED on Mission Control until next Friday |
| Task Scheduler, CFP Weekly Re-Research | 267009 = 0x41301 | "task is currently running". Not a failure. Mission Control maps it to Running |
| Task Scheduler, CFP Monthly Re-Research | 4294967295 | the disabled monthly job's last run on 9/30 failed; expected, the task is off |
| Research log | `[FAIL] Audit failed for FIRST Annual Conference 2027 ... after 4 attempts` | one row written as a stub after four transient Google errors; the import keeps last week's version of that row |
| Research log | `RESULT: FAIL (4 error(s))`, `ERRORS - do not ship this file` | the pre-gate format check. Its wording predates the automatic row rule: the import holds these rows back on its own, so FAIL here is routine, not a stop |
| Friday recap email | "Friday awards research: FAILED" | the recap treats exit 1 as FAILED while the import accepts exit 1 (worklog defect of 2026-11-06, still unfixed) |

### A new finding: why the Utility sheet failed intake

The live export of the Utility Global sheet (same sheet id and gid as configured) now comes back with its FIRST HEADER
CELL BLANK (a run of spaces where "CONFERENCE" was). Every other column is there and the data rows are intact (84 rows,
first row Sustainable Aviation Futures (MENA)). The Arnica sheet still reads "CONFERENCE". So this is not a wrong tab: someone
cleared or overwrote cell A1 in the customer's sheet. Until the header is restored (or the reader tolerates a blank first
header when every other column matches), every Saturday intake for Utility will fail and the Utility client layer will age.
Ask Nicolia's team to put "CONFERENCE" back in A1, or make the reader map a blank first column to CONFERENCE by position.

The fetch code also throws the export away on a validation failure ("Nothing was saved"), so the cause could only be found by
fetching again. That breaks QbD rule 2 (every failure keeps its evidence).

## 2. Defects found (ordered by what they cost)

1. **Research exit code is an unreliable signal, in both directions.** Saturday's wrapper reported exit 0 while both
   markets exited 1; Friday's reported exit 1 and the recap then said FAILED for a load that worked. `weekend_recap.py`
   still uses `exit == "0"` (lines 292, 340, 471). Fix: one shared "research usable" rule that reads the health JSON verdict
   (HEALTHY / DEGRADED / FAILED) and the row counts, used by import and recap alike. Until then every recap subject is suspect.
2. **The gate can hang past its timeout.** `weekend_import.run()` uses `subprocess.run(capture_output=True, timeout=7200)`;
   when accept_delivery's Playwright grandchild keeps the pipes open the kill does not return (2 h 17 min on 11-06). And
   `gate()` reads the previous round's `.gate.json` when a round writes none, so a hung round can be judged on stale results.
   Fix: write gate output to a file, kill the process tree, delete the old gate.json before each round. The Saturday task has
   a 5 h limit; research took 1 h 30, each gate round takes about 11 min for Cybersecurity, so three rounds per market plus
   the shadow steps already crowd the window.
3. **Intake throws away its evidence and gives the wrong hint** (section 1). Save the raw export on failure under
   runs_out\qa\<date>\ and name it in the message; say "header cell A1 is blank" when that is what happened.
4. **CFP MODEL TYPE is blank on 96 researched rows every week.** The narrow conference prompt does not ask for
   CFP_MODEL_TYPE (the narrow awards prompt does, rule 7), so the input's blank carries through. The input lists carry 79
   (Cybersecurity) and 31 (Utility) blanks, all rows added from the customer sheets. Every week these rows fail format rule 2.
   Fix: ask for CFP_MODEL_TYPE in the narrow conference prompt, or apply the "Not Announced" default at write time.
5. **Cited page not among the searched sources: 42 percent of rows.** Cybersecurity 45 of 108, Utility 28 of 74, Awards
   57 of 111. The model names the right site and guesses the page path (gap 1 in experiments/README.md, opened 2026-09-28,
   still "not started"). The gate catches only the 404s (4 last night); a live but wrong page passes. This is the single
   biggest quality gap and it is structural to "one grounded call does find and read in one go".
6. **Sequential pacing at 1 request per 16 s.** 182 rows took 90 minutes. The limiter dates from free-tier 429s
   (run_market_audit.py lines 100 to 108). On the paid tier the ceiling is the grounding quota (default 1,500 search
   requests per project per day per Google's pricing page, to be confirmed in AI Studio), not requests per minute. Four
   workers and a 60 s per-call timeout would cut the wall clock to about 20 minutes at the same cost.
7. **Repair ledger double-write on a resumed run** (worklog 11-06 defect 3). Small.
8. **Memory.** 2.8 GB free during the gate; 0.38 GB on 11-06 when a desktop Chrome grew. The headless gate browser plus
   any user Chrome is enough to stall the PC and the Claude Code hooks.
9. **Docs drift.** HANDOFF.md body "last fully revised 2026-08-01"; the home CLAUDE.md says FIVE tasks (there are six,
   Thursday pre-flight added 2026-10-13); run_monthly.ps1's header still describes the 8-market monthly job; the validate
   wording "do not ship this file" predates the automatic row rule.
10. **Housekeeping.** About 200 database backups (over 3 GB) in AppData\Local\CFP-Monitor from hand-run steps since July.

Also in last night's intake notes, for a person: new sheet columns DEADLINE TYPE, LEAD TIER, LEAD DAYS on both sheets are
not mapped; "Internal Estimate" appears 49 and 78 times in SUBMISSION DATE VERIFIED and is not recognised; six match
conflicts (Gastech, Sustainable Aviation Futures NAM, Decarb Connect UK, Black Hat Asia, CYBERUK, FIRST) wait for a ruling.

## 3. Why a manual Google AI search beats this process, and what to do about it

What you do by hand: you search, you open the official page, you read the date on it. The API call does one thing in one
shot: a JSON answer under a narrow prompt at temperature 0.1, 3 to 30 searches of its own choosing, no page in front of it,
and a citation that is often a redirect URI or a guessed path on the right site. You pay for every hidden search.

The repo already holds the evidence for the better shape. The finder plus reader experiment (experiments/finder_reader_test/
RESULT.md, 2026-10-04): real URLs from the site's sitemap and menu, a cheap reader, a verbatim quote checked by code, a
main-call rule. 12 of 14 known deadlines right with 0 wrong at about 0.4 cents an event, against the grounded call's 8 of 14
with 3 citations that did not state the date. The shadow finder has run beside Saturday since 10-04 read-only (10-17: agreed
on 13 of 26, differed on 3, found 4 deadlines we ship blank). Its weakness is speed (2.5 to 3 minutes an event, pages
rendered one at a time 2 s apart), which parallel fetching fixes.

### Current prices for the search step (read 2026-11-07, official pages)

| Option | Price | Returns source URLs | Notes |
|---|---|---|---|
| Gemini google_search (today) | 5,000 free searches a month shared across Gemini 3 models, then 14 USD per 1,000; default cap 1,500 search requests a day per project | redirect URIs; 42 percent not in sources | Interactions API returns url_citation with real URLs |
| Gemini url_context | input tokens only, up to 20 URLs a call | n/a (you supply the URL) | the cheap re-check path for a URL we already hold |
| OpenAI Responses web_search | 10 USD per 1,000 calls plus tokens | url_citation annotations | one call can run several searches |
| Claude API web search | 10 USD per 1,000 searches plus tokens | yes | web fetch tool free beyond tokens |
| Perplexity Search API | 5 USD per 1,000 (fast 1 USD) | yes, with page snippets | Sonar chat models retired |
| DeepSeek Search and Fetch | 0.75 USD per 1,000 each | yes, with summaries | young service, CN provider |
| Brave Search API | 5 USD per 1,000; 5 USD free credit a month | yes | card on file |
| Exa | 4 to 12 USD per 1,000; 10 USD free a month | yes | semantic search suits "the CFP page for X" |
| OpenRouter web_search tool | 0.005 to 0.007 USD a call | url_citation | key already in hand |
| Codex CLI (ChatGPT plan) | 0 USD marginal; `--search` for live results | prose only, no citation contract | plan limits; fine for ad hoc checks and shadows |
| Claude Code `claude -p` WebSearch (Max plan) | draws on the subscription | prose plus links | same caveats as Codex |
| Google Programmable Search JSON API | closed to new customers, ends 2027-01-01 | yes | dead end |

### Recommended shape: search, fetch, extract, prove

1. Search once per row for the official page (DeepSeek Search, Perplexity Search, Brave or Exa on free credit; or OpenAI
   web_search when a model should pick). Keep the held URL as candidate 0, and probe last year's URL with the year bumped.
2. Fetch the top 2 or 3 candidate pages through the existing fetch ladder (crawl4ai, Playwright, CDP) or Gemini url_context.
3. A cheap reader (Gemini Flash-Lite, DeepSeek) extracts deadline, dates, city and a verbatim quote from the fetched text.
4. Code asserts the quote is a substring of the fetched page and that the date is in it (the rule the finder already uses).
   A row with no proven quote ships last week's value and says so. This makes the 42 percent phantom-citation case impossible
   by construction.
Expected: about 1 to 5 USD a week instead of 30, minutes instead of 90, every shipped deadline backed by a page we fetched.
Keep Gemini grounding as the fallback for rows where no official page is found, through the Interactions API for real URLs.

### Test plan (shadow only, one change per experiment, per experiments/README.md)

- T1 (about 5 USD): 40 rows (the pinned answer-key events plus 26 live ones) through four arms on the same day: the current
  grounded call; search+fetch+extract with DeepSeek or Perplexity search; OpenAI Responses web_search with url_citation;
  Codex CLI `--search`. Score each: deadline equals the key, the cited page states the date, searches and cost, seconds.
- T2 (no extra cost): the current grounded path with 4 workers and a 60 s per-call timeout on a 40-row sample, to measure
  wall clock and the 504 rate against the serial run.
- T3 (tokens only): Gemini url_context on the URL we already hold, for the carried rows, as the Sunday re-check path.
- Adopt by making the new path the weekly row's primary source only after two shadow Saturdays agree with it, with the
  grounded call demoted to fallback. The existing shadow_finder, pass_lib.accept and main_call.py are the parts to reuse.

## 4. Open items for a person this weekend

- Utility sheet header A1 (section 1): ask the customer, or decide to tolerate it.
- Watch the import finish (expected 04:30 to 05:30 if each market needs up to three gate rounds); if a round runs past
  about 30 minutes the hang in defect 2 is back.
- Decide whether to fix defects 1 to 4 before Friday 11-13 (small, testable code changes in cfp-monitor).
- Decide whether to run T1 and T2 as shadow experiments before next Saturday.
