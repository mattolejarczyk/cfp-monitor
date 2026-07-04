"""Weekly executive report (M7 seed): opportunities + system health, as markdown."""
from __future__ import annotations

from collections import Counter
from datetime import date

from .alerts import parse_deadline
from .storage import Store


def weekly_report(store: Store, title: str = "PR Monitor — Weekly Report") -> str:
    recs = store.all_records()
    last_row = store.db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    last = dict(last_row) if last_row else None

    n = len(recs)
    verified = sum(1 for r in recs if r["verification_status"] == "verified")
    by_status = Counter((r["cfp_status"] or "unknown") for r in recs)
    by_quality = Counter((r["quality"] or "unknown") for r in recs)

    today = date.today()
    upcoming = sorted(
        (d, r["name"] or r["key"], r["url"])
        for r in recs
        if (d := parse_deadline(r["cfp_close_date"])) and d >= today
    )

    lines = [f"# {title}", ""]
    lines.append(f"**Tracked conferences:** {n}  ·  **human-verified:** {verified}")
    lines.append("**CFP status:** " + (", ".join(f"{k}={v}" for k, v in by_status.most_common()) or "—"))
    lines += ["", "## Upcoming deadlines"]
    if upcoming:
        for d, name, url in upcoming[:15]:
            lines.append(f"- **{d.isoformat()}** — {name}" + (f"  ({url})" if url else ""))
    else:
        lines.append("_No parseable upcoming deadlines (many events don't publish one — see 'needs verification' rows)._")
    lines += ["", "## System health"]
    if last:
        total = last["url_count"] or 0
        lines.append(f"- Last run finished: {last['finished_at']}  ·  {total} URLs")
        lines.append(f"- PASS {last['pass_count']} · PARTIAL {last['partial_count']} · "
                     f"BLOCKED {last['blocked_count']} · ERROR {last['error_count']}")
        if total:
            lines.append(f"- Usable coverage: {round(100 * (last['pass_count'] + last['partial_count']) / total)}%")
    else:
        lines.append("_No runs recorded yet._")
    lines.append("- Stored extraction quality: " + (", ".join(f"{k}={v}" for k, v in by_quality.most_common()) or "—"))
    return "\n".join(lines)
