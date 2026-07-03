# PR Monitor — Gap Analysis: VPS build vs. new local crawl4ai build
**Date:** 2026-07-02
**Context:** Evaluating the existing VPS-hosted PR Monitor 1 against a new `cfp-monitor` build that (a) runs locally on Matt's Windows machine and (b) uses native crawl4ai functionality to accomplish the same ends.
**Decision locked this session:** the new build's crawl **runs locally / from a residential connection** (not a rented VPS).

---

## 1. The reframe (the single most important point)

The headline pain on the VPS — *"sites keep blocking us"* — is **not a crawler-software problem.** It is a *where-the-crawler-runs* problem.

Websites (Cloudflare, 403s, residential-gated pages) block the VPS because the request comes from a **rented data-center IP address**, which sites distrust by default. Any crawler running there gets blocked; swapping crawling libraries does not change that.

- **What "going native with crawl4ai" fixes:** the machinery your VPS build *hand-rolled* — link-following, scoring, crawl orchestration, structured extraction, failure telemetry. crawl4ai ships all of that.
- **What "going native with crawl4ai" does NOT fix by itself:** blocking. A crawler can only *use* a proxy/stealth setting; it cannot turn a distrusted data-center IP into a trusted one.

**Why the local decision solves it:** running the crawl from Matt's own residential connection means requests come from a **trusted home IP**. That is precisely why the same URLs scored 18/25 PASS on the VPS but get blocked far less from a home connection. The elaborate "Local Browser Recovery + Windows runner" pipeline on the VPS existed *only* to borrow Matt's home IP after the fact — running locally makes that entire recovery apparatus **largely unnecessary from day one.**

> **Plain-English version:** The robot was running on a rented data-center computer that websites don't trust, so they slammed the door. Running the same robot from your own office/home connection means the door mostly stays open — no elaborate workarounds needed.

---

## 2. Gap analysis — technical (VPS components → native crawl4ai)

