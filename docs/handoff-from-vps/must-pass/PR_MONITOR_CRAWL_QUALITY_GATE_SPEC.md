
# PR Monitor Crawl Quality Gate Spec

**Project:** PR Monitor / PR in a Box  
**Created:** 2026-06-22  
**Scope:** Crawl only — using Nicolia-provided URL lists as input  
**Target:** 95% actionable crawl classification

---

## 1. Purpose

The Crawl Quality Gate prevents bad crawl results from silently poisoning extraction, enrichment, and review.

A URL must not proceed downstream unless the system has either:

1. Captured usable content, or
2. Classified the failure with a clear next action.

---

## 2. Input

Source rows from Nicolia-provided sheets:

- ENERGY sheet
- APPSEC/CYBERSECURITY sheet

Minimum input fields:

- source_list_name
- row_number
- conference_or_award_name
- conference_url
- submission_url, if present
- location, if present
- start_date, if present
- latest_update, if present
- current_status, if present
- market_tag

---

## 3. Output

One crawl quality record per URL.

Required fields:

```json
{
  "run_id": "crawl_quality_YYYYMMDD_HHMMSS",
  "source_list_name": "energy",
  "row_number": 4,
  "name": "World Hydrogen & Carbon Americas",
  "url": "https://wh2camericas.com",
  "normalized_url": "https://wh2camericas.com/",
  "status": "PASS",
  "status_reason": "usable_content_captured",
  "http_status": 200,
  "final_url": "https://wh2camericas.com/",
  "redirected": false,
  "content_bytes": 84231,
  "content_hash": "...",
  "crawl_seconds": 8.2,
  "fallback_protocols_used": [],
  "risk_flags": [],
  "next_action": "proceed_to_extract",
  "captured_at": "2026-06-22T...Z"
}
```

---

## 4. Crawl Status Taxonomy

### PASS

Use when:

- HTTP/render succeeds
- Content is meaningful
- Page appears to represent the expected organization/event/site
- Content length above minimum threshold

Next action: proceed_to_extract

### PARTIAL

Use when:

- Page responds but content is suspiciously thin
- Important rendered content may be missing
- Content length below threshold but not empty
- Page title/content suggests JS/lazy-load issue

Next action: retry_with_rendered_browser OR needs_manual_review

### BLOCKED

Use when:

- 403, 429, captcha, Cloudflare challenge, bot detection, Access Denied
- Content clearly indicates automated access was blocked

Next action: retry_with_fallback_protocol OR manual_check

### TIMEOUT

Use when:

- Crawl exceeds hard timeout
- Browser hangs
- Network read hangs

Next action: retry_once_with_extended_timeout, then manual_check

### INVALID_URL

Use when:

- malformed URL
- DNS failure
- unsupported scheme
- clearly dead domain

Next action: correct_url_from_source_or_manual

### NON_CONFERENCE_PLATFORM

Use when:

- URL is a platform/tool/listing page, not an event owner page
- Example: Sessionize listing or submission-management platform page

Next action: find_actual_event_owner_url

### REDIRECTED

Use when:

- URL redirects to a different domain or unexpected page
- final URL is materially different from input

Next action: provenance_review, then proceed or manual_check

### NEEDS_MANUAL

Use when:

- Ambiguous result
- Conflicting signals
- System should not proceed automatically

Next action: manual_review

---

## 5. Crawl Quality Metrics

### Actionable Classification Rate

```text
(PASS + PARTIAL + BLOCKED + TIMEOUT + INVALID_URL + NON_CONFERENCE_PLATFORM + REDIRECTED + NEEDS_MANUAL) / URLs attempted
```

Target: 95%+

Note: This should approach 100% if every URL receives a valid classification.

### Usable Content Rate

```text
PASS / URLs attempted
```

Initial target: 90%+
Stretch target: 95%+

### Silent Failure Rate

```text
URLs with no artifact and no classified failure / URLs attempted
```

Target: 0%

### Partial Content Rate

```text
PARTIAL / URLs attempted
```

Target: <5%

### Blocked Rate

```text
BLOCKED / URLs attempted
```

Target: <10%

### Timeout Rate

```text
TIMEOUT / URLs attempted
```

Target: <3%

---

## 6. PASS Criteria

A crawl should PASS only if all conditions hold:

1. URL response successful OR browser-rendered page successful
2. Content length >= minimum threshold (initial threshold: 1,500 chars markdown or 5,000 chars HTML)
3. Page has a meaningful title/body
4. Content is not a known block page
5. Content is not an empty shell requiring JavaScript that failed to render
6. Final URL is acceptable or redirected intentionally
7. Content hash generated successfully

---

## 7. Risk Flags

A PASS can still include risk flags.

Risk flags:

- `low_content_volume`
- `heavy_javascript_site`
- `redirected_domain`
- `submission_platform_detected`
- `multi_location_possible`
- `past_event_possible`
- `cfp_keywords_absent`
- `cfp_keywords_present`
- `international_site`
- `date_rollover_candidate`

These flags guide extraction and enrichment.

---

## 8. Fallback Protocols

Known crawler strategies should be named and logged.

Examples:

- `basic_http_fetch`
- `crawl4ai_static`
- `crawl4ai_browser_rendered`
- `playwright_headless`
- `alternate_user_agent`
- `extended_timeout`
- `manual_required`

Every fallback attempt should be captured in the crawl quality record.

---

## 9. Baseline Batch Strategy

Do not start with the full list.

Recommended first batch:

- 25 URLs total
- 15 APPSEC/CYBERSECURITY
- 10 ENERGY

Include:

- SecureWorld Expo (multi-location)
- ShmooCon or similar direct conference site
- CyberTech Global (international)
- Wild West Hackin' Fest
- At least one clean-energy international event
- At least one past event / date rollover candidate
- At least one submission URL if available

After baseline:

1. Classify failures
2. Improve crawler/fallback logic
3. Re-run same 25 URLs
4. Compare before/after
5. Expand to 50 URLs
6. Expand to full source lists

---

## 10. Required Report Summary

Each crawl run report must include:

```text
CRAWL QUALITY REPORT — [run_id]

URLs attempted: N
PASS: N (% N)
PARTIAL: N
BLOCKED: N
TIMEOUT: N
INVALID_URL: N
NON_CONFERENCE_PLATFORM: N
REDIRECTED: N
NEEDS_MANUAL: N
Silent failures: N

Actionable classification rate: X%
Usable content rate: X%
Target met? YES/NO

Top failure modes:
1. ...
2. ...
3. ...

Recommended improvements:
1. ...
2. ...
3. ...
```

---

## 11. Launch Gate

Crawl is ready to feed Extract only when:

1. Actionable classification rate >= 95%
2. Silent failure rate = 0%
3. Usable content rate >= 90% or explicit Matt/Nicolia acceptance
4. Blocked/TIMEOUT/partial URLs are routed to clear next actions
5. Latest report is saved and linked from dashboard/report index

---

## 12. Implementation Notes

Build this as a quality layer around the existing crawler, not a replacement.

Do not break the existing PR Monitor 1 flow.

Recommended implementation pattern:

1. Read input manifest JSON
2. Invoke existing crawl pathway
3. Inspect artifacts/output
4. Classify result
5. Write quality report
6. Return nonzero only for system execution failure, not for ordinary BLOCKED/TIMEOUT classifications

This lets quality reporting run in CI/cron without treating expected web friction as script failure.