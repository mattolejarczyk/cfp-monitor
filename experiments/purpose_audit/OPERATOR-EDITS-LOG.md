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
