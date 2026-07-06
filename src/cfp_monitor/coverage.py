"""Coverage report (M5 presentation): for a batch of crawl results, show at a glance how
many URLs worked vs. did not, and list every non-PASS URL with a concise reason.

Buckets (from the quality gate):
- PASS     -> worked: core facts extracted.
- PARTIAL  -> reachable but thin / little extracted -> routed to the human verify loop.
- BLOCKED / ERROR -> failed: refused, unreachable, or an unexpected error.

Pure formatting over finished ConferenceResults, so it is unit-testable offline.
"""
from __future__ import annotations

from collections import Counter

from .models import ConferenceResult
from .quality_gate import classify_result


def summarize(results: list[ConferenceResult]) -> list[dict]:
    """One row per result: url, verdict, concise reason, resolved name, canonical (post-nav)."""
    rows = []
    for r in results:
        q = classify_result(r)
        rows.append({
            "url": r.start_url,
            "verdict": q.verdict.value,
            "reason": q.reason,
            "name": (r.name.value or "").strip(),
            "canonical": (r.canonical_url or "").strip(),
        })
    return rows


def _pct(n: int, total: int) -> int:
    return round(100 * n / total) if total else 0


def coverage_markdown(title: str, rows: list[dict]) -> str:
    c = Counter(r["verdict"] for r in rows)
    total = len(rows)
    passed, partial = c.get("PASS", 0), c.get("PARTIAL", 0)
    failed = c.get("BLOCKED", 0) + c.get("ERROR", 0)
    worked = passed + partial

    out = [f"# {title}", ""]
    out.append(f"**{total} URLs** — worked **{worked} ({_pct(worked, total)}%)**: "
               f"PASS {passed}, PARTIAL {partial}  ·  failed **{failed} ({_pct(failed, total)}%)**")

    fails = [r for r in rows if r["verdict"] in ("BLOCKED", "ERROR")]
    out += ["", f"## Failed ({len(fails)}) — exact link + why"]
    if fails:
        out += ["| # | URL | Verdict | Reason |", "|--:|---|---|---|"]
        for i, r in enumerate(fails, 1):
            out.append(f"| {i} | {r['url']} | {r['verdict']} | {r['reason']} |")
    else:
        out.append("_None — every URL was reachable._")

    parts = [r for r in rows if r["verdict"] == "PARTIAL"]
    out += ["", f"## Needs verification / PARTIAL ({len(parts)}) — reachable but thin"]
    if parts:
        out += ["| # | URL | Reason |", "|--:|---|---|"]
        for i, r in enumerate(parts, 1):
            out.append(f"| {i} | {r['url']} | {r['reason']} |")
    else:
        out.append("_None._")
    return "\n".join(out)


def coverage_csv_rows(rows: list[dict]) -> list[list[str]]:
    """Full per-URL detail for a spreadsheet: header + one row each."""
    header = ["url", "verdict", "reason", "name", "canonical"]
    return [header] + [[r[h] for h in header] for r in rows]
