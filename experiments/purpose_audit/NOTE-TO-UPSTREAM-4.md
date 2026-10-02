# Note to upstream, round 4: verification of your reply (draft for the operator to forward, 2026-10-01)

Thank you for the reply and for taking all seven leads. We verified it before relying on it. Results:

## Confirmed
- The quotes for all seven new rows (Climate Change Emerging Scholar Awards, Black Hat Asia 2027 summits and briefings, SANS CTI and OSINT summits, Nullcon Goa 2027, ACT Expo Fleet Awards, TROOPERS27) and the WHEC 2026 correction are word for word on the pages we saved on 2026-10-01, and our date check reads every date in them. Nothing for us to change there.
- Your `IS_PROJECTED` values, the pass type (re-research) and the retirement of `2026-india-energy-week-kolkata` are noted. We will check each in the delivery itself when it arrives; nothing has been imported from this reply yet.

## Two things to fix on your side
1. **The Nullcon Goa 2027 row key does not match.** You assigned `2027-nullcon-goa-goa` and called it an update to an existing row. Our existing row is `2026-nullcon-goa-bambolim` (in your approved file it is `2026-nullcon-goa-2027-bambolim-speaking`, edition 2027, blank deadline). A key that matches nothing is an insert, which under 5.4 is yours to declare as a new row. Please either use the existing key for the update, or declare the new row and retire the old one as a duplicate (R15).
2. **The files on our machine were not changed by your "master-file sync".** `Utility_audited.final.csv` and `Cybersecurity_audited.final.csv` in our Markets folder had not been modified since 2026-09-27 and still held the old values for all four corrected rows. We applied your values to them ourselves tonight with the row-patch tool (backups kept; no row added or removed): Climate Change 2026-10-19 with its quote and `IS_PROJECTED` false; India Energy Week 2026-10-15 with the form-page citation; Global Energy Show 2026-12-04 with the call-for-submissions citation; SecureWorld citation withdrawn, deadline kept, `IS_PROJECTED` true. Please treat the copies on this machine as the master for Saturday's run, and tell us about any change you want in them rather than assuming a sync.

## Still open: the Global Energy Show submit link
Our row in `Utility_audited.final.csv` still holds `CFP_SUBMISSION_URL = https://www.globalenergyshow.com/speak/abstract-submission/`, which returns 404; the patch tool protects that field, and you said you locked the login URL "across all master records", which did not reach our copy. Please send `https://www.dmgeventsconferences.com/global-energy-show-2027/submitter/login` as `CFP_SUBMISSION_URL` in the re-research delivery. Until we import it, Saturday's load can bring the 404 address back over our one-field stopgap.
