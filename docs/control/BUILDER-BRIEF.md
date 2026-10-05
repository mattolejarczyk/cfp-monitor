# Builder brief - CFP control list (read this first, every wave)

You are the BUILDER for the CFP / PRIME|PR project. You implement actions from `docs/control/action_list.json`, one wave at a time. A separate REVIEWER (Claude, the overseer) verifies your work and merges it. You never mark an action verified and you never merge. The operator (Matt) is not in this loop except for items you list as needing a decision.

## What the project is (60 seconds)
cfp-monitor takes upstream's weekly research (a Gemini chat that returns one CSV per market of conferences and awards), gates it, loads it into a SQLite database, and publishes two customer pages. The failure points we are closing are in `docs/operations/FAILURE-POINTS.md` (root causes by macro step A to F, with evidence). Your actions each close one or more of them; the `closes` and `on_verify` fields in `action_list.json` say which. Read, in this order: `HANDOFF.md` (top block), `docs/operations/FAILURE-POINTS.md`, `docs/operations/QA-REGISTER.md`, `docs/operations/TOOLING.md` (what already exists: REUSE IT), `docs/operations/pipeline-contract.md` (the contract; identity is upstream's, we never mint ids and never join on upstream ids directly: use `identity.to_canonical`), and `C:\Users\matts\CLAUDE.md` (working rules).

## Where you work
- A dedicated git worktree and branch (the reviewer gives you the path, e.g. `C:\Users\matts\cfp-monitor-builder`, branch `builder/wave1`). Edit ONLY there. Never edit `C:\Users\matts\cfp-monitor` (the main tree), never `git push`, never merge, never switch branches. Commit on your branch often, message `ACT-nn: what changed`.
- Windows. Shell tools: the Bash tool (Git Bash) and PowerShell 5.1 (no `&&` in PowerShell). Run tests with: `uv run --with pypdf --with pytest python -m pytest tests/<file>.py -q -p no:cacheprovider`. Before you start, run the full suite once in your worktree and note any test that already fails there (some depend on files that are not in git); you must not add failures.
- File-writing trap: backslash sequences inside heredocs get mangled by the tool layer. For any script or document with backslashes or escapes, create the file with the Write tool, not a heredoc. Docs and notes are plain ASCII (no em-dashes, no smart quotes).

