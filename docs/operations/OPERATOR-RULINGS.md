# Operator rulings - definitions the operator has decided

A ruling here is a DEFINITION or a policy the operator decided, not a fact about one event (facts about one event are pins, `docs/operations/pinned_rows.json`). Each entry says what was decided, when, why, what it changed, and how to reverse it, so it can be changed later without archaeology. Newest first. Plain ASCII.

## R-001 - START DATE is the first day of the MAIN CONFERENCE, not of the whole event

- **Decided:** 2026-10-05, by the operator (in chat), answering the builder's question from the Wave 2 review.
- **The rule:** for an event that has a day or days BEFORE the main conference (a training day, workshops, a reception evening, an early on-site programme), `START DATE` is the first day of the main conference. `CONFERENCE DATES` text, where we write it ourselves (pins, operator edits), covers the main conference days. `EDITION` follows `START DATE` (contract R19.1), so it is unaffected unless the event straddles a new year.
- **When there is only ONE stated range and nothing on the page says part of it is something else,** the range is used as stated (the reader and the importer cannot know). The rule applies where the event's own page labels the days: a "Conference Day", "Conference", "Summit" or "Main conference" range beside separate "Training", "Workshop" or "Pre-conference" ranges. This matches what the reader already does since ACT-23 (`experiments/read_the_page_pass/pass_lib.py`, QA-REGISTER A32).
- **Why:** the customer is choosing whether to speak at the conference; the training days are a different product with their own call. (Operator's words: "first day of the main-conference".)
- **Cases known on 2026-10-05:**
  - German OWASP Day 2026 (Karlsruhe): trainings Wed 23 Sep, Conference Day Thu 24 Sep (page https://god.owasp.de/2026/, read 2026-10-05). The pin moved from START 2026-09-23 to 2026-09-24 (see `pinned_rows.json`, `ruled_on` 2026-10-05).
  - Troopers 2027 (Heidelberg): on-site 21-25 June, trainings 21-22, conference 23-24 June. START DATE should read 2027-06-23. Not pinned: the research should find it (the reader applies the labelled-range rule); check on the next load.
  - Industry Connect Canada 2026: ours says 26-27 October; its page header reads 27 October with a 26 October pre-event day. Under this rule START DATE is 2026-10-27. Not pinned and not yet changed; the Saturday shadow reader will show whether the research agrees.
- **What it did NOT change:** no value in the live database or an approved file was edited for this ruling; pins apply at the next load (Saturday 2026-10-10 for German OWASP Day).
- **Upstream:** the contract does not define which day START DATE means. Upstream should be told (draft with the Wave 4 notes) so their research uses the same day. Until then the importer and the arbiter (`scripts/start_date_arbiter.py`) are unchanged.
- **Upstream accepted it on 2026-10-05 (reply to note 29):** START DATE is the first day of the main conference, CONFERENCE DATES the main-conference range, and a single contiguous range is used as published.
- **To reverse:** delete this entry, set the German OWASP Day pin back to START DATE 2026-09-23 and CONFERENCE DATES "September 23 - September 24, 2026", and regenerate the answer key (`python scripts/answer_key_from_pins.py`).

## R-002 (2026-10-06) Sponsorship and contacts
- Delivery gate for sponsorship stays LINK-ONLY (R18b/R20a). Quotes are extracted by us (extract_sponsor_quotes.py, Chrome on port 9222, on a copy of the db first).
- A "Yes" with no quote shows on the customer page as "Sponsor required (unconfirmed)".
- An event with no call page but a published, named enquiry/programme email counts as FOUND/RESEARCHED: the address goes in COORDINATOR EMAIL, plus a row note (first case: Japan CCUS Summit 2026, Fiona@leader-associates.com).
- Model tests: GPT-6 Luna (max) through the operator's ChatGPT subscription first; on failure or exhausted usage report the exact reason, then fall back to the existing OpenRouter key. Free models OK for public page text only.
