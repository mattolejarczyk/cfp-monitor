# Evidence Pipeline Discovery Gap

## Summary
The `internal_link_discovery.py` module exists and is fully tested (42 tests), but the evidence-builder that consumes local-browser ZIP uploads does NOT invoke it with `--use-discovery`. This means evidence packages built from local-browser recovery only try guessed paths like `/contact/`, `/cfp/`, `/call-for-papers/` — which 404 on sites like Gartner.

## Symptom
Evidence packages from local-browser recovery have:
- `source: "local_browser_upload"` in the case JSON
- `categories.*.paths_planned = []` (empty)
- No `links_discovered` key
- Only guessed paths were tried

Meanwhile, the local-browser runner DOES save full HTML (`local_html_chars` is populated — e.g. 274,449 chars for Gartner base pages). The HTML is never mined for internal links.

## Root Cause
Two gaps in the pipeline:

1. **Local-browser runner side** (`local_browser_runner.py`): Fetches URLs and saves HTML/text, but never calls `internal_link_discovery.discover_links()` on saved HTML to find additional internal URLs to crawl.

2. **VPS ingestion side**: The evidence-builder that reads `local_browser_fallback/uploads/<run_id>/` and constructs evidence packages does not invoke `multi_page_evidence.py --use-discovery` or `internal_link_discovery.py` against saved page text.

## Concrete Example — Gartner
- Base page: `https://www.gartner.com/en/conferences/emea/identity-access-management-uk`
- Local browser PASS for: base page, `/speakers/`
- Local browser PARTIAL (404) for: `/contact/`, `/about/`, `/team/`, `/cfp/`, `/call-for-papers/`, `/call-for-speakers/`, `/submit/`, `/abstracts/`, `/submission/`, `/submissions/`
- HTML saved: 274,449 chars (base), 216,372 chars (speakers)
- Discovery module never ran on this HTML

If discovery had run on the base page HTML, it might have found actual links to contact/CFP pages with different URL patterns (e.g. `/contact-us`, `/call-for-abstracts/speakers`). These would have been prioritized before the guessed paths that all 404'd.

## Fix Options

### Option A: Runner-side discovery (preferred)
Patch `local_browser_runner.py` to:
1. After fetching each base page, run `discover_links(base_url, html=html)` on the saved HTML
2. Add discovered URLs to the crawl queue
3. Include discovered URLs in the job manifest

Pros: Catches internal links before the crawl job is packaged
Cons: Requires `beautifulsoup4` or HTML parsing on the Windows runner

### Option B: VPS-side discovery
Patch the evidence-builder ingestion path to:
1. After receiving a local-browser ZIP, extract saved HTML files
2. Run `internal_link_discovery.py --base-url <url> --html-file <path>` against each saved HTML
3. Merge discovered URLs into the evidence package's candidate list

Pros: No changes needed on Windows runner
Cons: Requires HTML to be saved in the ZIP (currently only text excerpts are saved in the light bundle)

### Option C: Hybrid
Save raw HTML alongside text in the local-browser ZIP, then run discovery on VPS side during evidence package construction.

## Resolution (2026-06-24)

### Runner-side discovery — IMPLEMENTED
`local_browser_runner.py` now calls `discover_internal_links()` after each successful page fetch:

```python
# After fetching, discover internal links from saved HTML and enqueue
if _HAS_DISCOVERY and not args.no_discovery and row.get("local_status") in ("PASS", "PARTIAL"):
    base_url = item.get("url") or row.get("local_final_url", "")
    if base_url:
        new_links = discover_internal_links(html_dir, base_url, max_links=12)
        for link in new_links:
            if link not in discovered_queue and link not in [i.get("url") for i in manifest.get("urls", [])]:
                discovered_queue.append(link)
                manifest.setdefault("urls", []).append({...})
```

Key details:
- `discover_internal_links()` resolves `extraction_benchmarks/` path automatically when run from subdirectory
- HTML files smaller than 200 chars are skipped (trivial/empty pages)
- Discovered URLs dedupe against both queue and existing manifest
- `--no-discovery` flag allows Matt to disable if it causes issues
- Discovered URLs are processed after all manifest URLs complete
- Summary JSON includes `discovered_from_html` count
- Console prints `[DISCOVERY] Found N additional internal links from saved HTML`

### Tests
`local_browser_fallback/windows_runner_v0_1/test_discover_internal_links.py` — 7/7 pass:
- Returns empty when no html_dir / no base_url / no HTML files
- Returns empty when HTML < 200 chars
- Extracts links from saved HTML
- Filters junk (privacy, assets, external urls)
- Respects max_links cap
- Deduplicates

### What Matt needs to do
Re-zip the runner folder and re-download to Windows. The BAT calls `local_browser_runner.py`.

## Related Files
- `extraction_benchmarks/internal_link_discovery.py` — discovery module (complete)
- `extraction_benchmarks/multi_page_evidence.py` — has `--use-discovery` flag (complete)
- `extraction_benchmarks/PHASE1_INTERNAL_LINK_DISCOVERY.md` — implementation docs (complete)
- `local_browser_fallback/windows_runner_v0_1/local_browser_runner.py` — discovery wired in (complete as of 2026-06-24)
- `local_browser_fallback/windows_runner_v0_1/test_discover_internal_links.py` — 7 tests passing
