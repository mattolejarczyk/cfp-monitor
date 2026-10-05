# Process failure points by root cause - 2026-10-05

Every way the CFP process can produce missing, wrong or late data, described by its ROOT CAUSE and not by the web page where we happened to see it. A page is only evidence: the same cause will appear on the next site we discover and crawl. Grouped by the six macro steps on the status board, and inside each step ordered by how often the cause occurs and how much it hurts. Generated from `docs/operations/failure_points.json` by `scripts/failure_points_doc.py`; the QA register (`QA-REGISTER.md`) lists the checks, the runbook (`market-runbook.md`) lists the symptoms, this lists the causes.

**How to read it.** SCORE = frequency x impact, each 1 to 3. Frequency: 3 = seen on many rows or every week; 2 = seen several times; 1 = seen once or hypothetical. Impact: 3 = wrong or missing data can reach the customer, or a whole run is lost; 2 = row-level quality or real cost; 1 = internal friction. **Status:** OVERCOME = a control prevents or detects it automatically and it has been shown to work; MITIGATED = detected or partly prevented, a residual remains; WATCH = a control is built but not yet proven in a live run; PENDING = known, no working control yet. The scores are a judgment made from the evidence quoted under each item; correct any that you see differently.

## Scoreboard

| Macro step | Failure points | Overcome | Mitigated | Watch | Pending |
|---|---:|---:|---:|---:|---:|
| **A** Ask Gemini (research and upstream delivery) | 15 | 8 | 5 | 0 | 2 |
| **B** Find the right pages | 10 | 1 | 3 | 2 | 4 |
| **C** Read and label the date | 9 | 6 | 3 | 0 | 0 |
| **D** Check and clean stored data | 12 | 5 | 5 | 0 | 2 |
| **E** Spend less and run weekly | 9 | 3 | 4 | 2 | 0 |
| **F** Project control | 5 | 2 | 2 | 0 | 1 |
| **All** | 60 | 25 | 22 | 4 | 9 |

25 of 60 are overcome and 26 more are mitigated or being proven. Weighted by score, 127 of 293 points of risk are overcome.

## How far we have come

| Measure | Before | Now | Note |
|---|---|---|---|
| Research calls that were genuinely grounded searches | about one third (09-27); 24 stub rows | 130 of 130 rows, 0 stubs (10-03) | narrow-first prompt; the full prompt grounded 9 of 24 in the test |
| Two-digit-year dates read by the date reader (the '(26)' style) | 0 of 35 | 35 of 35 | false positives 5 -> 0 of 322 |
| Start-date conflicts (start date vs dates text vs input list) | 66 conflicts | 0 year failures; agreement on 49 Utility and 63 Cybersecurity rows | arbiter, overlay, year checks |
| Unasked fields (organizer blank; a venue in CITY) | 130 blank; 28 venues | 14 and 2 blank; 1 and 0 venues | narrow overlay carries last week's same-edition value |
| Verified evidence lost in a load | 3 future deadlines lost in the first live load | carried by rule and replayed; load QA flags any loss | 16 database and 19 file cells were restored from backup |
| Weekend load step | never ran on 10-03 (flattened step list), hang risk of hours | steps built whole and listed by a test; 5-hour limit | first fully automatic load Sat 10-10 |
| Recall of verified facts when a model reads the page | 62% | 75% to 81%, 0 wrong accepted | render fallback, other-language dates, heading year |
| Known deadlines found (14 events, live calls) | grounded call 8 of 14, 2 different dates | real-URL path 12 of 14, 0 different (experiment; shadow run from 10-10) | gold favours the grounded call; n = 14 |
| Customer agreement on dates | 17 of 33 readable rows (52%, all rows, 10-02) | 14 of 15 live rows (93%), other-edition rows shown aside (10-04) | different definitions: live rows, same edition |
| Facts a person has verified once and never re-asks | 0 | 15 events pinned, 51 facts in the answer key | pins ledger |
| Awards Complete % | 68% | 77% | closed and not-announced awards are not expected to carry a deadline |
| Awards weekly research calls | every award (about 123) | about 80 (35% skipped), from Fri 10-09 | rehearsed: identical result to a full run; unproven live |

## The highest remaining risks

Not yet overcome, highest score first (the order to attack them in):

