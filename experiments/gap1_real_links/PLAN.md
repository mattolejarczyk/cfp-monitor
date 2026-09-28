# Gap 1 - made-up links

**Status:** theory written, not started.

## What happens today
The research AI finds facts through Google, but the pages Google returned were mostly listing sites
(10times, cfptime, infosecmap). For 27 of 89 researched rows the AI cited a page on a site that was
NOT among the pages it searched; in 26 of those 27 the event's own site did not appear in the search
results at all. The AI usually names the right official WEBSITE, but guesses the exact PAGE on it.

## Idea to test
Keep the AI's official website; let our own crawler find the real speaking / call-for-papers page on
that site (sitewalk.py ranking + the fetch ladder - the same crawler delivery_loop.py uses for
"link questions", which costs no AI). If none is found, keep the date but mark it projected with no
link, instead of showing a guessed one.

## How it would be measured (no AI cost)
- Input: the 27 flagged rows from the 2026-09-27 research.
- For each: does the AI's cited URL resolve? does our crawler find a real page on the same site?
  does that page carry the row's deadline?
- Compare: rows with a real, working link that carries the deadline - today vs with the crawler.

## "Proven" means
A clear gain in real, working links that carry the deadline, with no row gaining a wrong link.
A sample of accepted links checked by hand.
