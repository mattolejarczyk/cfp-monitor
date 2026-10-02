# Whole-page reader scored against the locked benchmark key (2026-10-02, offline, no model calls)

Script: `score_vs_key.py`. Reader answers: `library_results.json` (the 10-01 run over 347 saved pages, code-gated: the quote must be literally on the page, the date written in it, the year stated). Key: `docs/agents/results/01-benchmark-key.csv` (40 events; 16 high + 15 medium model rows, 9 hand labels).

## Result

| | Events scored | Result |
|---|---|---|
| Key row HAS a deadline | 11 | **HIT 7**, WRONG 2, MISS 2 |
| Key row has NO deadline (not announced, no call, closed with none, unknown) | 23 | **CLEAN 22**, CHECK 1 |
| Not scored (host not in the library) | 6 | Area41, AppSec Days France, SecureWorld x2, ESF MENA, Horizons Clean Energy Expansion Week |

## How to read it

- **The two WRONG are matching artefacts, not reader errors.** Pages are matched to an event by host. `blackhat.com` carries Black Hat USA, SecTor, Asia and others, and `defcon.org` carries several DEF CON events, so dates the reader correctly took from a different edition's page are counted against SecTor 2026 (key 2026-05-26) and DEF CON Singapore (key 2026-02-15). A per-event page match would very likely turn these into hits or clean misses.
- **The two MISS are by design.** BSides Las Vegas prints "May 8th" with no year; the reader's code gate requires a stated year, so it correctly refuses it. it-sa's deadline (2026-06-30) sits on a news article for an awards call, not on the pages in the library for that host.
- **The one CHECK is a known failure mode.** CarbonZero 2026-10-28 is the awards CEREMONY date (the earlier library run hand-checked 16 of 18 and named the ceremony date as one of the two false positives). The key has CarbonZero as `unknown`.
- **What the 22 CLEAN mean:** on events where the key says no submission deadline is published, the reader accepted no date on or after 2026-10-01 for 22 of 23. That is the number that protects the customer from a made-up date.

## Caveats

Small sample (34 scored). Host-level matching. The pages are the 10-01 fetch, and the key is the 10-02 reading of live pages. This is a first reading, not a proof; the pre-registered bar from the experiment (precision 0.95, recall 0.80) was NOT met on the original fresh pages and is not claimed here.