1. **B1** [WATCH, score 9] The page that states the call is not found, or not selected. - *open:* Not in the weekly path yet; about 2.7 minutes per event; sub-summit pages are not selected; n = 14.
2. **D1** [MITIGATED, score 9] An event cannot be tied to one permanent id (no id returned, a rename, a second row for one event, ids we do not hold). - *open:* About 11 rows a week still cannot load fresh until upstream returns the stamped ids; our side now triages replies by command.
3. **F2** [MITIGATED, score 9] A claim is treated as fact before it is checked against the data (ours and upstream's). - *open:* It recurred several times this week. The control depends on discipline, not on code.
4. **A7** [MITIGATED, score 6] Research states a date or status for an edition that no page states (wrong year, next or previous edition). - *open:* No prompt rule yet. A plausible guess with no page can still reach a projected row; a flag is for a person to confirm, not proof it is wrong.
5. **B4** [MITIGATED, score 6] The page shows another edition, or two editions at once. - *open:* Pages with no year beside the date stay blank (safe, but a lost answer).
6. **B5** [WATCH, score 6] Several calls on one site (posters, awards, workshops, tracks) and the wrong one is read. - *open:* No tested event had competing rounds; the rule is inverted for awards and not yet built.
7. **A13** [PENDING, score 6] Sponsorship 'Yes' is accepted with a link but no quote, and sponsorship questions dominate the weekend's cost. - *open:* A quote requirement is a contract question for upstream; option B and a reader pass are not built.
8. **A2** [MITIGATED, score 6] Research cites pages it never opened, or composes URL paths that do not exist. - *open:* Composed URLs still arrive every week and the fix depends on upstream replacing them. The finder is not yet a fallback in the weekly path.
9. **B3** [PENDING, score 6] Links die between runs (moved pages, expired call pages, stale evidence pages). - *open:* Replacement depends on upstream; nothing proposes a replacement automatically.
10. **C3** [MITIGATED, score 6] Date formats and layouts the reader does not know (other languages, ordinals, ranges, dd.mm.yyyy). - *open:* No year beside the date; two date ranges on one page (training and conference); country from a state.
11. **D3** [PENDING, score 6] Non-deadline facts (city, venue, format, organizer, categories) are wrong or unproven and nothing measures them. - *open:* A weekly reader pass on these fields (priority 6) is proposed, not built.
12. **D7** [MITIGATED, score 6] The customer's own view disagrees with ours (another edition, an earlier round, withdrawn rows, events they track that we lack). - *open:* The coverage gap needs a decision (A14).

## A. Ask Gemini (research and upstream delivery)

15 failure points: 8 overcome, 5 mitigated, 0 to prove live, 2 pending.

### A1. Research answers from memory instead of searching (ungrounded answers).

Rank 1 of 15 in this step. **OVERCOME** (since 2026-10-03); score 9 (frequency 3 x impact 3)

- **Seen as:** About a third of calls were genuine grounded searches on 09-27, 24 stub rows; the full prompt grounded 9 of 24 in the test. Cause: prompt size and our own 120 s timeout, not quota.
- **What overcame or reduces it:** Narrow-first prompt (24 of 24 in the test; 130 of 130 rows grounded, 0 stubs on the first live Saturday); grounding trail and health file every run; 5-row canary before the window; circuit breaker.
- **What remains:** The narrow prompt has not yet run on awards (first scheduled run Fri 10-09). Rollback is one environment variable (CFP_PROMPT_MODE=full).

### A4. A blank answer replaces a verified one.

Rank 2 of 15 in this step. **OVERCOME** (since 2026-10-03); score 6 (frequency 2 x impact 3)

- **Seen as:** The first live load blanked verified evidence on 3 future deadlines (16 database cells and 19 file cells restored from backup).
- **What overcame or reduces it:** Evidence-carry rule (a blank quote never replaces verified evidence); load QA flags any lost deadline, evidence, quote or link; backups, invariants, watch-list; replay of the case confirms the fix.
- **What remains:** Hand-loaded rows that are not in the approved file get no carry the first Saturday (see D6).

### A5. Research overrides or contradicts a ruling a person made after reading the event's own page.

Rank 3 of 15 in this step. **OVERCOME** (since 2026-10-03); score 6 (frequency 2 x impact 3)

- **Seen as:** Research returned a different, evidenced deadline for rows corrected by hand (abstract vs paper deadline; an aggregator date; a wrong start date); 15 events are pinned.
- **What overcame or reduces it:** Pinned rows ledger applied before the gate on every load; blank pins clear the database; 'Verified by you' panel; answer key generated from the same ledger. [ACT-11, verified 2026-10-05]
- **What remains:** A pin holds one edition; the next edition is a new row. A ruling only protects once it is entered.

### A7. Research states a date or status for an edition that no page states (wrong year, next or previous edition).

Rank 4 of 15 in this step. **MITIGATED**; score 6 (frequency 2 x impact 3)

- **Seen as:** 2027 start dates inside 2026 editions; one case that looked like this and was not (the page did state the 2027 date); a page that shows next year's edition.
- **What overcame or reduces it:** Year checks Y1 to Y4 on every row of every load; load QA lists any start date the load introduced on a projected row with no evidence; trap cases; the reader accepts a date only if the quote states that year.
- **What remains:** No prompt rule yet. A plausible guess with no page can still reach a projected row; a flag is for a person to confirm, not proof it is wrong.

### A13. Sponsorship 'Yes' is accepted with a link but no quote, and sponsorship questions dominate the weekend's cost.

Rank 5 of 15 in this step. **PENDING**; score 6 (frequency 3 x impact 2) - closed only by upstream

- **Seen as:** About 90% Yes on both markets with 0 quotes; sponsorship passes are about 70% of a weekend.
- **What overcame or reduces it:** Sponsorship carry-forward (option A) is live.
- **What remains:** A quote requirement is a contract question for upstream; option B and a reader pass are not built.

### A2. Research cites pages it never opened, or composes URL paths that do not exist.

Rank 6 of 15 in this step. **MITIGATED**; score 6 (frequency 3 x impact 2) - closed only by upstream

- **Seen as:** 7 of 14 first-try gate failures were HTTP 404 on composed or stale URLs; the cited host was not among the search sources for 30 to 35% of rows; the canary reported '404' without having observed it; 15 new dead links and 62 backlog on the 10-04 sweep.
- **What overcame or reduces it:** Gate checks that the cited page exists; weekly verify confirms dead links in a real browser; hand-back list to upstream; the real-URL finder uses only addresses taken from a site's own sitemap and menu (12 of 14 right, 0 wrong in test; shadow run from 10-10).
- **What remains:** Composed URLs still arrive every week and the fix depends on upstream replacing them. The finder is not yet a fallback in the weekly path.

### A6. Fields the short research question does not ask come back blank or as stale text from the input list.

Rank 7 of 15 in this step. **OVERCOME** (since 2026-10-03); score 6 (frequency 3 x impact 2)

- **Seen as:** Organizer blank on all 130 rows; a venue in CITY on 28 rows; input-list dates on 66 rows.
- **What overcame or reduces it:** Narrow overlay keeps last week's same-edition value for unasked fields (organizer blank 130 -> 14 and 2; venue in CITY 28 -> 1 and 0); load QA tracks blank rates.
- **What remains:** Carried values are last week's, not re-verified (see D3 and D8).

### A8. A row yields nothing (a stub) because every search attempt failed.

Rank 8 of 15 in this step. **OVERCOME** (since 2026-10-03); score 6 (frequency 3 x impact 2)

- **Seen as:** 24 stubs on 09-27, 0 on the narrow-prompt Saturday; 10 stubs in the 10-02 awards file.
- **What overcame or reduces it:** Narrow prompt; circuit breaker after consecutive stubs; a stub keeps last week's accepted row ('kept-last-week').
- **What remains:** Awards stub rate under the narrow prompt is unmeasured until Fri 10-09.

### A10. Upstream's writer produces malformed files.

Rank 9 of 15 in this step. **MITIGATED**; score 4 (frequency 2 x impact 2) - closed only by upstream

- **Seen as:** Unquoted commas (47 fields, the Market column holding dates) repeatedly; four times in two days.
- **What overcame or reduces it:** repair_delivery.py; format checks in the gate; we read, they format.
- **What remains:** Upstream's writer is unfixed, so it recurs.

### A11. Statements about upstream's own files do not match what is on disk.

Rank 10 of 15 in this step. **OVERCOME** (since 2026-10-05); score 4 (frequency 2 x impact 2) - closed only by upstream

- **Seen as:** Three false 'it is in the file' claims, ids that do not exist here, input lists claimed stamped but not (10-02 to 10-04).
- **What overcame or reduces it:** check_delivery_ids.py (claims are checked on disk first); gate note S (ACCEPTED is not the same as researched); the upstream QA protocol. [ACT-16, verified 2026-10-05]
- **What remains:** None known.

### A12. Status and lifecycle claims without evidence (discontinued, merged, out of scope).

Rank 11 of 15 in this step. **MITIGATED**; score 4 (frequency 2 x impact 2) - closed only by upstream

- **Seen as:** Two rulings with no R16 evidence and ids we do not hold; an 'out of scope' ruling on six events the customer tracks, reversed.
- **What overcame or reduces it:** Gate R16 needs the event's own page and a verbatim quote; such rows are held and keep blank dates.
- **What remains:** Waiting on upstream's evidence for the open cases.

### A14. Events the customer tracks are not on our research list.

Rank 12 of 15 in this step. **PENDING**; score 4 (frequency 2 x impact 2)

- **Seen as:** 41 verified, dated customer events have no match of ours (29 Arnica, 12 Utility), mostly older or out of scope; the live ones are covered (coverage 100%).
- **What overcame or reduces it:** Coverage is measured from the database; the six reversed events were loaded.
- **What remains:** Needs a decision on which of the 41 are live and worth adding.

### A9. Quota exhaustion, timeouts and 504s stop the research window.

Rank 13 of 15 in this step. **OVERCOME**; score 3 (frequency 1 x impact 3)

- **Seen as:** Quota was exhausted once (2026-08-04); a 120 s ceiling made failures costlier without rescuing calls.
- **What overcame or reduces it:** Circuit breaker (exit 3 and 4), per-request timeout, rate limiter over every request, canary, retries.
- **What remains:** Quota is account-level and shared (see E9).

### A3. Quotes are paraphrased, not verbatim.

Rank 14 of 15 in this step. **OVERCOME** (since 2026-09-12); score 3 (frequency 3 x impact 1)

- **Seen as:** 5 of 14 first-try gate failures: the date is on the page, the wording is not.
- **What overcame or reduces it:** Mechanical repairs for wording-only mistakes (contract v2.4, never changes a claim); gate quote check; the reader must return a literal sentence that code finds on the page.
- **What remains:** A paraphrase on a page that has since changed still ends as unproven.

### A15. Renamed, closed and successor events are not handled deliberately.

Rank 15 of 15 in this step. **MITIGATED**; score 2 (frequency 1 x impact 2)

- **Seen as:** Not tested; a probable duplicate pair is held with blank dates; trap case T06 needs a person to judge.
- **What overcame or reduces it:** Identity rules (never mint an id, never join on upstream ids) prevent the worst outcome. [ACT-19, verified 2026-10-05]
- **What remains:** The cases a person must judge are listed; no data-driven test of a live rename.

## B. Find the right pages

10 failure points: 1 overcome, 3 mitigated, 2 to prove live, 4 pending.

### B1. The page that states the call is not found, or not selected.

Rank 1 of 10 in this step. **WATCH**; score 9 (frequency 3 x impact 3)

- **Seen as:** FIND failed 7 rows in the first live load; the sitemap plus menu method reached a call page at 31 of 84 sites; the finder selected a page that states the known deadline for 13 of 14 events.
- **What overcame or reduces it:** Real-URL finder (sitemap, menu, home page, frozen page rules, main-call rule): 12 of 14 right, 0 wrong, versus 8 of 14 for the grounded call on the same events; shadow run every Saturday from 10-10.
- **What remains:** Not in the weekly path yet; about 2.7 minutes per event; sub-summit pages are not selected; n = 14.

### B4. The page shows another edition, or two editions at once.

Rank 2 of 10 in this step. **MITIGATED** (since 2026-10-03); score 6 (frequency 2 x impact 3)

- **Seen as:** A page showing next year's edition; a page with both editions; a header date with no year beside it.
- **What overcame or reduces it:** Year-specific reading; nearest-heading year rule checked in code; trap cases T01 and T02; the reader stays blank rather than guess. [ACT-15, verified 2026-10-05]
- **What remains:** Pages with no year beside the date stay blank (safe, but a lost answer).

### B5. Several calls on one site (posters, awards, workshops, tracks) and the wrong one is read.

Rank 3 of 10 in this step. **WATCH** (since 2026-10-04); score 6 (frequency 2 x impact 3)

- **Seen as:** 3 of 14 events returned a real date for a different call.
- **What overcame or reduces it:** Main-call rule: set aside other calls, prefer the page named for the call, earliest open date. 0 wrong in 14.
- **What remains:** No tested event had competing rounds; the rule is inverted for awards and not yet built.

### B2. The page cannot be read by a plain fetch (HTTP 403 wall, anti-bot, script-built content).

Rank 4 of 10 in this step. **OVERCOME** (since 2026-10-05); score 6 (frequency 3 x impact 2)

- **Seen as:** Rows that read 'unconfirmed' because of a 403; a script-built page returning no text; a walled page failing the quote check.
- **What overcame or reduces it:** Real-Chrome render fallback in the reader; the gate reports a walled page as a note, not a failure; offline page library (350 of 360 pages usable); hard anti-bot hosts skipped by design. [ACT-12, verified 2026-10-05]
- **What remains:** Hard anti-bot hosts are skipped by design.

### B3. Links die between runs (moved pages, expired call pages, stale evidence pages).

Rank 5 of 10 in this step. **PENDING**; score 6 (frequency 3 x impact 2) - closed only by upstream

- **Seen as:** 15 new dead links and 62 backlog on 10-04; 10 of the 15 are evidence pages for editions that have passed.
- **What overcame or reduces it:** Weekly verify confirms each dead link in a real browser and lists it; hand-back to upstream.
- **What remains:** Replacement depends on upstream; nothing proposes a replacement automatically.

### B10. New events and next editions are not discovered.

Rank 6 of 10 in this step. **PENDING**; score 4 (frequency 2 x impact 2)

- **Seen as:** Only the monthly sweep discovers events and it is disabled for prospect markets; the Sunday discovery looked at 6 rows and applied 1.
- **What overcame or reduces it:** Sunday discovery for known rows.
- **What remains:** Ideas not built: a countdown timer signals the next edition; sitemap dates.

### B6. A third-party or aggregator page is cited in place of the organizer's.

Rank 7 of 10 in this step. **MITIGATED**; score 4 (frequency 2 x impact 2) - closed only by upstream

- **Seen as:** An aggregator that does not list the event cited as evidence (trap case T05, a known gap).
- **What overcame or reduces it:** A pin handled the one known case. [ACT-14, verified 2026-10-05]
- **What remains:** Detected and flagged; the replacement page still has to come from upstream.

### B7. The date is only on the home page, or on a sub-event page inside a larger site.

Rank 8 of 10 in this step. **MITIGATED** (since 2026-10-04); score 4 (frequency 2 x impact 2)

- **Seen as:** Home-page-only dates on two sites; a sub-summit inside a larger event site not selected.
- **What overcame or reduces it:** The home page is always read as one extra page.
- **What remains:** Sub-event pages inside a larger site are not selected.

### B9. A page changes or vanishes after we read it, and the weekly path keeps no versioned snapshot.

Rank 9 of 10 in this step. **PENDING**; score 4 (frequency 2 x impact 2)

- **Seen as:** An offline library of 360 pages was fetched once (10-01); the refresh-by-lifecycle policy was designed and not built.
- **What overcame or reduces it:** Weekly verify re-reads cited pages.
- **What remains:** Refresh scheduler for conferences (priority 9).

### B8. Sites with no usable links or menus.

Rank 10 of 10 in this step. **PENDING**; score 2 (frequency 2 x impact 1)

- **Seen as:** Six of 84 sites (4 alias sites, 2 script-built menus).
- **What overcame or reduces it:** None specific.
- **What remains:** Not addressed.

## C. Read and label the date

9 failure points: 6 overcome, 3 mitigated, 0 to prove live, 0 pending.

### C1. The wrong kind of date is taken as the submission deadline (registration, early-bird, event, notification, ceremony).

Rank 1 of 9 in this step. **OVERCOME** (since 2026-10-04); score 9 (frequency 3 x impact 3)

- **Seen as:** Fixed rules failed on a fresh test (precision 0.33); the whole-page reader had precision 0.85 and one ceremony date taken as a deadline.
- **What overcame or reduces it:** The model picks, code proves (verbatim quote, year-specific, call wording); 0 wrong in 73 reads, and 0 in about 95 answers earlier.
- **What remains:** Samples are small; one reader.

### C2. The year or edition is misread (two-digit year styles, a year taken from elsewhere on the page).

Rank 2 of 9 in this step. **OVERCOME** (since 2026-10-02); score 9 (frequency 3 x impact 3)

- **Seen as:** The '(26)' style was read 0 of 35 times, false positives 5 of 322.
- **What overcame or reduces it:** Whole-date matching: 35 of 35 on 350 saved pages, 0 of 322 false positives; year checks in the load.
- **What remains:** Other unusual year styles, if any, would appear as blanks.

### C5. Several rounds or tracks (early, regular, late; abstract versus paper) and the wrong one is shipped.

Rank 3 of 9 in this step. **OVERCOME** (since 2026-10-05); score 6 (frequency 2 x impact 3)

- **Seen as:** Abstract vs paper deadlines; a registration end read as a proposal deadline.
- **What overcame or reduces it:** Earliest open round by default; the main-call rule; pins for rulings. [ACT-13, verified 2026-10-05]
- **What remains:** None known.

### C6. A 'verified' label means the call status was confirmed, not the date.

Rank 4 of 9 in this step. **OVERCOME** (since 2026-10-05); score 6 (frequency 2 x impact 3)

- **Seen as:** 13 of 48 stored deadlines were 'verified' from the status layer; 5 more had no evidence page.
- **What overcame or reduces it:** CORRECTION 2026-10-05: this register said all board figures counted proof from quoted evidence, never from the label. That was wrong: the provable-deadline figure and Accurate % counted a status-only 'verified' as proof (34 of 101 verified conference rows; 1 of the 16 live market-list deadlines moved from proven to status-only when this was fixed). Now each verification records its BASIS (date, status, link, none-found; column verify_basis, migration applied live 10-05 with proofs) and the board counts the date basis only; status-only rows are shown separately. [ACT-18, verified 2026-10-05] Operator decision 2026-10-05 (ACT-48): the customer export's CONFIDENCE column now reads 'Call confirmed, date not confirmed on page' for a status-only verification the evidence layer did not independently read (15 rows today); a status-only row whose date the evidence layer found on the page stays Confirmed (8 of the 34), and the board counts it as proven by that second route.
- **What remains:** The weekly HTML pages take their badge from the evidence layer (already worst-first), so they needed no change; nothing else open.

### C3. Date formats and layouts the reader does not know (other languages, ordinals, ranges, dd.mm.yyyy).

Rank 5 of 9 in this step. **MITIGATED** (since 2026-10-03); score 6 (frequency 3 x impact 2)

- **Seen as:** Recall on verified facts was 62%; after the limiters 75% to 81%, 0 wrong.
- **What overcame or reduces it:** Other-language month names, numeric formats, ordinals, range expansion, browser render, heading-year rule.
- **What remains:** No year beside the date; two date ranges on one page (training and conference); country from a state.

### C4. Start date disagrees with the dates text or the input list.

Rank 6 of 9 in this step. **OVERCOME** (since 2026-10-03); score 6 (frequency 3 x impact 2)

- **Seen as:** 66 start-date conflicts; where a page proved anything it proved the research date (5 of 5) and never the input text.
- **What overcame or reduces it:** Start-date arbiter, overlay restore of the dates text, year checks; now 0 year failures and agreement on 49 Utility and 63 Cybersecurity rows.
- **What remains:** None known.

### C8. Text fields are misread (a venue as the city, a country inferred, a format guessed).

Rank 7 of 9 in this step. **MITIGATED** (since 2026-10-02); score 4 (frequency 2 x impact 2)

- **Seen as:** A hotel name stored as a city; 'Park City' read as a venue and stored 'UT'; a country inferred that was not in the quote.
- **What overcame or reduces it:** A value must appear inside its own quote; venue words are flagged by load QA; city cleaning fixed.
- **What remains:** No measure of accuracy per field (see D3).

### C9. Look-alike numbers and time zones ('October 2' matched in 'October 12'; a deadline in another zone).

Rank 8 of 9 in this step. **OVERCOME** (since 2026-10-03); score 3 (frequency 1 x impact 3)

- **Seen as:** Trap cases T11 and T12.
- **What overcame or reduces it:** Whole-date matching; both cases pass.
- **What remains:** None known.

### C7. The same page gives different answers on different runs (reader variance).

Rank 9 of 9 in this step. **MITIGATED**; score 2 (frequency 2 x impact 1)

- **Seen as:** A reader found 7, 10 and 9 of 16 facts on identical input; one event passed and then returned blank.
- **What overcame or reduces it:** Blank is the safe failure; repeated runs; the older model recovers more.
- **What remains:** Two-model agreement is proposed and not run.

## D. Check and clean stored data

12 failure points: 5 overcome, 5 mitigated, 0 to prove live, 2 pending.

### D1. An event cannot be tied to one permanent id (no id returned, a rename, a second row for one event, ids we do not hold).

Rank 1 of 12 in this step. **MITIGATED** (since 2026-09-27); score 9 (frequency 3 x impact 3) - closed only by upstream

- **Seen as:** The largest failure step: 11 rows (3 Cybersecurity, 8 Utility) in the first live load; duplicates and renames in the first weeks.
- **What overcame or reduces it:** Ids are stamped on the input and carried through; identity.to_canonical (never join on upstream ids); we never mint an id; a row with no id is held, never guessed. [ACT-16, verified 2026-10-05]
- **What remains:** About 11 rows a week still cannot load fresh until upstream returns the stamped ids; our side now triages replies by command.

### D2. Silent loss or regression during a load.

Rank 2 of 12 in this step. **OVERCOME** (since 2026-10-03); score 6 (frequency 2 x impact 3)

- **Seen as:** Four rows deleted silently (08-08); rows missing after a multi-market import; evidence lost in the first live load (10-03).
- **What overcame or reduces it:** Backup before every load, invariant checks with automatic rollback, load QA, watch-list, second-process read-back.
- **What remains:** None known.

### D3. Non-deadline facts (city, venue, format, organizer, categories) are wrong or unproven and nothing measures them.

Rank 3 of 12 in this step. **PENDING**; score 6 (frequency 3 x impact 2)

- **Seen as:** 3 of 7 upstream events carried a wrong city, venue or date; 47 of 85 candidate facts could not be proven from the pages.
- **What overcame or reduces it:** Overlay, venue-in-city flag, answer-key candidates from the reader.
- **What remains:** A weekly reader pass on these fields (priority 6) is proposed, not built.

### D7. The customer's own view disagrees with ours (another edition, an earlier round, withdrawn rows, events they track that we lack).

Rank 4 of 12 in this step. **MITIGATED** (since 2026-10-03); score 6 (frequency 3 x impact 2)

- **Seen as:** Agreement 14 of 15 live rows; 3 other-edition rows and 1 far-future blank shown, not scored; 41 tracked events without a match.
- **What overcame or reduces it:** Customer intake read before research; withdrawn rows excluded; other-edition class; customer agreement used as accuracy evidence.
- **What remains:** The coverage gap needs a decision (A14).

### D10. A passed deadline shipped with STATUS Open.

Rank 5 of 12 in this step. **MITIGATED**; score 4 (frequency 2 x impact 2) - closed only by upstream

- **Seen as:** 8 awards held back on the 10-02 file.
- **What overcame or reduces it:** The gate holds such rows and the row rule keeps last week's version. [ACT-02, verified 2026-10-05]
- **What remains:** Closed once upstream's corrected patch is loaded; watch for the next passed-deadline-Open row.

### D4. The same event appears as two rows.

Rank 6 of 12 in this step. **PENDING**; score 4 (frequency 2 x impact 2) - closed only by upstream

- **Seen as:** A duplicate of one event under a 2026 key; two names for one summit with the same URL and date; a German OWASP duplicate.
- **What overcame or reduces it:** Duplicate rule R15; rows are held rather than merged without evidence.
- **What remains:** Upstream must retire the duplicates with evidence.

### D6. Data enters outside the process (hand edits, rows loaded by hand) and breaks signing or carry.

Rank 7 of 12 in this step. **OVERCOME** (since 2026-10-05); score 4 (frequency 2 x impact 2)

- **Seen as:** A hand edit broke Monday's publish; hand-loaded rows had no carry and lost evidence.
- **What overcame or reduces it:** Re-gate and re-promote procedure; pins; the publish guard. [ACT-10, verified 2026-10-05]
- **What remains:** None known.

### D8. A carried value outlives its truth (carry rules keep last week's organizer, evidence, sponsorship).

Rank 8 of 12 in this step. **MITIGATED** (since 2026-10-03); score 4 (frequency 2 x impact 2)

- **Seen as:** A new risk created by the carry rules; no case yet.
- **What overcame or reduces it:** Same-edition only; load QA; verified evidence carried only for the same or a future deadline. [ACT-17, verified 2026-10-05]
- **What remains:** Flagged when older than the limit; nobody re-verifies it automatically.

### D11. Accidental whole-database operations.

Rank 9 of 12 in this step. **OVERCOME** (since 2026-10-03); score 3 (frequency 1 x impact 3)

- **Seen as:** A re-verify without a market scope changed 13 rows' verification state.
- **What overcame or reduces it:** The unrestricted form is refused; changes are rehearsed on a copy first.
- **What remains:** None known.

### D12. Customer pages built from an edited, stale or unsigned file.

Rank 10 of 12 in this step. **OVERCOME** (since 2026-09); score 3 (frequency 1 x impact 3)

- **Seen as:** A hand edit made Monday's page refuse to publish (hash mismatch).
- **What overcame or reduces it:** Publish guard: the approved file must be signed, accepted, unchanged and fresh; the recap says will or will not publish.
- **What remains:** None known.

### D5. Canonical keys move (a city or venue in the key, a key built from the name).

Rank 11 of 12 in this step. **OVERCOME** (since 2026-08-08); score 3 (frequency 1 x impact 3)

- **Seen as:** A tidy-up rewrote 26 cities and 24 keys with every test passing; a venue or postcode in a key.
- **What overcame or reduces it:** key_year frozen from the edition, keys from the city never the venue, golden-master diff read before blessing, invariants.
- **What remains:** None known.

### D9. Rows whose deadline has passed look unproven for ever.

Rank 12 of 12 in this step. **MITIGATED** (since 2026-10-02); score 3 (frequency 3 x impact 1)

- **Seen as:** Of 39 stored deadlines 9 were proven; 16 absent and 12 unreadable were mostly passed deadlines.
- **What overcame or reduces it:** All proof figures are scored on live deadlines only.
- **What remains:** The old rows have not been reviewed.

## E. Spend less and run weekly

9 failure points: 3 overcome, 4 mitigated, 2 to prove live, 0 pending.

### E3. Money and time are spent asking questions whose answer cannot have changed.

Rank 1 of 9 in this step. **WATCH** (since 2026-10-04); score 6 (frequency 3 x impact 2)

- **Seen as:** Searches are 73% of cost; sponsorship passes about 70% of a weekend; 11 of 93 calls went on ended events (08-11); 76 of 129 awards are Closed.
- **What overcame or reduces it:** Awards refresh plan (35% skipped, about $2.60 a week, rehearsed: identical result); sponsorship carry; customer intake before research.
- **What remains:** The awards plan is unproven live; the conference refresh scheduler is not built (priority 9).

### E4. A new automated step fails in its first live runs.

Rank 2 of 9 in this step. **WATCH**; score 6 (frequency 3 x impact 2)

- **Seen as:** The narrow prompt, the load step and evidence handling all showed defects in their first live run.
- **What overcame or reduces it:** Sandbox rehearsal with the production checks, the canary, the list-steps test.
- **What remains:** First live runs ahead: awards Fri 10-09 (narrow prompt, refresh plan, load_awards) and Sat 10-10 (load, per-step trend, shadow run).

### E7. Throwaway code duplicates or contradicts existing tooling (a wrong join, a false count).

Rank 3 of 9 in this step. **MITIGATED** (since 2026-09-20); score 4 (frequency 2 x impact 2)

- **Seen as:** A throwaway comparison reported all 112 rows missing by joining on the upstream id; about 20 throwaways in one day.
- **What overcame or reduces it:** Announce 'USING EXISTING' or 'NEW CODE' before any code; the tooling index; reuse of the existing scripts.
- **What remains:** Relies on discipline.

### E1. The weekend job does not load, silently.

Rank 4 of 9 in this step. **OVERCOME** (since 2026-10-05); score 3 (frequency 1 x impact 3)

- **Seen as:** On 10-03 the load step never ran: a step list flattened into one array and Python started with single characters.
- **What overcame or reduces it:** Steps built whole by one function; empty input to Python; a missing-script guard; a test that runs the real step builder (-ListPostSteps) and checks every step; Saturday's task limit 5 hours.
- **What remains:** The first fully automatic load is Sat 10-10.

### E2. A stray prompt or hang holds the window for hours.

Rank 5 of 9 in this step. **OVERCOME** (since 2026-10-03); score 3 (frequency 1 x impact 3)

- **Seen as:** The 10-03 hang.
- **What overcame or reduces it:** Empty stdin, 5-hour task limit (was 10), hang procedure in the runbook.
- **What remains:** None known.

### E9. Two jobs touch the same database or quota at once.

Rank 6 of 9 in this step. **MITIGATED**; score 3 (frequency 1 x impact 3)

- **Seen as:** Quota is account-level; two audits against one database must never overlap.
- **What overcame or reduces it:** Procedure: check the scheduled tasks before running anything by hand.
- **What remains:** No lock enforces it.

### E5. Tool and environment traps (sandboxed copies of folders, PowerShell quoting, a locked database, a UI running the live build).

Rank 7 of 9 in this step. **MITIGATED**; score 2 (frequency 2 x impact 1)

- **Seen as:** Documented in the runbook's failure-mode table.
- **What overcame or reduces it:** Absolute paths, verify from the far side of a process boundary, the failure-mode table.
- **What remains:** Relies on discipline.

### E6. Process documentation drifts from the scripts.

Rank 8 of 9 in this step. **OVERCOME** (since 2026-10-03); score 2 (frequency 2 x impact 1)

- **Seen as:** Documents were told to be read and gave old truth.
- **What overcame or reduces it:** A fingerprint guard (22 scripts) says when the weekend process document is out of date; the tooling index; the QA register.
- **What remains:** None known.

### E8. A recap says something that did not happen.

Rank 9 of 9 in this step. **MITIGATED** (since 2026-10-03); score 1 (frequency 1 x impact 1)

- **Seen as:** 'Loaded automatically' after a by-hand load.
- **What overcame or reduces it:** Dry-run and read a recap before sending by hand.
- **What remains:** Manual step.

## F. Project control

5 failure points: 2 overcome, 2 mitigated, 0 to prove live, 1 pending.

### F2. A claim is treated as fact before it is checked against the data (ours and upstream's).

Rank 1 of 5 in this step. **MITIGATED**; score 9 (frequency 3 x impact 3)

- **Seen as:** A defect report blamed upstream wrongly (08-08); a date cleared wrongly after a summary was taken for a read of the page (10-03); this week an estimate of 45 seconds per event, a reason for a low awards score and the urgency of 15 dead links were each stated and later corrected. The register itself carried a wrong claim (C6: board figures never used the label), found by the builder's review on 10-05.
- **What overcame or reduces it:** Verify against the data before it leaves the building; claims about files are checked on disk; rehearsal on copies; a pin only when the operator said so; corrections written down.
- **What remains:** It recurred several times this week. The control depends on discipline, not on code.

### F1. A reported number is wrong, hard-coded or badly defined.

Rank 2 of 5 in this step. **OVERCOME** (since 2026-10-03); score 6 (frequency 3 x impact 2)

- **Seen as:** A 28% provable figure counted 44 of 48 deadlines that had passed; 40 rows counted customer-withdrawn rows; a weighted index counted the same check twice; counts hard-coded in strings.
- **What overcame or reduces it:** Board figures derived from the database with written definitions, live rows only; Complete % and Accurate % replace the weighted index; tests.
- **What remains:** Several measures rest on small samples (see F4).

### F3. The same fact is verified by a person more than once.

Rank 3 of 5 in this step. **OVERCOME** (since 2026-10-03); score 6 (frequency 3 x impact 2)

- **Seen as:** Several events were manually re-verified across days.
- **What overcame or reduces it:** A fact you verify is pinned, applied the same day, added to the answer key and shown on the board; you are not asked again.
- **What remains:** A pin holds one edition; the share of events needing a manual check per month is not yet measured.

### F4. Ground truth is thin, so improvements cannot be scored with confidence.

Rank 4 of 5 in this step. **PENDING**; score 6 (frequency 3 x impact 2)

- **Seen as:** The answer key holds 51 facts for 15 of the 40 benchmark events; the finder comparison is 14 events and its gold favours the grounded call; awards have no answer key.
- **What overcame or reduces it:** Answer-key candidates from the reader (85 facts, 0 disagreements); trap cases (14); the shadow run adds evidence each Saturday.
- **What remains:** The answer-key decision and an awards key (priorities 7 and 8).

### F5. Knowledge is lost between sessions.

Rank 5 of 5 in this step. **MITIGATED**; score 4 (frequency 2 x impact 2)

- **Seen as:** Context is lost between conversations.
- **What overcame or reduces it:** HANDOFF, worklog, QA register, runbook, board, long-term memory notes.
- **What remains:** Relies on keeping them current.

## Failure points only upstream can close

We can detect these and hold the row; the fix is in upstream's research or writer:

- **D1** [MITIGATED] An event cannot be tied to one permanent id (no id returned, a rename, a second row for one event, ids we do not hold). - About 11 rows a week still cannot load fresh until upstream returns the stamped ids; our side now triages replies by command.
- **A13** [PENDING] Sponsorship 'Yes' is accepted with a link but no quote, and sponsorship questions dominate the weekend's cost. - A quote requirement is a contract question for upstream; option B and a reader pass are not built.
- **A2** [MITIGATED] Research cites pages it never opened, or composes URL paths that do not exist. - Composed URLs still arrive every week and the fix depends on upstream replacing them. The finder is not yet a fallback in the weekly path.
- **B3** [PENDING] Links die between runs (moved pages, expired call pages, stale evidence pages). - Replacement depends on upstream; nothing proposes a replacement automatically.
- **A10** [MITIGATED] Upstream's writer produces malformed files. - Upstream's writer is unfixed, so it recurs.
- **A12** [MITIGATED] Status and lifecycle claims without evidence (discontinued, merged, out of scope). - Waiting on upstream's evidence for the open cases.
- **B6** [MITIGATED] A third-party or aggregator page is cited in place of the organizer's. - Detected and flagged; the replacement page still has to come from upstream.
- **D10** [MITIGATED] A passed deadline shipped with STATUS Open. - Closed once upstream's corrected patch is loaded; watch for the next passed-deadline-Open row.
- **D4** [PENDING] The same event appears as two rows. - Upstream must retire the duplicates with evidence.

## Limits of this view

- Frequencies come from the evidence in the repository's documents and the last two weeks of runs; the process is young and several figures are single runs or small samples (14 events for the finder comparison).
- A status of OVERCOME means the control has worked where it was tested, not that the cause can never return on a new kind of page.
- The causes are the ones we have seen. The register grows when a new failure is found: add it to the data file with its evidence, then regenerate.
