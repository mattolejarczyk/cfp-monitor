# RESULT - experiment 4: the read-the-page pass (2026-10-03)

Files: `pass_lib.py` (prompt, acceptance rules, scoring), `run.py` (runner), `results.json` (last run), `llm_log.jsonl` (every call, tokens, cost), `pages.json` (page cache, git-ignored).
Budget agreed: cap 60 requests and 0.50 USD. Spent over all runs: well under 0.10 USD.

## The question
Given the page a person verified (or one the first, grounded pass found), can a cheap model read the event's start date, end date, city, country, venue, organizer and format, **each with a verbatim quote**,
and stay **blank** when the page does not state it for the edition we ask about?

## Method
- The model gets the event name, the EDITION YEAR to report, and the page text (plain `verify.fetch_text`, 12,000 characters). It returns each field with a quote.
- **Code decides, not the model.** A field is accepted only if (a) the quote is a literal substring of the page, (b) a date's quote states that day, month and year (ranges spelled out first) in the asked edition's year, (c) a text field's value appears in its quote. Everything else is blank.
- Gold = what the operator verified (pins: 15 facts for 11 events, 3 of them 'the page states nothing') + the real ODSC East page (gold read by Claude in a browser, NOT by the operator) + the trap fixtures T01, T02 (asked for 2027 and for 2026), T09. 16 scored facts in all.
- Models: `deepseek/deepseek-v4.1-flash` (low reasoning effort) and `deepseek/deepseek-chat` (V3). Temperature 0.

## Results (clean runs: every call returned HTTP 200, none retried)
| | v4.1 flash | deepseek-chat (V3) |
|---|---|---|
| Wrong answers accepted | **0** | **0** |
| Blank-expected cases kept blank (wrong-edition page, dead page, page states nothing) | 3 of 3 | 3 of 3 |
| Verified facts found | 7 of 16 (an earlier run found 8 of 13 on the first gold set) | 10 of 16 |
| Cost of a full pass (13 calls) | about 0.8 cents | about 0.8 cents |

Across every run (about 70 scored answers) **no wrong date or city was ever accepted**, including the trap pages: a page that shows next year's edition (Carbon Capture Technology Expo MENA) and a page with two editions (ODSC East). The pass fails by returning blank, not by inventing.

## What limits recall (the misses are about the PAGE, not the model)
1. **Pages the plain fetch cannot render.** Global Energy Show Canada returned no text at all; Nullcon's dates sit in a timeline built by script; CES's home page prints no CES 2027 dates in text. A browser render is the fix (the page library already uses real Chrome over CDP).
2. **Date formats the reader does not know.** German OWASP Day writes dates in German form; the code rejected the quote. Our `find_date` needs dd.mm.yyyy, German month names and ordinals ('May 10-12th').
3. **The year is in the heading, not beside the date.** ODSC's speaker block says 'April 28-30' under 'ODSC AI East 2026': the strict rule (the quote must state the year) rejects it, correctly for safety. A rule that takes the year from the nearest heading, checked in code, would recover these.
4. **Run-to-run variance.** At low reasoning effort the same call sometimes returns blank (European CCUS and its trap fixture were right in one run, blank in the next). Blank is the safe failure; repeat runs or a second model recover some. The older V3 model found more facts here than the newer flash model, which is the opposite of what price would predict: do not choose on one run.

## A mistake of mine this experiment caught (and a rate-limit lesson)
- ODSC East: I had told you the page shows only the 2026 edition. The header states May 10-12th, 2027. V3 returned 2027-05-10 and I scored it a 'false accept' against a gold I had gotten wrong; checking in a real browser showed the model was right and I was wrong. Corrected everywhere (see OPERATOR-EDITS-LOG.md); trap case T02 rewritten.
- The first runs counted HTTP 429 (rate limit) as 'the model said blank'. The runner now retries and reports a failed call as a failure, never as a blank.

## Conclusions
- **Safe to build on:** quote-checked extraction from a page never made a wrong claim in these tests, which is the property that matters for data the customer sees.
- **Cheap:** about 0.06 cents a call; a 130-event weekly second pass over three pages each would cost roughly 20 cents.
- **Not yet a replacement for the research:** recall is 44-62% on the pages it can read, and the pages it cannot read are exactly the script-built ones.
- **The sample is small** (16 scored facts, 11 events, one set of runs per model). It shows direction, not a rate.

