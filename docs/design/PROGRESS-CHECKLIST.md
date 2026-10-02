# CFP customer-market data: the greater plan and progress checklist

Started 2026-09-30. Scope until further notice: the two customer markets (Cybersecurity, Utility). Prospect-market jobs are disabled.
**How this file is used:** it is shown to the operator once after each ITEM is accomplished (not after every reply), in the same four parts: What, Why, Done, Not done.
Update it in the same commit as the work that completes an item.

## The goal, in one paragraph
A customer reads one date per conference and acts on it, so that date must be the date they can SUBMIT by, and we must be able to show the sentence on the page that says so.
Today that is wrong or unprovable in places, the weekend research fails about 73% of its Gemini calls, and September cost 134 USD. The plan has five stages. Each stage ends with a
measured result, and nothing is wired into a scheduled job until Stage 5.

## Stage 0 - Diagnose (DONE)
- [x] Root cause of the grounding failures: prompt design and our own 120 s timeout, not quota.
- [x] Billing reconciled by SKU; searches are 73% of cost; sponsorship passes are about 70% of a weekend's searches.
- [x] Prospect-market monthly and awards tasks disabled (re-enable with an elevated `Enable-ScheduledTask`).

## Stage 1 - Ask Gemini a smaller question (the "narrow prompt")
The production prompt asks for about 33 fields in one call. The narrow prompt asks for 9: conference name, deadline, deadline quote, evidence URL, submission URL, status,
status details, start date, projected flag. Which fields were measured, on 12 easy rows (all with a verified future deadline):
- [x] Calls that grounded: 24 of 24 narrow vs 9 of 24 full. Median time 16 s vs 28 s.
- [x] Deadline equals our verified value: 33 of 33 grounded narrow answers. Start date 24 of 24.
- [ ] Quote quality: UNRESOLVED. Only 33% of quotes were word-for-word on the page, and our own verified quotes scored the same, so the checker was weak, not proven bad. Needs the repo's own verifiers.
- [ ] Hard cases (closed, discontinued, renamed, successor events): not tested. Needs a rule against renaming in the prompt (4 of 24 narrow answers renamed the conference).
- [ ] The other ~24 fields (city, categories, overview, organiser, sponsorship, and so on): NOT YET DECIDED how they are filled: keep the existing record, carry forward, or a second narrow call. Each choice must be validated separately; none has been.

## Stage 2 - Prove the date ourselves (page discovery + reading), so we need not trust a quote
- [x] Page discovery designed and tested: sitemap + homepage menu + priority rules; 364 pages across 84 sites, a call page found at 31 sites.
- [x] Sentence picking tested: precision 1.00 for both cheap models, about 5 cents per run; recall 12 of 24 as designed.
- [x] Heading-aware reader Phase 1 run (tables and schedules). RESULT: NOT reliable yet. Labelled pages 24/24 after fitting; fresh holdout precision 0.33. Advisory use only.
- [ ] Reader revision plus a fresh, larger holdout (20+ pages, with more deadlines in it); the revised rule must pass it unseen.
- [ ] Fix inventory gaps: four alias sites, two script-built menus, a per-site language preference for h2meet.com.

## Stage 3 - Clean the data we already hold
- [x] Purpose audit of 39 stored deadlines: 9 confirmed, 1 mismatch, 16 absent, 12 unreadable. Three live rows written up.
- [~] 2026-10-01: upstream accepted and re-emitted; our merge guard (report mode on a DB copy) then applied to the live DB after backup (`cfp_monitor.pre-r6-20261001.db`): India Energy Week 2027 (date 10-15, verified by the audit), Climate Change (date 10-19), SecureWorld citation withdrawn. Far-side check passed; invariants pass. Global Energy Show pending (anti-bot wall). IS_PROJECTED unchanged on corrected rows; 2026 India Energy Week duplicate row remains. Tool fix: `scripts/apply_resolutions.py` now escalates on a block page (`tests/test_apply_resolutions_block_page.py`).
- [ ] (original line) Correct the Climate Change row and the three live rows (SecureWorld Gov & CI, India Energy Week 2027, Global Energy Show Canada 2027). Path chosen 2026-10-01: contract path. DRAFTED: `experiments/purpose_audit/CORRECTION-PACKAGE.md`. NOT YET: sent to upstream, applied, imported.
- [ ] Review the rest: 16 absent and 12 unreadable rows, almost all with passed deadlines; check which were never confirmed by a date (8 of the 12 status-layer-verified rows).

## Stage 4 - Spend less
- [ ] Sponsorship carry-forward: design, sign-off, test. Re-ask only Unknown rows or rarely; skip rows by status and context.

## Stage 5 - Wire it in
- [ ] A written plan, tests and a budget; a shadow run beside the current weekend job; compare; then switch.
- [ ] Re-enable the disabled tasks only if and when the prospect markets are wanted again.

