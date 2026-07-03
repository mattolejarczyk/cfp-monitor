# Voice of Customer — MASTER (Nicolia / PRIME|PR)

**Authored running synthesis** of customer voice for the conference/CFP + awards monitor. This is the *living* VOC doc for the local build; the frozen VPS handoff copy is `../handoff-from-vps/must-pass/VOICE_OF_CUSTOMER_REQUIREMENTS.md` (baseline, do not edit).

**Raw sources (unedited):** `transcripts/Prime-Nicolia-Transcript-20260617.txt`, `transcripts/Prime-Nicolia-Transcript-20260624.txt`.
**Precedence rule:** when calls conflict, the **later** call wins (6/24 > 6/17).
**Customer Google Sheet** (READ-ONLY reference, never edit): source-of-truth conference/award lists live in Nicolia's Google Sheets, tabbed by market.

---

## 0. Decisions locked (2026-07-03) — supersede conflicting VOC above
- **Pure-local (the user's computer) for now.** Crawl runs from the user's machine to avoid VPS blocking. The 6/24 "hybrid cloud+local ~90/10" framing is **deferred** — VPS/hybrid crawling is **archived for potential future scale** (learnings preserved in `../handoff-from-vps/`), MAYBE the scaled approach later, not built now. (Supersedes §2.)
- **Conferences first, awards later.** Awards sequenced *after* the conference pipeline is solid (§3 awards = deferred entity).
- **Own the data end-to-end.** No Brandable DB access today, so we maintain **our own DB as source of truth** now. Brandable plugs in *later* to read from our DB (via a read API/export). Not a locked architectural decision yet — low-regret default; revisit when Brandable integration is real.

---

## 1. Product shape (clarified 6/17)
**Two distinct layers — build them as separate concerns:**
1. **Master database = source of truth.** All conferences/awards across all markets, agent-crawled, then **human-verified** by Prime/Nicolia. This is the "reality" layer.
2. **Customer-facing dashboards = per-subscriber views** over the master. Filtered by **market tags** (a hydrogen customer never sees cybersecurity). Each customer can add **their own private notes** per row. Read-only projection of the master + personal annotations.

**Integration target — do NOT rebuild what exists:** the customer layer plugs into the existing **Brandable PR** app (`app.brandable-pr.com`, Figma/Cloudflare, built by a Fiverr dev "Sharif"). Brandable **already has user login / role-based access / billing**. So our job is likely to **feed master data + tag-filtered views** into Brandable, NOT build auth/portal from scratch. (Confirm Sharif's backend before assuming — Matt to have that conversation.) This can **shrink** the "client portal" (M8) scope.

## 2. Crawl + extract model (6/24 is latest)
- **Hybrid cloud + local, ~90/10.** Bulk crawling in the **cloud** (fast) for sites that allow it; the **blocked minority** routed to a **local desktop app** on the customer's/Matt's machine (residential IP bypasses anti-bot). Seamless to the user: "wasn't able to get these — run locally? yes."
  - ⚠️ **Reconcile with gap analysis:** our gap-analysis chose "run locally / residential" to kill blocking. Matt's 6/24 framing keeps cloud for speed + **local only as the fallback for blocked URLs** — i.e., the local-browser recovery concept is *not fully dead*, it's the 10%. Decide: pure-local vs hybrid. (Local proved 7/7 URLs accessible in Matt's test vs cloud failures.)
- **Tiered model strategy:** 3–5 **best free/cheap** models do the bulk extraction; **premium model only on the gap** (hard/complex pages) — "don't pinch pennies on smart extraction; it's $2 vs $10." Continuous free-model benchmarking. → matches WBS D1 (gold-set) + tiered extraction.
- **Internal-link discovery** (human-like): land on site, extract internal links, crawl the promising ones (register/CFP/submit/contact) rather than hard-coded URL guesses. Cut a 105-static-URL crawl to 38 (~67% faster). → matches methodology docs.
- **Smart URL / path memory:** remember which page yielded the data; revisit it first next time. → matches B3.

## 3. Data-model requirements (new specifics)
- **Market tags** on every master record (cybersecurity, hydrogen/energy, AI, SaaS, …); customer dashboards filter by subscribed tags.
- **Conferences AND awards** are **both first-class** (separate discovery prompts + lists). The current `cfp-monitor` build is conference/CFP-centric — **awards is a parallel entity to add.**
- **Verification lifecycle (human-in-the-loop):** agent proposes a value → state `needs verified` → human checks → `verified` (higher trust; agent guessed dates are ~80% wrong, so verification is required before customer trust). Preserve verified values (→ correction-precedence, B4).
- **"Last checked / last crawl date" is customer-visible and required.** Customers want to know *when we last looked*, even if nothing changed ("has anyone looked at this recently? yes, yesterday").
- **Past-event rollover:** weekly job must re-check **past-dated** events for the **next-year edition** (e.g., SecureWorld 2026 → find 2027), not just pending "needs verified" rows.
- **Multi-location / multi-edition events:** one event with many cities/dates (e.g., SecureWorld across cities) — represent cleanly; list each as an opportunity.
- **Platform false-positives:** distinguish aggregator/platform pages (e.g., **Sessionize**) from the actual conference; follow through to the real event URL.

## 4. Workflow & cadence
- **Weekly automated crawl** (Nicolia's Gobi ran Mondays 4am): (a) verify pending, (b) roll over past events, (c) surface new opportunities.
- **Alerts on change** (new CFP found, new/updated deadline) — immediate or end-of-day digest, by market. → bucket C.
- **Weekly executive report** = opportunities + **system health** (failures, extraction quality metrics), not just CFPs. → C3.
- **Cadence:** weekly Wednesday ~4pm CT check-ins; short show-and-tell demos.

## 5. Economics & relationship (context / project memory)
- **The $500/mo is a token/development budget** (raised from $250 → $500 by Nicolia to remove Matt's token constraints), NOT a productized service retainer. Paid ~monthly on the 18th to **AI Digital Agents LLC**.
- **Partnership on the table:** Nicolia offered **equity + % of sales in perpetuity** (Option B) over a one-time build fee (Option A); both prefer B. Matt "really good with that."
- **Pricing model for the product:** Brandable base ~**$49/mo** (conference/award access + guaranteed publishing); stack **add-on services quarterly** (pitching ~$299/mo, SEO blog+video ~$199/mo) to re-monetize existing customers.
- **Build philosophy Nicolia bought into:** modular/componentized so pieces can be swapped when models get cheaper/native; "what costs $5k today is free next year."

## 6. Downstream vision — Phases 3–5 (OUT OF SCOPE now; recorded so we build Phase 2 compatibly)
- **Phase 3 — AI-assisted warm pitching:** build a media list of relevant editors, generate hyper-personalized 3-email sequences referencing each editor's latest article; ~30–40 sends/day. (Nicolia has this working manually / semi-automated.)
- **Phase 4 — cold marketing outbound:** Apify LinkedIn scrape → hyper-personalized cold email (Instantly/Seamless), 10k-contact lists. (Beyond PR.)
- **Phase 5 — voice agents:** inbound + outbound calls (regulatory caveats).
- **Adjacent ideas (6/24):** blog→YouTube SEO video (animated explainer/avatar), auto-blog in Nicolia's style. Strong external interest (a ~5,000-employee PR firm would deploy org-wide) → TAM signal.

---

## 7. Impact on the plan (what changed vs the 62-req scorecard / gap analysis / WBS)
| New/changed insight | Effect |
|---|---|
| Two-tier: master (verified) + tag-filtered customer dashboards | Expands bucket B; reshapes M8. But Brandable already has auth/billing → M8 may **shrink** to "feed data + views." Confirm Sharif's backend. |
| Hybrid cloud+local (90/10), not pure-local | **Reconcile** with gap-analysis "run local" decision — local may be the 10% fallback, not the whole engine. Genuine architectural fork. |
| Verification lifecycle + last-checked date (customer-visible) | Concretizes B4 (correction-precedence) + provenance; adds a required state machine + timestamp surfaced to customers. |
| Past-event rollover (find next-year edition) | New crawl behavior; add to scheduler (C1) + change detection (B2). |
| Multi-location / multi-edition events | New data-model + extraction case; needs a good model (premium tier). |
| Awards as first-class alongside conferences | New parallel entity in schema/discovery; current build is CFP-only. |
| $500/mo = token budget + equity path (not a fixed retainer) | Corrects project economics; equity aligns incentives for a longer build. |

---

## 8. Customer sheet format (target OUTPUT view)
Real customer file: `Utility Global Conference List 2026.xlsx` (stored raw in this folder; single tab "Conference List", ~1,001 rows). This is the **customer-facing view** — distinct from our internal **54-column** extraction schema (`../handoff-from-vps/must-pass/PROCESS_DOCUMENTATION.md`). Our own DB is the rich source of truth; we **transform/export** it down to these 15 columns for the customer (and later feed the same into Brandable).

**The 15 columns (A–O):**
| Col | Header | Maps to VOC / our field |
|---|---|---|
| A | CONFERENCE | conference name |
| B | CONFERENCE URL | canonical event URL |
| C | LOCATION | city/venue/country (handle **multi-location** events, §3) |
| D | START DATES | event dates |
| E | LATEST UPDATE | **last-checked date** (§3) — shown even when nothing changed |
| F | SUBMISSION DEADLINE | CFP close date |
| G | SUBMISSION DATE VERIFIED | **verification lifecycle** (§3) — human-verified flag |
| H | PRIORITY | customer/analyst priority |
| I | STATUS | e.g. Submitted / Open / Not yet scheduled |
| J | STATUS DETAILS | free-text basis (e.g. "not yet scheduled a 2027 conference") — supports **past-event rollover** (§3) |
| K | SUBMISSION URL | where to submit |
| L | COORDINATOR EMAIL | contact |
| M | OVERVIEW | short conference description |
| N | CATEGORIES | **market tag(s)** (§3) — e.g. Decarbonization |
| O | NOTES | customer's private notes (§1 customer layer) |

**Format quirks for whoever builds the export:**
- Dates (D, E, F) are stored as **Excel serial numbers** (e.g. `45916`), not text — convert on read/write.
- Many rows have blank F/G/L — sparse is normal; treat missing as unknown, never fabricate.

**Implication:** add a **transform/export layer** (internal 54-col DB → this 15-col customer sheet/dashboard). This is the "enrich → present" step Matt showed on 6/17; it's a bucket-B/output concern, sequenced with storage (B1).

---

## Files in this folder (docs/voc/)
- `VOC-MASTER.md` — this authored synthesis
- `transcripts/Prime-Nicolia-Transcript-20260617.txt` — raw call (product shape, economics)
- `transcripts/Prime-Nicolia-Transcript-20260624.txt` — raw call (latest VOC; crawl model)
- `Utility Global Conference List 2026.xlsx` — real customer sheet (15-col target output format)
