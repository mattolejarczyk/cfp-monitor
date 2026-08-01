# Joint Pipeline Contract — upstream grounding ↔ downstream monitor

**Version 1.1** · 2026-08-01 · **supersedes v1.0 in full**
**Status:** authoritative for both sides. Where this and upstream *Specification v4.3*
disagree on interface, boundary, acceptance or defect rulings, **this document wins** and
v4.3 is amended to match.
**Read this first** if you are picking up the CFP pipeline with no prior context.

> **One text, both sides.** This file is versioned in the downstream git repo and sent whole
> after any change. Replace any earlier copy with it verbatim rather than merging — two
> divergent copies of a joint document is the exact failure this contract exists to prevent.

---

## What changed since v1.0

v1.0 was assembled from an extract and was missing five sections. Nothing in it was wrong;
this version is a superset.

| Added | Why it matters |
|---|---|
| **§10 Rulings on hard cases** | The most important addition. Nine precedents that each cost real debugging — venue-vs-city, one event running several calls, regional siblings, renamed duplicates, editions, PDFs, 403s. Without these they get re-litigated. |
| **§6 Verification model** | The three layers and the five guards, each traced to the false positive that produced it. Explains *what makes a citation useful downstream*, so the deep-link rule reads as a consequence rather than a preference. |
| **§7 What the customer sees** | The four confidence labels, so it is clear where `IS_PROJECTED` actually lands. |
| **§5 Downstream obligations** | What downstream promises never to do to upstream's data. |
| **§12 Ruling log** | Dated trail, so future changes are traceable. |

Also amended: R9 and R10 now carry the reasoning behind them, and the acceptance gate states
explicitly which side owns each criterion.

---

## 1. What this describes

Two independent systems produce one deliverable for the customer (Nicolia Wiles / PRIME|PR).

| | |
|---|---|
| **Upstream** | A Google-Search-grounded research process. Discovers events, deadlines, statuses and citations. Emits one 35-column CSV per market. Operates to *Specification v4.3*, which mirrors §4 of this document. |
| **Downstream** | `cfp-monitor` — a local, residential-IP crawler and verification layer. Imports the CSV, crawls and checks claims against live pages, derives the customer view. |

Neither side is subordinate. Upstream has reach we cannot match; downstream has verification upstream cannot perform. **The contract is the interface between them.**

---

## 2. Principles

These are the load-bearing decisions. Everything mechanical below follows from them.

**2.1 Discovery is innocent until proven guilty.**
An upstream claim stays in the customer's sheet unless a page positively contradicts it. "We could not verify it" is *never* a disproof — it is a label (`Unconfirmed`), not a deletion. This is the single most important rule; several bugs were fixed by restoring it after code had quietly started treating silence as refutation.

**2.2 Derive, don't mutate.**
Gates and labels are computed at display time against the current date, never written into storage. A row that says "Closed" says so because the deadline has passed *today*, not because someone stamped it. Stored gates go stale the day after they are written.

**2.3 Status outranks the date.**
The customer's question is *"can my client still submit?"* — not *"what was the date?"*. A page saying *"the deadline has expired and submissions are no longer accepted"* answers it definitively with no date at all. Closure language is first-class evidence and is checked **before** any date comparison.

**2.4 Correction-precedence.**
A human-verified value is never silently overwritten by a later crawl or a later delivery.

**2.5 Decline rather than guess.**
Where a match, a merge or a verdict is ambiguous, produce nothing. An unlabelled row is honest; a row wearing another event's evidence is wrong in a way nobody downstream can see.

**2.6 An honest blank beats a confident guess.**
This applies to both sides, and it is why upstream is never scored on how many rows it verifies. Pushing that number up produces invented citations — which is exactly what happened before these rules existed.

---

## 3. The boundary

| Owned by upstream | Owned by downstream | Owned by the customer |
|---|---|---|
| Event discovery | Crawling and verification | `STATUS` (their submission pipeline) |
| Deadlines, statuses, citations | `GATED_STATUS`, `ISSUES`, `CONFIDENCE` | `NOTES` |
| `OPPORTUNITY_TYPE` | Canonical keys, market membership | `SUBMISSION DATE VERIFIED` |
| `IS_PROJECTED` | `RESEARCH STATUS`, `EDITION`, `TRACK` | |

**Downstream never edits the customer's Google Sheet.** Output is a file they import.

Two columns exist in the upstream schema but are **computed downstream and ignored on import**: `GATED_STATUS` and `ISSUES`. Upstream leaves them blank.

---

## 4. Upstream obligations

Full text lives in *Specification v4.3*. Summarised here so this document stands alone.

**R1 — Citation withdrawal is a citation-only edit.** Clear `DEADLINE_EVIDENCE_URL` and `DEADLINE_QUOTE`; `SUBMISSION DEADLINE` is untouched. A date change is new research and needs a new citation.

**R2 — `IS_PROJECTED`.** `false` only when the deadline is past with `STATUS = Closed`, or a future date is backed by a live citation carrying the claim. Otherwise `true`.

