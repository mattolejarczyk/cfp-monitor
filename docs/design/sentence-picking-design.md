# Sentence-picking step (discovery mode) - design

Drafted 2026-10-01. **DESIGN ONLY. No LLM request has been made and nothing is wired.** Follows the experiments rules: one change per experiment, copies only,
a stated budget agreed BEFORE any AI request, advisory output only, a written RESULT.

## 1. What this step is for
Upstream of it, the page-discovery work now selects a handful of pages per site (median 4) and a deterministic date reader (`dates_v2.py`) returns date
CANDIDATES near call wording. Two failures remain that no reader can fix because the gap is semantic:
- which dated sentence is the SUBMISSION deadline (h2meet's award schedule page also shows 9/30; an events listing shows the date an event is HELD);
- whether a date belongs to this edition (troopers.de's "CfP ends on: March 31st, 2027" is the NEXT edition's deadline).
This step reads the page text and POINTS at the sentence, and code proves the pointer. The repo's rule applies: the question is never "is the model good
enough" but "can we check the answer without trusting the answerer" (`docs/operations/market-runbook.md`, "Where an LLM is safe").

## 2. What already exists, and the one real difference
`scripts/extract_citations.py` already implements the safe pattern: `llm_pick_sentence` (model selects), `locate_verbatim` (code proves the sentence is on the
page and re-cuts the page's own characters), `_WRONG_PURPOSE` (withdrawal / notification / registration / hotel / early-bird dates refused), `verify_call_label`
(the model's label must be echoed by the page nearby), statuses `ok / blank / not-on-page / wrong-purpose / unparseable-target / no-date / undated / unavailable`,
and the rule "a considered blank stands; fall back to heuristics only on an outage". It reads through litellm and the configured provider
(`CFP_LLM_PROVIDER`, today `openrouter/deepseek/deepseek-chat`).
**The difference:** it works in VERIFICATION mode - it is GIVEN the claimed date and finds the sentence containing it, and it refuses to run without one
("NO TARGET, NO CITATION", written after a real incident). Our pages need DISCOVERY mode - no date given; find what the deadline is. Discovery removes the
target that every existing guard compares against, so each guard must be rebuilt around something else (section 4).

## 3. The pipeline (per selected page)
0. INPUT: page text from `crawl_pages.json` (fetched by us through the renderer, so real by construction), the page URL, the event name, and the
   edition year taken from the URL or title (`2027-conference`, `troopers27`) or, failing that, stated unknown. NO customer data in the prompt (public repo).
1. PRE-FILTER (free): ask only where there is something to point at. Run `dates_v2.any_date_near_call`; a page with no date near call wording is skipped, not sent.
   Non-English pages are skipped and flagged (prefer the English twin; a language-aware reader is a separate step).
2. EXCERPT (free): not the whole page. Cut windows of +-600 characters around each date-near-call hit, merge overlaps, cap at 6,000 characters. The existing
   function truncates at 16,000; windows cost less and remove the cookie-banner noise seen on ccus-expo.
3. MODEL: one request, temperature 0, JSON out. Candidate list, at most 5: `{sentence, call, kind, date_text}` with `kind` one of
   `submission_deadline | opens | notification | event_dates | registration | other`. A blank list is a valid, final answer.
4. CODE GATES (a candidate is ACCEPTED only if every gate passes; each rejection is counted by reason):
   a. VERBATIM: `locate_verbatim(page, sentence)`; else `not-on-page`. What is stored is the page's own characters.
   b. PURPOSE: `_WRONG_PURPOSE` must not match and submit vocabulary must (`_SUBMIT_VERB`); the model's `kind` must be `submission_deadline` AND the code must agree.
   c. DATE FROM THE SENTENCE, BY CODE: extract the date with `dates_v2` (extended to EXTRACT, not only find). The model's `date_text` is not trusted; it must
      be inside the verified sentence. No parseable date -> `undated`.
   d. YEAR: an explicit year wins; else the edition year; else the page's single most common year; if still unknown the date is kept with `yearless-noyr`
      (weak) and is never auto-accepted. A year different from the edition's is `next-edition`, reported separately (Gap 5), never a conflict.
   e. CALL LABEL: `verify_call_label` (page nearby must use the label's words); an unverifiable label is dropped, the date stays.
5. COMPARE with what we hold (read-only): `agree` (same date), `contradicts` (different date, same edition and call), `new` (we hold no deadline),
   `next-edition` (year ahead of ours), `older` (a past cycle).
6. OUTPUT: advisory rows (page URL, quote, date, confidence, call, comparison, model, prompt version), the `extract_citations` OUT_COLUMNS shape so it
   flows to the existing `apply_resolutions.py --citations` merge guard. Nothing is written to `conferences`, the deliveries or the research inputs.

## 4. Why discovery is harder, and what replaces the missing target
| Guard that used the target date | Replacement in discovery |
|---|---|
| "date must be in the sentence" | the date is parsed from the verified sentence by code and must be unambiguous |
| "NO TARGET, NO CITATION" | no accepted deadline without a parsed date AND a purpose pass AND a verbatim pass |
| "different date = contradiction" | only after comparing with our stored value for the SAME edition and call |
| "undated sentence settles nothing" | kept: `undated` is a counted rejection |
Risk this creates: the model can now choose a date, not just a sentence. The gates make the choice checkable (is it verbatim, is it about submitting, what year);
they cannot prove it is THE deadline when a page lists several calls. Those cases are returned as multiple candidates with their call labels, never merged.

## 5. Draft prompt (version 1; the existing `SELECT_INSTRUCTION` is the base)
"You are shown excerpts of ONE web page for the event named below. List every sentence that states a deadline for SUBMITTING something: a paper, abstract,
proposal, speaker application, nomination or entry. Copy each sentence EXACTLY as it appears, as a literal substring; do not fix, reword or join.
Give `kind` and `call` (which call it belongs to: abstract, full paper, poster, awards ...) for each. Dates for withdrawing, notification, registration,
hotels, early-bird pricing or the event itself are NOT submission deadlines: label them with their kind or leave them out. If the page states no submission
deadline, return an empty list: an honest blank is correct and always acceptable. Do not answer from memory; use only the text shown."

## 6. Model and tooling
Model under test: `deepseek/deepseek-v4.1-flash` through OpenRouter (operator's choice; the model page lists `response_format` and `reasoning` parameters, and 429 as
rate limiting; pricing was not shown on the page and has NOT been verified). The repo default is `openrouter/deepseek/deepseek-chat`; it stays as the comparison model.
`litellm`, which `llm_pick_sentence` imports, is NOT installed in the Python used by these experiments, so the existing function would return `unavailable`.
Decision needed: install it (a package change) or call OpenRouter's OpenAI-compatible endpoint with `httpx` (already installed). Recommendation: `httpx`, same
request shape, no new dependency, and the gate code is imported unchanged. Operator key present (`OPENROUTER_API_KEY`); balance not yet checked (free read-only call).
Reliability: an earlier session recorded OpenRouter deepseek-chat answering 429 "rate-limited upstream" on nearly every page; so retries with backoff, and
`unavailable` is never reported as `blank` (the repo rule).

## 7. Test plan (one change; copies only; nothing written to the DB)
INPUT: the 40 saved pages. Ask only where the pre-filter finds a date near call wording (about 15-20 pages). LABELS ARE WRITTEN BEFORE THE RUN, by reading each
page, and committed (the model's output never grades itself): for every date-bearing sentence, is it a submission deadline of this edition, of the next edition,
another call (award, journal), or not a deadline.
ARMS (same pages, same gates):
- A. deterministic baseline: the first date near submit wording (what the pipeline has today, no model).
- B. `deepseek-v4.1-flash` discovery.
- C. (optional) repo default `deepseek-chat`, to separate model from prompt.
METRICS: accepted-candidate precision against the labels; recall of the known deadlines (h2meet 2026-09-30, blackhat 2026-03-23, on-climate 2026-12-19,
globalenergyshow 2026-12-04); decoys correctly rejected (h2meet award schedule, ccus event dates, SecureWorld listing); next-edition dates correctly labelled
(troopers 2027-03-31, on-climate 2028 call); rejection counts per gate (`not-on-page` must be printed every run); latency and cost.
SUCCESS, fixed in advance: B accepted precision >= 90%; zero accepted sentences that fail the verbatim gate (by construction); all four known deadlines
recovered; every troopers/on-climate next-edition date labelled `next-edition`; and B must beat A on decoys, otherwise the model is not earning its place and
the deterministic reader plus the gates is the answer.
BUDGET (to be agreed before the run): at most 60 requests and 1 US dollar for all arms. Expected: about 20 pages x 3 arms, roughly 3,000 input and 300 output
tokens each, which is cents at any plausible price. Hard stops: the request cap, the dollar cap (from provider-reported usage), two 429s in a row.

## 8. Guardrails
Public repo: no customer detail in prompts, logs or this folder. Pages are public web text. The model sees only text we fetched. No write to the live DB.
Every request, prompt version and raw response is logged for audit. Rejection counts reported per run. `blank` and `unavailable` kept distinct.
Non-English pages skipped and flagged. A page the pre-filter skips costs nothing.

## 9. Decisions needed
1. Budget: 60 requests / 1 USD for the test?  2. `httpx` against OpenRouter instead of installing `litellm`?  3. Include arm C (the repo default model)?
4. Pre-label the pages myself and commit the labels before the run (recommended), or have you spot-check them?
5. After the test: wire into the weekly chain as advisory rows only, or keep it offline until a second sample confirms?
