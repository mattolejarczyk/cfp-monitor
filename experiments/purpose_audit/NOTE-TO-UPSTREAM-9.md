Two status cleanups that keep our files from passing the gate: H2 MEET 2026, and six award rows with passed deadlines still marked Open

Thank you for the awards routing answers. Both award rows are now in `Awards_input.csv` with your IDs stamped by our tool, and in the awards file the page reads. While gating those files we found two groups of rows whose STATUS contradicts their own deadline. None of them come from the new rows. Gate check 6 ("no past deadline presented as open") fails on them, and the same rows would fail the same check on any file that carries them, so please correct them at source, in your next delivery, through your normal path. We have not touched them on our side.

## 1. H2 MEET 2026 (Utility, speaking call)

- EVENT_ID: `2026-h2-meet-2026-goyang-speaking`
- Our approved Utility file holds: SUBMISSION DEADLINE `2026-09-30`, STATUS `Open`, STATUS DETAILS "The call for speakers is currently open for the second intake round. Round 1 closed on August 31, 2026. Round 2 is active from September 1 through September 30, 2026."
- Cited page: https://www.h2meet.com/html/en/speaker.php
- Today is 2026-10-02, so the second round has passed and the row is presenting a closed call as open.

Please re-check that page and answer one of:
(a) the call has closed and there is no later round: set STATUS and STATUS DETAILS to say so, keep the deadline `2026-09-30` as the last known date (contract R1);
(b) there IS a later round or an extension: give us the new deadline with its page and a verbatim quote, and show both dates per the rounds rule (DEADLINE = first round not yet passed, later rounds in STATUS DETAILS).

## 2. Six award rows marked Open after their deadline (plus one dead link)

All are in the awards file as delivered on 2026-09-05; we are carrying them unchanged.

| EVENT_ID | Market | Stored deadline | STATUS now |
|---|---|---|---|
| `2026-cso-conference-awards-nashville-awards` | Cybersecurity | 2026-09-16 | Open |
| `2026-globee-awards-for-innovation-golden-bridge-awards-unknown-awards` | Cybersecurity | 2026-09-11 | Open |
| `2026-sans-difference-makers-awards-washington-awards` | Cybersecurity | 2026-09-14 | Open (IS_PROJECTED true, no citation) |
| `2026-tech-trailblazers-awards-unknown-awards` | Cybersecurity | 2026-09-30 | Open |
| `2026-world-green-energy-awards-2026-unknown-awards` | Utility | 2026-09-27 | Open |
| `2026-blue-planet-prize-2026-unknown-awards` | Utility | 2026-10-01 | Open |

For each, please say whether the call is now closed (then STATUS says so and the last known date stays), or has been extended or reopened for a later window (then the new date with its page and a verbatim quote).

Separately, `2026-clinton-global-initiative-cgi-commitments-to-action-2026-unknown-registration` (Utility, IS_PROJECTED true, blank deadline, STATUS Open) cites https://www.clintonfoundation.org/our-work/clinton-global-initiative/ and a real browser now gets a 404 there while a plain fetch gets a 403. Under criterion 2 that is a dead citation on a row with no deadline. Please either give a working page for it or withdraw the citation under R1 and keep the row honestly blank.

## What we will do on our side

Nothing is changed until your delivery arrives. When it does we run it through the gate as usual, load it, and run the health check. We are not editing any STATUS in our copies: STATUS belongs to your delivery, and a hand edit on our side would be overwritten the next time a row passes your research.

Please reply with the corrected rows for H2 MEET and the six award rows (and the CGI answer) in one CSV block, strict RFC 4180 with 45 fields per row and any comma-containing field quoted.
