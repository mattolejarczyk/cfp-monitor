# cfp-monitor

Local, native-**crawl4ai** rebuild of the "PR Monitor" conference/CFP opportunity monitor for customer **Nicolia / PRIME|PR** ($500/mo). Runs from a **residential connection** (not a VPS) — the original VPS build's #1 pain was datacenter-IP blocking, which local egress sidesteps.

## Start here
- Verified crawl4ai API: skill `crawl4ai-expert` (`.claude/skills/crawl4ai-expert/`) — auto-loads; prefer over recalling docs.
- **Handoff context from the old VPS build:** `docs/handoff-from-vps/00-INDEX.md` — read it first. It tiers every carried-over doc:
  - `local-build-analysis/` — our gap analysis + full 62-requirement mapping (authoritative)
  - `must-pass/` + `must-pass/methodology/` — customer truth, quality gates, 54-col schema, roadmap, extraction methodology
  - `reference-only/` — old VPS code/UI/contracts; mine for logic, do NOT copy architecture

## Key facts
- The 9 unmet requirements are all **automation/delivery** (scheduling, alerts, reporting, Sheets) — none are crawler problems. crawl4ai secures/simplifies the crawl+extract core; the real remaining build is bucket C.
- Biggest gap = automated scheduling (#37); local egress means it depends on an always-on home machine — decide hosting shape before M6.
- Extraction: prefer calling litellm directly on crawled markdown; provider strings LiteLLM format (`openrouter/deepseek/deepseek-chat`); keys in `.env` only.
- Carry-over principle from the (excluded) recovery loop: "Blocked/partial pages must be classified and routed; no silent failures."
