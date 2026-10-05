# Operator-ruled edits to the live database (audit trail)

One entry per edit that was NOT made by a delivery import or the merge guard. Contract 2.4: nothing is overwritten silently.

## 2026-10-01 11:38 - Global Energy Show Canada 2027, submission link
- Event: `2027-global-energy-show-canada-calgary`. Field: `grounding_facts.submission_url` (one field, one row, guarded on the old value).
- Old: `https://www.globalenergyshow.com/speak/abstract-submission/` (returns 404).
- New: `https://www.dmgeventsconferences.com/global-energy-show-2027/submitter/login` (HTTP 200).
- Why: the operator confirmed on the live page that the "SUBMIT AN ABSTRACT" button after the deadline sentence links here; our browser read the same href on all three buttons; a Hermes browser read returned the same target. Upstream's re-emit had set the information page instead. The contract's mechanical repair (v2.4 class B) only carries a URL upstream sent, so this is an operator ruling, not a mechanical repair.
- Left alone on purpose: the old URL in `link_checks` (its 404 result) and in an old `evidence` row, which are history, not claims; the customer's own sheet fields.
- Backup before the edit: `%LOCALAPPDATA%\CFP-Monitor\cfp_monitor.pre-ges-link-20261001.db` (sha256 starts 5352ccd03045924a). After: sha256 starts 616a88a9f26c63ba; read back from a second process; `PRAGMA integrity_check` ok; `check_invariants.py --db` all hold.
- Lasting fix still needed from upstream: Saturday's load can bring the old link back unless their approved file carries the new one (see NOTE-TO-UPSTREAM-2.md, items 1 and 2).

## 2026-10-01 20:29 - approved market file, Global Energy Show submission link (one cell)
- File: `Markets/Utility_audited.final.csv` (the approved file Saturday 02:00 reads), row `2027-global-energy-show-canada-2027-calgary-speaking`, column `CFP_SUBMISSION_URL`. One cell; the operator approved it in chat.
- Old: `https://www.globalenergyshow.com/speak/abstract-submission/` (404). New: `https://www.dmgeventsconferences.com/global-energy-show-2027/submitter/login`.
- Why by hand: `Markets/apply_row_patch.py` protects `CFP_SUBMISSION_URL`, so the patch tool cannot make this change; upstream confirmed the same value and said it will carry it in its re-research delivery.
- Method: guarded on the old value; written with the patch tool's own settings (utf-8, QUOTE_ALL, CRLF); the script proved that exactly one cell differs from the backup before replacing the file. Backup: `Utility_audited.final.pre-cell-edit-20261001-202915.bak.csv`. Before the earlier patch sha256 started 1fc74033; after this edit 07a9c474. Read back from a second process: 54 rows, new link present, deadline, projected flag and citation intact.
- Context: the same link was set in our database on 2026-10-01 11:38 (entry above). Upstream acknowledged on 2026-10-01 that our local copies are the master for Saturday's run.

