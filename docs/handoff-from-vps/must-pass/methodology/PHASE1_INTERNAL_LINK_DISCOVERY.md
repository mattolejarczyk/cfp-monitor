# Phase 1 & 2 — Internal Link Discovery Module: Complete Documentation

## Overview

This document describes the full implementation of the **Internal Link Discovery Module** and its **Integration into PR Monitor Step 4 v2 evidence collection**. The module extracts, canonicalizes, scores, and classifies internal links from saved page content (HTML or plain text), then uses them as higher-priority candidates before falling back to guessed URL paths.

This work was built according to the strategic plan outlined in two GitHub gists:
- Most efficient coding path: `gist:e2d661aec9691405d541e7d47f766c73`
- Specific current task: `gist:025de7bf825affad83fba131e0d6136e`

---

## Design Principles

1. **"Fetch once, save once, extract many times."** — The module operates on saved content only. It makes no network calls.
2. **No production coupling** — Integration is opt-in via CLI flag. Default behavior unchanged.
3. **Testability** — All logic is deterministic and testable offline without browser or network flakiness.
4. **Modularity** — Standalone module with clean integration points.
5. **Fallback preservation** — Guessed paths still work as fallback when discovery finds nothing.

---

## Files Summary

| File | Purpose | Status |
|---|---|---|
| `extraction_benchmarks/internal_link_discovery.py` | Main module | Created (Phase 1) |
| `extraction_benchmarks/test_internal_link_discovery.py` | Unit tests | Created (Phase 1) |
| `extraction_benchmarks/multi_page_evidence.py` | Integration target | Modified (Phase 2) |
| `extraction_benchmarks/test_phase2_integration.py` | Integration tests | Created (Phase 2) |

---

## Phase 1: Standalone Module

### Files Created

| File | Size |
|---|---|
| `extraction_benchmarks/internal_link_discovery.py` | 16,522 bytes |
| `extraction_benchmarks/test_internal_link_discovery.py` | 11,309 bytes |

### Module API

**Primary Function:**

```python
def discover_links(
    base_url: str,
    *,
    html: Optional[str] = None,
    text: Optional[str] = None,
    max_links_per_conference: int = 12,
    reject_junk: bool = True,
) -> Dict[str, Any]:
```

**Parameters:**
- `base_url`: The source page URL (used for resolving relative links and domain filtering)
- `html`: Raw HTML content (preferred, parsed with BeautifulSoup)
- `text`: Plain text content (fallback for text-only evidence packages)
- `max_links_per_conference`: Cap on selected links (default: 12)
- `reject_junk`: Whether to filter low-value URLs (default: True)

**Returns:**
```python
{
    "base_url": str,
    "domain": str,
    "links_discovered": int,      # Total after dedup, before selection
    "links_selected": int,         # After capping
    "links_rejected": int,         # Discovered minus selected
    "selected": List[Dict],       # Links chosen for crawling
    "rejected": List[Dict],       # Links not selected
    "grouped": Dict[str, List],    # {category: [links]}
}
```

### Secondary Functions

| Function | Purpose |
|---|---|
| `canonicalize_url(url)` | Normalize URL: strip fragments, tracking params, normalize trailing slash, lowercase host |
| `resolve_url(base, relative)` | Resolve relative URLs against base URL |
| `extract_links_from_html(base_url, html)` | Parse all `<a href>` tags from HTML |
| `extract_links_from_text(base_url, text)` | Extract navigation labels from plain text (ALL CAPS patterns) |
| `is_junk(url)` | Check if URL is privacy/terms/login/social/assets |
| `score_href(href, category)` | Score URL path tokens against a category |
| `score_anchor(anchor, category)` | Score anchor text tokens against a category |

### Category Definitions

