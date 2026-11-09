# Customer context in research and decisions: plan (drafted 2026-11-09)

Status: PLAN, nothing built. Matt asked for it on 2026-11-09 ("Yes, plan it here").

## Goal

Each week, the customer's own row from their sheet reaches two places:

1. The Friday (awards) and Saturday (conferences) research, as CONTEXT, NOT EVIDENCE: what the customer
   believes about the event, so the search checks it and says plainly where the event's own page differs.
2. Our downstream decisions: which rows are always researched, what the page says, and what the recap flags.

## What exists today (checked 2026-11-09)

- All four sheets are copied every week (11-08 09:43 this week) and pass the release gate's age check.
- The two CONFERENCE sheets are loaded into the database each week (Arnica 125 rows, Utility 84 rows seen on
  11-08). The two AWARDS sheets are read from the copies only (customer_awards.py), never loaded.
- The sheets already drive: coverage (every customer event is on the research list), edition links (D1, D2),
  and the "what the client has acted on" step of the Monday build (customer_context.py).
- GAP: nothing from the customer's row reaches the research prompt. run_market_audit.py reads a NOTES column
  from the input lists, but that is seed text from when each row was first added, not the live sheet.
- HAVE SOMETHING CLOSE: scripts/customer_row_answers.py (built 2026-10-08, ACT-54 c and d, QA-REGISTER A51, A52).
  It writes a proposed CUSTOMER_ROW column (name, link, place, start date only) and the page wording
  "Your sheet says X; we found Y". Never switched on: no column on the input lists, the prompt does not read
  it, the page builder does not print it, and the per-row answers are not in the Saturday recap.

## What the customers actually fill in (this week's copies)

| Field | Arnica conf (125) | Utility conf (84) | Arnica awards (87) | Utility awards (66) |
|---|---|---|---|---|
| Name, link | all | all | all | all |
| Place | 125 | 83 | 57 | 26 |
| Event start | 124 | 84 | 52 | 21 |
| Their deadline | 124 | 79 | 77 | 42 |
| Their submission link | 118 | 65 | 87 | 66 |
| Status | 22 | 35 | 2 | 20 |
| Status details | 9 | 18 | 11 | 37 |
| Notes | 45 | 7 | 59 | 53 |
| Priority | 123 | 69 | 38 | 0 |
| Coordinator contact | 118 | 73 | 74 | 30 |

Statuses in use on the conference sheets: Closed 17, Submitted 16, Info Needed 15, Accepted 5, a few others.

## Rules this plan keeps

- Contract section 3: STATUS, NOTES, PRIORITY, SUBMISSION DATE VERIFIED and SPEAKER & ABSTRACTS SUBMITTED are the
  customer's. We may READ them; we never write them, and the research must never return NOTES.
- 2.1 and 2.6: the customer's row is context, never evidence. A value on the page comes from the event's own page,
  never from the sheet. Where they differ, both are written in STATUS DETAILS.
- Personal data never goes to a model: COORDINATOR CONTACT is never sent, and email addresses and phone numbers
  are removed from any free text (Arnica keeps contact emails in some columns). LOGIN and PW are never copied
  (the snapshot job already drops them).
- No extra spend in November: the prompt grows by a few lines per row; no new grounded requests. Any change that
  researches MORE rows is report-only until Matt says otherwise.
- One change at a time: this week's Friday and Saturday runs prove the 11-09 evidence fixes alone.

## Steps (story points)

| # | Bucket | Step | Pts | Who |
|---|---|---|---|---|
| 1 | Web research | Decide the fields and the go-live date (D9, D10, D11 on Daily Review) | 1 | Matt |
| 2 | Web research | Context text for conference AND awards rows, from the database and the awards copies, personal data removed; tests | 3 | Claude |
| 3 | Web research | Weekly writer refreshes the CUSTOMER_ROW column on the three research lists after the intake (backup, read-back proof that nothing else changed) | 5 | Claude |
| 4 | Web research | Research prompt reads CUSTOMER_ROW as context, not evidence (a patch to run_market_audit.py the operator applies) | 3 | Claude, Matt applies |
| 5 | Web research | Codex reads the writer and the prompt patch against the contract (read-only, code only, no customer data) | 2 | Codex, Claude checks |
| 6 | QC data | Offline rehearsal: build every prompt, count rows carrying context, prove 0 emails or phone numbers, measure how much each prompt grows | 2 | Claude |
| 7 | QC data | The pages say "Your sheet says X; we found Y" where they differ | 3 | Claude |
| 8 | QC data | The one-line answer per customer row goes into the Saturday recap (A52 hooked in) | 2 | Claude |
| 9 | Optimization | Rows the client is working on (Info Needed, Submitted, Drafting, or their deadline within 30 days) are never skipped by the refresh plan: REPORT ONLY in November | 3 | Claude |
| 10 | Web research | Read the first live run: a CUSTOMER CONTEXT verdict line, disagreements found, no value copied from the sheet | 3 | Claude |
| 11 | Close | Contract amendment, QA-REGISTER A51 and A52, TOOLING, worklog; retro with estimates against actuals | 2 | Claude |

Total: 29 points. Steps 2 and 3, and 7 and 8, can run side by side; 4 needs 2; 6 needs 2 to 4; 10 needs D10.

## How each run proves itself (quality by design)

- The writer prints `CUSTOMER CONTEXT: n of m research rows carry the customer's row; k from awards sheets;
  p items of personal data removed; 0 left in any prompt` and exits DEGRADED when a sheet copy is missing or older than 2 days.
- Every refusal (a row it could not pair, a field it dropped) is written to a file named in the log line.
- The recap repeats the line; the Monday release gate shows it next to the sheet-age check.
- Test: good input survives untouched (the research lists keep every other column byte for byte).

## Decisions for Matt (to file on Daily Review)

- D9 Which of the customer's fields go into the research prompt?
  A. Event facts only: name, link, place, dates, their deadline and their submission link.
  B. Event facts plus their status details and notes, with contact details, emails and phone numbers removed.
  Recommend B: their notes and status details are where their feedback lives (Utility awards: 53 rows of notes,
  37 of status details). Risk: their working notes go to Google's model along with the event names it already sees.
- D10 When does it go live?
  A. Fri 11-20 (awards) and Sat 11-21 (conferences), after one quiet week proving the 11-09 fixes.
  B. This Friday and Saturday (11-13, 11-14).
  Recommend A: two changes in one run make a bad result impossible to pin on one of them.
- D11 Should rows the client is actively working on always be researched weekly?
  A. Report only in November; switch on in December.
  B. Switch on now.
  Recommend A. Cost: each extra researched row is about 0.12 USD (estimate from A59); the rehearsal counts how many
  rows it would add before anything is switched on.
