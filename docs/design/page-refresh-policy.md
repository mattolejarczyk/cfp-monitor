# Page refresh policy by event lifecycle (operator's idea, 2026-10-01; DESIGN ONLY, not built)

**Principle.** Fetch a page when a change on it would matter, not on a clock. The first full fetch of the page library is a one-time snapshot of all 364 planned pages. After that, each page refreshes according to its event's lifecycle category. The library already stores a timestamp and a sha256 per page and keeps older versions, so the policy needs only two added columns (`category`, `next_refresh_at`) and a scheduler.

## Categories, with today's counts (95 conferences in the two customer markets, latest edition each, as of 2026-10-01)
| | Category | Count | Refresh | Why |
|---|---|---|---|---|
| A | Call open: deadline still ahead | 3 | **weekly** (every 3 to 4 days in the last 14 days before the deadline) | The deadline can be extended or a round can open; this is what the customer acts on. |
| B | Event within 6 months, call closed or no deadline stored | 38 | **every 2 weeks**; weekly when no deadline is stored | These are the rows where a missing or stale date is still costing something; the event date can also move. |
| C1 | Event ended in the last 60 days (or is happening now) | 15 | **do not fetch** for 45 days after the event ends | Operator's rule: nothing useful changes just after an event. |
| C2 | Event ended more than 60 days ago | 25 | **monthly**, to catch the NEXT edition's announcement and call | Organisers usually post the next call soon after the event; we need to see the first sign of it. |
| D | Event more than 6 months away, call closed or no deadline | 10 | **monthly** | Low urgency, but dates and calls appear. |
| E | Unknown, TBD or not-announced dates | 4 | **every 2 weeks**, backing off to monthly after 3 fetches with no change | A date announcement is the one change that matters here, but waiting costs nothing, so do not hammer. |
| F | Discontinued or retired | n/a | **quarterly** | A revival is rare. |
These counts come from stored start dates and deadlines. 11 rows read "Needs Verification" and 11 "Upcoming"; those belong in B or E depending on whether a date is stored.

## Overlays (applied on top of the category)
- **Change detection backs off.** A page whose hash did not change on its last 3 fetches moves one step slower (weekly to every 2 weeks to monthly) and snaps back to its category rate the first time it changes. A sitemap `lastmod` newer than our last fetch triggers an early refresh.
- **Customer overlay.** A row the customer has already submitted, accepted or declined needs no research (`customer_context.py` buckets MOOT); a row marked Urgent on a customer sheet is raised one step. The existing weekly intake already records both.
- **Cost ceiling.** One full pass of 364 pages takes about 100 minutes through real Chrome, so a policy that refreshes about half of them each week keeps the weekly fetch under an hour and spreads hits across sites.

## Open decisions
1. Cooling-off after an event: 45 days as above (your range was 30 to 60).
2. Is a 6-month horizon right for category B, or should it be 4 months?
3. Do we treat "Needs Verification" with a stored deadline as B, or fetch it weekly until verified?

## Build order (after the first full fetch finishes and its report is read)
1. Add `category` and `next_refresh_at` to `page_library.db`; map each planned page to its event's category (host to conference keys through the inventory).
2. `--refresh-due` mode in `scripts/page_library.py`, with a test.
3. One shadow week: log what it would have fetched, compare with the weekend research list, then schedule it.