| Category | Example targets | Href tokens | Anchor tokens |
|---|---|---|---|
| `conference_event` | Home, agenda, register | home, event, conference, agenda, register | home, event, conference, agenda, overview, register |
| `contact_info` | Contact, sponsors, about | contact, about, team, organizer, inquiries | contact, about, team, organizer, sponsor |
| `cfp_info` | Speakers, CFP, abstracts | speaker, cfp, call-for-papers, abstract | speaker, cfp, call for papers, agenda, submit |
| `submission_url` | Submit, portal, apply | submit, submission, portal, apply, proposal | submit, submission, portal, apply, speaker |

### Junk Filtering

URLs are rejected if they match any of these patterns:
- Privacy, terms, cookies, login, signup, logout
- Social platforms (facebook, twitter, instagram, linkedin, youtube)
- CMS paths (wp-admin, wp-content, wp-includes)
- Static assets (images, css, js, fonts, cdn-cgi)
- File extensions (pdf, jpg, png, gif, svg, webp, mp4, mp3, zip, doc, xlsx, pptx)
- Non-navigational schemes (mailto:, tel:, javascript:, #)

### Selection Algorithm

1. Always include the base URL first (as `conference_event`)
2. Round-robin from categories: contact_info → cfp_info → submission_url → conference_event
3. Within each category, links are sorted by score (descending)
4. Stop when `max_links_per_conference` is reached

### Phase 1 Test Coverage

30 unit tests across 6 categories — **30/30 passing**

| Test Category | Count | Coverage |
|---|---|---|
| URL Canonicalization | 6 | Trailing slash, fragments, tracking params, path preservation, host lowercasing, empty input |
| URL Resolution | 3 | Relative resolution, absolute passthrough, junk scheme rejection |
| Junk Filtering | 6 | Privacy/terms/login, images/assets, social, positive cases |
| Scoring | 4 | Href path, anchor text, multi-category |
| HTML Extraction | 4 | Count, junk filtering, deduplication, anchor preservation |
| Text Extraction | 2 | Nav label detection, long label filtering |
| Integration | 5 | Full discover_links (HTML & text), cap enforcement, rejected count, metadata |

### Phase 1 Smoke Testing Results

| Conference | URL | Discovered | Selected | Notes |
|---|---|---|---|---|
| Reuters Energy Transition Europe | `reutersevents.com/energy-transition/energy-transition-europe` | 28 | 12 | Found `/contact-us`, `/speakers`, `/sponsors`, `/partner-with-us`, `/agenda` |
| Black Hat Asia 2026 | `blackhat.com/asia-26/` | 13 | 12 | Found `/strategic-partners`, `/conference-highlights`, `/register-now` |
| Gartner IAM 2026 | `gartner.com/en/conferences/emea/identity-access-management-uk` | 0 | 1 | JS-rendered nav not in plain text; guessed-path fallback applies |

---

## Phase 2: Integration into Evidence Collection

### Files Modified

`extraction_benchmarks/multi_page_evidence.py` — the existing evidence package builder

### Files Created

`extraction_benchmarks/test_phase2_integration.py` — integration tests

### Changes to `multi_page_evidence.py`

**1. Import added:**
```python
from internal_link_discovery import discover_links, canonicalize_url
```

**2. New function `build_candidate_urls_with_discovery()`:**
```python
def build_candidate_urls_with_discovery(
    base_url: str,
    category: str,
    case: Dict[str, Any],
    use_discovery: bool = True,
) -> List[str]:
```
Returns URLs with priority order:
- Discovered internal links (from page text)
- Guessed paths (fallback, deduped)

**3. Modified `build_evidence_package()`:**
- Added `use_discovery: bool = True` parameter
- Uses `build_candidate_urls_with_discovery()` when enabled
- Adds `collection_method` field to package: `"discovery_guessed"` or `"guessed_only"`

**4. Modified `write_local_browser_manifest()`:**
- Added `use_discovery: bool = True` parameter
- Passes through to URL building function
- Adds `collection_method` field to manifest

**5. Modified `main()`:**
- Added `--use-discovery` flag (opt-in)
- Added `--no-discovery` flag (explicit disable)
- Default: discovery disabled (safe for production)

### Key Design Decisions

| Decision | Rationale |
|---|---|
| Opt-in via `--use-discovery` flag | Safe for production; no behavior change unless explicitly requested |
| Guessed paths preserved as fallback | For sites where discovery finds nothing (JS-heavy sites like Gartner) |
| `collection_method` field in output | Enables comparison between v1 and v2 evidence packages |
| No changes to `run_top5_multi_page_benchmark.py` | Benchmark remains unchanged; consumes whatever evidence packages exist |
| Discovery runs on `main_text` only | Uses existing saved page text; no additional fetches required |

### Phase 2 Test Coverage

12 integration tests across 4 categories — **12/12 passing**

| Test Category | Count | What's Verified |
|---|---|---|
| URL Priority Ordering | 4 | Discovered URLs come before guessed; guessed still present as fallback; no duplicates; base URL included |
| Package Building | 2 | `collection_method` field set correctly for both modes |
| Discovery Effectiveness | 3 | `/contact-us`, `/call-for-papers`, `/speakers` discovered from page text |
| Quality & Real Data | 3 | Quality metrics present; real Reuters case finds contact/sponsor links |

### Combined Test Results

| Test Suite | Tests | Result |
|---|---|---|
| Phase 1 Unit Tests | 30 | PASS |
| Phase 2 Integration Tests | 12 | PASS |
| **Total** | **42** | **All passing** |

---

## Dependencies

- `beautifulsoup4` — For HTML parsing (optional; falls back to text extraction if unavailable)
- Standard library only: `re`, `urllib.parse`, `typing`, `json`, `time`, `zipfile`, `argparse`

---

## Acceptance Criteria

### Phase 1

- [x] Standalone module at exact path: `pr_monitor_1/extraction_benchmarks/internal_link_discovery.py`
- [x] Tests at exact path: `pr_monitor_1/extraction_benchmarks/test_internal_link_discovery.py`
- [x] Tests pass (30/30)
- [x] Verified on representative pages (Reuters, Black Hat)
- [x] `/speakers` and `/speakers/` dedupe correctly
- [x] Contact links rank above privacy/terms
- [x] CFP/speaker/submit links rank above generic pages
- [x] Same-domain filter works
- [x] Max page cap is respected
- [x] Output includes selected/rejected metadata
- [x] No production code modified
- [x] No browser collection behavior changed

### Phase 2

- [x] Integration into `multi_page_evidence.py` complete
- [x] Discovered links used as higher-priority source before guessed paths
- [x] Guessed paths preserved as fallback
- [x] `--use-discovery` flag added (opt-in, safe default)
- [x] `collection_method` field added to packages and manifests
- [x] Integration tests pass (12/12)
- [x] Phase 1 unit tests still pass (30/30)
- [x] No breaking changes to existing behavior
- [x] `run_top5_multi_page_benchmark.py` unchanged

---

## Risk Acknowledgment

- owl-alpha is provisionally the best **extraction** model; its coding ability was validated through this narrow, testable task only.
- Future phases should verify outputs before production integration.
- The text-based extraction (for Gartner-type JS-heavy sites) has limited reach; HTML-based extraction will be needed for full coverage. This is expected to be addressed when the production pipeline saves raw HTML alongside extracted text.
- The integration is opt-in and can be reverted by removing the `--use-discovery` flag.

---

## Next Steps (Phase 3+)

When ready, the remaining steps per the original gist plan:

1. **Run one more local-browser collection** using `--use-discovery` to get v2 evidence packages
2. **Run top-5 benchmark** against v2 evidence packages
3. **Compare v2 vs v1 benchmark results** — only replace production Step 4 if v2 beats current output
4. **Add v2 endpoint/mode**: `/api/pr-monitor-1/extract-v2-multipage` (separate from current Step 4)
5. **Add path memory** from successful runs (discovered links that produced good extraction results get priority in future runs)
6. **Save raw HTML** alongside extracted text in evidence packages (to enable full `<a href>` extraction for JS-heavy sites)
