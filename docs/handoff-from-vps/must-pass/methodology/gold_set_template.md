# Free OpenRouter Model Benchmark — Gold Set Template

Purpose: provide human-reviewed truth so model scoring measures accuracy, not just JSON shape.

Fill one block per benchmark case after reviewing source page/content.
Use N/A only when truly absent.

```json
[
  {
    "case_id": "case_01",
    "url": "",
    "conference_name": "",
    "conference_dates": "",
    "conference_location": "",
    "conference_description": "",
    "contact_name": "N/A",
    "contact_email": "N/A",
    "contact_phone": "N/A",
    "contact_org": "N/A",
    "cfp_status": "Unknown",
    "cfp_deadline": "N/A",
    "cfp_link": "N/A",
    "review_notes": ""
  }
]
```

Accuracy scoring workflow:
1. Generate a reviewer template from benchmark output:
   `python3 score_against_gold_set.py --results runs/<run>/raw_results.jsonl --write-template runs/<run>/gold_set_review_template.json`
2. Fill the top-level gold values for each case. `model_candidates_for_review` is helper context only and is ignored by the scorer.
3. Score model outputs offline:
   `python3 score_against_gold_set.py --results runs/<run>/raw_results.jsonl --gold-set gold_sets/<name>.json --out runs/<run>/gold_score`

Scoring behavior:
- exact/normalized match for CFP status and email
- phone digit normalization
- fuzzy/contains match for names, dates, location, descriptions, requirements, instructions
- URL-normalized match for `cfp_link`
- hallucination penalty when the gold set says a field is absent but the model invents a value
- acceptance threshold: high JSON validity + >=90% critical-field accuracy + low hallucination rate