## Stage 6 - Project control (so the operator can stay zoomed out)
- [x] Status board published (private Artifact), generated from `docs/design/status.json` by `scripts/status_dashboard.py`.
- [x] Standing strategy file `docs/design/STRATEGY.md` with the 5-line opener.
- [x] Agent brief template and three briefs: `docs/agents/`.
- [x] Agent channels checked 2026-10-01: Hermes works through `hermes -z` (one-shot, about 46 s); its MCP link timed out. OpenClaw installed, `openclaw agent -m` exists, not messaged yet.
- [x] Hermes 2-event test of brief 01 (`hermes -t web -z`, 2026-10-01): format right, blanks honest, trap dates avoided, consistent with our records; BUT only search snippets (page-read tool broken) and one wrong claim (called a redirecting URL a China mirror; it redirects to the Hamburg event site). 2 rows is not the 10-row success test.
- [ ] Benchmark built and spot-checked (brief 01). [ ] Platform census run (brief 02).

## Progress at 2026-10-01
Stage 0 done. Stage 1: the speed and grounding half is proven, the quality and field-coverage half is not. Stage 2: three of five items done. Stage 3: audit done, correction package drafted, awaiting send and apply.
Stages 4 and 5 not started. Rough share of the work finished: about one third (an estimate, not a measurement).

## 2026-10-01 later
- [x] Global Energy Show applied by operator ruling (operator confirmed the sentence on the live page; our built-in browser pane also read it and the Submit link `https://www.dmgeventsconferences.com/global-energy-show-2027/submitter/login`). Guard run with today's rendered page text because plain fetch and our browser rungs were walled; backup `cfp_monitor.pre-ges-20261001.db`; far-side check passed.
- [x] Whole-page model reader, ONE-page demo: DeepSeek chat on the Climate Change call page, 21 s, $0.0009: Regular 2026-10-19 and Late 2026-12-20 labelled submission, the three Registration rows labelled registration, every unit_text verbatim on the page. Early row mislabelled 'opens'. Not a measurement; the real test is brief 03 against the benchmark.

- [x] Whole-page reader experiment (approved cap 60 requests / 0.50 USD; spent 56 / 0.082): see `experiments/whole_page_reader/RESULT.md`. As run: precision 0.85, recall 9/12 on holdout + fresh (fails the 0.95 / 0.80 bar); 0 wrong-purpose in 69 accepted. Post-hoc: 0.875 / 11 of 12. Promising, not proven. Next: 40-event benchmark.
- [x] Hermes browser-toolset read test (Global Energy Show): passed, full page, exact sentence, correct link target (4m10s).
- [x] Hermes benchmark stage 1 (3 events with known answers, `hermes -t web,browser -z`, about 2 min): B01 closed/blank, B31 open 2026-12-04, B39 open 2026-10-19 with the Late round noted; all correct. Both quotes I had not seen were verified on their pages. Browser backend was down; it used its fetch tool. A premature 40-event launch was stopped within a minute of starting (operator caught it); the rollout ladder is now in docs/agents/README.md.
- [x] Global Energy Show submit link fixed by one-field operator edit (backup, guarded update, far-side check, integrity and invariants ok; logged in `experiments/purpose_audit/OPERATOR-EDITS-LOG.md`). Lasting fix is upstream's.
- [ ] Hermes benchmark stage 2 (5 new events: B02, B03, B04, B22, B23) NOT PASSED: 0 of 5 read, twice. Cause is tooling, not the agent: browser backend has no Chrome listening on 127.0.0.1:9222; page reader is a search-only backend. Hermes correctly returned honest 'unknown' for all five and refused to use search snippets as evidence. Needs the operator: start a debug Chrome, or provide an extractor key.
- [~] Offline page library built (`scripts/page_library.py`, 6 tests pass, indexed in TOOLING.md): 6-page trial clean through real Chrome (CDP); full 364-page fetch started 12:11, resumable. Next: report on usable pages, then run the whole-page reader offline over the library.
- [x] Offline page library COMPLETE 2026-10-01 16:5x: 364 planned = 360 distinct URLs; 350 usable (97%), 10 thin or soft 404, 0 blocked, 0 errors, 69 of 69 sites; 2.6 MB. The first run died at 12:50 (debug Chrome closed) and was resumed; it is resumable by design. Refresh policy designed and settled (docs/design/page-refresh-policy.md).
- [~] Whole-page reader over the offline library started 17:23 (approved: all usable pages, cap 0.60 USD / 420 requests). A detached job from the tool shell died at 17:44 after 136 requests; relaunched at 19:3x as an independent Windows process (Win32_Process.Create) and resumed. Lesson: long jobs must be launched that way, not from the tool shell.
- [x] Whole-page reader over the offline library COMPLETE 2026-10-01 20:1x: 347 pages, 0 errors, 0.453 USD (cap 0.60). 40 pages with a submission deadline; 18 dates still ahead on 9 sites; 16 of 18 look right on hand check, 2 false positives. Details: experiments/whole_page_reader/LIBRARY-RUN-RESULT.md.
