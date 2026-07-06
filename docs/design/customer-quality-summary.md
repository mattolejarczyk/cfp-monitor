# PR Conference Monitor: What It Is, How It Works, Where It Adds Value
*Internal tool for PRIME|PR*

## What it is
An internal tool that automates the labor-intensive parts of tracking conference and event speaking / submission opportunities. Today it runs human-in-the-loop (a person works alongside it and verifies flagged items). The design goal is fast, verifiable automation that can become mostly, then eventually fully, hands-off as trust builds.

## How it works
1. You give it a list of conference websites (paste them in, or upload a file).
2. It visits each site the way a person would, using a real browser, and reads the key facts: conference name, dates, location, whether there is a speaking or submission opportunity, and where to submit.
3. It saves everything in one place, flags what needs a human check, and produces an updated, reviewable list.

## What the test showed
- Ran 44 real conference websites through it, end to end.
- 43 of 44 fully worked. 0 failed silently. 0 were left blocked.
- About 98% success, and when it cannot get something it says so, rather than being quietly wrong.

## Where it adds value
The genuinely hard parts of this problem, and how the tool handles each:

| Challenge | Why it is a problem | How the tool handles it |
|---|---|---|
| Websites block automated access | Cloud / data-center tools get blocked or return empty or wrong data | Runs from a real browser on a normal computer, so sites treat it like a person and it gets in |
| Strong anti-bot sites (e.g. Reuters events) | Stop most automated tools entirely | Drives a genuine Chrome browser and gets the page where automation fails |
| Cookie-consent pop-ups block the page | Automation gets stuck at the "Accept" wall | Dismisses them automatically |
| Key info hidden behind buttons, not plain links | Simple scrapers miss it | Extracts the real destination from buttons and clicks through |
| Submission deadlines are often not published | Guessing produces wrong dates | Never guesses: marks "opportunity found, needs verification" and gives the submission link for a human to confirm |
| Human corrections must persist | Re-runs can overwrite verified data | Locks verified values so later runs cannot overwrite them |
| Knowing what actually worked | Silent failures make results untrustworthy | Labels every site: got it / partial / blocked |

## Human-in-the-loop now, automation over time
- **Now:** the tool does the heavy lifting; a person verifies the small set it flags. This removes most of the manual research time while keeping accuracy high.
- **Next:** as verified data accumulates and site patterns are learned, more results become trusted automatically, moving toward mostly hands-off with spot checks.
- **Goal:** fast, trustworthy automation.

## Value produced today
- Replaces hours of manual, site-by-site research with a run that takes minutes.
- Maintains one reliable list that is not silently changed.
- Scales across markets and volumes without adding manual effort.

## Planned improvements (roadmapped)
Two input-side gaps surfaced in testing. Both are on the roadmap; the first needs a short discussion to confirm the approach.

- **Aggregator / directory sites (needs discussion / confirmation).** Some list entries point at an organization or directory that lists MANY events rather than one conference (for example a foundation homepage, a certification body, or a community hub). The tool currently reports "no single conference here," which is accurate but not the result you want. Planned approach: use the spreadsheet row context (location, dates, conference name) to navigate the directory to the specific event, then read it. This mirrors what a person does by hand. Worth confirming the desired behavior before building.
- **Dead or mistyped URLs (last resort, human-confirmed).** Some list entries are simply wrong (a missing letter, so the address does not resolve). Today the tool flags these as unreachable so a person can fix them. Planned option: when an address does not resolve, search the conference name and propose the most likely correct site for a person to confirm. It never silently substitutes a URL.
