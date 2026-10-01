# Site page-discovery (sitemap + navigation inventory) - design

Drafted 2026-09-30. **DESIGN ONLY. Nothing here is built or wired.** Follows the experiments rule: one change at a time,
copies only, advisory before anything writes, a written RESULT per phase.

## 1. Why
The grounding-reliability work found that the answers are mostly right (deadline correct 33 of 33) but about a third of the
citations point at the wrong page: a listing page, the homepage, a different conference's site, an invented variant of a real
path, or a consent shell. The strict tracer then wasted 16 of 20 page visits wandering menu links by keyword. Discovery is the
weak step, not matching. HANDOFF already records that "no sitemap step exists anywhere in the joint process", and Gap 5
(next year's editions) needs an early signal that a site has published something new.

## 2. What exists / what is missing
Exists: `src/cfp_monitor/sitewalk.py` (`sitemaps_from_robots`, `sitemap_candidates`, `parse_sitemap`, `rank_links`, `plan`,
`NOT_A_PAGE`, a last-resort `fallback_urls`); `scripts/check_urls_against_site.py` (read-only: robots -> sitemaps, one index
level, cap 4000 URLs, soft-404 test, call-like scoring); the `evidence` table (per claim: field, source_url, quote, method);
`fetch._render_with_consent` (browser ladder); `cdp` protections for hard anti-bot domains.
Missing: (a) nothing is STORED - every look is forgotten; (b) no change detection; (c) nothing creates an inventory for a site with
no sitemap; (d) nothing links a page to the fields it supplies; (e) sitemaps of multi-event platforms are not scoped to one event.

## 3. Measured feasibility (17 sites from the test sample; plain HTTP, no AI; `experiments/sitemap_discovery/measure.json`)
| | Count |
|---|---|
| Sites with a usable sitemap (robots-named or conventional path) | 11 of 17 |
| ...named in robots.txt | 8 of 17 |
| ...with `lastmod` dates in the first sitemap | 7 of 17 |
| Sites listing pages that mention 2027 | 4 of 17 |
| No sitemap at all | 6 of 17 (incl. OFC, ECTC, SecureWorld www - three of the problem sites) |
| Sitemaps that hit the 4,000-URL cap (multi-event platforms: SecureWorld events, Informa, AACR, SSCS) | 4 |
| Model-cited URLs present in the site's own sitemap, sites WITH a sitemap | 7 of 14 |
Reading: a sitemap covers about two thirds of sites; it would have caught the invented Commodity Classic path; half of cited URLs on
sitemap sites are not in the map (some are redirects or trailing-slash variants, so "not listed" is a flag, not a verdict).
The sites with NO sitemap include the worst offenders, so navigation crawling is required, not optional.

## 4. Design
### A. Store (additive tables, never on `conferences`)
- `site_profile(site_origin, events_served, sitemap_urls, sitemap_how, has_lastmod, multi_event_platform, scope_prefix,
  nav_only, anti_bot, last_fetched, last_changed)`
- `site_pages(site_origin, url, source[sitemap|nav|cited], page_type, first_seen, last_seen, lastmod, status[live|gone|redirect|soft404], content_hash)`
- `page_fields(url, field, event_id, last_used, last_verified)` - a VIEW over the existing `evidence` table where possible.

### B. Discovery ladder (never invent a page)
1. `robots.txt` -> named sitemaps (follow indexes; raise the current one-level / 4,000 cap, per-site).
2. The conventional sitemap paths (a published convention with one right answer; a wrong guess fails to parse as XML).
3. No sitemap: build OUR OWN inventory from the site's real navigation - homepage + menu links, depth 2, at most 100 pages,
   through the existing fetch ladder. Stored with `source='nav'`. Run on first sight and then monthly, not weekly.
4. Still nothing (JS shell, blocked, anti-bot): mark `undiscoverable` and route to a person. No guessed paths.

### C. Scope
Platform sitemaps (events.secureworld.io had 4,000+ entries) are cut to the event's own sub-path or sub-domain using its known URL;
an event is never allowed to claim another event's pages (the CO2 answer that cited a different conference's site).

