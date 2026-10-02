# Proposed fix for verify.find_date (built and tested 2026-10-02, NOT applied)

Held out of the working tree on purpose: the operator deferred the "(26)" part until after Monday 2026-10-05, and `find_date` is imported by Saturday's scheduled job (verify_grounding via weekend_import).

What it does (src/cfp_monitor/verify.py):
1. A date is not that date if a digit is glued to either side. Fixes a false positive: a claim of 2 October 2026 was "found" on a page that only says "12 October 2026" (5 of 5 sampled real pages, e.g. Black Hat's call page).
2. Reads the two-digit-year style "19 October (26)" / "12 October 26": 0 of 35 matched on the saved pages before, 35 of 35 after.

Evidence: measured on the 350 saved library pages with `experiments/purpose_audit/find_date_recall_scan.py` (recall by style unchanged for the 4-digit styles; false positives 5 -> 0 of 322 checked), and `find_date_corpus.py` (Climate Change 2026-10-19 now verifies on its cited page). Full suite with the fix in the tree: 1,307 passed, 0 failed.

To apply, from the repo root:

    git apply experiments/purpose_audit/proposed_find_date/find_date_boundaries.patch
    copy experiments\purpose_audit\proposed_find_date\test_find_date_boundaries.py.txt tests\test_find_date_boundaries.py
    uv run --with pytest python -m pytest tests/test_find_date_boundaries.py tests/test_verify.py -q

then run the full suite and commit. To undo, `git checkout -- src/cfp_monitor/verify.py` and delete the new test file.
