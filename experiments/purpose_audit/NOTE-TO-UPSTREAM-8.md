Where does Utility_Awards_master.csv live, and how do we add the two awards rows to it?

Thank you for confirming the seven IDs are permanent and for the ACT Expo rename declaration. One thing we cannot yet act on: you said to route both awards rows into `Utility_Awards_master.csv`. We cannot find a file with that name on this machine. Our copy of the awards pipeline works from these files in `...\Nicolia-PR-Prime\Markets\`:

- `Awards_input.csv` is the research input list for awards: 135 rows (64 Cybersecurity, 71 Utility), with a permanent id column `EVENT_ID_CANON`. The paused Friday run reads it.
- `Awards_audited.csv` is the last Friday output (2026-09-28): 27 rows, all Cybersecurity.
- `Awards_20260905_out.csv` is the last full awards delivery: 127 rows (64 Cybersecurity, 63 Utility).

State on our side right now: both award rows (`2027-climate-change-emerging-scholar-awards-johannesburg-awards` and `2026-act-expo-fleet-awards-tbd-awards`) passed the gate (23 of 23) and are loaded into our awards tables under your IDs, in the Utility market. What we still need is for them to be on the list that future awards research reads, so they are re-researched and keep their identity.

Please answer, in this order:

1. Is `Utility_Awards_master.csv` the same list as the Utility rows of our `Awards_input.csv`, a different file, or the name of something on your side only? If it is a different file, where does it live (full path or system), and what is its column header? Paste the header line.
2. Who writes to it, and by which tool? If the only way to change it is a file on this machine, say so, and we will add the rows through our stamping tool; we will not hand-edit an id.
3. If we should add the two rows to `Awards_input.csv` instead, confirm, and confirm that you want them under the ids above with the blank city kept blank for ACT Expo (2.6).
4. The Friday awards run is paused on our side. Until it resumes, which file do you want treated as the approved Utility awards delivery (the one the customer page is built from)? Today our approved awards file holds only Cybersecurity rows, so these two Utility rows will not appear on any page until a Utility awards file is approved.
5. Anything else you need from us to include the two rows in your next awards delivery (inputs, the format of the rows, or a date by which you need them)? Climate Change Emerging Scholar Awards closes 2026-10-06.
