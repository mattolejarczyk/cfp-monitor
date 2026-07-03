# Evidence Existence Check Pattern

When a model returns N/A for contact/CFP fields, do not assume the data is genuinely absent from the site. Check these artifacts in order before concluding:

## Artifact Check Order

1. **`local_browser_fallback/uploads/<run_id>/<zip>_summary.json`**
   - Read `recovery_map` array
   - Each entry has: `url`, `name`, `original_vps_status`, `local_browser_status` (PASS/PARTIAL), `recovered` (bool), `fallback_method`
   - `local_browser_status: "PASS"` means real content was extracted
   - `local_browser_status: "PARTIAL"` with title "404 Page" means page was reached but no useful content

2. **`evidence_packages/<package_dir>/<case>.json`**
   - Check `categories.<cat>.paths_tried[]`
   - Each entry has: `candidate_url`, `status` (PASS/PARTIAL), `title`, `http_status`
   - `paths_planned = []` means discovery was NOT invoked — only guessed paths were tried

3. **`evidence_packages/<package_dir>/index.json`**
   - Shows `source_status_counts` (PASS vs PARTIAL totals)
   - Lists all package files

## Interpretation Matrix

| VPS status | Local browser status | Evidence exists? | Gold truth |
|---|---|---|---|
| PASS | PASS | Yes | Score against evidence |
| 404 | PASS | Yes (local only) | Score against local evidence |
| 404 | PARTIAL (404 title) | No | N/A — crawl failed |
| 404 | Not crawled | Unknown | N/A — flag as "not attempted" |

## Key Pitfall: `recovered_by_local` is misleading

The `recovered_by_local` counter in summary JSON only increments when a URL changed from BLOCKED to PASS. Many Gartner pages were already MULTI_PAGE_DISCOVERY on VPS (not BLOCKED), so the counter stays 0 even when local browser provided content. Always read `recovery_map` entries individually — do not rely on the aggregate counter.

## Gartner-specific pattern (2026-06-24)

For all 3 Gartner URLs:
- Base pages: PASS (conference basics extractable)
- /speakers pages: PASS (speaker names, but no contact/CFP data)
- /contact, /about, /team, /organizers, /committee: all PARTIAL with title "404 Page"
- /cfp, /call-for-papers, /call-for-speakers, /submit, /abstracts: all PARTIAL with title "404 Page"

Conclusion: Gartner does not expose contact or CFP data at public URLs accessible to either VPS or local browser. Gold truth for these fields should be N/A, but explicitly note this was a crawl coverage gap, not a model failure.
