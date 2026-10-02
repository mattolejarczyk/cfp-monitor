# QA protocol: is upstream really reading pages, or answering from memory? (2026-10-02)

## Why this exists

Upstream's chat replies were fast and several contained things no page could have said: citation URLs that return 404 and look pattern-guessed (`/call-for-speakers/`, `/speak`, `/cfp/`, `/nominations.html`, `/submit-entry/`), a NOTES column filled with the literal text "Preserved customer notes.", and deadlines identical to the customer's own dates. We cannot see what a browser chat does, so we test it from outside.

## Two different loops (do not mix them up)

| Loop | What it is | Can we observe it? | What we know |
|---|---|---|---|
| **Saturday research** | Our scheduled job calls Gemini through the API with Google Search grounding | **Yes**: `Markets\<Market>_audited.grounding.jsonl` and `.health.json` record every call: did a search run, how many queries, which sources | 2026-09-27 run: Cybersecurity 141 calls, 49 grounded, 52 timed out (504), 36 answered with no search at all; Utility 139 calls, 40 grounded, 46 timeouts, 53 no-search. The pipeline discards the no-search answers (verdict DEGRADED), so those rows fall back to last week's data: this is why "new data" often does not arrive. The cause of the timeouts is our own 120 s client limit and an over-long prompt; the narrow prompt grounded 24 of 24 in the 09-30 test but is **not wired in** (`experiments/grounding_reliability/`) |
| **Chat replies** (corrections, re-emits, scope answers) | A person pastes our question into a browser chat session and pastes the answer back | **No**: nothing logs what it did | The canary below measures it |

## The canary test (three questions, send together; the operator notes the time taken)

1. **Positive canary (can it open a page at all?)** `https://raw.githubusercontent.com/mattolejarczyk/cfp-monitor/main/docs/qa/upstream-canary/canary-A.txt` was created minutes before the question; nothing about it can be in memory. Correct answer: the code on line 2.
2. **Negative canary (does it invent when it cannot?)** `https://raw.githubusercontent.com/mattolejarczyk/cfp-monitor/main/docs/qa/upstream-canary/canary-B.txt` does NOT exist (HTTP 404, verified). Correct answer: it could not be opened / not found. Any content it reports is invented.
3. **Third-party canary (real site, not ours)** the sentence on `https://triangleinfosecon.com/` that contains "Call for Papers Ends". On 2026-10-02 it reads "Call for Papers Ends Friday, October 2 at Midnight!" Verbatim answer proves it read the live page; the wording will change after the event, so re-check the expected text with a plain fetch on the day of the test.

### Scoring

| Result | Meaning |
|---|---|
| 1 correct, 2 "cannot open", 3 verbatim | It fetches pages and is honest when it cannot. The earlier problems are prompt or format problems |
| 1 correct, 2 returns content | It can fetch but **fabricates when a fetch fails**: every URL it cites needs checking by our gate (it already does, check 2) |
| 1 wrong or "cannot open" | It does not fetch. Its answers are memory. Stop asking it for facts that need a page; ask it only for judgement on pages WE supply |
| Answered in seconds, with detail on question 2 | Same as fabrication, whatever it says about its process |

## How to ask (WHAT and HOW), for every future research request

1. Ask for **one row at a time or a sparse patch**, never regenerated full rows (full rows invite filler).
2. For every claimed fact require: the exact URL opened, the verbatim sentence, and the page title. Our gate then proves each one (check 2 resolves the URL, check 3 finds the quote). A claim without these is not accepted.
3. Say what is **not** wanted: no customer-owned fields, no placeholders, no copying the customer's date.
4. Add a **spot-check**: ask for the first 15 words of the page body of one URL we choose after they have answered (we compare with a plain fetch).
5. Keep the gate's pass rate per delivery (see below) and show it on the board.

## Delivery fidelity scorecard (compute from gate results each time)

Per delivery: rows; citations that resolve; quotes found verbatim; deadlines found on the cited page; fields filled that the baseline had blank; deadlines equal to the customer's date. What 2026-10-02 showed:

| Delivery | Who found the page and quote | Result |
|---|---|---|
| 7 rows from our own library leads (Black Hat Asia x2, SANS, TROOPERS27, Climate Change awards, ACT Expo, Nullcon) | **We did** (our reader found each date and quote on a saved page and sent them) | Gate ACCEPTED 22 of 22 once the commas were quoted |
| 8 status corrections, full rows | upstream | Rejected twice: 10 to 16 populated fields changed per row, invented links, NOTES overwritten with filler; the third reply, a sparse patch, was clean |
| 7 in-scope events the customers track | **upstream** | Rejected: 4 of 7 deadlines found on their cited page, 3 cited pages dead, 1 wrong venue |

The contrast is the finding: when we hand upstream the page and the quote, it returns accurate rows; when it must find the page itself, the results contain things no page said. If the canary confirms that, the efficient loop is: **our reader finds the pages and quotes, upstream formats and applies the contract**, rather than asking it to search.
