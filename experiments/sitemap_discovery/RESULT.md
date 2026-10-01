# RESULT - sitemap discovery for the two customer markets (2026-09-30)

Scope: Cybersecurity + Utility only (operator decision; other markets are speculative and on hold). Page cap per site: 50.
NO page crawling: robots.txt and sitemap XML only, plain HTTP, 1.5 s between requests. Script `customer_markets_sitemaps.py`;
raw results `customer_markets.json`, log `customer_markets_log.txt`. Read-only; nothing written to the DB.

## Findings (84 distinct sites)
| | Sites |
|---|---|
| Sitemap found | 48 (57%) |
| ...named in robots.txt | 39 of 48 |
| ...with lastmod dates | 44 of 48 |
| ...hit the 20,000-URL safety cap | 1 |
| No sitemap found | 36 (43%) - Cybersecurity 24 of 38 sites, Utility 12 of 46 |
| Sitemap sites listing pages that name 2027 | 18 of 48 (62 pages) |
"No sitemap found" means robots.txt and the conventional paths returned nothing over plain HTTP; a site that answers 403 to scripts
would look the same. NOT yet separated. The 36 include blackhat.com, defcon.org, gartner.com, usenix.org, first.org, secureworld.io,
ceraweek.com, adipec.com, infosecworldusa.com, events.reutersevents.com (hard anti-bot), cloud.withgoogle.com.

## Pages per site that qualify for crawling (48 sitemap sites, rules below)
Qualifying pages per site: median 24.5, 75th percentile 438, max 4,015. 4 sites 0; 22 sites 1-50 (fit under the cap); 22 sites over 50.
At a 50 cap the crawl would be 1,463 pages (Cybersecurity 397, Utility 1,066).
**But the rules are far too broad.** Of 21,526 qualifying pages: P1 call/submission 202 (1%), P2 programme/awards/speakers 10,576,
P3 sponsor/exhibit/partner 9,564, P4 edition/venue 1,184. The big counts are speaker / contributor / exhibitor profile pages.
Among sitemap sites: 17 of 48 have ZERO P1 pages, 26 have 1-10, 5 have 11-50, none over 50. So the pages we actually want are few.
Dropped before scoring: 11,529 files, 10,567 generic (legal, privacy, login, news, blog...), 88 assets, 16 other-language.

## Rule defects seen in the samples (to fix before any crawl)
- Substring matching: "cfp" matched inside a company slug (`...carbon-compliance-cfp-energy`), "author" matched `not-authorized`.
- Profile pages (`/contributor/`, `/speaker/<name>`, `/exhibitor/<company>`) match "speaker"/"partner"/"sponsor" and swamp the tiers.
- Platform scoping used the first path segment of the event URL, which can be a language or section (`/en-us`, `/events`,
  `/training-events`) and, for isc2.org (`/congress`), matched 0 pages and fell back to the whole site.
- News is dropped as generic, which also drops announcements like "2027 dates announced".
- Not stored: the full URL lists were not saved (only 5 samples per site), so re-scoring needs a re-fetch.

## UPDATE - inventory saved, rules v2, menu vs map (same day)
Correction to the figures above: the first pass counted image entries (`image:loc`) inside sitemaps as pages (one checked sitemap:
364 address tags = 138 pages + 226 images), so "URLs listed" was inflated; `sitewalk.parse_sitemap` has the same flaw (not changed).
Inventory: `site_inventory.db` (local, this folder only): 71,540 real-page URLs from 48 sitemaps (an earlier draft of this note said
73,636; that figure wrongly included menu links), plus 3,744 homepage links with their zone (menu / header / footer / body) for
79 of 84 homepages. 5 not readable: bsidesaustin.org, devseccon.com, connectinghydrogeneurope.com,
futurefuelsmena.com (thin pages) and events.reutersevents.com (skipped on purpose - hard anti-bot protection).
Rules v2 (`rules_v2.py`): whole-word matching; profile/detail pages dropped (a page under /speakers/, /exhibitors/, /sessions/ ...);
"family collapse" (8+ siblings under one named parent: children dropped, index kept); long slugs and deep paths dropped; per-tier
budgets (P1 all up to 50, P2 10, P3 3, P4 5; total 50).
Result: pages that would be crawled = 439 (was 1,463 with v1). Per site: median 4, 75th percentile 7, max 34; 18 sites select 0,
56 select 1-10, 10 select 11-34. By tier: P1 call/submission 85, P2 programme/dates/awards 203, P3 sponsorship 128, P4 next-edition 23.
By market: Cybersecurity 161 pages, Utility 278. Avoided: 32,102 profile/detail and family-child pages, 5,912 long-slug articles,
6,286 too-deep paths, 11,747 news/blog, 9,622 generic.
Menu vs map (pages the v2 rules keep, 745 in all): map only 492, menu only 132, both 100, homepage body/footer only 21. For the
call/submission pages (85): map only 56, menu only 15, both 10, body/footer only 4. By site: a call/submission page was found at only
29 of 84 sites (menu reaches 18, map 16, both 7, menu-only 11 - mostly sites with no sitemap, e.g. Black Hat, Gartner, SHMOOCON,
OffensiveCon; map-only 9). No call page was found at 55 sites by either method; menus on the ones inspected list agenda / speakers /
sponsors / registration with no call link at all. Median menu size: 21 navigation links.
Rule quality still weak (inspected samples): isc2.org selects a nomination committee, exam schedules and award winners;
sans.org selects work-study and state-local "program" pages; nullcon.net selects CFP pages for 2014, 2016, 2017 (stale editions).
Menu link TEXT was not stored, only URLs; the link label ("Call for Speakers") often says more than the address.

