# Gold-Set Scoring Workflow

Deterministic offline accuracy scoring for PR Monitor extraction benchmarks.

## Why this exists
Structural scoring (JSON valid? field populated?) is not enough. We need accuracy scoring against human-reviewed truth before promoting any default extraction model. This workflow is repo-local, zero-cost, and repeatable.

## Scripts

### `score_against_gold_set.py`
Compares `raw_results.jsonl` against a filled gold-set JSON. Produces:
- `scored_results.jsonl`
- `accuracy_summary.json`
- `accuracy_summary.csv`
- `field_accuracy_matrix.csv`
- `accuracy_report.md`

Usage:
```bash
python3 score_against_gold_set.py \
  --results runs/<run>/raw_results.jsonl \
  --gold-set gold_sets/<name>.json \
  --out runs/<run>/gold_score
```

### `prefill_gold_set_from_evidence.py`
Deterministically extracts suggested truth from saved evidence packages. No model calls.

Usage:
```bash
python3 prefill_gold_set_from_evidence.py \
  --evidence-dir evidence_packages/<dir> \
  --out runs/<run>/gold_set_prefilled.json
```

### `test_gold_set_scoring.py`
Runs the scorer against synthetic fixtures. No network, no model calls.

## Scoring behavior
- exact/normalized match for email and CFP status
- phone digit normalization
- URL normalization for CFP links (strips tracking params, normalizes trailing slash)
- fuzzy/contains matching for names, dates, location, descriptions, requirements
- hallucination penalty when truth says absent but model invents a value
- missing penalty when truth says present but model returns N/A
- ranking prioritizes critical-field accuracy, then all-field accuracy, JSON validity, and low hallucination count

## Critical fields
- conference_name
- conference_dates
- conference_location
- contact_name
- contact_email
- contact_org
- cfp_status
- cfp_deadline
- cfp_link

## Gold-set JSON shape
```json
{
  "metadata": {"source": "...", "created_at": "..."},
  "cases": [
    {
      "case_id": "case_01",
      "case_name": "...",
      "url": "...",
      "conference_name": "...",
      "conference_dates": "...",
      "conference_location": "...",
      "conference_description": "...",
      "contact_name": "N/A",
      "contact_email": "N/A",
      "contact_phone": "N/A",
      "contact_org": "N/A",
      "cfp_status": "Unknown",
      "cfp_deadline": "N/A",
      "cfp_opens": "N/A",
      "cfp_requirements": "N/A",
      "cfp_link": "N/A",
      "submission_portal_name": "N/A",
      "submission_instructions": "N/A",
      "review_notes": ""
    }
  ]
}
```

## Workflow
1. Run benchmark → `raw_results.jsonl`
2. Generate reviewer template:
   `python3 prefill_gold_set_from_evidence.py --evidence-dir <dir> --out <out>.json`
3. Matt/Nicolia fills critical fields in the generated JSON
4. Run scorer:
   `python3 score_against_gold_set.py --results <jsonl> --gold-set <json> --out <dir>`
5. Review `accuracy_report.md`

## Pitfall: VPS-only truth is unfair
Do not build gold truth from VPS-crawl evidence alone when local-browser recovery evidence exists for the same URLs. VPS contact pages 404'd on Gartner and other JS-heavy sites, but local-browser recovery often succeeded for the same paths. If you score models against VPS-only truth, you penalize models for "missing" data that was actually never made available to them.

Rules:
- Before scoring, check both `local_browser_fallback/uploads/<run_id>/` and `evidence_packages/` for VPS vs local-browser evidence.
- Build gold truth from the best available evidence per URL, preferring local-browser success over VPS 404.
- If local browser succeeded for a category, score that field — do not mark N/A just because VPS failed.
- If both VPS and local browser failed for a category, mark the field as N/A in truth and treat model "N/A" responses as correct-absent.
- If a model invents a value where truth says N/A, score it as hallucination.
- When evidence quality varies across cases, produce a per-case "evidence viability mask" indicating which fair fields to score. Do not compute a single aggregate accuracy number mixing fair and unfair fields.

## Codex quota awareness
The scorer and prefill scripts are deterministic Python with zero model calls. They can run on any machine with Python 3.10+ and no API keys. Reserve Codex for:
- repo code changes
- API wiring
- dashboard UI
- test harness changes
- deterministic scoring/validation scripts

Delegate to cheaper models (owl-alpha, free OpenRouter):
- reading saved evidence text
- drafting suggested truth values from evidence
- summarizing evidence for reviewer handoff
- producing per-case notes about evidence quality
