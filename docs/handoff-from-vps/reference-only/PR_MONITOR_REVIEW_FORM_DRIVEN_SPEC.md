# PR Monitor Review - Form-Driven UI + Prompt Excellence Spec

Date: 2026-05-29
Scope: Step 1 discovery UX for conference + award source identification, tied to `pr-monitor-review`
Status: Implementation-ready

## 1) Objective
Create an easy form-driven experience where users provide minimal inputs, and the system generates high-quality discovery prompts using Step-1 best practice, then returns reviewable sources in one workflow.

## 2) Minimal Inputs (Required)
Only three user-facing required inputs:
1. `market_focus` (text)
2. `conference_geo_preference` (text)
3. `award_geo_preference` (text)

### 2.1 Recommended Input Helpers (Optional UI fields)
- `date_window` (e.g., "next 12 months")
- `priority_mode` (`local_first`, `state_first`, `domestic_first`, `international_first`, `balanced`)
- `include_unknown_geo` (default: true)

These are optional to keep UX simple. If omitted, defaults apply.

## 3) UX Design (Simple + Fast)

### 3.1 Screen Sections (single page)
1. Setup Form (top)
2. Generated Prompt Preview (collapsible)
3. Run Controls
4. Results Table + Filters
5. Unknown Geo Queue

### 3.2 Friction Rules
- Keep visible form fields <= 6.
- Use placeholder examples in each field.
- One primary CTA only: `Generate & Run`.
- All advanced controls collapsed under `Advanced`.

### 3.3 Input UX Copy (Plain-English)
- Market focus: "What market are we targeting?"
- Conference geo preference: "Where should conference opportunities be prioritized?"
- Award geo preference: "Where should award opportunities be prioritized?"

## 4) Data Model

## 4.1 Existing v1 compatibility
Keep existing 54-field extraction untouched.

## 4.2 v2 geo enrichment fields (row-level)
Add:
- `geo_city`
- `geo_state`
- `geo_country`
- `geo_confidence_status` (`GEO_CONFIRMED` | `GEO_PARTIAL` | `GEO_UNKNOWN`)
- `record_type` (`conference` | `award`)

### 4.3 User preference storage (shared across conferences + awards)
Table: `geo_preferences`
- `id` (pk)
- `user_id`
- `market_focus`
- `conference_geo_preference` (text)
- `award_geo_preference` (text)
- `priority_mode`
- `include_unknown_geo` (bool, default true)
- `created_at`
- `updated_at`

Table: `geo_preferences_history`
- `id` (pk)
- `geo_preference_id`
- `changed_by`
- `old_payload_json`
- `new_payload_json`
- `changed_at`

## 5) API Contract

### 5.1 Generate prompt pack
POST `/api/pr-monitor/prompt-pack/generate`

Request JSON:
```
{
  "market_focus": "Hydrogen and energy transition conferences",
  "conference_geo_preference": "Austin first, then Texas, then US, then international",
  "award_geo_preference": "Texas and US awards first, then international",
  "date_window": "next 12 months",
  "priority_mode": "local_first",
  "include_unknown_geo": true
}
```

Response JSON:
```
{
  "prompt_pack_id": "pp_...",
  "schema_version": "step1_prompt_pack_v1",
  "prompts": {
    "conference_discovery": "...",
    "award_discovery": "...",
    "url_validation": "...",
    "geo_enrichment": "...",
    "output_standardization": "..."
  },
  "defaults_applied": ["date_window", "include_unknown_geo"]
}
```

### 5.2 Run discovery
POST `/api/pr-monitor/discovery/run`

Request JSON:
```
{
  "prompt_pack_id": "pp_...",
  "market_focus": "...",
  "record_types": ["conference", "award"],
  "run_mode": "full"
}
```

Response JSON:
```
{
  "run_id": "run_...",
  "status": "queued"
}
```

### 5.3 Save preferences
POST `/api/pr-monitor/geo-preferences/save`

## 6) Prompt Excellence Framework (Best-Practice Layer)
Each generated prompt must enforce the following:

1. Market relevance first
- Must match user-defined market before scoring high.

2. Geo preference hierarchy
- Parse user preference language into rank order.
- Example parse output: `city > state > domestic > international > unknown`.

3. Source quality checks
- Canonical event/award page preferred.
- Reject weak directory duplicates when canonical exists.

4. Traceability
- Every accepted source must include:
  - why accepted
  - geo evidence snippet
  - confidence note

5. Unknown-geo protection
- Unknown geo rows are included and tagged, never silently dropped.

## 7) Prompt Templates (System-Side)

### 7.1 Conference Discovery Prompt Template
"Identify high-relevance conference sources for market: {market_focus}. Prioritize geography by: {conference_geo_preference}. Return canonical URLs only where possible. Include rationale, geo evidence, and confidence notes."

### 7.2 Award Discovery Prompt Template
"Identify high-relevance award opportunities for market: {market_focus}. Prioritize geography by: {award_geo_preference}. Return application/source URLs, deadlines if available, geo evidence, and confidence notes."

### 7.3 URL Validation Prompt Template
"Validate each candidate URL for relevance, canonical quality, and freshness. Mark APPROVE, HOLD, or REJECT with explicit reason."

### 7.4 Geo Enrichment Prompt Template
"Extract/verify city, state, country from page content or trusted linked pages. Output `geo_city`, `geo_state`, `geo_country`, `geo_confidence_status`. If uncertain, use `GEO_PARTIAL` or `GEO_UNKNOWN`."

### 7.5 Output Standardization Template
"Return records in standardized schema with deterministic fields and explicit status tags."

## 8) Results UI Spec

### 8.1 Table columns
- URL
- Record Type
- Market Match Score
- Geo City
- Geo State
- Geo Country
- Geo Confidence
- Priority Tier
- Decision (`Approve`, `Hold`, `Reject`)
- Reason

### 8.2 Filters
- Record type
- City
- State
- Country
- Geo confidence
- Decision status

### 8.3 Queue tabs
- Approved
- Hold
- Rejected
- Unknown Geo

## 9) Scoring + Ranking
Final rank score:
`final_score = opportunity_score + geo_priority_score + source_quality_score`

Rules:
- Unknown geo rows receive penalty, not exclusion.
- If two rows tie, prefer canonical source.

## 10) Safety + Quality Guardrails
1. No silent exclusions for unknown geo.
2. Require reason string for reject actions.
3. Keep raw user preferences stored exactly as entered.
4. Preserve original `conf_location` while adding parsed geo fields.

## 11) Rollout Plan

### Phase 1 (UI + prompt generation)
- Add form and prompt pack generation endpoints.
- Store preferences and history.

### Phase 2 (discovery execution + table)
- Wire run execution and result rendering.
- Add filters and decision actions.

### Phase 3 (geo enrichment + unknown queue)
- Add v2 geo fields + confidence statuses.
- Add Unknown Geo queue and QA checks.

## 12) Acceptance Criteria
- User can submit in under 60 seconds.
- Prompt pack is generated deterministically from input + SOP standard.
- Conference and award preferences are stored separately but in one unified profile.
- Unknown geo rows are visible and filterable.
- Results are reviewable in `pr-monitor-review` without leaving page.

## 13) Build Checklist (Dev)
- [ ] Add form component with 3 required fields
- [ ] Add preference storage table + history table
- [ ] Add prompt-pack generation endpoint
- [ ] Add discovery run endpoint
- [ ] Add results table + filters + queue tabs
- [ ] Add unknown-geo queue
- [ ] Add QA test: no unknown-geo silent drops

