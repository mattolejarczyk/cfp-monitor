# Model bake-off (ACT-56)

Tests any model as (1) the page READER and (2) a SECOND OPINION, on the person-confirmed tier of `docs/qa/answer-key.csv`, with the production acceptance rule (a quote must be
code-proven verbatim on the page). Every call is blind: one fresh single-turn request holding only the event, the edition year and the page text. No model sees the key, an earlier
answer or another model's answer; scoring and the second-opinion comparison happen in our code afterwards. Public web pages only: never customer data or credentials.

## The three commands (run from the repo root; use the project venv python, e.g. `C:\Users\matts\cfp-monitor\.venv\Scripts\python.exe`, with `PYTHONPATH=.`)

1. RUN a model (18 jobs per pass; every call appends rows to `registry.jsonl`):
   `python experiments/model_bakeoff/run_bakeoff.py --model nemo --repeats 3`
   Codex models (route `codex`) run a fresh `codex exec --ephemeral` each call, effort from the config, and STOP at the first Codex error, printing its exact text.
   Each GPT call costs about 8-17k subscription tokens: use `--limit 1` to prove a setup, one pass to screen, 3 runs only for a model that is precise.
2. COMPARE (reads the registry only):
   `python experiments/model_bakeoff/compare.py --models ds,nemo`
   `python experiments/model_bakeoff/compare.py --runs ds-20261006-1,luna-20261006-1 --second-opinion ds luna`
   Prints each fact with every model's answer, the key and the verdict (correct, correct-blank, missed, wrong-accepted, call-failed), then a per-model summary (precision,
   wrong-accepted, found rate, stability, cost, latency). A model with wrong-accepted above 0 is dropped.
3. ADD a model: add an entry to `models.json` (id, route `openrouter` or `codex`, effort, price figures, where and when the price was seen). No code change. Then run command 1.

## Files
- `models.json` model definitions. `bakeoff_lib.py` blind request, providers, scoring glue. `registry.py` append-only log (`registry.jsonl`: full raw response, prompt and page hashes,
  quote check, key value, verdict, tokens, cost, latency, error). `pages/<sha>.txt` the page text of each call, for replay (git-ignored: third-party text).
- `llm_log.jsonl` (OpenRouter cost log, also the spend cap), `codex_usage.jsonl` (Codex tokens per call), `RESULTS.md` the findings.
