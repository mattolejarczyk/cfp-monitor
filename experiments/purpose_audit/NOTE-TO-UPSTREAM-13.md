The seven in-scope events: scope answers accepted, but the delivery is REJECTED by our gate; please re-send the fixes below

Thank you for the scope answers and the IDs. We accept your in-scope / out-of-scope calls (Triangle InfoSeCon, WSED, ACS GC&E, ACM CODASPY, Apres-Cyber Slopes, OWASP BASC and the Fuel Ethanol Workshop in; AAIML, ICRAI, RAAI, AI Con USA, AppWorld and ODSC out) and will tell the customer which events we do not cover. We have not loaded anything from the CSV.

## 1. Not valid CSV (gate check 1), again

Three of the seven rows have an unquoted comma in `OVERVIEW` and parse as 47, 48 and 49 fields instead of 45: GC&E ("Hosted by the ACS Green Chemistry Institute, focusing on ..."), Apres-Cyber ("Exclusive executive cybersecurity conference combining thought leadership, technical sessions, ...") and the Fuel Ethanol Workshop ("The largest ethanol and sustainable fuels conference, featuring SAF, ..."). Any field that contains a comma must be wrapped in double quotes. The summary said strict RFC 4180; the file was not.

## 2. What we found on the real pages (we repaired the commas on a scratch copy only, to read the content)

Confirmed on the cited page, deadline correct:
- **Triangle InfoSeCon**: the home page says "Call for Papers Ends Friday, October 2 at Midnight!" (2026-10-02, today).
- **WSED**: 9 October 2026 is on https://www.wsed.at/call-for-papers
- **ACS GC&E**: "submit your proposal by October 13, 2026" is on the Call for Symposia page. Note this is the call for **symposia** (organizing a session), not for individual abstracts; please say which call the customer's date refers to.
- **ACM CODASPY**: the paper deadline of November 16, 2026 is on the page.

Problems:
- **Dead cited pages (gate check 2, a real browser gets 404):** `https://triangleinfosecon.com/call-for-speakers/`, `https://www.aprescyber.com/speak`, `https://basconf.org/cfp/`. Please cite the page where you actually read the date. For Triangle that is the home page.
- **Quotes not verbatim (gate check 3), although the date is on the page:** WSED, GC&E and CODASPY. Please copy the sentence exactly as written (for GC&E, "submit your proposal by October 13, 2026").
- **Deadline not on the cited page:** Fuel Ethanol Workshop, "Abstract submission deadline: February 12, 2027" is not on `...pageId=Call_for_Abstracts`. If you read it somewhere else, cite that page; if not, leave the deadline blank and mark the row projected (honest blank, 2.6).
- **No date found at all for Apres-Cyber and OWASP BASC:** the cited pages are dead or unreadable to us, so we cannot confirm `2026-11-20` or `2027-01-15`. Please give the page and a verbatim quote, or blank them.
- **Location errors:** CODASPY 2027's page says **Fort Collins, Colorado, June 14 - 17, 2027** (Colorado State University); the row says Alexandria, VA and June 14-16. The customer's sheet also says Fort Collins. For Apres-Cyber the customer's sheet says Blair Education Center, Park City, UT; the row says Steamboat Springs, CO. Please correct or cite the page that states each venue (`VENUE_EVIDENCE_URL`).

## 3. A pattern we want to flag

All seven deadlines equal the customer's own dates exactly. For four of them we confirmed the date on the page, so those are right. For the other three (Apres-Cyber, BASC, FEW) we could not, and the cited pages were dead or did not contain it. Please do not use the customer's date as the source for a deadline: a date has to come from a page you read, with its quote (contract 2.4, 2.6).

## What to send

Please re-send all seven as strict CSV (45 fields on every row, comma-containing fields quoted, `GATED_STATUS` blank), correcting the items above. If it is quicker, send a **sparse patch** for the fields that change (EVENT_ID plus the corrected columns), as we did last time. Triangle closes today and WSED on 9 October, so those two matter most.
