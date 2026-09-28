# Experiments - research-quality gaps (opened 2026-09-28)

**Nothing in this folder is wired into a scheduled job.** Each gap is explored on its own, on
copies and samples, against a fixed baseline, and only proposed for the real pipeline once its
result is proven on its own merit. Operator rule, 2026-09-28: keep each change separate so one
change's effect cannot be confused with another's.

## Rules for every experiment here

1. **One change per experiment.** Never combine two gaps' ideas in one test run.
2. **Fixed baseline.** Compare against the 2026-09-27 research (`Markets\Cybersecurity_audited.csv`,
   `Utility_audited.csv` and their `.grounding.jsonl`) unless the plan says otherwise.
3. **Copies only.** No write to the live database, the approved `.final.csv` files or the
   research input lists. Outputs go in the experiment's own folder.
4. **State the cost before spending.** Any AI request needs a stated budget, agreed first.
5. **Written result.** Each folder ends with `RESULT.md`: the numbers, what it proves, what it
   does not, and a recommendation - adopt, change, or drop.

## The gaps (baseline = the 2026-09-27 research, 113 rows, ~280 AI requests)

| # | Gap | Baseline | Folder |
|---|---|---|---|
| 1 | Made-up links | 27 of 89 researched rows cite a page on a site the search never visited | `gap1_real_links/` |
| 2 | Paraphrased quotes | quotes rewritten rather than copied; unprovable word for word | `gap2_verbatim_quotes/` |
| 3 | Answering from memory | 89 of 178 successful answers ran no search (~32% of spend) | `gap3_search_every_time/` |
| 4 | Rows never researched | 24 of 113 (4 avoidable by the tree; ~98 Google 504 timeouts) | `gap4_stubs/` |
| 5 | Next year's editions not picked up | 41 past events re-researched as the old edition; successors visible but not captured (contract R13-R15 never built) | `gap5_next_edition/` |

Status of each is kept in its `PLAN.md` and reported in every update until resolved.
