# Gap 2 - paraphrased quotes

**Status:** theory written, not started. Measured independently of gap 1.

## What happens today
The AI writes a "quote" of the deadline sentence that is often reworded, so it cannot be proven
word for word against the page. Monday's re-check then reports "not on page" even when the date is.

## Idea to test
Never use the AI's quote. Open the row's cited page ourselves and copy the deadline sentence word for
word (self_heal.find_deadline_sentence: the date in any usual form, near words like "deadline",
"submissions due", "call for"). If no such sentence exists, leave the quote blank - honest "not on
page" - rather than keep a reworded one.

## How it would be measured (no AI cost)
- Input: every 2026-09-27 researched row with a cited page (unchanged links - gap 1 is not applied).
- Per row: is today's AI quote on the page verbatim? can our extractor find a verbatim deadline
  sentence on the same page? does that sentence carry the same date?
- Compare the count of rows with a provable, word-for-word quote: today vs extractor.

## "Proven" means
More rows provable word for word, and no row whose extracted sentence names a different date than
the row claims (those are reported as disagreements, never silently swapped).

## Known limit
Some sites build pages with JavaScript or phrase dates unusually; deadline dates verified better than
event dates in the 2026-09-22 self-heal work, but yield will be partial.