## 2026-10-03 - five Utility rows: start date vs conference dates (operator verified on the live pages)
- Files: `Markets/Utility_audited.csv` (Saturday 10-03 research output, read by weekend_import) and `Markets/Utility_input.csv` (the input list; the wrong text came from it). Script: `experiments/purpose_audit/operator_rulings_20261003.py`; backups `*.pre-rulings-<stamp>.bak.csv` beside each file; the script proved that only the listed cells changed.
- European CCUS 2027: start 2027-01-26 correct; dates text 'March 9 - 10' wrong -> 'January 26 - January 27, 2027' (event page https://ccus-carbon-capture.com/ reads '26 - 27 January 2027 | Amsterdam'; operator found no source for March 9-10).
- Carbon Capture USA 2026: start 2026-11-16 correct; text 'October 14 - 15' (last week's approved file and the input list) wrong -> 'November 16 - November 17, 2026' (Houston); CFP_SUBMISSION_URL -> https://www.usa.carbon-capture-conference.com/speakers (operator).
- Future Fuels MENA Summit 2026: operator cannot find the event; futurefuelsmena.com is a bad domain. START DATE and CONFERENCE DATES blanked (2.6), as last week's approved row had them.
- Sustainable Fuels Global Summit 2027: start 2027-04-13 correct; text 'February 16 - 17' wrong -> 'April 13 - April 14, 2027'. The site now redirects to safeusummit.com (SAF Europe Summit 2027, 13-14 April 2027, Rotterdam): same URL and date as our held row 2027-saf-europe-summit-rotterdam, so probably ONE event under two names (identity is upstream's to rule, 5.4).
- Carbon Capture Technology Expo MENA 2026: the site now shows the 2027 edition (8-9 June 2027, ADNEC Centre, Abu Dhabi; countdown timer). The 2026 edition's dates are not on the page: START DATE and CONFERENCE DATES blanked. The 2027 edition needs its own row (note 22). Likely cause of the research's 2026-06-09: the model read June 9 of the 2027 edition as 2026.

## 2026-10-03 - ODSC East 2027: the load re-introduced a cleared start date
- Saturday's narrow research returned START DATE 2027-05-10 and STATUS Upcoming for ODSC East 2027 (the model's guess; the input row has no date, and no page states a 2027 edition: upstream agreed on 10-02). The 07:49 load wrote both into the database and the approved file after we had cleared them.
- Fixed: database start_date NULL and status 'Needs Verification'; `Markets/Cybersecurity_audited.final.csv` START DATE blank and STATUS 'Needs Verification' (2 cells, backup `*.pre-odsc-<stamp>.bak.csv`; database backup `cfp_monitor.pre-odsc-fix-<stamp>.db`).
- Still open (design): the narrow prompt can return a guessed START_DATE for an unconfirmed edition. The year checks cannot catch it (the year is consistent). Check the next Saturday's report for a start date on a row whose edition has no page evidence.

## 2026-10-03 (later) - CORRECTION: ODSC East 2027 was a correct date; the entry above and the pin were wrong
- What I got wrong: I wrote that 'no page states a 2027 edition' and cleared START DATE 2027-05-10, set STATUS 'Needs Verification', and pinned the row blank as 'operator verified'. The operator had NOT verified it; the claim came from a page summary (WebFetch) that reported only the 2026 speaker block ('April 28-30, 2026') and missed the header.
- What the page says (read in a real browser 2026-10-03, https://odsc.ai/east/): 'MENINO CONVENTION AND EXHIBITION CENTER, BOSTON, MA | MAY 10-12TH, 2027 REGISTER YOUR INTEREST FOR 2027'. The research's 2027-05-10 was right. (Upstream's earlier 'May 10-13' is one day too long: the page says 10-12.)
- Fixed: database start_date 2027-05-10 and status Upcoming restored (backup cfp_monitor.pre-undo-odsc-*.db); approved Cybersecurity file START DATE and STATUS restored (backup *.pre-undo-odsc-*.bak.csv), re-gated 23 of 23 and re-promoted; the ODSC pin removed; the trap case T02 rewritten around the real page; the answer key regenerated.
- Why it happened and the rule: a summary of a page is not a read of the page. Evidence for a 'the page states nothing' ruling must come from the page's full text or a real browser read, and a pin is only 'operator verified' if the operator said so.
- Not pinned: ODSC East 2027 is a page read by Claude, not an operator verification. The operator may verify once (a pin follows); until then the research value stands.

## 2026-10-05 - nine input-list rows stamped with the ids upstream confirmed (answer to note 27)
- Upstream confirmed that nine input rows are events we already hold and named the id we hold for each; every id was checked in the live database and none was already carried by another input row. `EVENT_ID_CANON` stamped on those rows in `Markets/Cybersecurity_input.csv` (1) and `Markets/Utility_input.csv` (8); backups `*_input.pre-identity-<stamp>.bak.csv`. Script: `experiments/purpose_audit/identity_map_20261005.py`.
- Effect: Saturday's research loads these rows onto the held ids instead of holding them back as 'no permanent id'. These events were in the database but not on last week's approved page, so they will join the page after Saturday's load.
- Not stamped: 'OWASP Global AppSec Europe 2026' and 'OWASP German Chapter Conference (AppSec Karlsruhe 2026)' are second listings of events another input row already carries (duplicates); they need a DUP_OF decision.
- Not accepted from the same reply: the city changes for India Energy Week 2027 (Goa) and WHEC 2026 (Istanbul): the events' own pages state Kolkata (28-31 January 2027) and Singapore (22-26 June 2026). The two expo quotes are not on their pages; nine withdrawal rows and both expo rows carry ids that are not ours.


## 2026-10-05 (later) - one input row marked DUP_OF, one stamped (answer to note 28)
- Upstream confirmed two OWASP input rows are second listings (R15) and withdrew its two location claims (India Energy Week 2027 stays Kolkata, WHEC 2026 stays Singapore). `Markets/Cybersecurity_input.csv` gained a DUP_OF column: 'OWASP Global AppSec Europe 2026' is marked a duplicate of 2026-owasp-global-appsec-eu-vienna (another input row already carries that id). 'OWASP German Chapter Conference (AppSec Karlsruhe 2026)' is STAMPED with the survivor id 2026-german-owasp-day-karlsruhe instead, because no other input row carries it and marking it DUP_OF would stop the event being researched. Backup `Cybersecurity_input.pre-dupof-20261005-093004.bak.csv`; script `experiments/purpose_audit/dup_of_20261005.py` (an earlier version of this entry, written before the check had run, said both rows were marked DUP_OF: that was wrong and is replaced).
- Effect: 72 of 73 Cybersecurity rows are researched Saturday; every researched row now carries a permanent id (unresolved 11 -> 1, the DUP_OF row, which is skipped).
- Upstream's corrected sparse patch: 20 rows, all keyed on ids we hold. STATUS and link columns cannot travel in a sparse patch (apply_row_patch refuses them), so they arrive through the research. Not applied by hand: withdrawals of dead citations on past editions (ACT-46) and retiring the duplicate database rows for Hack In The Box, Indonesia CCS, German OWASP and India Energy Week (ACT-47).

## 2026-10-05 (evening) - Saturday job script: shadow reader step added (ACT-20)
- `Markets/run_monthly.ps1`: a Saturday-only step `shadow_reader.py --markets <live markets> --max-minutes 45` inserted between the recap and the finder shadow run. Read-only, never fails the run. Applied by inserting the patch block `docs/control/patches/ACT-20-run_monthly.ps1.patch` (the patch tool could not match the file's context). Backup `Markets/run_monthly.ps1.pre-shadowreader-20261005`.
- Proof: `-ListPostSteps` lists five Saturday steps, all found; test_run_monthly_steps and test_shadow_reader_hook pass; WEEKEND-PROCESS.md step 10b written and re-confirmed.
- NOT applied: the ACT-22 Friday awards shadow patch (`docs/control/patches/ACT-22-run_monthly.ps1.patch`), held until after Friday 2026-10-09's first scheduled awards run so that run stays clean.
