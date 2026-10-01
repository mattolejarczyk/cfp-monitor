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
- [ ] Correct the Climate Change row and the three live rows (SecureWorld Gov & CI, India Energy Week 2027, Global Energy Show Canada 2027). Path chosen 2026-10-01: contract path. DRAFTED: `experiments/purpose_audit/CORRECTION-PACKAGE.md`. NOT YET: sent to upstream, applied, imported.
- [ ] Review the rest: 16 absent and 12 unreadable rows, almost all with passed deadlines; check which were never confirmed by a date (8 of the 12 status-layer-verified rows).

## Stage 4 - Spend less
- [ ] Sponsorship carry-forward: design, sign-off, test. Re-ask only Unknown rows or rarely; skip rows by status and context.

## Stage 5 - Wire it in
- [ ] A written plan, tests and a budget; a shadow run beside the current weekend job; compare; then switch.
- [ ] Re-enable the disabled tasks only if and when the prospect markets are wanted again.

## Progress at 2026-10-01
Stage 0 done. Stage 1: the speed and grounding half is proven, the quality and field-coverage half is not. Stage 2: three of five items done. Stage 3: audit done, correction package drafted, awaiting send and apply.
Stages 4 and 5 not started. Rough share of the work finished: about one third (an estimate, not a measurement).
