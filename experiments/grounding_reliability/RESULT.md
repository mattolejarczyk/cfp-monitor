# RESULT - experiment E: narrow prompt vs full prompt (2026-09-30)

Files: `probe_narrow.py` (harness), `sample.json`, `calls.jsonl` (every call), `scored.json`, `run_log.txt`.
Budget agreed: at most 48 requests, ~$4. Spent: 48 requests, estimated $2.25 (search fees + tokens; billing
report will confirm after it posts). Nothing outside this folder was written; no scheduled job touched.

## Setup
12 live-market rows with a verified future deadline (truth = the deadline, quote and evidence page already in the
database). Each row run on both arms twice, interleaved in random order (so time of day cannot favour an arm), one
attempt per call, no retries, 120s client timeout, `gemini-3-flash-preview`, same temperature / JSON mode / search tool.
Arm A = production conference prompt (11,900 chars, 33 fields). Arm E = same identity + anti-echo scaffold, short rules,
9 fields (2,850 chars). Prior deadline was NOT shown in either arm (it would leak the answer), unlike production.

## Numbers (24 calls per arm)

| | A full prompt | E narrow prompt |
|---|---|---|
| Grounded (a search ran, answer returned) | 9 (38%) | 24 (100%) |
| 504 DEADLINE_EXCEEDED (calls that hit 120s) | 8 | 0 |
| Answer with NO search | 7 | 0 |
| Median latency of grounded calls | 28.0 s | 16.4 s |
| Mean thinking tokens per grounded call | 5,259 | 2,340 |
| Mean searches per grounded call | 4.0 | 3.8 |
| Estimated cost per grounded call | $0.077 | $0.061 |
| Deadline equals the known deadline (of grounded) | 9 of 9 | 24 of 24 |
| Same evidence page as our verified one | 1 of 9 | 9 of 24 |
| Same evidence HOST as our verified one | 7 of 9 | 20 of 24 |

Arm A's 38% matches production's ~27-30%, so the harness reproduces the real problem. 24/24 vs 9/24 is far outside chance.
Per row, A's failures are not tied to particular conferences: most rows grounded on one repetition and failed on the other.

## What this shows
- The prompt is a major cause of both failures, at least for this kind of row. Same model, same tool, same rows, same
  hours: the short prompt never timed out and never skipped the search.
- The "504" is our own 120s deadline being enforced by Google (the client library sends it as `X-Server-Timeout`).
  Every A failure of that kind stopped at 118.7-119.5 s. So it means "did not finish in 120s", and the narrow prompt
  finishes in 9-34 s.
- The narrow prompt also uses about half the thinking tokens, and is faster and cheaper per grounded call.
- Failed calls cost ~nothing in search fees (billing reconciliation, 2026-09-30), so A's waste was time and retries.

## Free re-score of the other asked fields (no Gemini calls; `rescore_fields.py`, `rescored_fields.json`)
Saved answers compared with what the database already holds for the same 12 events. Grounded calls only (A 9, E 24).

| Field | A full | E narrow | Reading |
|---|---|---|---|
| START_DATE equals database | 9 of 9 | 24 of 24 | Exact match. Meaningful. |
| STATUS equals database | 9 of 9 | 24 of 24 | Weak: every row is "Open" by construction. |
| IS_PROJECTED equals database (false) | 9 of 9 | 24 of 24 | Consistent with verified rows. |
| CFP_SUBMISSION_URL identical to ours | 3 of 9 | 7 of 24 | Differs often; same website 8 of 9 / 20 of 24. Differing page is not proof of error - unchecked. |
| DEADLINE_QUOTE states the deadline date | 9 of 9 | 24 of 24 | After fixing a regex that missed "13th" style dates (5 apparent misses were all fine). |
| DEADLINE_QUOTE identical to our verified quote | 1 of 9 | 7 of 24 | Different wording is normal; says nothing about accuracy. |
| STATUS_DETAILS claims event ended | 0 | 0 | No false lifecycle claims on these rows. |
| CONFERENCE name changed by the model | 1 of 9 | 4 of 24 | e.g. "IEEE 77th Electronic Components..." for our shorter name. Identity risk: see below. |

Still NOT checkable from saved data: whether each quote is verbatim on the live page, and whether a different
CFP link works. Both need a page fetch (free of Gemini, needs a real-browser tool - the earlier simple fetch found our own
verified quotes on only 4 of 12 pages).
Rename note: `EVENT_ID` derives from the name. Production carries identity from the input (`EVENT_ID_CANON`), which reduces
the risk, but the conference prompt - unlike the awards prompt - does not forbid renaming. Worth an explicit rule in any
narrow prompt that goes live.

## Live-page check with the repo's own browser rung (no Gemini calls; `browser_verify.py`, `browser_verify.json`)
36 distinct pages rendered once each via `fetch._render_with_consent` (dedicated Chrome profile), plus our OWN verified
quote against our OWN verified page as calibration.

