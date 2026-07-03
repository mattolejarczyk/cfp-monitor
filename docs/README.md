# docs/ — documentation & reference

This folder separates **inherited reference material** from **documentation we author** for the new local `cfp-monitor` build. Keep that separation as the repo grows.

## Layout & storage strategy

```
docs/
├── handoff-from-vps/     # FROZEN reference imported from the old VPS "PR Monitor 1" build
│   └── 00-INDEX.md        # ← read first: tiers every carried-over doc + the exclude list
└── (design/)             # AUTHORED docs for THIS build — add as decisions get made
```

- **`handoff-from-vps/`** — carried over from the VPS build (customer truth, quality gates, 54-col schema, roadmap, extraction methodology, and old code for mining logic). Treat as **read-only reference**; do not edit these to reflect new decisions. Tiers inside:
  - `local-build-analysis/` — our gap analysis + full 62-requirement mapping (authoritative for the local direction)
  - `must-pass/` + `must-pass/methodology/` — product/customer/quality/schema/roadmap + extraction methodology
  - `reference-only/` — old VPS code/UI/contracts: **mine for schema/logic, do NOT port as architecture**
  - See `handoff-from-vps/00-INDEX.md` for the excluded (not-carried-over) docs and why.

- **`design/`** (create when needed) — decisions authored for the new build (design notes, ADRs, schema choices). This is where *new* thinking lives, so `handoff-from-vps/` stays a clean historical baseline.

## Rule of thumb
Inherited → `handoff-from-vps/` (frozen). Authored → `design/` (living). If you're recording a decision *we* made, it does not belong under `handoff-from-vps/`.

> Context recap: this build runs crawling **locally from a residential connection** (the VPS's datacenter IP was the blocking cause) and uses **native crawl4ai** (see `.claude/skills/crawl4ai-expert/`). The 9 unmet requirements are all automation/delivery (scheduling, alerts, reporting, Sheets) — not crawler problems.