**R3 — What counts as a citation.** The exact page the sentence was read on. It must (a) resolve, (b) be the specific page — never a homepage, section index or `/exhibit` page, (c) contain the claim. **HTTP 403 is acceptable** — the page exists but blocks readers; keep the deep URL and downstream marks it *Blocked-but-Trusted*. Never substitute a shallower URL to obtain a 200.

**R4 — Prose matches evidence.** `STATUS DETAILS` is what a human reads. "Active" / "Open" / "Closed" only when read on a page and quoted. Otherwise the projection form: `[Call for Speakers Pending / Expected Fall 2026]`.

**R5 — Opportunity typing.** `OPPORTUNITY_TYPE` ∈ `Speaking` | `Awards` | `Exhibiting` | `Registration`. One row per real opportunity. `Exhibiting`/`Registration` rows carry no submission deadline. The citation must match the row's type.

**R6 — Declare the pass type.** `correction` (only the fields named in feedback; no rows added or removed, no dates changed) · `re-research` (anything may change; manifest required) · `schema` (structure only).

**R7 — Change manifest** on every re-research: row counts, added, removed *with a reason each*, deadlines changed, dates changed, citations added and withdrawn.

**R8 — File format.** RFC 4180 via a real CSV writer. Exactly 35 columns. `CITY` holds a city — venues belong in `LOCATION`. `GATED_STATUS` and `ISSUES` blank.

**R9 — Name stability.** *(added 2026-07-31)* Do not rename an existing event between deliveries. Our canonical key is derived from the name, so a rename creates a second record for one event. If a rename is unavoidable, list it under `RENAMED: <old> -> <new>` in the manifest.

**R10 — Call-level identity.** *(added 2026-07-31)* One event may run two distinct `Speaking` calls — IBC has Technical Papers *and* the Accelerator programme, with different deadlines. `OPPORTUNITY_TYPE` does not separate those. Emit them under distinct event names, or populate `CALL_NAME`.

---

## 5. Downstream obligations

1. **Never overwrite a grounding claim.** Claims live in their own table (`grounding_facts`); crawled facts live in `conferences`. A failed or thin crawl can neither confirm nor erase a claim.
2. **Only positive contrary evidence contradicts.** 404 disproves a link. A page stating a different deadline disproves a date — *but only on the page that was cited for it*. Timeouts, 403s, blocked pages and empty fetches resolve to `not_found`, and the claim stands.
3. **Match evidence to the right record.** Editions must agree; sibling calls and regional variants must not borrow each other's evidence; where it is ambiguous, attach nothing.
4. **Recompute keys.** We derive `EVENT_ID` ourselves (`<year>-<name-slug>-<city>[-<opportunity>]`, market deliberately excluded so one event can serve several markets). Upstream's `EVENT_ID` column is not read.
5. **Report the market vocabulary.** Unknown market labels are surfaced for a human decision, never auto-registered.
6. **Gate at display time.** Past deadlines read `Closed`; the row self-corrects as dates pass.

---

## 6. Verification model

Three layers, cheapest first. Each may resolve a claim or decline to.

| Layer | What it does | Cost |
|---|---|---|
| **L0 / L0s** | Cross-check against pages we have already crawled. `L0s` compares **status** first, `L0` the deadline. | free |
| **L1** | HTTP check of the submission link. Only ever returns a negative: 404/410 means the link is dead. | fast |
| **L2** | Fetch the cited page and check status, then date. Reads PDFs (deadlines are often only in the call-for-papers PDF). | slow |

**Outcomes:** `verified` · `contradicted` · `not_found` (claim stands) · `unverified` (not yet checked).

**Guards, each earned from a real false positive:**

- L0 declines when the editions differ — our 2026 record says nothing about a 2027 claim.
- L0 declines when our own record has expired — a row reading "open" whose close date was last December is stale, not evidence.
- L0 declines when our crawl quality is not `PASS`, including for *confirmation* — a thin row may itself have been populated from grounding, and grounding confirming grounding is circular.
- L2 accepts a rival date as a contradiction **only on the cited page**. A homepage carries event dates, registration dates and last year's deadline side by side.
- L2 labels the result by the page actually read, so a fallback page's silence is never reported as the cited page's silence.

---

## 7. What the customer sees

`CONFIDENCE` answers *"can I act on this without checking first?"*

| Label | Meaning |
|---|---|
| **Confirmed** | We read this deadline on the event's own page |
| **Unconfirmed** | Research we could not confirm — including every `IS_PROJECTED` forecast |
| **Check link** | The submission link did not resolve; do not send a client to it |
| **Disputed** | A page positively contradicts the claim |
| *(blank)* | No deadline and no claim — nothing to characterise |

A projected deadline can never read `Confirmed`, even if it later proves right: at the time of writing, nothing on the page said it.

`RESEARCH STATUS` is ours (Open / Closed / Needs Review, with the edition year). `STATUS` is the customer's own submission pipeline and **we never write it**.