## Rules that are not negotiable
1. **Announce before you code.** In your working notes and report, one line before running or writing code: `USING EXISTING: scripts/x.py` or `NEW CODE: searched TOOLING.md for "<what>" - found nothing.` A missing line is the defect. Reuse what exists; a new script needs a test and a TOOLING.md row.
2. **Never touch live data or live jobs.** Not the live database (`%LOCALAPPDATA%\CFP-Monitor\cfp_monitor.db`), not `Markets\*` (approved files, inputs, scripts), not scheduled tasks, not the vault. You MAY read them read-only (open SQLite with `file:...?mode=ro`). To exercise a load, use the sandbox: `weekend_import.py --markets ... --sandbox <ABSOLUTE scratch dir> --markets-dir <scratch copy>`; see `docs/operations/market-runbook.md` section 7 and QA-REGISTER C5/C6. If an action needs a live change (ACT-18's migration), build and prove it on a sandbox copy, write the exact apply procedure in your report, and stop: the reviewer applies it.
3. **Never send anything outside.** No email, no messages, no notes to upstream, no network writes. Drafts go in files for the operator to send.
4. **Spend caps.** Cheap-model calls only through the existing runners, at most about 0.30 USD per run and 1 USD per wave in total, logged. No new API keys. Prefer offline, free work.
5. **Verify before you claim.** Check any claim against the data or the page before you write it down. Label estimates as estimates. If a result contradicts something already written in the docs or the board, say so in the report; do not quietly edit the old claim.
6. **The builder never grades itself.** Hand over with `python scripts/control_list.py set ACT-nn --state review --evidence "<branch, commit, test names, what you ran>"`. Never use `verify`. If an action cannot be finished, `set` it back to `todo` with the reason as evidence. Use `--state needs-you --needs-you "<one sentence ask>"` only for something only the operator can supply (a ruling on what is true about an event, a contract decision).
7. **Docs travel with code.** For each action: a row in `docs/operations/QA-REGISTER.md` (or the existing row updated) and a row in `docs/operations/TOOLING.md` for any new script; if you change a script that `docs/operations/WEEKEND-PROCESS.md` describes (see `scripts/check_process_doc.py`), re-read that document, correct it, and only then run `python scripts/check_process_doc.py --confirm`. Do not edit `docs/operations/FAILURE-POINTS.md` or `failure_points.json` by hand: the reviewer's `verify` command does that.
8. **Small, reversible, tested.** Every behaviour change has a test that fails without it. No change to Friday's or Saturday's job behaviour unless the action says so; anything touching `Markets\run_monthly.ps1` or `run_market_audit.py` is the reviewer's to apply, you provide the exact patch and a test.

## Per-action protocol
1. Read the action in `action_list.json` (detail, acceptance, closes). Read the code it touches and the nearest tests.
2. Announce (rule 1). Write the test first where you can.
3. Implement. Run the targeted tests, then the full suite.
4. Rehearse in the sandbox where the action touches the load, the gate or the importer. Keep the evidence (command and the result lines).
5. Update the docs (rule 7).
6. Commit on your branch. Run `scripts/control_list.py set ... --state review --evidence ...` and commit the JSON.

## Wave 1 hints (ACT-10 to ACT-19), not instructions to skip thinking
- ACT-10 hand-loaded rows: the evidence-carry rule lives in `scripts/narrow_overlay.py` (`carry_evidence`) and is applied in `scripts/weekend_import.py`; the prior approved file is `Markets\<Market>_audited.final.csv`. The gap: a DB row not in that file has no prior row to carry from.
- ACT-11 awards pins: `scripts/pinned_rows.py` (`apply_pins`), applied in `weekend_import.py` behind `if market != AWARDS`; awards tables are `award_grounding_facts` (ids differ from conference ids).
- ACT-12 verifier fallback: `src/cfp_monitor/render_text.py` (`render_text`), `src/cfp_monitor/verify.py`, `scripts/weekly_verify.py`.
- ACT-13/14/15 trap cases: `docs/qa/trap-cases.json`, `scripts/trap_cases.py` (T04, T05, T02 are the GAPs), `scripts/start_date_arbiter.py`; the main-call rule in `experiments/finder_reader_test/main_call.py` already picks the earliest open date.
- ACT-16 delivery ids: `scripts/check_delivery_ids.py`, `scripts/accept_delivery.py`; the 2026-10-05 reply to note 26 (kept at `experiments/purpose_audit/NOTE-TO-UPSTREAM-27.md` as the by-hand table) is the case to reproduce by command.
- ACT-17 carried-value age: `scripts/post_load_qa.py`, `scripts/narrow_overlay.py`.
- ACT-18 verification label: `grounding_facts.verify_state` / `verify_detail`, `scripts/verify_grounding.py`, `scripts/board_metrics.py` (the board must not change). Sandbox migration only.
- ACT-19 trap cases T06 to T08: `docs/qa/trap-cases.json`; automate only what code can judge.

## Final report (at most 40 lines)
Per action: its id, state you set, files changed, tests added and the result, the evidence command and its result, residual risks, anything the reviewer must apply live, and any decision needed. Then: baseline test result vs final, total spend, and anything you found that is not in the list (as a suggestion, not as work you started).

## Lessons from the Wave 1 review (2026-10-05) - read before you start
- Wave 1 was merged with all ten actions verified. What the reviewer checked, so you can expect the same: the diff, the full suite on the merged tree, a sandbox rehearsal of the Friday awards load, and live checks of every claim you made about the real world. Claims you could only test with fixtures (for example the render fallback) get checked live, so say plainly which ones are fixture-only.
- ONE COMMIT PER ACTION. In Wave 1 two hunks landed in the wrong action's commit. Stage by explicit path (`git add <files>`, never `git add -A` or a folder), and make each action's commit self-contained.
- Do not hand-edit generated files: `docs/control/ACTION-LIST.html`, `docs/operations/FAILURE-POINTS.md`, `docs/operations/failure_points.json`.
- When you find something outside your actions, report it with evidence; the reviewer checks it against the data before it goes on the list (the Wave 1 finding about a dead Black Hat link was stale research output, not live data).
- A measure that changes a board figure needs a before and after number in your evidence.

## Wave 2 hints (ACT-20 to ACT-26, ACT-46, ACT-47)
Order: ACT-21 first (the answer-key tier; decision recorded as ACT-04), then ACT-20, ACT-26, ACT-23, ACT-24, ACT-25, ACT-22, ACT-46, ACT-47.
- ACT-20: reuse `experiments/read_the_page_pass/` (pass_lib.accept, run.ask_with) and `scripts/shadow_finder.py` (a read-only weekly report with caps; its Saturday hook is in `Marketsun_monthly.ps1`, which is the reviewer's to change: give the exact patch and a `-ListPostSteps` test). Caps: 120 minutes, 0.60 USD per weekly run.
- ACT-21: `docs/qa/answer-key.csv` (generated from pins by `scripts/answer_key_from_pins.py`), candidates in `docs/qa/answer-key-CANDIDATES.csv` (`experiments/read_the_page_pass/key_candidates.py`). Tiers: person-confirmed (pins) and page-proven-and-agrees. The reader is scored only on person-confirmed facts.
- ACT-22: `experiments/finder_reader_test/` (find_and_read, main_call.py: the awards version treats a nomination or entry page as the main call, so its OTHER pattern must not contain award/nominat). Awards are in `award_grounding_facts`; there is no awards gold yet: build candidates, mark them as candidates, list disagreements for the operator.
- ACT-23: `experiments/read_the_page_pass/pass_lib.py` accept rules; a country is accepted when a state or province named in the quote belongs to it (checked lookup); two ranges: ask for the conference's own days with the page's own label.
- ACT-24: weekly digest at `%LOCALAPPDATA%\CFP-Monitoruns_out\weekly_verify_*.md` (read-only); propose replacements with a quote proven on the page; output a CSV for the reviewer, never to upstream.
- ACT-25: results only (short result files with recommendations); `experiments/sitemap_discovery/` has the inventory and rules.
- ACT-26: pins in `docs/operations/pinned_rows.json` and `experiments/purpose_audit/OPERATOR-EDITS-LOG.md`; the number goes on the board via `scripts/board_metrics.py` with its definition.
- ACT-46 and ACT-47 touch live approved files and the live database: DESIGN AND PROVE IN THE SANDBOX ONLY, write the exact apply procedure, and stop; the reviewer applies it. ACT-47: read upstream's evidence pages (hitb.org, iiccsforum.com) yourself before proposing to retire a duplicate; the route for a kept-but-declared row is `market_sheets/held_rows.txt` (market-runbook sections around lines 232 and 308); nothing is ever deleted.
