# Sponsor check: cost-cutting plan (DRAFT for the operator, 2026-10-11)

Status: PLAN ONLY. Nothing is built, nothing is changed. Numbers are estimates from our own run logs, at Google's list price for grounded search (about 14 USD per 1,000 search queries, before any free allowance). The real bill is on the AI Studio spend page.

## 1. What the sponsor check is, and what it costs

- After each weekly research, a second pass asks one question per event: does it require paid sponsorship, and what does it cost (SPONSOR_REQUIRED, SPONSOR_URL, SPONSOR_COST). It runs for Cybersecurity (Arnica) and Utility (Global) only. The customer sees the answer in the "sponsor required" column and, since ruling R-002, an "unconfirmed" badge when we cannot prove it.
- Each check is one grounded request that runs about 13 to 15 Google searches. The research request for the same event runs about 8.
- Saturday 2026-10-10 (one cycle): about 235 sponsor requests, about 3,100 searches, about 44 USD at list price. Over 3-10 October the sponsor checks were about half of all grounded searches (about 5,000 of 8,900).

## 2. Why it costs this much (root cause, verified in the code)

The check was designed NOT to re-ask settled answers. The comment in `Markets/run_market_audit.py` (run_sponsor_only_pass) says a row already marked Yes or No "is written straight through for free, so a weekly re-run against last week's own output only ever pays for rows still Unknown".

That never happens in the weekly cycle. Every Saturday `run_monthly.ps1` moves last week's audited file into the archive, the new research file starts with the sponsor cells BLANK, and the pass therefore sees every row as "Unknown" and pays for all of them. Last week's answers are only put back AFTER the fact (scripts/sponsor_carry.py, option A: "never lose a known answer"), so we pay to re-ask and then keep the old answer anyway.

Measured on the 2026-10-10 research against last week's approved files (read-only):

| | Arnica | Utility | Total |
|---|---|---|---|
| rows checked | 134 | 85 | 219 |
| answered last week (Yes/No), same edition: could be skipped | 60 | 44 | **104** |
| new event, no prior answer: must ask once | 66 | 38 | 104 |
| prior answer was Unknown or blank: ask again | 8 | 3 | 11 |

So 47 percent of this week's sponsor spend repeated an answer we already held. The 104 "new" events are a one-time cost: asked once, they are answered next week.

## 3. The proposal

One small step BEFORE the existing sponsor pass: copy last week's settled sponsor answer into the new research file for rows that qualify. The existing pass then skips them by its own rule. We do not change the research prompt, the gate, the badge, or the quote extraction.

A row is carried (not asked) only when ALL of these hold:
1. the event has the same permanent id (matched with `identity.to_canonical`, never by name) and the same edition as last week's row;
2. last week's SPONSOR_REQUIRED is Yes or No (Unknown and blank are always re-asked);
3. for Yes: the stored SPONSOR_URL is present and is not RECORDED DEAD in `link_checks`. REVISED 2026-10-11 (reviewer): a sponsor URL with NO `link_checks` record is carried, because the weekly sweep does not cover `sponsor_url` yet and the first rule would have re-asked 87 of 104 settled Yes rows; the 8-week rotation is the safety net. A blank URL on a Yes, or a recorded-dead URL, forces a re-ask. The strict behaviour (a missing record asks) is one switch away (`--missing-link-asks`, default off) for when the Sunday sweep covers sponsor_url;
4. it is not due for a periodic re-check (section 4).

A row is asked when any condition fails. First-time events are always asked. Sources for last week's answer, in order: the approved file (`<Market>_audited.final.csv`), then the previous cycle's archived audited file, so an event that failed the gate and never shipped keeps its answer instead of being re-bought every week.

## 4. How we still notice change (the safety rail)

A settled answer can change (a No becomes a paid prospectus; a fee changes). So carried rows are re-checked on a rotation, not never: each settled row is re-asked about every N weeks, spread evenly by a fixed hash of the id so the cost is level, not a spike. CORRECTED 2026-10-11: the ACT-17 ledger (`carry_ledger.json`) does NOT age rows carried by the prefill (the import sees a filled answer as fresh and drops the ledger entry), so it is only an extra safety net (used when an entry exists, 8 weeks or older forces a re-check); the rotation by a fixed hash of the id alone guarantees every settled answer is re-asked within 8 weeks. Also re-asked at once: a changed edition, a dead sponsor link, and any row the operator names. An Unknown answer is re-asked every 2 weeks (it usually stays Unknown, so weekly is wasteful).

DECISION FOR THE OPERATOR: N. Shorter is safer, longer is cheaper (estimates in section 5).

## 5. Expected saving (estimates)

Per-check cost is about 13 to 15 searches, about 0.19 USD at list price.

| Policy | Checks per Saturday (steady state) | Sponsor cost per Saturday | Saving vs today (about 44) |
|---|---|---|---|
| today | 219 | about 44 | none |
| carry only, no periodic re-check | about 20 (unknown + new) | about 4 | about 40 |
| carry + re-check every 8 weeks | about 45 | about 9 | about 35 |
| carry + re-check every 6 weeks | about 52 | about 10 | about 34 |
| carry + re-check every 4 weeks | about 68 | about 13 | about 31 |

The first Saturday after the change saves less (about 20 USD) because new events must still be asked once. These are estimates built from the 2026-10-10 counts; the real figure depends on how many events are added or change.

What the customer notices: nothing in the normal case. The only risk is a sponsorship change that is up to N weeks late.

## 6. Other levers (not part of this plan, listed so nothing is lost)

