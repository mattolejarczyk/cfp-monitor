# PR Monitor Review - API Schemas and Payload Fixtures

Date: 2026-05-29
Companion to: `PR_MONITOR_REVIEW_FORM_DRIVEN_SPEC.md`

## 1) JSON Schema: Prompt Pack Generate Request
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "PromptPackGenerateRequest",
  "type": "object",
  "required": [
    "market_focus",
    "conference_geo_preference",
    "award_geo_preference"
  ],
  "properties": {
    "market_focus": { "type": "string", "minLength": 3 },
    "conference_geo_preference": { "type": "string", "minLength": 3 },
    "award_geo_preference": { "type": "string", "minLength": 3 },
    "date_window": { "type": "string", "default": "next 12 months" },
    "priority_mode": {
      "type": "string",
      "enum": ["local_first", "state_first", "domestic_first", "international_first", "balanced"],
      "default": "balanced"
    },
    "include_unknown_geo": { "type": "boolean", "default": true }
  },
  "additionalProperties": false
}
```

## 2) JSON Schema: Prompt Pack Generate Response
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "PromptPackGenerateResponse",
  "type": "object",
  "required": ["prompt_pack_id", "schema_version", "prompts"],
  "properties": {
    "prompt_pack_id": { "type": "string" },
    "schema_version": { "type": "string" },
    "prompts": {
      "type": "object",
      "required": [
        "conference_discovery",
        "award_discovery",
        "url_validation",
        "geo_enrichment",
        "output_standardization"
      ],
      "properties": {
        "conference_discovery": { "type": "string" },
        "award_discovery": { "type": "string" },
        "url_validation": { "type": "string" },
        "geo_enrichment": { "type": "string" },
        "output_standardization": { "type": "string" }
      },
      "additionalProperties": false
    },
    "defaults_applied": {
      "type": "array",
      "items": { "type": "string" }
    }
  },
  "additionalProperties": false
}
```

## 3) JSON Schema: Discovery Run Request
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "DiscoveryRunRequest",
  "type": "object",
  "required": ["prompt_pack_id", "market_focus", "record_types"],
  "properties": {
    "prompt_pack_id": { "type": "string" },
    "market_focus": { "type": "string" },
    "record_types": {
      "type": "array",
      "items": { "type": "string", "enum": ["conference", "award"] },
      "minItems": 1,
      "uniqueItems": true
    },
    "run_mode": {
      "type": "string",
      "enum": ["dry_run", "full"],
      "default": "full"
    }
  },
  "additionalProperties": false
}
```

## 4) JSON Schema: Discovery Run Response
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "DiscoveryRunResponse",
  "type": "object",
  "required": ["run_id", "status"],
  "properties": {
    "run_id": { "type": "string" },
    "status": { "type": "string", "enum": ["queued", "running", "completed", "failed"] }
  },
  "additionalProperties": false
}
```