## UPDATE 2 - rules v3 + menu link text, full comparison (`rules_v3.py`, `collect_menu_labels.py`, `analyze_v3.py`, `analysis_v3.json`)
v3 = v2 + stale-year drop (pages naming only years before 2026), narrower P2 (bare "program" needs event context), noise terms
(exam, committee, winners, membership, course ...), and scoring on menu link TEXT (a label can rescue a page the address rules call
"no keyword" and can upgrade a tier; it never rescues stale, noise, profile, family-child, too-deep or long-slug pages).
Link text captured for 76 of 84 homepages (3,405 links). Unreadable: bsidesaustin.org, devseccon.com, connectinghydrogeneurope.com,
futurefuelsmena.com, events.reutersevents.com (skipped, anti-bot protection), ushydrogenforum.com (text but no links; failed a retry).
| | v1 | v2 | v3 |
|---|---|---|---|
| Pages to crawl in total | 1,463 | 439 | 360 |
| Per site: median / p75 / max | - | 4 / 7 / 34 | 4 / 6 / 15 |
| Sites selecting 0 / 1-10 / 11+ | - | 18 / 56 / 10 | 17 / 60 / 7 |
By tier (v3): P1 call/submission 61, P2 programme/dates/awards 151, P3 sponsorship/exhibit 127, P4 next-edition hint 21.
By market: Cybersecurity 109 pages, Utility 251. Pages kept only through link text: 24; found by both address and text: 170; address only: 415.
Sites with a call/submission page: 29 (v2) -> 30 (v3); link text found the call page on 3 sites (for example sans.org "Speak at a
Summit"). 54 sites still have none. Where P1 pages were found: menu 18 sites, map 15, both 7, menu only 11, map only 8.
On the menus of the 46 no-call sites with readable text, the commonest wording is exhibit / sponsor / partner (over 100 links), register,
and "Speakers" (a directory of speakers, 26 links). Real call links missed by the label rules: h2meet.com "JOIN AS A SPEAKER",
troopers.de "Contribution", first.org "Participate". So most of the 54 appear to have no call link in either the menu or the sitemap now
(consistent with next-year calls not yet open), not a wording problem; 2-3 sites are a wording gap.
Residual false positives in v3: `/about/cfp-review-board/` (nullcon.net), `/en/products/proposal-review` (gartner.com); the same call page
appears twice on blackhat.com (two address forms); nullcon.net still lists `nullcon-goa-15` (a 2-digit edition year).

## UPDATE 3 - v3.1 frozen, two defects found by the crawl test, crawl test result (2026-10-01)
v3.1 (`rules_v31.py`, `plan()` = all four fixes): removed 4 false/stale pages and 10 duplicates (each with a surviving twin), added 2 real call
pages (h2meet.com, troopers.de); no legitimate page lost.
Defects found by running real pages (both fixed):
1. Relative menu links were resolved against the bare site address instead of the page the browser landed on. h2meet.com redirects to
   /html/ko/main.php, so `speaker.php` became /speaker.php (404). Fixed in `collect_menu_labels.py` (`doc_base`); all menu rows re-collected
   (old rows kept in `site_pages_menu_v1`). Link filtering also now compares against the landed domain.
2. Redirect aliases: carboncapture-expo.com -> hydrogen-worldexpo.com, cloudsecurityexpo.com -> techshowlondon.co.uk,
   sustainablefuelsglobal.com -> safeusummit.com, cloud.withgoogle.com -> cloud.google.com. Their menus belong to another domain; their
   sitemaps were fetched from the alias address and are suspect. Flagged, not fixed. hceeweek.com and ushydrogenforum.com return no links
   (script-built menus); need a manual look.
3. The "8+ siblings = family" rule treated a site's whole home folder as a profile directory (h2meet: everything under /html/ko/). Fixed: a
   parent holding more than 60% of a site's pages, whose name is not a directory word, is the home folder.
Final numbers (frozen v3.1, corrected inventory): 364 pages to crawl in total; per site median 4, p75 6, max 15; 14 sites select 0, 63 select
1-10, 7 select 11-15. Tiers: call/submission 59, programme/dates/awards 149, sponsorship 127, next-edition hint 29. Sites with a call page
31 of 84 (Cybersecurity 16 of 38, Utility 15 of 46): menu reaches 19, map 15, menu only 12, map only 8, both 7.
Crawl test (6 customer-market sites with a database deadline, 23 pages read, 2 s apart): the correct call page was selected at 6 of 6 sites
(ccus-expo /call-speakers, actexpo /call-for-speakers, sans /speak-at-a-summit, blackhat /call-for-papers.html, troopers /contribute,
h2meet /speaker.php). Only 3 of 6 sites show a date near call wording on a selected page; the known deadline was found at 1 of 6 (blackhat).
5 of the 6 known deadlines are already past, so the pages have probably rolled to the next cycle: recall is NOT a fair test here. h2meet.com
is in Korean (see below). Of 23 pages, 4 showed a date near call wording; sponsorship pages (P3) are for the sponsorship field, not measured.
LANGUAGE: h2meet's Korean pages carry ~9,600 Hangul characters, 1 English call word and Korean-style dates ("2026년 9월 1"), which none of
our English checks read; the English twin (/html/en/) has ~23 English call words. Rule needed: prefer the English version of a site when one
exists; otherwise flag the site as non-English for a language-aware reader.

## UPDATE 4 - language-rule validation (2026-10-01; operator: test before adding a rule)
Prevalence (structure only): 13 of 84 sites have a language folder in their pages; 3 show a language-switch label in the menu; only 1 site
(h2meet.com) has SELECTED pages in a non-English folder: 5 of 364 pages. Sites that are non-English at the same addresses (no folder) are not
measured (homepage text was not stored).
Validation on that one site (`crawl_test.py --sites h2meet.com --swap ko=en`): the Korean pages gave 0 of 5 useful pages (no English call
wording, Korean-style dates); the English twin gave 3 of 5. The English speaker page does state the deadline: "Speaker Registration - 1st:
7/1 ~ 8/31 - 2nd: 9/1 ~ 9/30", which matches our database (2026-09-30), but our date check missed it because it needs a year: year-less
month/day and "~" ranges are not recognised. So the language gain is real and so is a date-format gap.
Recommendation recorded: do not build a general prefer-English rule on one site; set a per-site preferred language path for h2meet.com and
revisit if more non-English sites appear. Add year-less M/D and range date formats to the page date check.
Open deadlines for a fair recall test (customer markets, deadline >= 2026-10-01): only 3: SecureWorld Government & Critical Infrastructure
(2026-10-28), Global Energy Show Canada 2027 (2026-12-04, not verified), International Conference on Climate Change (2026-12-19).

## UPDATE 5 - date reader v2 and re-score of the 23 pages (`dates_v2.py`, `rescore_dates.py`, `crawl_pages.json`, `rescore_dates.json`)
`dates_v2.find_target` reads year-less month/day, "~" ranges, East-Asian, dotted European and German/French/Spanish/Italian month forms, with a
confidence per match (with-year / yearless / yearless-noyr / ambiguous). Two precision defects were caught by inspecting the first re-score and
fixed: (1) a date followed within 12 characters by a DIFFERENT year ("CfP ends on: March 31st, 2027") is another edition and is rejected (it had
falsely matched troopers.de's 2026 deadline); (2) plain "registration"/"apply" removed from the call wording (ccus-expo's pages matched an event date).
17 of 18 unit cases pass (the 18th was a wrong expectation). Page text and links for all 23 pages are saved in `crawl_pages.json`.
Re-score on the same 23 pages (old reader vs corrected new reader): sites where the known deadline is found 1 -> 2 of 6 (blackhat.com, and
h2meet.com now with a strong with-year match: "Sep. 1 (Tue) - Sep. 30 (Wed), 2026"); pages with a date near call wording 7 -> 8. An earlier,
uncorrected run showed 3 sites and 14 pages; those figures were inflated by the two defects above and should not be quoted.
troopers.de: the contribute page states "CfP ends on: March 31st, 2027" - the NEXT edition's deadline - which the corrected reader rightly does not
count against the 2026 known deadline, and which is exactly the next-edition information Gap 5 wants. The other four sites' known deadlines
(2026-03-23 to 2026-09-10) are past; their pages have rolled to a newer cycle, so absence there is expected, not a miss.

## UPDATE 6 - fair recall test, events whose deadline is still ahead (`recall_test.py`, `recall_test.json`, `recall_test_log.txt`)
Three customer-market events had a database deadline on or after 2026-10-01. 16 pages read (2 s apart), corrected date reader, plus a CONTROL (the call
page the database already holds) for each.
| Event | Pages selected | Result |
|---|---|---|
| International Conference on Climate Change (on-climate.com, 2026-12-19) | 9 | **CORRECTED 2026-10-01: NOT a genuine hit.** The page states 2026-12-19 as the end of the REGISTRATION period; proposal periods end 2026-06-19 / 2026-10-19 / 2026-12-20 (see `experiments/sentence_picking/RESULT.md`). Originally reported as: HIT at rank 2, /2027-conference/call-for-papers, medium confidence (month and day, year named elsewhere); the control page is the same page and the plan selected it |
| Global Energy Show Canada 2027 (globalenergyshow.com, 2026-12-04, database state not_found) | 6 | HIT at rank 1, /conferences/2027-call-for-submissions/, strong (full date with year). The database's own submission URL (/speak/abstract-submission/) states NO deadline and was not selected, so the plan found a better page than the one we hold |
| SecureWorld Government & Critical Infrastructure 2026 (secureworld.io, 2026-10-28) | 1 | MISS, but the ground truth is doubtful: its stored "evidence" is the events listing (a date beside the name), HANDOFF records that SecureWorld publishes no submission deadline, and the plan found no call page at that site. Not a selection failure. events.secureworld.io (a platform of 3,800 pages) was not tested |
Reading: 2 of 2 valid cases found, at rank 1 and 2 of the selected pages, from a site with no sitemap and one with. n = 2 is far too small for a rate.
It does show that the selection plus the date reader works end to end on a currently-open call, and that it can upgrade an unverified row to one with a
cited page. Side signals: on-climate.com already lists a 2028 conference call page, and troopers.de states its 2027 CfP end date (both next-edition
information for Gap 5). The date reader returns CANDIDATES; it cannot tell a submission deadline from another date near call wording (h2meet's award
schedule page also showed 9/30), which is the job of the sentence-picking step (model picks, code proves).

## Suggested next steps (none started)
v3.1 candidates (now applied, kept for reference): noise terms "board" and "review"; dedupe address variants; label phrases "join as a speaker", "contribution"; 2-digit
edition years; look at ushydrogenforum.com by hand (text but no links).
Revised order (from the earlier update): (a) drop stale-year pages when a newer year exists; narrow P2 ("program" and "schedule" are too generic; exclude exam,
committee, winners); (b) store menu link labels (re-render homepages, ~20 min) and score on the label as well as the address;
(c) a crawl-time stop rule: after 3 consecutive pages from one path family with no field found, skip the rest of that family;
(d) separate blocked from absent for the 36 sites without a sitemap; (e) fix the image counting in `sitewalk.parse_sitemap`.
Earlier list, kept for reference:
1. Tighten the rules: whole-word/segment matching, exclude profile and directory paths, per-tier page budgets (for example all P1, at
   most ~10 P2 limited to dates / programme index / awards call, at most ~3 P3 for the sponsorship prospectus).
2. Save the sitemap URL lists (this is the design's `site_pages`) so rules can be retuned with no network.
3. Separate "blocked" from "absent" for the 36 (one browser fetch of /robots.txt and /sitemap.xml each, not a crawl).
4. Replace first-segment scoping with an explicit per-event scope.
