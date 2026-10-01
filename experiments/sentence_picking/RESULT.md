# RESULT - sentence-picking, discovery mode (2026-10-01)

Design: `docs/design/sentence-picking-design.md`. Runner `sentence_pick.py`; answer key `labels.json` (sha256 in `labels.sha256`, locked before any request and re-checked
at every scoring); every request and response in `llm_log.jsonl`; scores in `scored.json` (as designed) and `scored_posthoc.json`.
Budget approved: at most 60 requests and 1 USD. Spent: 36 requests, 0.045 USD. Nothing written to the database or deliveries. The OpenRouter key was read from the
environment and never printed or logged. Calls went through `httpx` (litellm is not installed).

## Setup
40 saved pages; 15 pass the free pre-filter (a date near call wording); the other 25 were checked by hand and carry no submission deadline. Answer key written by one
labeller (me) from the page text: 24 submission-deadline labels, 4 recurring journal rounds, plus open / notification / event / registration / not-a-call decoys.
Arms: A deterministic baseline (every dated sentence with submit wording, no model); B `deepseek/deepseek-v4.1-flash` (the operator's model); C `deepseek/deepseek-chat`
(the repo default). One request per page per model. The model sees only excerpts of the page text we fetched. Code gates, applied to every candidate: sentence verbatim
on the page (existing `locate_verbatim`), purpose check (existing `_WRONG_PURPOSE`), submit wording, the date parsed by code from the verified sentence, a year
(explicit, "(26)", range, else the nearest heading year), call label echoed by the page.

## Results as designed (gates exactly as written before the run; B includes a retry of its truncated pages at 4,000 tokens)
| Arm | Accepted | Correct | Wrong-purpose | Unlabelled | Precision | Recall | Cost | Mean time |
|---|---|---|---|---|---|---|---|---|
| A no model | 24 | 12 | 6 (opens-dates taken as deadlines) | 6 (event dates and journal rounds given invented years) | 0.50 | 12/24 | 0 | - |
| B deepseek-v4.1-flash | 12 | 12 | 0 | 0 | 1.00 | 12/24 | $0.040 (21 requests) | 4.6 s |
| C deepseek-chat | 13 | 13 | 0 | 0 | 1.00 | 12/24 | $0.0047 (15 requests) | 3.0 s |
Before B's retries it had 8 accepted / 8 correct / recall 8/24 with 4 unusable answers.

## Post-hoc re-score (changes made AFTER seeing the key: NOT a pre-registered result)
Two gate changes: the submit-wording check also accepts "deadline", "CfP/CfT ends", "due" and similar; month/day dates such as "8/31" are read when the day is above 12.
B: 16 accepted, 16 correct, recall 16/24. C: 17 accepted, 17 correct, recall 16/24. A unchanged. Precision stays 1.00 for both models. These changes were chosen from the
misses and need a fresh sample before they are adopted.

## Against the success criteria fixed in advance
| Criterion | Outcome |
|---|---|
| Accepted precision at least 90% | met: 12/12 (B), 13/13 (C), also 16/16 and 17/17 post-hoc |
| No accepted sentence fails the verbatim gate | met: the verbatim gate rejected 0 candidates for either model, so neither fabricated a sentence |
| Beat the baseline on decoys | met: A accepted 6 "opens" dates and 6 invented-year dates; neither model accepted any decoy |
| All four known deadlines recovered | NOT met as stated. Black Hat 2026-03-23 and Global Energy Show 2026-12-04 recovered by both. h2meet's speaker deadline (2026-09-30) not recovered from the speaker page (B unusable, C rejected for no year); only the same date for its AWARD call was. on-climate's stored 2026-12-19 is a REGISTRATION date, so correctly not accepted (see below) |
| Next-edition dates labelled | partly: troopers.de 2027-03-31 and 2027-02-28 recovered post-hoc by both; the on-climate 2028 proposal dates missed by both |

## What the misses are (post-hoc, 8 of 24 for each model)
All of them sit on three pages, and all are table-like or schedule-like rather than sentence-like: h2meet speaker.php (a schedule with month/day dates and no year in
the sentence), on-climate 2027 call-for-papers and on-climate 2028 call-for-papers ("Proposal Periods: Early Launch to 19 June (26) Regular 20 June (26) to 19 October (26)
Late ..."). The unit there is a row under a heading, not a sentence, and the heading ("Proposal Periods" versus "Registration Periods") is what separates a submission deadline
from a registration date. That is the next design problem: heading-aware, list-aware extraction.

## Arm B versus arm C
Same precision and recall; C cost about one eighth as much ($0.0047 versus $0.040), answered faster, and gave a usable answer on all 15 pages. B wrote long reasoning on
pages with several dated calls: 4 of 15 answers hit the 1,500-token limit, two were still unusable at 4,000 tokens, and a low-reasoning setting did not change that.
On this evidence the repo's existing default model is the better choice; v4.1-flash is not recommended here. 15 pages is a small sample and one run each.

## A data finding, separate from the model test
on-climate.com's stored deadline for the Climate Change conference, 2026-12-19, is marked "verified" in our database, but the detail is "[L0s] the page itself states the call is open"
(the call status was confirmed, not the date), the deadline's own evidence verdict is `no_quote` with a claimed value of 2026-12-20, and 2026-12-19 equals the end of the REGISTRATION
regular period on the call page. Across the two customer markets, 13 of 48 stored deadlines are `verified` only through that status layer and 5 more are `verified` with no evidence page. The page's proposal periods end 2026-06-19 (early), 2026-10-19 (regular) and 2026-12-20 (late). The earlier fair recall test counted that date as a hit; that was
wrong, because the reader matched a registration date. The stored value needs review before it reaches the customer.

## Limits
15 pages; 24 labels; one labeller; one run per model; post-hoc changes flagged; only English pages; the year fallback (nearest heading year) caused the baseline's invented-year
errors and is the weakest rule; deadlines were not compared with the database here (design step 5 not exercised).