- Stop researching AND sponsor-checking customer events that cannot ship yet. ACT-63 now loads most of them; the 16 that fail the gate each week still cost money. The archive-as-source rule in section 3 removes their sponsor cost.
- Apply the dormant-event skip that already saves about 34 percent on awards to conferences (ACT-33). That cuts research and sponsor cost for closed events whose next edition is far away.
- A cheaper model or a cap on searches per request for the sponsor question. Not tried; needs a bake-off on our own answer key before anyone trusts it.

## 7. How it would be built and checked

1. A builder (own worktree, not the live folders) writes `scripts/sponsor_prefill.py` with tests: carry rules, dead link forces re-ask, edition change forces re-ask, Unknown re-asked, rotation level and deterministic, archive fallback, nothing written when anything is unclear, failure isolated (an error means "carry nothing", i.e. today's behaviour).
2. A dry run on the real 2026-10-10 files, no API calls, reproduces the table in section 2 and lists every row it would carry and ask. We read that list.
3. A one-line addition to `run_overnight.ps1` calls it before the sponsor pass. That script is the live scheduled job's, so the operator runs the apply script (the permission classifier blocks my edits of live scripts), with a backup, as for the `-Resume` switch.
4. First live Saturday: the log prints how many rows were carried and how many asked; the reviewer reads it and the spend. Rollback = copy the backup back.
5. Docs travel with it: TOOLING row, QA-REGISTER row, WEEKEND-PROCESS step.

Target: built and rehearsed during the week of 12 October, applied before Saturday 17 October 02:00 if the dry run looks right. It saves nothing until applied.

### 7a. What was built (ACT-64, 2026-10-11) - written after the build, numbers from our own dry run

- `scripts/sponsor_prefill.py` (test `tests/test_sponsor_prefill.py`, 33 tests plus a check that the unchanged pass skips carried rows). Default is a dry run; `--apply` writes only SPONSOR_REQUIRED, SPONSOR_URL and SPONSOR_COST of carried rows (backup, read-back proof). Settled answers: 8-week rotation by a fixed hash of the permanent id (about 1/8 per Saturday, none twice in a window) plus the carry-ledger date as a safety net; Unknown: 2-week slot. Not live: the one-line call is in `docs/control/patches/ACT-64-run_overnight.ps1.patch` for the reviewer to apply.
- Dry run on read-only copies of the 2026-10-10 files (last week's approved = the pre-promote files named in the brief; the new file = the 2026-10-10 audited file with the four sponsor cells blanked, because the live file already holds the answers the pass wrote; no model call, no network). Reproduced exactly: new events 66 + 38 = 104. Settled-and-same-edition (the plan's 60 + 44): 61 + 44 = 105 here (one more than the plan in Arnica; the plan's own query is not recorded, so the one row is unexplained). Unknown or blank: 7 + 3 (plan: 8 + 3).
- **What would have stopped the saving, found by the dry run (and the reason rule 3 was revised, see below):** a Yes may be carried only if its SPONSOR_URL is alive in `link_checks` (rule 3). The weekly link sweep (`weekly_verify.py`, `CUSTOMER_FACING`) does not include `sponsor_url`, so 87 of the 104 settled Yes rows (52 of 60 Arnica, 35 of 44 Utility; 1 more is recorded dead) have no entry and are asked again. As the data stands the first Saturday would carry only 13 of 219 rows. With the sponsor pages recorded alive (simulated on a scratch copy of the database, to show the ceiling) it carries 55 + 36 and re-asks 6 + 8 that fall due (the 11 October slots): about 91 of 219 carried on the first Saturday, and a steady state of about 45 asked per Saturday after the 104 new events have been asked once (the plan's estimate for N = 8). Covering `sponsor_url` in the Sunday sweep (a one-word change in `weekly_verify.CUSTOMER_FACING`, not made here) would let the strict switch be turned on later. REVISION (reviewer, 2026-10-11): rule 3 now carries a Yes whose sponsor link has no `link_checks` record and asks only for a blank or recorded-dead link; the strict rule remains as `--missing-link-asks`. Dry run again on the same read-only copies (11 October slots): Arnica 55 carried (46 of them with the link not recorded), 79 asked = 66 new + 7 Unknown + 6 due for the rotation; Utility 35 carried (31 not recorded), 50 asked = 38 new + 3 Unknown + 8 due + 1 recorded-dead link. Total 90 of 219 carried, 129 asked; the following Saturdays (18 and 25 October slots) carry 96 and 90. Estimates for money: about 90 fewer checks on the first Saturday (about 17 USD at about 0.19 USD each), then a steady state of about 45 asked per Saturday (about 9 USD).
- **Second limit (unchanged):** the existing pass treats every blank or Unknown cell as pending, so Unknown rows cannot be skipped. The 2-week Unknown rotation is computed and reported (`unknown_deferred`) but those rows (about 11, about 2 USD a week) are still asked every week until `run_market_audit.py` (upstream's file, outside this work) is changed.
- The carry ledger (ACT-17) only records values carried by `sponsor_carry` after the fact. A row carried by this script looks FRESH to the import, so its ledger entry is dropped; the 6-week "carried values not re-confirmed" flag therefore does not age these rows. The rotation alone guarantees the 8-week re-check (this corrects the earlier remark that the ledger supplies the last-confirmed date).

## 8. Decisions (made by the operator, 2026-10-11)

1. Re-check cadence N for settled answers: **8 weeks** (expected steady cost about 9 USD per Saturday, saving about 35 USD).
2. Unknown answers: re-asked **every 2 weeks**.
3. Build approved as ACT-64 (zero spend to build). Applying it to the live job still needs the operator to run the apply script and is not done until the dry run has been read.