| VPS component | What it does | Native crawl4ai equivalent | Verdict |
|---|---|---|---|
| Step 2 multi-model discovery | LLM proposes candidate URLs | Not crawl4ai (LLM task); `prefetch=True` two-phase adds on-site link discovery | **Keep custom**, augment with native prefetch |
| Step 3 crawl + best-first frontier + custom scorer | Prioritized deep crawl | `BestFirstCrawlingStrategy(url_scorer=<your scorer>)` | **Native replaces it** — delete hand-rolled frontier; keep your custom scorer (crawl4ai's `KeywordRelevanceScorer` scores conf pages ~0, so plug `scoring.score_link` in as the `url_scorer`) |
| `crawl_engine_metrics.json` / `alerts.jsonl` / "0 silent failures" | Per-page success telemetry + fallback counters | `result.success` / `status_code` / `error_message` + content-length/Cloudflare-marker checks | **Native gives the raw signals**; the quality gate is thin app logic on top (cleaner than custom counters) |
| Step 3.5 local browser recovery + Windows runner | Residential egress for BLOCKED urls | crawl4ai can only accept `proxy_config`; can't change origin IP | **Made largely unnecessary** by the local-egress decision |
| `batch_processor.py` 54-col extract | Structured extraction | `LLMExtractionStrategy` *or* direct litellm on cached markdown | **Native-capable**; runtime preference is direct-litellm-on-markdown — keep that |
| Step 5/6 review, DB, change detection, provenance | Data layer | Out of crawl4ai scope | **Separate workstream** |
| M6/M7 scheduling, alerts, exec report, gold-set scoring, client-fit | Automation & eval | Out of crawl4ai scope | **Separate workstream** |

**Scope boundary:** "Adopt crawl4ai" is not the same as "close all the gaps." crawl4ai owns a *slice* — usable-content %, partial-content detection, the crawl half of the quality gate, and retiring hand-rolled plumbing. It does **not** touch scheduling, alerts, reports, gold-set scoring, or the risk of human corrections being overwritten by recrawls. Those remain separate work regardless of crawler choice.

---

## 3. Gap analysis — non-technical (shareable)

Plain-language version of the same picture, safe for a non-technical audience.

| Business capability | Handled by the new local approach? | What it means for you |
|---|---|---|
| Finding conference websites | ✅ Yes (unchanged) | AI still suggests where to look; that part already works well |
| Reading / collecting the pages | ✅ Yes — improved | Running from your own connection means far fewer sites block us, so more pages are read successfully |
| **Getting blocked by websites** | ✅ Largely solved | This was the #1 pain. It was caused by the rented server, not the software. Your own connection is trusted, so most blocks disappear |
| Pulling out the 54 data points | ✅ Yes (rebuilt on standard tooling) | Same rich data, on better-supported, easier-to-maintain plumbing |
| Knowing when something failed (no silent errors) | ✅ Yes | We still see exactly which pages worked, were blocked, or came back incomplete |
| Reviewing & correcting the data | ➖ Unchanged | The review screen and manual overrides work the same |
| Scheduled automatic runs | ⏳ Not yet — separate work | Changing the crawler doesn't add automation; still to be built |
| Email alerts (CFP opens / deadline nearing) | ⏳ Not yet — separate work | Still to be built |
| Weekly executive report to Nicolia | ⏳ Not yet — separate work | The report capability exists but isn't wired to send automatically |
| Google Sheets integration | ⏳ Not yet — separate work | Still to be built; Nicolia's sheets stay read-only for now |
| Protecting human corrections from being overwritten | ⚠️ Needs a safeguard | Important for trust; it's a data rule, not a crawler feature |

**Bottom line for a non-technical reader:** Moving the tool to run from your own connection fixes the biggest, most visible problem (websites blocking us) and rebuilds the "engine" on stronger, standard parts. The remaining work — automatic scheduling, alerts, and the weekly report — is about turning a working tool into a hands-off service, and is separate from the blocking fix.

---

## 4. Impacts of the "run locally" decision (align on these)

Choosing local/residential egress is the right call, but it has honest trade-offs worth agreeing on now:

1. **Blocking pain drops sharply** — expect the 6 BLOCKED / 1 PARTIAL baseline to improve materially with native crawl4ai + stealth from a home IP. *(To be confirmed by the spike — see §6.)*
2. **The recovery pipeline can retire** — the VPS Step 3.5 job→runner→upload dance, `local_browser_fallback/`, the Windows runner ZIPs, and upload endpoints are no longer needed as a core path. Big simplification.
3. **⚠️ The main new trade-off: an always-on service now depends on a machine that's actually on.** The VPS advantage was 24/7 uptime. If crawls run from Matt's Windows machine, then **M6 scheduled runs require that machine (or a home always-on box) to be powered and online** at run time. This is the one thing local egress makes *harder*, and it should shape how M6 is designed (e.g., a dedicated always-on home mini-PC, or a hybrid where only scheduling lives in the cloud and crawling reaches back to the home connection).
4. **Anti-bot API specifics still need verification.** The native stealth/undetected-browser and `proxy_config` details are **not** in the verified `crawl4ai-expert` skill (which covers crawl/scoring/extraction, not evasion). Those exact parameters must be confirmed against crawl4ai 0.9.0 docs before coding — no config from memory.

---

## 5. 62-requirements mapping (local-crawl4ai lens)

**Source:** full 62-requirement scorecard retrieved 2026-07-02 (channeled.org static export `requirements_comparison_with_62_scorecard_20260703T013831Z`). Totals: **40 MET / 13 PARTIAL / 9 NOT MET.** Mapped line-by-line in §5c.

### 5a. The four buckets (how the local-crawl4ai decision affects each)

| Bucket | What's in it | Effect of the local + native decision |
|---|---|---|
| **A. Crawl & extract core** | discovery, crawling, blocking, usable content, 54-col extraction, failure telemetry | **Directly improved / rebuilt.** Local egress fixes blocking; native crawl4ai replaces hand-rolled crawl+score; extraction reproduced on standard tooling |
| **B. Data & review layer** | review queue, overrides, geo enrich, change detection, provenance/freshness, correction-preservation | **Unaffected by crawler choice.** Carries over; the correction-overwrite risk still needs a merge rule |
| **C. Automation & delivery** | scheduled runs (M6), email alerts, weekly exec report (M7), Sheets integration | **Not touched by crawler choice.** Separate workstream; note the "machine must be on" impact from §4.3 |
| **D. Evaluation & scoring** | gold-set accuracy, model default selection, client-fit scoring | **Not touched by crawler choice.** Separate workstream |

Legend — **Bucket:** **A** = crawl & extract core (improved/rebuilt by local + native crawl4ai) · **B** = data & review layer (unaffected by crawler choice) · **C** = automation & delivery (separate workstream) · **Pre** = pre-crawl LLM discovery (keep custom, not crawl4ai).

### 5c. Full 62-requirement mapping (local + native crawl4ai lens)

| # | Requirement | Status | Bucket | Impact under local + native crawl4ai |
|---|---|---|---|---|
| 1 | Automate monitoring of 100–500+ conf sites | MET | A/C | Native crawl handles scale reliably from home IP; the "automated" half is scheduling (bucket C) |
| 2 | Find CFP status | MET | A | Reproduced via native crawl + extraction |
| 3 | Find abstract submission deadlines | MET | A | Reproduced |
| 4 | Track conference dates | MET | A | Reproduced |
| 5 | Track location / geo | MET | A/B | Extracted natively; enrich in data layer |
| 6 | [Infrastructure req — unspecified] | PARTIAL | ? | Source label opaque; revisit when infra req is named |
| 7 | [Infrastructure req — unspecified] | PARTIAL | ? | Source label opaque; revisit when infra req is named |
| 8 | Conference name field | MET | A | Extraction schema — reproduced (direct-litellm 54-col) |
| 9 | Conference URL (primary target) | MET | A | Native `result.url` preserved |
| 10 | Location (city, state/country) | MET | A/B | Extract + enrich |
| 11 | Event dates | MET | A | Reproduced |
| 12 | CFP deadline | MET | A | Reproduced |
| 13 | CFP status (Open/Closed/Not Yet) | MET | A | Reproduced |
| 14 | Submission URL | MET | A | Reproduced |
| 15 | Contact info (name/email/phone) | MET | A | Reproduced |
| 16 | Submission tracking (submitted/not) | MET | B | Data-layer flag — unaffected |
| 17 | Desired CFP status values (Open/Urgent/Submitted) | PARTIAL | B | Post-extraction categorization rule — small data logic, not a crawler gap |
| 18 | CFP→Open ⇒ HIGH alert | PARTIAL | C | Change data exists; alert layer separate |
| 19 | Deadline <30d ⇒ HIGH alert | PARTIAL | C | Urgency computed; proactive alert separate |
| 20 | New conference ⇒ MEDIUM alert | PARTIAL | C | Discovery works; alert separate |
| 21 | Dates changed ⇒ MEDIUM alert | PARTIAL | C | Tracked; push separate |
| 22 | Submission URL changed ⇒ LOW alert | NOT MET | B/C | Needs recrawl+diff (crawl gives raw signal) + alert layer |
| 23 | Discover CFP page paths (not just main page) | MET | A | **Native deep crawl (BestFirst + custom scorer) does this — retire hand-rolled frontier** |
| 24 | Path memory system | MET | B | Keep custom `source_registry`; native crawl underneath |
| 25 | Path confidence tracking | MET | B | Custom data layer — unaffected |
| 26 | Self-healing path update | MET | B | Custom — unaffected |
| 27 | Fast return visits (stored path first) | MET | B | Custom; crawl4ai cache modes assist |
| 28 | Per-run scan summary | MET | A/C | Native per-page signals feed summary; dashboard UI exists |
| 29 | Weekly executive report (7 sections) | PARTIAL | C | Generator exists, not wired — separate |
| 30 | Email delivery of reports | NOT MET | C | Separate workstream |
| 31 | Top action items section | NOT MET | C | Separate workstream |
| 32 | Urgent deadlines section | PARTIAL | C | Data exists; auto-gen separate |
| 33 | New/changed opportunities section | PARTIAL | B/C | Needs change detection (B) + report wiring (C) |
| 34 | Compare current vs previous scan | MET | B | Data-layer diff — unaffected |
| 35 | Identify change types | MET | B | Unaffected |
| 36 | Flag items needing team action | PARTIAL | B/C | Detected; active flagging/push separate |
| 37 | **Run automatically on schedule (weekly min)** | NOT MET | C | **Separate + gated by "home machine must be on" (§4.3) — the biggest gap** |
| 38 | Weekly → Daily once proven | NOT MET | C | Same as #37 |
| 39 | [Automation infrastructure] | NOT MET | C | Separate workstream |
| 40 | Read conf list from Google Sheet | NOT MET | C | Integration — separate; currently master-list file |
| 41 | Update Google Sheet with findings | NOT MET | C | Separate; sheets stay read-only until authorized |
| 42 | Client-specific filtered views | NOT MET | B/C | Separate; no Sheets connection yet |
| 43 | Track success/failure per site | MET | A | **Reproduced cleanly from native `success`/`status_code` — the "0 silent failures" spine** |
| 44 | Retry logic | MET | A | crawl4ai retry; note VPS "fallback mode" = local-browser recovery, which **local egress subsumes** |
| 45 | Failure reporting | PARTIAL | A/C | Signal is native (A); proactive email is C |
| 46 | US-only scope (all/48/custom) | MET | B | Config/enrich — unaffected |
| 47 | International (global) scope | MET | B | Unaffected |
| 48 | Specific non-US countries | MET | B | Unaffected |
| 49 | Separate geo prefs (conf vs awards) | MET | B | Unaffected |
| 50 | AI discovery (multiple models) | MET | Pre | Keep custom multi-model discovery — not a crawl4ai task |
| 51 | Cross-reference models for confidence | MET | Pre | Keep custom — unaffected |
| 52 | Find both conferences AND awards | MET | Pre/A | Discovery + extraction — reproduced |
| 53 | Review extracted data in table | MET | B | Review UI — unaffected |
| 54 | Filter by multiple criteria | MET | B | Unaffected |
| 55 | Mark reviewed / follow-up / re-open | MET | B | Unaffected |
| 56 | Override extracted values | MET | B | Unaffected — **and where the correction-precedence safeguard applies** |
| 57 | Track reviewer identity + timestamp | MET | B | Unaffected |
| 58 | Export to CSV | MET | B | Unaffected |
| 59 | Locked 54-column extraction format | MET | A | Reproduced via direct-litellm-on-markdown |
| 60 | Source URL preservation (`conf_page_url`) | MET | A | Native `result.url` |
| 61 | Completeness metrics (col 54) | MET | A/B | Computed post-extraction |
| 62 | Minimal operational cost (<$5/mo) | MET | ✕-cutting | **Local decision moves crawl compute off the VPS to the home machine; API spend unchanged (`deepseek-chat` cheap). Still well under target; trade cloud cost for home uptime/electricity** |

### 5d. What the full 62 shows at a glance

- **Bucket A (crawl/extract core, ~24 reqs):** almost all already MET — native crawl4ai *reproduces* these on stronger tooling, and the local IP is what lifts the two soft spots (usable-content %, blocked-URL recovery, #44). This is where adopting crawl4ai pays off directly.
- **Bucket B (data/review, ~20 reqs):** overwhelmingly MET and **unaffected** by the crawler switch — they carry over as-is. The one watch item is the correction-precedence safeguard (#56).
- **Bucket C (automation/delivery, ~14 reqs):** this is where **every NOT MET and most PARTIALs live** — scheduling (#37–39), alerts (#18–22), reporting/email (#29–33), Sheets (#40–42). **None of these are solved by changing the crawler.** They are the real remaining product build, and #37 is directly shaped by the local-egress "machine must be on" trade-off.
- **Bucket Pre (discovery, 3 reqs):** MET, keep your custom multi-model discovery untouched.

**Headline:** switching to local + native crawl4ai *secures and simplifies* the ~24 already-working crawl/extract requirements and fixes the blocking soft spots — but **0 of the 9 NOT MET requirements are crawler problems.** They are automation/delivery/integration work (bucket C). Adopting crawl4ai is necessary hygiene, not the thing that closes the customer-visible gaps.

---

## 6. Recommended decision path / next steps

1. **✅ Egress model decided:** local / residential.
2. **Native-crawl4ai spike on the known-bad URLs:** re-run the 6 BLOCKED + 1 PARTIAL baseline from the home connection with stealth on, and measure recovery. This empirically confirms §4.1 before investing further.
3. **Port the quality gate to native signals** (`success` / `status_code` / content checks) to reproduce "0 silent failures" cleanly.
4. **Decide the M6 hosting shape** given §4.3 (home always-on box vs. cloud-scheduler-reaching-home).
5. **Then** wire downstream: finalize extraction default via gold-set scoring, then M6/M7.
6. **Add a correction-precedence rule** so recrawls never silently overwrite human-verified data (trust safeguard, bucket B).

---

*Full 62-requirement mapping complete (§5c, source retrieved 2026-07-02). Anti-bot/stealth/proxy API specifics still pending verification against crawl4ai 0.9.0 docs.*
