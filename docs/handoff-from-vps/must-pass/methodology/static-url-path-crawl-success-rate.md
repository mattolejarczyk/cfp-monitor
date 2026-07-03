# Static URL Path Crawl Success Rate Analysis

Session learning from `multi_page_step4_v2_crawl_quality_scheduled_20260622_141102` run (105 URLs via local Windows Playwright crawler, 2026-06-23).

## Why this exists

The multi-page evidence builder uses both "guessed" static URL extensions (appended to base URL) and "discovered" internal links (parsed from page HTML). Static guesses that consistently 404 waste crawl time and have zero evidentiary value. This analysis quantifies success rates per category/path to inform which static paths to keep vs disable.

## Success rate by category (local browser crawl)

### conference_event (base URL `/`)
- **100% PASS** (5/5 cases)
- All base URLs return meaningful content (2903-7950 text chars)

### contact_info (`/contact/`, `/about/`, `/team/`, etc.)
- **0% PASS, 100% PARTIAL** (40 URLs across 5 cases)
- Every contact-type static path returns either soft 404 or 404 page content
- Gartner: "We can't seem to find the page" (674 chars — soft 404)
- Black Hat: "ERROR 404 | PAGE NOT FOUND" (839 chars)
- Reuters Events: actually PASSES on /contact/, /about/, /team/ (6390 chars each) — outlier

### cfp_info (`/speakers/`, `/cfp/`, etc.)
- **15% PASS, 85% PARTIAL** (40 URLs)
- Only `/speakers/` path returns real content (3021-3409 chars on Gartner/Reuters)
- `/cfp/`, `/call-for-papers/`, `/call-for-speakers/`, `/submit/`, `/abstracts/` — all 404

### submission_url (`/submit/`, `/submission/`, etc.)
- **0% PASS, 100% PARTIAL** (20 URLs)
- All submission-type paths 404

## Key insight: the problem is the URL, not the crawler

The local browser runner reaches pages correctly and saves text. The issue is that guessed URL extensions simply do not exist on these sites:
- Gartner does not use `/contact/`, `/cfp/`, or `/call-for-papers/`
- Black Hat does not use `/contact/`, `/speakers/`, or `/cfp/`
- Only Reuters Events uses conventional subpage paths

## Disable pattern (2026-06-24)

Static paths with 0% success are disabled in `multi_page_evidence.py` `CATEGORY_PATHS`:

```python
CATEGORY_PATHS = {
    "conference_event": ["/"],           # KEEP — 100% success
    "contact_info": [],                   # DISABLED — 0% success
    "cfp_info": ["/speakers/", "/speakers"],  # KEEP only /speakers/ (15% success)
    "submission_url": [],                 # DISABLED — 0% success
}
```

Disabled paths are documented in a registry comment block above `CATEGORY_PATHS` with instructions for re-enabling. Internal link discovery is NOT affected by this disable — discovered URLs from page HTML still get crawled regardless of static path status.

## Impact

- Before disable: 105 URLs crawled per run
- After disable: ~25 URLs crawled (5 base + 5×2 speakers + discovered links)
- Discovered internal links (from HTML parsing) still run — unaffected

## Re-enable criteria

Re-enable a static path only when crawl evidence from 3+ sites shows the target sites actually serve real content at that path. Do not re-enable based on hope — require evidence.

## Future improvement: learn from discovered links

Over time, track which URL extensions appear in discovered internal links across crawl runs. Build a frequency map of successful URL patterns per domain. This data can inform which static paths to re-enable — replacing guesswork with evidence from actual site structures.

## Data source

All stats computed from `local_browser_fallback/uploads/multi_page_step4_v2_crawl_quality_scheduled_20260622_141102/` ZIP. Never compute static path success rates from `evidence_packages/` (VPS `requests.get()` 403s on session-dependent subpages — not representative of what the local browser can reach).