## Next steps (in order of payoff)
1. Page access: render script-built pages in the browser and re-run (measure the share of pages where the plain fetch yields no dates).
2. Date formats: dd.mm.yyyy, German and other month names, ordinals, in `find_date` and the arbiter; add them to the trap cases.
3. Year from the nearest heading, with a code check, for blocks like ODSC's speaker announcement.
4. Repeat each run three times; try both models and an agreement rule (experiment 5) before choosing.
5. Grow the gold set as the operator verifies more of the benchmark events.

---

# UPDATE (2026-10-03, later): the three recall limiters, re-run three times per model

**What changed:** (1) a page whose plain text has no dated sentence is rendered in the real Chrome (`src/cfp_monitor/render_text.py`; Chrome on 127.0.0.1:9222); (2) dates in German, French, Spanish, Italian, Dutch and Portuguese, numeric day-month-year (23.09.2026), accents and ordinals, with the YEAR always required; (3) a quote that states no year may take the nearest EARLIER year on the page (within 400 characters), only if it is the date's year and the asked edition. The fourth limiter found along the way: `expand_ranges` needs a 'not preceded by a digit' guard on every pattern (a bug of mine, caught by the full suite, fixed; it only affected end dates).
Same gold (16 verified facts: 15 operator facts, the real ODSC page, trap fixtures), three runs per model, every call HTTP 200, 91 requests and 0.056 USD in all.

| | before the limiters (one clean run) | after: run 1 / 2 / 3 | found in EVERY run |
|---|---|---|---|
| deepseek-chat (V3) | 10 of 16 | **12 / 13 / 13 of 16 (75% to 81%)** | **12 of 16** (13 in at least one) |
| deepseek-v4.1-flash | 7 of 16 | 7 / 10 / 9 of 16 (44% to 63%) | 7 of 16 (10 in at least one) |
| Wrong answers accepted | 0 | **0 in all six runs** | |
| Blank-expected cases kept blank | 3 of 3 | 3 of 3 in all six runs | |

## What was recovered
Global Energy Show Canada (page now rendered), German OWASP Day (German date format), the ODSC East header (heading-year and header date), Carbon Capture USA, SAF Europe, CarbonZero and the European CCUS page for the older model.

## What is still missed, and why (most are correct refusals)
- **CES start date:** the page prints 'January 6-9' with no year beside it and no year within 400 characters before it. Rejecting it is the safe behaviour; a person verified it (pinned).
- **CES country 'USA':** the page says 'Las Vegas, NV'; the model inferred 'USA' and the code rejected it because the value is not in the quote. Correct.
- **Nullcon start date:** the rendered page states 'Conference: 27th - 28th February 2027' next to 'Training: 24th - 26th February 2027'; both models return blank. A prompt that asks for the conference day explicitly, or reads the timeline block, is the next thing to try.
- **The faster model** (v4.1 flash) is simply more conservative: it returned blank on easy facts (the European CCUS page, even the one-line fixture) in every run. Price did not predict recall: the older, cheaper-per-token model found more.
- **ODSC asked for the 2026 edition:** found in 2 of 3 runs by the older model (the year comes from the heading).

## Conclusions after the limiters
- **Safety held:** across six runs and about 95 scored answers the pass accepted nothing wrong. It still fails by returning blank.
- **Recall is now 75% to 81% (older model) on pages the pass can read**, up from 62%; the gains came from page access (rendering) and date formats, as predicted. What is left is mostly 'no year beside the date' and 'two date ranges on one page'.
- **Do not choose a model on one run**: the faster model moved between 7 and 10 of 16 on identical input.
- **Still a small sample** (16 facts, 11 events): direction, not a rate. Grow the gold set as the operator verifies more.

## Next steps
1. Prompt and rule for pages with several date ranges (training / day zero / conference): ask for the main conference's days and require the page's own label.
2. Accept a country when the page names a state or province of that country (Las Vegas, NV: United States) through a small, checked lookup, or leave the country blank.
3. Run the same pass on the 26 benchmark events not yet verified, then have the operator confirm only the disagreements.
4. Compare with the grounded call on the same events (experiment 3's finder side) before changing any weekly job.
