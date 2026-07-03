# Work Breakdown & LOE — cfp-monitor (local build)

**Date:** 2026-07-03 · **Authored** (living). Updates the WBS first drafted in session, now reflecting the locked post-VOC decisions.

**Inputs:** `../voc/VOC-MASTER.md` (customer voice + §0 decisions), `../handoff-from-vps/local-build-analysis/20260702-PR-Monitor-Gap-Analysis-Local-Crawl4ai.md` (gap analysis + full 62-req map), current `src/cfp_monitor/` code.

## Locked decisions shaping this plan
- **Pure-local** crawl (user's computer). Hybrid/VPS deferred as future-scale (archived, not built).
- **Conferences first; awards deferred** until the conference pipeline is solid.
- **Own DB as source of truth** (SQLite → Postgres path). Brandable reads from it later.
- **Two formats:** internal **54-col** schema (truth) → customer **15-col** view (`../voc/Utility Global Conference List 2026.xlsx`) via a **transform/export layer** (new item B6).
- **Two-tier product:** verified master DB + per-customer tag-filtered dashboards; portal (M8) likely **shrinks** because Brandable already has auth/billing.

## Starting point — maturity by bucket
The crawl→extract **core already exists** (~1,280 LOC, native crawl4ai: deep-crawl, discovery, evidence-backed extraction, consolidation, trace, Streamlit UI + CLI). This is *finish & productize*, not build-from-zero.

| Bucket | Area | State |
|---|---|---|
| A | Crawl + extract core | **~70%** — needs 54-col contract, quality gate, stealth |
| B | Persistence + review + **transform** | **~5%** — single-shot; no DB, history, change-detection, path-memory, review, 54→15 export |
| Pre | Discover new conferences | **0%** — takes a fixed URL list |
| C | Automation + delivery | **0%** — no scheduler, alerts, email, weekly report, Sheets |
| D | Extraction quality/eval | **0%** — no gold-set, model selection |

**Legend** — Complexity S/M/L/XL · Effort = "build-sessions" (~½-day focused block) · Tokens = rough agent-build ballpark incl. iteration (least reliable; ±50–100%).

## WS-A — Finish & harden the core (exists ~70%)
| # | Feature | Cplx | Sessions | Tokens |
|---|---|---|---|---|
| A1 | Map `ConferenceResult` → locked **54-column** contract (mine `batch_processor.py` + PROCESS_DOCUMENTATION) | M | 2–3 | 300–600k |
| A2 | **Quality gate**: PASS/PARTIAL/BLOCKED, usable-content %, "0 silent failures" telemetry | M | 2–3 | 300–500k |
| A3 | **Stealth/anti-bot** config for local egress (verify crawl4ai 0.9.0 stealth/proxy API vs docs) | S–M | 1–2 | 150–350k |
| A4 | **Blocked-URL spike** — validate local egress on the 6 BLOCKED+1 PARTIAL baseline (measurement gate) | S | 1 | 100–200k |

## WS-B — Persistence, transform & review (exists ~5%)
| # | Feature | Cplx | Sessions | Tokens |
|---|---|---|---|---|
| B1 | **SQLite** storage + run history + result upsert (source of truth) | M | 2–3 | 300–500k |
| B2 | Change detection (current vs previous; typed diffs) + **past-event rollover** (find next-year edition) | M | 2–3 | 300–500k |
| B3 | Path memory / source registry + self-healing | M | 2–3 | 300–550k |
| B4 | **Verification lifecycle** (needs-verified→verified) + **correction-precedence** (never overwrite verified) + **last-checked date** | M | 2–3 | 300–550k |
| B5 | Review workflow UI (filters, mark reviewed/follow-up, override, reviewer+timestamp, CSV export) | L | 3–5 | 600k–1.2M |
| B6 | **Transform/export layer**: 54-col DB → 15-col customer sheet format (Excel-serial dates, tags→CATEGORIES) | M | 2–3 | 300–500k |

## WS-C — Automation & delivery (0%) — the real customer gap
| # | Feature | Cplx | Sessions | Tokens |
|---|---|---|---|---|
| C1 | Scheduler (weekly/daily) wired end-to-end on the local machine | M | 2–3 | 300–500k |
| C2 | Alert engine (CFP→open, deadline<30d, new conf, dates changed, URL changed) + email delivery | L | 3–4 | 500–900k |
| C3 | Weekly executive report (opportunities + system-health metrics) + delivery | M–L | 2–4 | 350–700k |
| C4 | Feed to Brandable / customer dashboards (data + tag-filtered views; NOT auth — Brandable has it) | M | 2–3 | 300–550k |

## WS-D — Extraction quality / eval (0%)
| # | Feature | Cplx | Sessions | Tokens |
|---|---|---|---|---|
| D1 | Gold-set harness + deterministic scoring + tiered model-default selection (free bulk / premium on hard pages) | M–L | 2–4 | 350–700k |
| D2 | Multi-page Step-4-v2 extraction improvements (incl. multi-location/multi-edition events) | M | 2–3 | 300–550k |

## WS-Ops
| # | Feature | Cplx | Sessions | Tokens |
|---|---|---|---|---|
| O1 | Packaging, secrets/config, logging/metrics, deploy on the local always-on machine, runbook | M | 2–3 | 250–450k |

## Deferred (record, do NOT build now)
| # | Item | Why deferred |
|---|---|---|
| DEF-1 | **Awards** discovery + schema (parallel entity) | After conference pipeline is solid |
| DEF-2 | **Multi-model discovery** of new conferences (Perplexity/GPT/Gemini) | Build takes a fixed list for now; add when expanding markets |
| DEF-3 | **Client-fit scoring** | Downstream product feature |
| DEF-4 | **Hybrid cloud+local / VPS scale** | Future scale path; learnings archived |
| DEF-5 | **Phases 3–5** (warm pitching, cold email, voice) | Out of scope for Phase 2 |

## Rollup (in-scope only)
| Workstream | Sessions (mid) | Tokens (mid) |
|---|---|---|
| WS-A | ~7.5 | ~1.25M |
| WS-B | ~15 | ~2.6M |
| WS-C | ~11.5 | ~2.0M |
| WS-D | ~5.5 | ~1.0M |
| WS-Ops | ~2.5 | ~0.35M |
| **Total (in-scope)** | **~42 build-sessions** | **~7.2M tokens** |

**Translated:** ~42 half-day build-sessions ≈ **~4–5 weeks** focused solo at the ideal; realistically **6–8 weeks** with review/testing/slippage. Deferring awards + multi-model discovery trimmed scope vs the first draft.

## Recommended sequence
Customer value is bucket C, but **C depends on A + B** — don't automate un-trusted, un-remembered data.
1. **Phase 0 — Validate** (A4 + A3, ~2.5 sess): prove local egress recovers blocked URLs.
2. **Phase 1 — Trust the data** (A1, A2, D1, ~8 sess): 54-col contract, quality gate, gold-set.
3. **Phase 2 — Remember, verify & present** (B1, B2, B4, B6, B3, B5, ~15 sess): storage, change/rollover, verification lifecycle, 54→15 transform, path memory, review UI.
4. **Phase 3 — Hands-off service** (C1–C4, ~11.5 sess): scheduler → alerts → weekly report → Brandable feed.
5. **Phase 4 — Grow** (D2, O1, then DEF items): multi-location extraction, hardening, then awards & discovery.

## Assumptions & swing factors
- Assumes reuse of the existing core spine + *mining* reference-only logic (not porting the VPS app).
- Biggest swings: B5 review UI (may be partly absorbed by Brandable), C2 alerts (email deliverability infra), A3 (anti-bot API verification risk).
- Token estimates are order-of-magnitude.
- "Session" = one focused build block; parallelizing compresses calendar time, not token total.
