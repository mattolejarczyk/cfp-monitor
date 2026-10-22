# Manual troubleshooting protocol

Written 2026-10-19. For the moments when something looks wrong and a person (or Claude) starts
poking at it by hand. Every line below is a mistake that already happened. This is a checklist,
not a theory: run it top to bottom before concluding anything.

It points at existing tools and rules; it does not restate them. Fetch ladder: TOOLING.md.
Judgement rules (capped): JUDGEMENT.md. Quality checks: QA-REGISTER.md.

## 0. Announce first (CLAUDE.md rule)

One line before any code runs: `USING EXISTING: <path>` or `NEW CODE: searched TOOLING.md for
"<what>" - found nothing`. No line means the check was skipped, and that is the defect.

## 1. Run what already exists before writing anything

1. Search TOOLING.md and QA-REGISTER.md for the job ("compare delivery", "check links", "read page").
2. Run the sanctioned script (`qa_import.py`, `check_invariants.py`, `weekly_verify.py`,
   `release_gate.py`, `customer_context.py`, `live_build.py` ...). Existing scripts carry the joins and guards
   that throwaway code lacks.
3. A hand-made comparison is only allowed after saying nothing covers it. If it is useful twice,
   it goes in the repo with a test.
4. Any manual check that is not in QA-REGISTER.md belongs there.

## 2. A page that will not load is NOT an answer (the CDP step)

Never record "dead", "unclear", "no sponsor", "not found" from a failed or empty read.

Climb the whole ladder, in order, and write down which rung gave the answer:

1. plain fetch / crawl4ai
2. Playwright fallback
3. **the real Chrome over CDP (port 9222, profile `%USERPROFILE%\cfp-cdp-profile`)**
4. a person looking at it
5. only then "unresolved" (and say it is unresolved, not negative)

- Before blaming the site, check the BROWSER LAYER is alive: `python scripts/cdp_ctl.py check`.
  If it is down, start it (`scripts\launch_chrome_cdp.bat`, or `cdp_ctl.py wait`) and re-read. Stop it
  afterwards only if you started it (`cdp_ctl.py stop`).
- Hard anti-bot hosts (403, Cloudflare, Akamai, "verify you are human", timeouts only on that host)
  are read through the real Chrome. They are never hammered with repeated plain requests: a flagged
  home IP costs more than a missed event.
- Several different hosts all failing at once means OUR layer is down (browser crash, dialog
  crash, network), not that 100 sites died. Stop and fix the layer before recording anything.
- Zero readable pages for an event is a failed read. It is never stored as a finding.
- Different failures, different handling (JUDGEMENT 11): host does not resolve vs page will not load
  vs blocked vs empty. Name which one you have.

## 3. Verify the claim against the data before saying it

- Count from the file or database, do not estimate. State what was counted and with which tool.
  (Past errors: "65 files behind" when 84; "10 unclear" when 15.)
- Check today's date and weekday before saying "before Sunday" or "this week".
- Match on the value, not the key: cross an upstream EVENT_ID with `identity.to_canonical`.
  An empty map returns zero findings that read as agreement.
- Check you have the right EVENT, not just the right name (CCUS vs WCCUS: the "confirmed dates"
  belonged to a different event).
- A claim that goes to Nicolia, upstream or a customer is verified first, from the data, in the open.

## 4. Change things only through the sanctioned path

- Code to the live build: `scripts/live_build.py` only. Never copy a file across by hand
  (JUDGEMENT 13: partial copies die at import).
- Data edits: back up to `Markets/backups/` first; use pins (`pinned_rows.json`) or the relay,
  never a quiet hand edit of an audited CSV. Customer-owned columns are never written.
- After any import or migration: `scripts/check_invariants.py`. Never bless a golden-master diff unread.
- An input row that is not researched yet can stop an import "short": remove, import, restore
  byte-identical, and say so.
- Anything another program must read lives inside the project folder; verify from the far side
  (size, timestamp, hash). A Claude shell may write to a sandboxed copy.
- Spend, billing and caps are Matt's decision. Do not run paid grounding to "just check".

## 5. Test the way it will really run

- Unit tests passing is not the same as the scheduled job working. Rehearse on a copy, then
  confirm with one real or one-time cloned scheduled run (never a hand-built command line).
- Run the tests that cover what you touched, and the live interpreter's smoke (`live_build.py`).
- A fix to a long job: run a SMALL real slice first and read its output before the full run.
- When a run produces a surprising number, ask who produced it (JUDGEMENT 10) before reporting it.

## 6. Shell and tooling traps on this machine

- Windows PowerShell 5.1: no `&&`. Chain with `;` and `if ($?) { }`.
- Python with backslashes or heredocs: write a script file (Write tool) rather than inline quoting;
  `\b` in a normal string becomes a backspace character.
- Edit tool needs the file read first. Check line endings (CRLF) when patching by bytes.
- Never print keys or tokens.

## 7. Before saying "done"

- Created, changed or disabled a scheduled task? Its entry in `agentos/tools/scheduled-tasks.manifest.json`
  (purpose, criticality, what depends on it, whether the PC must be on) is part of the change, not a follow-up.

- State what was verified, how, and what was NOT verified.
- Anything left running (Chrome on 9222 that you opened, background jobs) is closed or named.
- Uncommitted fixes are committed, or listed as uncommitted.
- Changed behaviour of the weekend process: update WEEKEND-PROCESS.md, then
  `check_process_doc.py --confirm`.
- Offer a memory save if a decision, gotcha or new tool came out of the session.

## When a new mistake repeats

Do not add a paragraph here first. Ask: can it be a test or a guard in code (JUDGEMENT cap
rule)? If not, add ONE line to the matching section above.
