# Three live rows for review - 2026-10-01

Advisory. **Nothing was changed** in the database, the deliveries or the customer pages. Pages were read today (2026-10-01) through the repo renderer; the stored values
are from the live database (read-only). These are the rows from `purpose_audit.py` whose stored deadline has NOT passed and is not confirmed by its cited page.

## 1. SecureWorld Government & Critical Infrastructure 2026 (Cybersecurity)
| | |
|---|---|
| Stored | deadline 2026-10-28, status Open, "Fixed Deadline", `verified` |
| Why it reads verified | `[L2] page states 2026-10-28 <- https://www.secureworld.io/events` |
| Stored quote | `Government & Critical Infrastructure 2026 2026-10-28` (the event name followed by the date: it is not a sentence from the page) |
| Cited page today | the events list. It shows this event on **Dec 9, 2026 (virtual)**, which matches the stored start date 2026-12-09. The text "Oct 28" / "10-28" appears nowhere on it. |
| Submission link | none stored (`NO_SUBMISSION_URL`); the page does have a "Become a Speaker" link. |
| What I could not establish | whether the page said 10-28 when it was verified on 09-19, or whether the verifier matched the date inside the stored quote itself. |
| Read | The stored date has no support on its cited page today, and the quote cannot be the page's own words. Treat as unconfirmed. |
| Options | (a) re-research the row for a real call page and date; (b) blank the deadline until one is found. Your call; either is a data change, not made here. |

## 2. India Energy Week 2027 (Utility)
| | |
|---|---|
| Stored | deadline 2026-09-30, status Open, **`is_projected` = true**, no quote, no evidence URL. Two rows share this conference key: "India Energy Week 2027 (IEW 2027)" is `verified`, "India Energy Week 2027" is `not_found`. |
| Why one reads verified | `[L2] page states 2026-09-30 (not the cited page; no evidence URL supplied) <- https://bit.ly/4yuBPgO` |
| Page today (the short link, a Call for Abstracts submission form) | "Submission deadline: **15 October 2026**" and "Full paper and presentation submission: 15 November 2026". 2026-09-30 is not on it. |
| The site's own Call for Papers page | still the previous cycle: "extended and final deadline ... **19 September 2025**", dated 2025 and 2026 throughout. It does not describe the January 2027 event. |
| What I could not establish | which page is authoritative, and whether the short link points to the organiser's real 2027 form (it carries the 2027 banner and the same footer). Also whether the page said 09-30 on 09-19. |
| Read | The stored 09-30 is a projected date that the cited page contradicts today (15 Oct). The deadline has not passed, so the customer-facing value is wrong now or will be on 09-30 either way. Also a duplicate row. |
| Options | (a) replace with 2026-10-15 once a person confirms the short link is the organiser's form; (b) collapse the duplicate row. |

## 3. Global Energy Show Canada 2027 (Utility)
| | |
|---|---|
| Stored | deadline 2026-12-04, projected, `not_found`, no quote, submission link `https://www.globalenergyshow.com/speak/abstract-submission/` |
| Cited page today | a **404 "Page Not Found"** page. That is why the status is `not_found`. |
| A different page on the same site | `/conferences/2027-call-for-submissions/` says "all submissions must be completed through the online submission form by the **December 4, 2026** deadline." This is the page that also carries our locked answer-key label for 2026-12-04. |
| Read | **The date looks right; the link is wrong.** The stored date is supported by a live page of the same site, but the row cites a dead one. |
| Options | point the evidence and submission links at the live page and keep the date. Low risk; still a data change for you to approve. |

## Summary
| Row | Stored date | Today's page | Verdict |
|---|---|---|---|
| SecureWorld Gov & CI | 2026-10-28 | not on the page; event is Dec 9 | unsupported |
| India Energy Week 2027 | 2026-09-30 | 15 Oct 2026 | contradicted, plus a duplicate row |
| Global Energy Show Canada 2027 | 2026-12-04 | live page states it; cited link 404 | date right, link wrong |
