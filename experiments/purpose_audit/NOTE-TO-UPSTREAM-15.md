Your sparse patch for the seven in-scope events: what we verified, one correction that matters, and our own page reads for you to apply literally

Thank you for the tooling answer (a search index with no outbound fetch) and for the three rules. We checked every citation in your sparse patch against the live pages. Results first, then what we are asking.

## Your five citations

| Event | Your citation | Our check |
|---|---|---|
| Triangle InfoSeCon | sessionize.com/triangle-infosecon-2026/, "Call closes at 11:59 PM. 02 Oct 2026" | Verbatim on the page. Good. |
| WSED | fedarene.org/open-call-european-energy-efficiency-conference-2027/, "...Deadline: 9 October 2026." | Verbatim on the page, which is about the WSED 2027 energy-efficiency conference. Good. |
| ACS GC&E | gcande.org, "Call for Symposia: Deadline October 13, 2026." | Present on the page. Note it is the call for **symposia**. Good. |
| ACM CODASPY | codaspy.org/2027/, "Abstract submission deadline: November 16, 2026." | **Right fact, wrong page.** The sentence is on `https://www.codaspy.org/2027/cfp.html`, not on the home page you cited. It is also the **abstract** deadline: the same page gives the **research paper** deadline as November 23, 2026. |
| Fuel Ethanol Workshop | ethanolproducer.com article, "The deadline for submitting a presentation abstract is Fri., Oct. 30, 2026" | **Wrong event, and the quote is not on the page.** The article is about the 2027 *International Biomass Conference & Expo*; it mentions the Fuel Ethanol Workshop only in a sidebar advertisement, and the text "Oct. 30" does not appear on it. Please withdraw this change. |

## The correction that matters

Your change moved the Fuel Ethanol Workshop / Sustainable Fuels Summit deadline from 2027-02-12 to 2026-10-30. **The original date was right.** The event's own page (`https://few.bbiconferences.com/ema/DisplayPage.aspx?pageId=Sustainable_Fuels_Summit__SAF__Renewable_Diesel__Biodiesel`) says: "Presentation abstracts will be accepted for the 2027 Sustainable Fuels Summit: SAF, Renewable Diesel, Biodiesel through February 12, 2027." So a snippet from a different conference's article was attributed to this one and overwrote a correct value. A search index can return a snippet that does not belong to the event being researched; please check that the event name in the page text matches the row before attributing any date to it.

## Our own page reads, for you to apply literally (your rule 3)

We read these in a real browser (two are JavaScript pages a plain fetch cannot see). Please put exactly these in the sparse patch, unchanged:

| EVENT_ID | Fields | Value |
|---|---|---|
| `2027-acm-codaspy-alexandria-speaking` | DEADLINE_EVIDENCE_URL / CFP_SUBMISSION_URL | `https://www.codaspy.org/2027/cfp.html` |
| | DEADLINE_QUOTE | `Abstract submission deadline: November 16, 2026` |
| | STATUS DETAILS (as a customer-facing note, one sentence) | Abstracts are due November 16, 2026; the research paper deadline is November 23, 2026. |
| | LOCATION / CITY / STATE_PROVINCE | The page says Fort Collins, Colorado, USA, June 14 - 17, 2027 (Colorado State University). The row currently says Alexandria, VA, June 14-16. Please correct. |
| `2027-apres-cyber-slopes-summit-steamboat-springs-speaking` | SUBMISSION DEADLINE | `2026-11-20` |
| | DEADLINE_EVIDENCE_URL / CFP_SUBMISSION_URL | `https://sessionize.com/apres-cyber-slopes-summit-2027` |
| | DEADLINE_QUOTE | `Call closes at 11:59 PM 20 Nov 2026` |
| | IS_PROJECTED / GROUNDING_CONFIDENCE | `false` / `Verified (2027)` |
| | LOCATION / CITY / STATE_PROVINCE | The event page (`https://www.aprescyber.com/2027-summit`) says "Blair Education Center, Park City, UT", February 24-26, 2027. Your row says Steamboat Springs, CO. Please correct to Park City, Utah. (Note: your EVENT_ID contains steamboat-springs; the identity is yours, 5.4, so tell us whether you will declare a rename.) |
| `2027-owasp-boston-application-security-conference-boston-speaking` | SUBMISSION DEADLINE | `2027-01-15` |
| | DEADLINE_EVIDENCE_URL | `https://basconf.org/` |
| | DEADLINE_QUOTE | `Jan 15, 2027 Call for Papers closes Submissions due by 11:59 PM EST.` |
| | SUBMISSION_OPENS | `2026-11-01` (the page says "Call for Papers opens" Nov 1, 2026; submissions go through Sessionize) |
| | IS_PROJECTED / GROUNDING_CONFIDENCE | `false` / `Verified (2027)` |
| `2027-fuel-ethanol-workshop-sustainable-fuels-summit-omaha-speaking` | SUBMISSION DEADLINE | `2027-02-12` (revert your change) |
| | DEADLINE_EVIDENCE_URL | `https://few.bbiconferences.com/ema/DisplayPage.aspx?pageId=Sustainable_Fuels_Summit__SAF__Renewable_Diesel__Biodiesel` |
| | DEADLINE_QUOTE | `Presentation abstracts will be accepted for the 2027 Sustainable Fuels Summit: SAF, Renewable Diesel, Biodiesel through February 12, 2027.` |
| | CFP_SUBMISSION_URL | `https://few.bbiconferences.com/ema/DisplayPage.aspx?pageId=Submit_Presentation_Ideas` |
| | IS_PROJECTED / GROUNDING_CONFIDENCE | `false` / `Verified (2027)` |

Keep your Triangle, WSED and GC&E rows as sent.

## What we ask of you this time, so we can learn how your loop behaves

1. Send back the final sparse patch with exactly the values above. If you change any of them, say which and why. We will gate it and compare it field by field with this note; any difference we did not ask for is a finding.
2. For each row, say in one line **how** you got each value: from a search-result snippet, from an opened page, or from our table above.
3. If a search result's text does not name the event in the row, do not attribute it to that event.

Triangle's call closes tonight (11:59 PM) and WSED's on October 9, so those two are time-critical; we will load them as soon as the patch passes the gate.
