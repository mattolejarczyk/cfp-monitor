# Heading-aware reader (tables, schedules, labelled lines) - design

Drafted 2026-10-01. **DESIGN ONLY. Nothing is built or wired; no request has been made.** Follows the experiments rules: one change at a time, copies only,
advisory output, a stated budget agreed before any AI request, a written RESULT.

## 1. Why: what the sentence step could not read
The sentence-picking test (`experiments/sentence_picking/RESULT.md`) recovered every sentence-shaped deadline with precision 1.00 for both models, and missed 8 of 24
labels, all on three pages. The pages state their deadlines as TABLES or SCHEDULES, where a single line means nothing without the heading above it. Raw page text,
as the renderer returns it (line breaks and tabs preserved):

    Proposal Periods                                   <- heading
    Proposals will be reviewed within two to four weeks of submission.      <- legend
    Early\t\tLaunch to 19 June (26)                    <- row: tier, range
    Regular\t\t20 June (26) to 19 October (26)
    Late\t\t20 October (26) to 20 December (26)
    Registration Periods                               <- the SAME rows again, a different purpose
    Early\t\tLaunch to 19 July (26)
    Regular\t\t20 July (26) to 19 December (26)
    Late\t\t20 December (26) to 20 January (27)

and, on another page, `· Speaker Registration Period` / `- 1st : Jul. 1 (Wed) – Aug. 31 (Mon), 2026` / `- 2nd : Sep. 1 (Tue) – Sep. 30 (Wed), 2026`, and a journal block
`Submission Timeline` / `Submission Round 1\t\t15 January`. Black Hat uses labelled lines (`Call for Briefings Closes: 20 October 2026`, `Notification to Submitters: ...`).
The lines "Regular 20 June (26) to 19 October (26)" (a proposal period) and "Regular 20 July (26) to 19 December (26)" (a registration period) are identical in shape; ONLY the
heading separates them. That is the same mistake our database holds: its deadline for this event, 2026-12-19, is the registration end (HANDOFF 2026-10-01).

## 2. Units the reader recognises
| Unit | Looks like | Purpose comes from |
|---|---|---|
| TABLE ROW | `Tier<tab>date or range` | heading path + legend |
| LIST ITEM | `- 1st : Jul. 1 ... Aug. 31, 2026` or a bullet | heading path |
| LABELLED LINE | `Label: date` (`Closes:`, `Notification to Submitters:`) | the label words, then the heading |
| PROSE | a sentence | existing sentence step (unchanged) |

## 3. Algorithm (deterministic first; no model needed for the three pages above)
1. INPUT: the page's raw text with its line structure (already saved in `crawl_pages.json`; the renderer also returns HTML if a page needs it).
2. LINES: split on line breaks; cells on tabs. A line with a date is a ROW candidate. A HEADING is a short line (at most 7 words), no date, not ending in a full stop, on its
   own line and followed by a blank line or by rows. Keep the two nearest preceding headings as the heading path, plus any LEGEND sentence between the heading and its
   first row ("The dates below indicate the opening of both ...").
3. DATES: the existing extractor (`extract_dates`) per row: range END is the closing date, "(26)" is the year 2026, a range shares the year written at its end, ordinals read.
   A year is never invented: no year in the row, the legend or the heading path, then the page's edition year from the URL, else the row is `needs-year` and not accepted.
4. PURPOSE by rule, heading path first, then label, then legend. Classes as in the answer key: SUB, OPEN, NOTIF, EVENT, REG, NOT_CFP, plus UNKNOWN.
   Words under SUB: proposal(s), abstract, submission, call for, paper, nomination, entry, application, deadline, speaker registration (a speaker application, not attendee
   registration: decided by the page's own wording, see risks). Under REG: registration, register, attend, ticket, early-bird. A heading beats a row label ("Late" under
   "Registration Periods" is REG). Conflicting or empty evidence is UNKNOWN: never guessed.
5. OPTIONAL MODEL STEP (later phase, only for UNKNOWN units): the model is given the unit with its heading path and asked to choose ONE label from the closed list. It
   cannot write text, and the unit was cut by code from the page, so it is verbatim by construction. A classification is easier to check than free generation.
6. TIERS: keep every round. A tier name (Early / Regular / Late, Round 1 ... 4) travels with its date. Selection of the round a person can act on today (R23) is a separate,
   labelled step: the first round whose end is on or after today. Recurring rounds with no year (journal: 15 January, 15 April ...) are reported as recurring and never dated.
7. EVIDENCE FORMAT: the heading line plus the row line, both verbatim from the page, with the URL and the edition year; confidence strong (explicit or "(26)" year) or medium
   (year taken from the heading or legend). Decision needed (section 8): the downstream gate expects a quote that contains the date as the page writes it; a two-line quote does.

## 4. How it fits with the sentence step
Run the reader first; its units are removed from the page text; the remaining prose goes to the existing sentence step with its gates unchanged. Union the results,
de-duplicate by (date, call), keep each item's source (unit or sentence).

## 5. Second use, probably the more valuable: a PURPOSE AUDIT of stored deadlines
The Climate Change row shows a stored date can sit on its evidence page as a REGISTRATION date and still read `verified`. The same reader answers a question the current
checks cannot: for each stored deadline, find the unit carrying that date on its evidence or submission page and report its purpose. Outcomes: CONFIRMED (a SUB unit has the
date), MISMATCH (the date appears only in REG / EVENT / OPEN / NOTIF units), ABSENT (not on the page), ALTERNATIVE (SUB units exist with other dates, including the round a person
can act on now). Scale: 48 stored deadlines in the two customer markets, of which 13 are `verified` only through the call-status layer and 5 more have no evidence page. Page
loads only; no model; output is an advisory list for a person, with no database writes.

## 6. Test plan
Phase 1 (deterministic, free): the 15 labelled pages (answer key locked, sha256 in `experiments/sentence_picking/labels.sha256`). Criteria, fixed in advance: at least 7 of the
8 missed labels recovered; no regression on the 16 already recovered; zero REG / OPEN / NOTIF / EVENT / NOT_CFP dates accepted as SUB; no year invented (the journal rounds come
out as recurring); every accepted unit verbatim on the page.
Phase 1b, because those 15 pages are the ones the rules would be shaped around: a HOLDOUT of about 10 pages from sites not yet read, selected from the inventory's call and
dates pages, labelled by me and locked with a checksum BEFORE the reader runs. A result that holds on the holdout is evidence; one that holds only on the labelled 15 is not.
Phase 2 (free): the purpose audit over the 48 stored deadlines.
Phase 3 (later, own budget, not requested now): the closed-label model step for UNKNOWN units, at most 40 requests and 0.25 USD, to be agreed first.

## 7. Risks and guardrails
Pages whose text arrives without line breaks (script-built tables) fall back to the sentence step. Multi-column tables read across rows. A heading like "Important Dates" or
"Schedule" could be a call or the event: UNKNOWN, not guessed. "Registration" is ambiguous (a speaker registration is a submission; an attendee registration is not): the unit's
own wording decides and doubt is UNKNOWN. English pages only (prefer-English is a separate, per-site decision). Public repo: no customer detail anywhere in these files. Nothing writes
to the database or the deliveries.

## 8. Decisions needed
1. Phase 1 plus the 10-page holdout (labelled and locked by me first), then Phase 2: go ahead?  2. R23 round selection: in this step, or downstream?  3. Two-line evidence quote
(heading plus row): acceptable to the downstream gate?  4. Run the purpose audit (Phase 2) before anything else, since it protects the customer-facing field directly?