| Check | A full (9) | E narrow (24) | Our own verified quotes/pages (12) |
|---|---|---|---|
| Cited page rendered | 9 | 23 | 12 |
| Quote appears word for word on the cited page | 2 (22%) | 8 (33%) | 4 (33%) |
| Deadline date appears on the cited page | 4 (44%) | 12 (50%) | 8 (67%) |
| CFP link rendered | 9 | 24 | - |
| CFP link looks like a call/submission page (keyword test only) | 6 | 19 | - |

Reading: the tool cannot confirm even our own known-good quotes on their own pages (4 of 12), so the ceiling here is the
pages (consent walls and thin renders, e.g. SecureWorld returns ~600 characters; pages that have changed since we verified).
The narrow prompt's rate (33%) equals the rate for our own verified quotes, so on this evidence it is no worse than our
baseline - but "verbatim on the live page" remains UNPROVEN for both arms. One full-prompt answer cited a Facebook post as
its deadline evidence (banned host, R22); production's post-filter would drop it, the harness has no such filter.
Deeper pass (`browser_trace.py`, `browser_trace.json`): for every quote not found on its cited page, the existing tracer
(`trace_quote_to_page.trace`, 5 pages per site) looked for the exact sentence. Result: A 0 of 7, E 0 of 12, and OUR OWN
verified quotes 0 of 8 - every page was readable. The site walk confirmed nothing, including quotes we already trust, so
it has NO power to separate good quotes from bad here. Likely causes (not investigated): the pages changed since we verified
them, text the renderer does not see (PDF, iframe, image), or the tracer's strict full-match rule. Conclusion: word-for-word
quote accuracy cannot be established by automation on this sample. Do not use it as a metric for this experiment; use
"deadline date on the cited page" (E 50%, A 44%, ours 67%) and the deadline match (24/24, 9/9), and spot-check by hand.

### Loosened (free, non-AI) match on the 27 jobs the strict tracer missed (`loosened_match.py`, `loosened_match.json`)
Ignores case, spacing, punctuation, apostrophes, garbled characters, smart quotes, ordinals; date check in any common format,
with and without a year. Page text is cached in `page_cache.json` for the next step.
Rescued (whole quote found on the cited page): A 2 of 7, E 4 of 12, our own stored quotes 4 of 8 = 10 of 27. The date-proximity
tiers (T2 with year, T3 year-less) rescued none, so date-format variability was not the cause.
The 17 still missing: 5 cited pages returned almost nothing (<1000 chars: a consent/redirect shell, a Facebook post, a
wrong URL variant); 2 have the date with a year but a reworded sentence (the only AI-step candidates); 10 cite a page that does
NOT carry the date - SecureWorld /events listing (5; HANDOFF already records SecureWorld listing dates mistaken for deadlines),
OFC submit-a-paper, the IEEE CICC homepage, a Green Chemistry page, and one full-prompt answer that cited a DIFFERENT
conference's website (advancedbiofuelsusa.info for the CO2-based fuels conference).
Reading: the answers were mostly right (deadline 33 of 33) but a third of the citations point at the wrong page. That is a
page-discovery problem (sitemap / site navigation), not a matching problem.

## What this does NOT show
- **Quote quality is unmeasured.** The simple page fetch found our OWN verified quotes on only 4 of 12 pages (10 of 12
  resolved), so the "quote found on page" scores (E 5/24, A 2/9) reflect the checker, not the model. Do not use them.
- **The "cited host among search sources" check is broken here** (0 for both arms): grounding sources are redirect
  links, not publisher hosts. Ignore it. The production trail compares hosts by title and is the right tool.
- **Narrow means fewer fields.** Arm E returns 9 of the ~33 fields. Production needs the rest (city, categories,
  overview, organiser...). Whether they come from a second small call, from carry-forward, or from the existing record is
  undecided, and each has its own cost and failure modes.
- **Easy rows only.** All 12 have a verified future deadline (every answer came back Open, not projected). Closed,
  discontinued, renamed and successor cases - where rule 6a and the lifecycle claims matter - were not tested.
- **12 rows, one model, one day.** Time-of-day and a bad-Google-day effect were balanced, not eliminated.

## Recommendation
Adopt as the direction; do not wire in yet. Next, in order, each its own experiment (one change per experiment):
1. Quality: re-score with the existing verifiers (`verify_grounding` layer 2 / browser-ladder) instead of the simple fetch.
2. Hard cases: 12 rows across Closed / Upcoming / discontinued / successor, both arms, before any change to production.
3. Field coverage: decide how the other ~24 fields are filled (second narrow call vs the existing record).
4. Only then propose changing `run_market_audit.py`. Thinking-level and model arms (B, C) are now lower priority.
