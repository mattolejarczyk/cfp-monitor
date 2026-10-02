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