### D. Page typing (deterministic, no AI)
Type each page from URL + menu label + title using the existing keyword sets: call-for-speakers, important-dates, programme,
sponsorship, registration, awards, other. Known trap: a listing page where a date beside a name is the date the event is HELD
(SecureWorld /events) is typed `listing` and can never be evidence for a submission deadline.

### E. Change detection (weekly, cheap)
Per site: re-fetch robots + sitemap files with conditional requests (ETag / If-Modified-Since). Diff against `site_pages`:
new URL, removed URL, changed `lastmod`. No `lastmod`: compare URL sets, and hash only the pages typed call / dates.
Emits events: NEW_PAGE(type), PAGE_CHANGED, PAGE_GONE, NEW_EDITION_HINT (a new URL or title naming next year). The hint feeds
Gap 5 (R13-R15); this step NEVER mints an id or edits a row.

### F. Consumers (each advisory first)
1. Citation check: a cited URL must appear in the site's inventory or be reachable from its nav; otherwise flag "not in the site's
   own map" (soft 404 and consent-shell tests reused from `check_urls_against_site`).
2. Retarget proposals: for a row whose cited page lacks the date, read the inventory's typed pages (call / dates) with the
   existing renderer and test for the date with the existing date matcher; propose a better page. Writing it back stays a
   separate evidenced step (existing rule). The AI sentence-picker (`extract_citations`, model picks, code proves) applies after.
3. Successor detection for Gap 5 (NEW_EDITION_HINT).
4. Research can be told which pages to read instead of searching blind (later, out of scope here).

### G. Website intelligence page
One read-only HTML page like the evidence matrix: per event - site profile, inventory size, page-type coverage, which page supplied
each field (from `evidence`: source_url, method, last verified), and the change log. Answers "where does this data come from and
did that page change".

## 5. Cost
No AI in discovery, diffing or typing. Weekly traffic is plain HTTP: about 2-15 small requests per site for robots + sitemaps
(conditional requests mostly return "not modified"). The site count for all 401 conferences is NOT measured; the sample had 17 sites
for 12 events, so expect a few hundred. Rendering happens only for new or changed typed pages (a few dozen a week, estimate).
Navigation crawls (no-sitemap sites) are the expensive part: up to 100 pages at ~12 s each is ~20 min per site, so first sight
and monthly only, paced per host, never hammering anti-bot hosts.

## 6. Guardrails
Respect robots.txt and crawl-delay; one request stream per host; hard anti-bot domains are not auto-crawled (existing IP-protection
rule); never solve CAPTCHAs; never guess content paths; inventory lives beside the DB in its own tables with a backup before any
schema change; no customer detail in this public repo; nothing writes to `conferences`, deliveries or the research inputs.

## 7. Phases (each its own experiment with a RESULT.md)
P1 Inventory on the 17 sample sites into a COPY of the DB: sitemap sites via step B1-2, the 6 others via nav (measure pages found,
   time, failures). P2 Use the inventory on the 27 missed citations: does a typed call / dates page holding the date exist for
   the 10 "date not on the cited page" rows? Success = a correct page found for most. P3 Weekly diff dry-run: two snapshots a week
   apart, check new-page and 2027-hint events are real. P4 Website intelligence page. P5 Hook to Gap 5.

## 8. Decisions needed
(1) Scope: start with the two customer markets (Cybersecurity, Utility) or all markets. (2) Page cap per no-sitemap site (100?).
(3) Store page-text hashes (enables change detection on sites without lastmod) - yes/no. (4) Inventory in the live DB or a separate
file beside it. (5) Who acts on NEW_EDITION_HINT before Gap 5's rules exist.
