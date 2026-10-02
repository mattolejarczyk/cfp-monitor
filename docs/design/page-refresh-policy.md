# Page refresh policy by event lifecycle (operator's idea, refined by the operator 2026-10-01; SHADOW PLANNER BUILT 2026-10-02, scheduler not built)

**Principle.** Fetch a page when a change on it would matter, not on a clock. The first full fetch of the page library is a one-time snapshot of all 364 planned pages. After that, each page refreshes according to its event's lifecycle category. The library already stores a timestamp and a sha256 per page and keeps older versions, so the policy needs only two added columns (`category`, `next_refresh_at`) and a scheduler.

## Categories, with today's counts (95 conferences in the two customer markets, latest edition each, as of 2026-10-01)
| | Category | Count | Refresh | Why |
|---|---|---|---|---|
| A | Call open: deadline still ahead | 3 | **weekly**, no more often than that | The deadline can be extended or a round can open; this is what the customer acts on. |
| B | Event within 6 months, call closed or no deadline stored | 38 | **every 2 weeks**; weekly when no deadline is stored | These are the rows where a missing or stale date is still costing something; the event date can also move. |
| C1 | Event ended in the last 60 days (or is happening now) | 15 | **do not fetch** for 45 days after the event ends | Operator's rule: nothing useful changes just after an event. |
| C2 | Event ended more than 60 days ago | 25 | **monthly**, to catch the NEXT edition's announcement and call | Organisers usually post the next call soon after the event; we need to see the first sign of it. |
| D | Event more than 6 months away, call closed or no deadline | 10 | **monthly when the call, speaker and abstract-submission dates are known; when they are not known, wait 45 days, then every 2 weeks until they are** (operator's decision, 2026-10-01) | Low urgency, but dates and calls appear. |
| E | Unknown, TBD or not-announced dates | 4 | **EXCEPTION BATCH, troubleshot weekly** (operator's decision, replacing the back-off idea): not a fetch schedule but a short list a person or agent works through each week to find out why no date is known (wrong page, no sitemap entry, site behind a wall, genuinely TBD) | These rows will not fix themselves by refetching; the cause has to be found. |
| F | Discontinued or retired | n/a | **quarterly; once a row has been discontinued for more than 2 years, never crawl it again** and mark it discontinued | A revival is rare; after 2 years it is not worth the visits. |
These counts come from stored start dates and deadlines. 11 rows read "Needs Verification" and 11 "Upcoming"; those belong in B or E depending on whether a date is stored.

## Overlays (applied on top of the category)
- **Change detection backs off.** A page whose hash did not change on its last 3 fetches moves one step slower (weekly to every 2 weeks to monthly) and snaps back to its category rate the first time it changes. A sitemap `lastmod` newer than our last fetch triggers an early refresh.
- **Customer overlay, written for more than one customer (operator, important).** A row is skipped only when NO customer still has it open: it must be submitted, accepted or declined (or withdrawn) for EVERY customer who tracks it. If any one customer still has it open, it keeps its category rate. A row marked Urgent by ANY customer is raised one step. Today there are two customers on separate markets, and one conference can sit in more than one market, so this is not hypothetical. `customer_context.py` buckets a row from one customer sheet at a time; the scheduler must combine them across all sheets, not take the first.
- **Cost ceiling.** One full pass of 364 pages takes about 100 minutes through real Chrome, so a policy that refreshes about half of them each week keeps the weekly fetch under an hour and spreads hits across sites.

## Open decisions
1. Cooling-off after an event: 45 days (inside your 30 to 60 range). Confirm.
2. (Settled 2026-10-01) Category D: dates known gives monthly; dates not known gives no fetch for 45 days, then every 2 weeks (not monthly) until known.
3. 6-month horizon for B: keep 6 months (your wording) unless the first shadow week shows it is too wide.

## Build order (after the first full fetch finishes and its report is read)
1. Add `category`, `next_refresh_at` and an `exception` flag (for E) to `page_library.db`; map each planned page to its event's category (host to conference keys through the inventory).
2. `--refresh-due` mode in `scripts/page_library.py`, with a test.
3. One shadow week: log what it would have fetched, compare with the weekend research list, then schedule it.


## Status 2026-10-02
`scripts/refresh_planner.py` implements the categories and overlays above as a report-only shadow planner (tests in `tests/test_refresh_planner.py`). It fetches nothing and adds no columns to `page_library.db`. On live data: 95 conferences in the two markets (as designed); categories A 4, B 25, C1 12, C2 22, D 6, E 1, F 3, SKIP (every customer done) 22. The shadow-week comparison (plan vs what the weekend research actually looked at) is the next step; build order items 1 and 2 (columns in the library, `--refresh-due` in `page_library.py`) wait for it. Open: whether a row every customer has finished (SKIP, 22 today) should still be watched for the NEXT edition, as the policy text says it is skipped only while every customer is done.
