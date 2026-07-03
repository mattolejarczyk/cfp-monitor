
# Weekly Executive Report — Safe Draft Guidance

Status: draft
Source: Roadmap Card 9 expectations + active POC surface
Scope: Card 9 only; do not expand to later cards unless asked.

## Intended consumer
Nicolia / leadership. One-page answer each week:
- What should we act on now?
- Which deadlines are at risk?
- What changed?
- What failed and needs attention?
- Recommended next actions?

## Desired sections
1. Top action items
2. Urgent deadlines
3. New/changed opportunities
4. Client-ready items
5. Failures requiring attention
6. Run quality metrics
7. Recommended next actions

## Header requirements
- generated_at
- source_extract path
- latest run / report references
- links to dashboard inspect endpoints when available

## Data grounding rule
Do not invent conference details. Each line should carry:
- conference name or unnamed with source URL
- current action state
- current CFP/deadline values as found
- evidence text extracted from row/crawl notes
- review state when present

If no credible extract state exists, say so explicitly instead of fabricating tier lists or contact details.

## Known gap to preserve
Card 9 implementation is not yet wired into production run flow.
Weekly execution is not configured.
This guidance exists as the handoff context to note current known data sources and avoid premature artifact claims.

## Suggested next step
Feed the safe handoff into the Card 9 deploy run. After the run:
1. Verify actual artifact path under extract_runs
2. Link report from job completion output
3. Update this note with the true artifact path for repeatable weekly delivery