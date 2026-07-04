"""Scheduled run (M6) — crawl a URL list, persist, and emit alerts + feed + report.

Designed as a RUN-ONCE job (invoked by Windows Task Scheduler / cron), not a long-running
daemon — that fits the local-machine constraint and survives reboots. Writes an alerts
digest, a weekly report, and the customer feed; emails the digest only if SMTP env is set.

CLI:  python -m cfp_monitor.scheduler --urls examples/urls.txt --db cfp_monitor.db --out runs_out
Windows Task Scheduler: point a Basic Task at scripts/run_scheduled.bat on your schedule.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from .alerts import compute_alerts, digest_markdown, maybe_send_email
from .config import Settings
from .export import write_feed
from .pipeline import run_urls
from .quality_gate import classify_result
from .report import weekly_report
from .storage import Store


def _now_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


async def scheduled_run(urls: list[str], db_path: str = "cfp_monitor.db",
                        out_dir: str = "runs_out", settings: Settings | None = None) -> dict:
    settings = settings or Settings()
    settings.require_llm_key()
    results = await run_urls(urls, settings)

    store = Store(db_path)
    run_id = store.start_run()
    counts = {"url_count": len(results)}
    for r in results:
        q = classify_result(r).verdict
        counts[q.value] = counts.get(q.value, 0) + 1
        store.upsert(r, q, run_id=run_id)
    store.finish_run(run_id, counts)

    alerts = compute_alerts(store, run_id=run_id)
    digest = digest_markdown(alerts)
    report = weekly_report(store)
    os.makedirs(out_dir, exist_ok=True)
    tag = _now_tag()
    with open(os.path.join(out_dir, f"alerts_{tag}.md"), "w", encoding="utf-8") as fh:
        fh.write(digest)
    with open(os.path.join(out_dir, f"weekly_report_{tag}.md"), "w", encoding="utf-8") as fh:
        fh.write(report)
    feed = write_feed(db_path, out_dir)
    email_sent = maybe_send_email(f"PR Monitor alerts ({len(alerts)})", digest)
    store.close()
    return {"results": len(results), "counts": counts, "alerts": len(alerts),
            "email_sent": email_sent, "feed_rows": feed["count"], "out_dir": out_dir, "tag": tag}


def run_from_file(url_file: str, **kw) -> dict:
    with open(url_file, encoding="utf-8") as fh:
        urls = [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    return asyncio.run(scheduled_run(urls, **kw))


def _cli():
    import argparse

    p = argparse.ArgumentParser(description="Scheduled CFP monitor run")
    p.add_argument("--urls", required=True, help="text file of URLs, one per line")
    p.add_argument("--db", default="cfp_monitor.db")
    p.add_argument("--out", default="runs_out")
    a = p.parse_args()
    print(run_from_file(a.urls, db_path=a.db, out_dir=a.out))


if __name__ == "__main__":
    _cli()
