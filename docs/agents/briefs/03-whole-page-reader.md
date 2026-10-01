# Brief 03: whole-page model reader, label every date on a page (Codex or Hermes, about 1 USD)

**DO NOT START until brief 01 is complete and its 10-row spot-check has passed.** This brief is scored against that key.

**1. Goal.** A script that takes a web page's text, asks a cheap model to label EVERY date on it from a closed list, and has code prove the labels are grounded in the page. Output: for each page, the submission deadline(s) it states.

**2. Why.** Our rule-based reader fails when a date's meaning comes from a heading or table layout (holdout precision 0.33). A model reading the whole page sees the layout. The risk is a model inventing or mislabelling, so code, not the model, decides what is accepted.

**3. Inputs.**
- Page text for the 40 benchmark events: the agent fetches each event's call page (URLs from `docs/agents/results/01-benchmark.csv` `evidence_url`, plus each `event_home_url`). Page text must be saved to `docs/agents/results/03-pages.json` (url to text) so the run is repeatable.
- Existing code to REUSE, not rewrite: `experiments/sentence_picking/sentence_pick.py` (`extract_dates`, `gate`, the OpenRouter call pattern, request and cost caps) and `scripts/extract_citations.py` (`locate_verbatim`).
- Model: `deepseek/deepseek-chat` via OpenRouter, key from the environment variable already set on the machine. Never print or log the key.

**4. Allowed.** Writing new files under `experiments/whole_page_reader/` and `docs/agents/results/`. Running the script. Read-only fetch of the pages.

**5. Forbidden.** README rules plus: do not edit any existing file; do not touch the database, deliveries or customer sheets; no model other than the one named; do not look at the benchmark answers while designing the prompt (use only the 15 labelled pages in `experiments/sentence_picking/labels.json` to develop; the benchmark is the unseen test).

**6. Output.** `experiments/whole_page_reader/reader.py`, and `docs/agents/results/03-reader-results.csv` with columns `id, date, label, label_set, unit_text, accepted`. `label` is one of: `submission_deadline`, `opens`, `notification`, `registration`, `event_dates`, `exhibitor_or_payment`, `other`. A date is `accepted` as a submission deadline only if (a) the model labelled it so, AND (b) `unit_text` is a literal substring of the page text, AND (c) the date as written in `unit_text` parses to the stated ISO date with a year stated in the unit or its heading.

**7. Honest blanks.** Pages with no submission deadline produce no accepted rows. The model may answer `none`.

**8. Budget and stop rule.** Hard caps in the script: 80 requests, 1.00 USD, whichever first; stop and report at the cap. One request per page; no retries beyond one for unparseable output.

**9. Success test (fixed before the run).** Against the benchmark key: precision (accepted dates that equal the key's `submission_deadline`) at least 0.95, and recall (key deadlines found) at least 0.80, on pages where the key records an open deadline. Zero accepted rows whose date equals a registration or event date in the key's `other_dates_seen`. Report the as-run score first. Any prompt change after seeing the score is declared as such and scored on a fresh set, not this one.

**10. Report.** 5 lines: pages processed; accepted count; precision and recall as defined; requests and cost; files written.
