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
