# Request to upstream: the new rows as a full CSV now (2026-10-02)

Thank you for accepting the leads and for confirming that our local approved files are the master for Saturday's run. One request, so that we can have the new rows in our database and checked before Monday's customer pages rather than after.

**Please send the new rows as a full CSV, in the normal delivery format, with their final EVENT_IDs.** We will import it through our normal import path and run the database health check on it, exactly as for any delivery.

Rows wanted (the six we sent as new, plus the one we agreed is an update):

1. Climate Change Emerging Scholar Awards (deadline 2026-10-06)
2. Black Hat Asia 2027, summits (2026-10-12)
3. Black Hat Asia 2027, briefings (2026-10-20)
4. SANS CTI and OSINT summits (2026-10-19)
5. ACT Expo Fleet Awards (2026-11-20)
6. TROOPERS27
7. Nullcon Goa 2027: this is an UPDATE of the existing row `2026-nullcon-goa-2027-bambolim-speaking`, not a new row. We have already written 2026-10-30 into our copy of the approved file. Please do not send it as a new row.

For each row we need the full set of columns, not only the date: EVENT_ID, event name, organizer, city, venue, dates, CONFERENCE URL, the submission link, the deadline with its evidence URL and quote, IS_PROJECTED, and your usual source and verification fields.

Conditions, so that nothing has to be redone:

- Use the EVENT_ID you will use in Saturday's run, so the same row is not created twice.
- If a row would be a duplicate of one we already hold (for example under an older edition's ID), say so rather than sending it as new.
- Leave the customer-owned columns (STATUS, STATUS DETAILS, NOTES, PRIORITY, SUBMISSION URL) blank, as always.
- Where a field is unknown, leave it blank. An honest blank beats a guess.

Please reply with the CSV in one block, plus one line per row saying "new" or "update", and its final EVENT_ID.
