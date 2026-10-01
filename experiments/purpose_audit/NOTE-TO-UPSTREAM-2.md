# Note to upstream, round 2 (draft for the operator to forward, 2026-10-01)

Thank you for the re-emit. We verified it and applied it to our database: India Energy Week 2027 (deadline 2026-10-15, evidence on the organiser's form page), the Climate Change conference (2026-10-19), the SecureWorld citation withdrawal, and Global Energy Show Canada 2027 (2026-12-04). Each change was backed up, applied through our merge guard, and read back from a second process. Five follow-ups, in priority order:

## 1. Before Saturday 02:00: please apply these corrections to your own audited files
Saturday's job re-researches every conference from scratch. A row whose new research passes our approval check replaces what we hold. A row that fails it, or is not researched, keeps "last week's approved version", which comes from your approved market files. If `Utility_audited.final.csv` still holds the old values, any of these four rows that falls back to it would put the old date back (09-30 for India Energy Week, 12-19 for Climate Change, the old SecureWorld citation, the dead Global Energy Show link) just before Monday 07:00, when our customer page is built. Please apply the four corrections to your approved files so the fall-back is the corrected version, and tell us when that is done.

## 2. Global Energy Show Canada 2027: the real submit link
The page you cited has a "Submit an Abstract" button. Its link goes to `https://www.dmgeventsconferences.com/global-energy-show-2027/submitter/login` (confirmed on the live page by our operator, and read from the page's HTML by a browser). Your payload set `CFP_SUBMISSION_URL` to the information page `https://www.globalenergyshow.com/conferences/2027-call-for-submissions/`. Please send the login URL as `CFP_SUBMISSION_URL`. Our import tools do not accept a URL upstream did not send (contract v2.4 class B), so on 2026-10-01 our operator ruled a one-field edit on our row (logged, backed up) so the customer page links to the working URL. That edit is only a stopgap: please send the login URL as `CFP_SUBMISSION_URL` and carry it in your approved file, or Saturday's load can bring the old 404 address back.

## 3. `IS_PROJECTED`
You set `IS_PROJECTED` to `false` for India Energy Week, Climate Change and Global Energy Show. Our merge guard changes the deadline and the citation but not that flag, so all three still read `true` here. Please include the flag in a delivery we import in the normal way, or tell us how you want it carried.

## 4. India Energy Week duplicate
We hold both `2026-india-energy-week-kolkata` and `2027-india-energy-week-kolkata`. Our tools cannot merge or retire an event identity (5.4), so the 2026 row, still dated 2026-09-30 and now a duplicate, will read Closed on the customer page until it is retired. Please confirm the surviving id and send the retirement (R15) in a delivery.

## 5. Pass type
These changes moved two dates and retired one row. Under R6 a `correction` pass changes no dates and removes no rows, so this is a `re-research` pass and needs a manifest (R7). We have accepted it as agreed, but please declare the pass type correctly next time so our audit runs against the right file.

## One question
The Climate Change quote `Regular 20 June (26) to 19 October (26)` carries a two-digit year in brackets, which our date check cannot yet read. We will extend the check after Monday. Until then that row's date verdict reads `not_found` even though the page states it.
