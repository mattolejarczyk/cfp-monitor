# ACT-25 (a): which events sit on a standard platform we could read directly (2026-10-05)

Read-only. Script `census.py` (live database opened with mode=ro; nothing fetched by the script). Five platform pages were fetched once by hand with the plain fetcher (`verify.fetch_text`) to see what they say.
The answer is a recommendation; nothing is built.

## What was counted
The 127 events on the Cybersecurity and Utility market lists. For each, the host of the event page, the submission page and the deadline evidence page was put in a family. Two kinds:
SUBMISSION platforms (the page is the call) and ORGANISER platforms (one company, many events, one site).

| Family | Events | Date proven today (`verify_state` verified, basis date) | What the verifier says about the rest |
|---|---:|---:|---|
| SecureWorld (organiser) | 12 | 2 | 10 contradicted, basis `link` (dead pages) |
| Sessionize (submission) | 7 | 3 | 1 status-only, 2 dead link, 1 not found |
| OWASP chapter and event pages | 4 | 0 | 3 dead link, 1 not found |
| Reuters Events (organiser) | 4 | 0 | 4 not found |
| Gartner (organiser) | 4 | 0 | 4 not found |
| Black Hat / Informa Tech (organiser) | 4 | 0 | 1 status-only, 1 contradicted, 2 not found |
| Pretalx (submission) | 1 | 0 | not found |
| Microsoft CMT (submission) | 1 | 1 | - |
| HotCRP (submission) | 1 | 1 | - |

35 of 127 events (28 percent) have a cited page on one of these families. Only 7 have their SUBMISSION page on a submission platform (4 Sessionize, 1 Pretalx, 1 CMT, 1 HotCRP): 5 percent.

## What the platform pages say in plain text (fetched once, 2026-10-05)
- **Sessionize**: states the whole call in plain text: 'Call opens at 12:00 AM 01 Jan 2026', 'Call closes at 11:59 PM 06 Mar 2026', and 'Call for Speakers is closed' (AppSec Israel 2026; AppSec Days France 2026 the same).
  The date has its year, so the generic reader already proves it; a Sessionize-specific parser would add nothing it cannot already read.
- **Pretalx**: 'Submissions closed on 2026-03-01 18:00 (Europe/Berlin)' (OffensiveCon 2026). Same.
- **HotCRP**: 'Submissions are currently closed.' Status only, no date, 504 characters (CODASPY 2027's own page; the date is on the conference's own cfp page, which a pin already covers).
- **Microsoft CMT**: a login page of 463 characters, no call text at all (WFCC 2026). Nothing a plain reader can use.

## Recommendation
1. **Build no per-platform reader now.** 10 of the 127 events (8 percent) have a cited page on a submission platform (7 as their submission page); the generic reader plus the verifier already prove 5 of those 10 by date
   (Sessionize 3, CMT 1, HotCRP 1); the rest are dead pages of past editions, one status-only and one not found. Sessionize and Pretalx state the date in plain text with a year, so a parser would add no fact; HotCRP
   and CMT state none in plain text, so a parser could not either.
2. **The real lever is the organiser sites, not the submission platforms**, and there the problem is not the format: SecureWorld's 12 events are 10 dead links (past editions; earlier notes in the repo say SecureWorld publishes no
   submission deadline, which I have not re-checked today), and Reuters, Gartner and Black Hat answer scripts with a wall (all 'not found' or status-only). The render fallback of ACT-12 and the shadow reader (ACT-20) are the tools
   for those; a platform parser is not.
3. Revisit if the Sessionize share of events grows past about 10 percent; the one cheap addition then would be to let the verifier treat Sessionize's 'Call for Speakers is closed' sentence as a closed-call status.

Not done: no platform fingerprint of the event SITES themselves (WordPress, Wix, Cvent): the page library stores text, not HTML, so the builder cannot be told from it. hceeweek.com is a Cvent-built page (seen in its raw HTML);
that is the only builder identified, by hand.