## 5) JSON Schema: Save Geo Preferences Request
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "SaveGeoPreferencesRequest",
  "type": "object",
  "required": [
    "user_id",
    "market_focus",
    "conference_geo_preference",
    "award_geo_preference"
  ],
  "properties": {
    "user_id": { "type": "string" },
    "market_focus": { "type": "string" },
    "conference_geo_preference": { "type": "string" },
    "award_geo_preference": { "type": "string" },
    "priority_mode": {
      "type": "string",
      "enum": ["local_first", "state_first", "domestic_first", "international_first", "balanced"],
      "default": "balanced"
    },
    "include_unknown_geo": { "type": "boolean", "default": true }
  },
  "additionalProperties": false
}
```

## 6) JSON Schema: Search Results Row (UI Table)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "DiscoveryResultRow",
  "type": "object",
  "required": [
    "url",
    "record_type",
    "geo_confidence_status",
    "decision_status"
  ],
  "properties": {
    "url": { "type": "string" },
    "record_type": { "type": "string", "enum": ["conference", "award"] },
    "market_match_score": { "type": "number", "minimum": 0, "maximum": 100 },
    "geo_city": { "type": "string" },
    "geo_state": { "type": "string" },
    "geo_country": { "type": "string" },
    "geo_confidence_status": {
      "type": "string",
      "enum": ["GEO_CONFIRMED", "GEO_PARTIAL", "GEO_UNKNOWN"]
    },
    "priority_tier": {
      "type": "string",
      "enum": ["LOCAL", "STATE", "DOMESTIC", "INTERNATIONAL", "UNKNOWN"]
    },
    "opportunity_score": { "type": "number", "minimum": 0, "maximum": 100 },
    "geo_priority_score": { "type": "number", "minimum": -100, "maximum": 100 },
    "source_quality_score": { "type": "number", "minimum": 0, "maximum": 100 },
    "final_score": { "type": "number" },
    "decision_status": {
      "type": "string",
      "enum": ["approved", "hold", "rejected", "needs_review"]
    },
    "decision_reason": { "type": "string" }
  },
  "additionalProperties": false
}
```

## 7) Payload Fixtures

### 7.1 Prompt Pack Generate (request)
```json
{
  "market_focus": "Hydrogen + clean energy event opportunities",
  "conference_geo_preference": "Austin first, then Texas, then US, then international",
  "award_geo_preference": "Texas and US awards first, then international",
  "date_window": "next 12 months",
  "priority_mode": "local_first",
  "include_unknown_geo": true
}
```

### 7.2 Prompt Pack Generate (response)
```json
{
  "prompt_pack_id": "pp_20260529_0001",
  "schema_version": "step1_prompt_pack_v1",
  "prompts": {
    "conference_discovery": "Identify conference sources relevant to: Hydrogen + clean energy...",
    "award_discovery": "Identify award opportunities relevant to: Hydrogen + clean energy...",
    "url_validation": "Validate each URL for canonical quality and relevance...",
    "geo_enrichment": "Extract city/state/country and set GEO_CONFIRMED/PARTIAL/UNKNOWN...",
    "output_standardization": "Return deterministic schema and status tags..."
  },
  "defaults_applied": ["date_window"]
}
```

### 7.3 Discovery Run (request)
```json
{
  "prompt_pack_id": "pp_20260529_0001",
  "market_focus": "Hydrogen + clean energy event opportunities",
  "record_types": ["conference", "award"],
  "run_mode": "full"
}
```

### 7.4 Discovery Run (response)
```json
{
  "run_id": "run_20260529_0001",
  "status": "queued"
}
```

### 7.5 Save Geo Preferences (request)
```json
{
  "user_id": "matt_001",
  "market_focus": "Hydrogen + clean energy event opportunities",
  "conference_geo_preference": "Austin first, then Texas, then US, then international",
  "award_geo_preference": "Texas and US awards first, then international",
  "priority_mode": "local_first",
  "include_unknown_geo": true
}
```

### 7.6 Discovery Row (response item)
```json
{
  "url": "https://example-event.com/2026",
  "record_type": "conference",
  "market_match_score": 91,
  "geo_city": "Austin",
  "geo_state": "Texas",
  "geo_country": "United States",
  "geo_confidence_status": "GEO_CONFIRMED",
  "priority_tier": "LOCAL",
  "opportunity_score": 85,
  "geo_priority_score": 25,
  "source_quality_score": 90,
  "final_score": 200,
  "decision_status": "needs_review",
  "decision_reason": "Auto-ranked high; pending human review"
}
```

## 8) QA Fixture Cases (must pass)
1. Unknown geo retained:
- Input row with no geo parse still appears with `GEO_UNKNOWN`.

2. Reject reason required:
- Any `decision_status = rejected` must have non-empty `decision_reason`.

3. Prompt deterministic:
- Same input payload yields same prompt pack (except IDs/timestamps).

4. Preferences shared:
- Conference + award preferences saved in same profile record.