---

## 8. Acceptance gate

A market list is accepted when all of these pass. Criteria 1–5 are upstream's, 6–8 ours.

| # | Criterion | Threshold |
|---|---|---|
| 1 | Every row parses to exactly 35 fields | 100% |
| 2 | Cited pages returning 404 | 0 |
| 3 | Cited page contains its quote (403 exempt) | 100% |
| 4 | Confident prose on an `IS_PROJECTED = true` row | 0 |
| 5 | `Exhibiting`/`Registration` row carrying a speaking deadline | 0 |
| 6 | Past deadline still presented as open | 0 |
| 7 | Row wearing another event's evidence | 0 |
| 8 | Open rows labelled `Confirmed` or `Unconfirmed`, never blank | 100% |
| 9 | Verified count | **reported, never targeted** |

**On criterion 9.** Semiconductor reached 15 confirmed of 44; Consumer Electronics 7 of 45. That gap is not a quality difference — Consumer Electronics is mostly forecast-stage events with nothing yet citable. **A verification rate is a property of the market, not a score.** Targeting it would push upstream back toward inventing citations, which is precisely the failure these rules removed.

---

## 9. The review loop

Proven over three cycles (Semiconductor, Consumer Electronics, Bioeconomy):

```
upstream delivers  ->  downstream audits  ->  defend-or-correct  ->  re-emit  ->  accept
```

**The audit runs against the previous file, not just the new one.** This is why R6 matters: an undeclared re-research forces a full re-verification instead of checking the handful of fields that changed.

**Defend-or-correct** — every finding offers three answers, all acceptable:

- **Defend** — supply the exact URL where it was read; we re-check.
- **Correct** — supply the right value with a working citation.
- **Withdraw** — blank the citation and quote, keep the deadline, set `IS_PROJECTED = true`.

**Verify corrections as rigorously as original claims.** Every cycle so far has had at least one problem introduced *by* a fix: a deadline moved silently behind a withdrawal, a homepage substituted for a blocked deep link, an exhibiting page cited for an awards deadline. The diagnosis has consistently been sound; the execution is where data moves unnoticed.

---

## 10. Rulings on hard cases

Precedents. Each cost real debugging; do not re-litigate without new evidence.

| Case | Ruling |
|---|---|
| **Venue vs city** | `CITY` is the city. Repaired on import, but city-states are protected — dropping "state" would destroy Berlin, dropping "country" would destroy Hong Kong. |
| **One event, several calls** | Different calls at one event never share evidence. IBC's Accelerator programme is not IBC Technical Papers. |
| **Regional siblings** | `Europe` / `USA` / `East` / `West` / `Spring` / `Fall` separate distinct events that may share 75% of their words. Similarity alone must not merge them. |
| **Renamed duplicates** | "AAOS 2027 Annual Meeting" and "AAOS Annual Meeting 2027" are one event — neither contains the other, so substring matching is insufficient. |
| **Editions** | Never compare across editions, in either direction, for any purpose. |
| **PDF citations** | Valid and welcome. Detected by magic bytes as well as content-type; an unreadable PDF resolves to `not_found`, never a disproof. |
| **HTTP 403** | Real but blocked. Never a disproof, never grounds for substituting a shallower URL. |
| **Multi-market events** | Membership is many-to-many in its own table; market is excluded from the key so one event is one record. |
| **Near-duplicate markets** | Merge threshold 0.70, measured: real variants scored ≥0.75, distinct markets ≤0.44. |

---

## 11. Related documents

| Document | Held by | Contents |
|---|---|---|
| *Specification v4.3* | upstream | Full upstream mechanics. §4 here is a **summary only** — v4.3 is the full text. If a rule changes, change it there and tell us. |
| `docs/operations/market-runbook.md` | downstream | The operating procedure: commands, order, checks, failure modes. Internal — no action for upstream. |
| `HANDOFF.md` | downstream | Project-wide map |
| `docs/design/roadmap-status.md` | downstream | Feature status and history |

The last three are downstream-internal and listed for completeness, not as required reading.

---

## 12. Ruling log

| Date | Ruling |
|---|---|
| 2026-07-29 | Grounding claims live in their own table; a crawl never overwrites them |
| 2026-07-30 | Status verified before date; closure language is decisive without a date |
| 2026-07-30 | Quality gate precedes confirmation as well as contradiction (no circular self-confirmation) |
| 2026-07-30 | PDF citations read and accepted |
| 2026-07-31 | A result is labelled by the page actually read, not the page cited |
| 2026-07-31 | Status cross-check must respect edition and staleness |
| 2026-07-31 | A rival date disproves only on the cited page |
| 2026-07-31 | Grounding keys include the opportunity; `Speaking` stays unsuffixed |
| 2026-07-31 | Evidence attaches to the record it describes, or to nothing |
| 2026-07-31 | R9 name stability, R10 call-level identity added |
| 2026-08-01 | Contract v1.1 issued as one shared text, superseding the v1.0 extract |
