# Step 4 v2 — Multi-page extraction foundation + model benchmark

## Session learning
Step 4 extraction quality cannot be judged from a single conference page. The project requirements say CFP/contact/submission information is often on subpages, so model benchmarking must run after a multi-page evidence package is built.

## Correct sequence
1. Start with base conference URLs from Step 3/crawl quality.
2. Expand each base URL into category candidate pages:
   - `conference_event`: `/`
   - `contact_info`: `/contact/`, `/about/`, `/team/`, `/organizers/`, `/organisers/`, `/committee/`
   - `cfp_info`: `/speakers/`, `/cfp/`, `/call-for-papers/`, `/call-for-speakers/`, `/call-for-abstracts/`, `/submit/`, `/abstracts/`
   - `submission_url`: `/speakers/`, `/submit/`, `/submission/`, `/submissions/`, `/call-for-papers/`, `/call-for-speakers/`
3. Preserve `paths_planned`, `paths_tried`, `selected_source_urls`, text snippets, status, text length, and field/category evidence.
4. Use Matt's Windows local-browser runner when VPS/direct HTTP fetch hits blocking or JS-heavy pages.
5. Build one identical multi-page evidence package per conference.
6. Run each model as a separate extraction pass over the same evidence package.
7. Score structural JSON/completeness first, then perform gold-set field accuracy before selecting a default/fallback route.

## Top free models carried forward for Step 4 v2 benchmark
- `openrouter/owl-alpha`
- `poolside/laguna-xs.2:free`
- `nvidia/nemotron-3-super-120b-a12b:free`
- `nvidia/nemotron-3-ultra-550b-a55b:free`
- `openai/gpt-oss-120b:free`

## Runner/path pitfall fixed
A multi-page job can produce long Windows paths because it combines a long run ID, deep extracted runner folder, and long page labels. This caused `FileNotFoundError` while writing HTML/text files. The durable fix is to shorten only local output folder/file slugs while preserving the full run ID in `summary.json` and upload metadata.

## Special multi-page job status interpretation
For multi-page discovery jobs, `original_status` may be `MULTI_PAGE_DISCOVERY`. The old recovery summary computes `recovered=true` only when original status was `BLOCKED` or `PARTIAL`, so `recovered_by_local: 0` can be misleading. For Step 4 v2 jobs, use `local_browser_status` counts (`PASS`, `PARTIAL`, `ERROR`, etc.) and uploaded text artifacts, not `recovered_by_local`, as the success signal.

## User-facing verification guidance
When giving Matt Windows instructions, be concise and definitive:
- Job file goes in `C:\\Users\\<user>\\Downloads\\` and must match `recovery_job_*.json`.
- The one-click runner auto-imports the newest matching job from Downloads into its `jobs\\` folder.
- If multiple job files exist, delete old ones or ensure the intended file is newest.
- After the run, local results are in `windows_runner_v0_1\\runs\\<newest>\\summary.json`, `text\\`, `html\\`, and the sibling `.zip` bundle.

## Durable implementation lessons from local-browser multi-page run
- Multi-page job manifests published manually must include an `upload` block and matching token under `local_browser_fallback/upload_tokens/<run_id>.json`; otherwise the Windows runner can finish locally but skip upload.
- Verify the job URL after publishing: HTTP 200, expected URL count, `run_id`, and `upload.enabled=true`.
- For Matt-facing reruns after a runner fix, tell him to download both the new runner ZIP and a fresh copy of the job JSON; old job files may hold stale/missing upload tokens.
- If the server recovery endpoint says `available:true` and `PASS/PARTIAL` counts exist, the upload worked even if `recovered_by_local` is zero for `MULTI_PAGE_DISCOVERY` jobs.
- Rebuild evidence packages from the uploaded ZIP by grouping `summary.json.results` by `case_id` and `categories`, matching text files by numeric prefix (`text/NN_*.txt`), and preserving `local_status`, `local_final_url`, title, text length, snippets, and source ZIP path.

## Current structural benchmark pattern
After rebuilding evidence from the uploaded 105-page local-browser bundle, run the top-5 benchmark over the local-browser evidence directory. Produce:
- `report.md` for model-level structural summary.
- `field_population_matrix.md/csv` for column-level completeness across cases.
- `contact_cfp_values.md` for actual contact/org/CFP values by model and case.

Example interpretation from the 105-page run: event basics may score 5/5 across valid models while contact email/phone and CFP deadline/link still remain 0/5. Do not conclude model failure until link discovery confirms the true contact/CFP pages were included.

## Next extraction improvement
Guessed paths are not enough. Add link discovery from fetched pages before model judgment:
- Extract anchor text + href from rendered HTML where available.
- Rank links by labels/URLs containing `contact`, `speaker`, `cfp`, `call for`, `abstract`, `submit`, `proposal`, `agenda`, `sponsor`, `media`, `press`.
- Add top-ranked discovered links to the category evidence package before running model passes.
- Keep guessed-path fallback and path memory, but prefer discovered site-specific links when available.
