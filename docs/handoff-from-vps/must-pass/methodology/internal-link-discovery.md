# Internal Link Discovery Module — Phase 1+2 Implementation

## What it does

Extracts, canonicalizes, scores, and classifies internal links from saved page content (HTML or plain text). Used to improve multi-page evidence collection for Step 4 extraction by prioritizing actual site links over guessed URL paths.

## Files

| File | Purpose |
|---|---|
| `extraction_benchmarks/internal_link_discovery.py` | Standalone module (16,522 bytes) |
| `extraction_benchmarks/test_internal_link_discovery.py` | Unit tests (30 tests) |
| `extraction_benchmarks/multi_page_evidence.py` | Integration target (modified, `--use-discovery` flag) |
| `extraction_benchmarks/test_phase2_integration.py` | Integration tests (12 tests) |

## Module API

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

Returns: `{base_url, domain, links_discovered, links_selected, links_rejected, selected, rejected, grouped}`

## Priority ordering (v2)

1. Base URL (always first)
2. Discovered internal links (from page text/HTML)
3. Guessed paths (fallback, deduped)

## Categories

- `conference_event` — home, agenda, register
- `contact_info` — contact, sponsors, about
- `cfp_info` — speakers, cfp, abstracts
- `submission_url` — submit, portal, apply

## Integration into multi_page_evidence.py

- Added `from internal_link_discovery import discover_links, canonicalize_url`
- New function `build_candidate_urls_with_discovery()` wraps guessed-path fallback
- `build_evidence_package()` and `write_local_browser_manifest()` accept `use_discovery: bool = True`
- `main()` accepts `--use-discovery` flag (opt-in)
- Packages include `collection_method: "discovery_guessed"` or `"guessed_only"`

## Test results

- Phase 1 unit tests: 30/30 passing
- Phase 2 integration tests: 12/12 passing
- Real data smoke test: Reuters (28→12 links), Black Hat (13→12), Gartner (0, expected for JS-heavy)

## Key pitfall: Python environment divergence

`execute_code` runs in a different Python environment (Python 3.11 venv) than the terminal (Python 3.12 system). `beautifulsoup4` was installed in the system Python but not available in the execute_code sandbox.

**Symptom:** `HAS_BS4 = False` in execute_code context even though `from bs4 import BeautifulSoup` works from terminal.

**Fix:** Always run tests from `terminal` (not execute_code) when they depend on pip-installed packages. If you must use execute_code, verify the package is importable in that context first.

## Key pitfall: LSP false positives on conditional imports

Wrapping `from bs4 import BeautifulSoup` in a module-level `try/except` sets `HAS_BS4 = False` if the import fails during any import context. The LSP may report `BeautifulSoup is possibly unbound` even though the code handles it at runtime.

**Fix:** Use local imports inside functions (`from bs4 import BeautifulSoup as _BS4`) rather than relying on the module-level `HAS_BS4` guard for type checking.

## Key pitfall: Register/signup pages are NOT junk in PR monitoring

The `is_junk()` function in `internal_link_discovery.py` does **not** reject `/register`, `/signup`, or `/register-*` paths. This is intentional.

**Why:** In PR monitoring, register/signup pages often contain high-value conference data:
- Pricing tiers and early-bird deadlines
- Group discount structures
- Contact emails for registration inquiries
- Cancellation/refund policies
- Attendance justification templates
- Dates and venue confirmation

Filtering these would miss critical intelligence that PR professionals track for their clients.

**User correction (2026-06-24):** Initially these were in `JUNK_PATTERNS` alongside login/logout. Matt explicitly reversed this: "When I go to the signup page there is often valuable information that we can scrape/extract for the conference. So I think both signup and register related links are good internal links to crawl - do NOT exclude."

**What IS still junk:** `/login`, `/logout`, privacy, terms, cookies, social links, CMS paths, static assets, file extensions.

**Pitfall for future agents:** Do not "clean up" the junk filter by re-adding register/signup. If you are tempted to reduce the URL set for "quality," score register/signup pages lower via the category scoring system instead of hard-rejecting them.

## Usage

```bash
# Run tests
python3 test_internal_link_discovery.py
python3 test_phase2_integration.py

# Use discovery in evidence collection
python3 multi_page_evidence.py --use-discovery --case-limit 5

# Use guessed-only (default behavior)
python3 multi_page_evidence.py --no-discovery --case-limit 5
```
