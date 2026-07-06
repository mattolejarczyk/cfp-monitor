"""Coverage report (M5 presentation): for a batch of crawl results, show at a glance how
many URLs worked vs. did not, WHICH fetch workflow satisfied each one, and list every
non-PASS URL with a concise reason.

Verdict buckets (from the quality gate):
- PASS     -> worked: core facts extracted.
- PARTIAL  -> reachable but thin / little extracted -> routed to the human verify loop.
- BLOCKED / ERROR -> failed: refused, unreachable, or an unexpected error.

Resolution path (how the winning start page was fetched) shows the escalation ladder and the
complexity of each URL:
- crawl4ai            -> satisfied on the FIRST pass (cheapest, fastest).
- playwright-fallback -> needed our own rendered browser (consent walls / JS shells).
- cdp                 -> needed the real signed-in Chrome (hard IP-reputation anti-bot).
- unresolved          -> no path produced a usable start page (a failure).
`bypass` records the last render bypass DEPLOYED even when the URL still failed, so we can see
which method was tried and did not clear the site.

Pure formatting over finished ConferenceResults, so it is unit-testable offline.
"""
from __future__ import annotations

from collections import Counter

from .models import ConferenceResult
from .quality_gate import classify_result

# Escalation ladder, cheapest first; "unresolved" is the failed tail. Internal keys stay
# stable (also used in the CSV); the labels are the plain terms shown in the report.
PATH_ORDER = ["crawl4ai", "playwright-fallback", "cdp", "unresolved"]
_PATH_LABEL = {
    "crawl4ai": "Core crawl (first pass)",
    "playwright-fallback": "Browser control (rendered)",
    "cdp": "Signed-in browser (hard sites)",
    "unresolved": "Unresolved (no content)",
    "": "—",
}


def friendly(path: str) -> str:
    """Plain-terms label for a resolution/bypass path (Core crawl, Browser control, ...)."""
    return _PATH_LABEL.get(path, path or "—")


def _bypass_deployed(result: ConferenceResult) -> str:
    """The last render bypass actually run for this URL (from the trace), or '' if none."""
    seen = ""
    for e in result.trace or []:
        if e.get("action") == "fallback":
            seen = "cdp" if "cdp" in (e.get("reason") or "") else "playwright-fallback"
    return seen


def summarize(results: list[ConferenceResult]) -> list[dict]:
    """One row per result: verdict, reason, resolution path, bypass deployed, hop flag."""
    rows = []
    for r in results:
        q = classify_result(r)
        rows.append({
            "url": r.start_url,
            "verdict": q.verdict.value,
            "reason": q.reason,
            "name": (r.name.value or "").strip(),
            "canonical": (r.canonical_url or "").strip(),
            "path": r.resolution_path or "unresolved",
            "bypass": _bypass_deployed(r),
            "hop": bool(r.aggregator_hop),
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

    # Resolution-path matrix: which workflow satisfied each URL (and where a bypass failed).
    out += ["", "## By resolution path (which workflow satisfied the URL)"]
    out += ["| Path | PASS | PARTIAL | Failed | Total |", "|---|--:|--:|--:|--:|"]
    present = [p for p in PATH_ORDER if any(r["path"] == p for r in rows)]
    for p in present:
        pr = [r for r in rows if r["path"] == p]
        pc = Counter(r["verdict"] for r in pr)
        pf = pc.get("BLOCKED", 0) + pc.get("ERROR", 0)
        out.append(f"| {friendly(p)} | {pc.get('PASS', 0)} | {pc.get('PARTIAL', 0)} | {pf} | {len(pr)} |")
    hops = [r for r in rows if r["hop"]]
    if hops:
        out += ["", f"**Aggregator hops (directory/org → specific event): {len(hops)}**"]
        for r in hops:
            out.append(f"- {r['url']} → {r['canonical']}" + (f"  ({r['name']})" if r["name"] else ""))

    fails = [r for r in rows if r["verdict"] in ("BLOCKED", "ERROR")]
    out += ["", f"## Failed ({len(fails)}) — exact link, bypass tried, why"]
    if fails:
        out += ["| # | URL | Verdict | Bypass tried | Reason |", "|--:|---|---|---|---|"]
        for i, r in enumerate(fails, 1):
            out.append(f"| {i} | {r['url']} | {r['verdict']} | {friendly(r['bypass'])} | {r['reason']} |")
    else:
        out.append("_None — every URL was reachable._")

    parts = [r for r in rows if r["verdict"] == "PARTIAL"]
    out += ["", f"## Needs verification / PARTIAL ({len(parts)}) — reachable but thin"]
    if parts:
        out += ["| # | URL | Path | Reason |", "|--:|---|---|---|"]
        for i, r in enumerate(parts, 1):
            out.append(f"| {i} | {r['url']} | {friendly(r['path'])} | {r['reason']} |")
    else:
        out.append("_None._")
    return "\n".join(out)


def coverage_csv_rows(rows: list[dict]) -> list[list[str]]:
    """Full per-URL detail for a spreadsheet: header + one row each."""
    header = ["url", "verdict", "path", "bypass", "hop", "reason", "name", "canonical"]
    return [header] + [[str(r[h]) for h in header] for r in rows]
