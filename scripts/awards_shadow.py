"""The LIVE awards as shadow-run events (ACT-22): read-only, from the awards table of the database.

    from scripts.awards_shadow import live_awards

There is no `Awards_audited.final.csv` approved file (awards load through import_awards.py into `award_grounding_facts`), so the awards shadow run and the awards answer-key candidates start
from the table, opened with mode=ro. An award is LIVE when its status is Open or Upcoming, or its deadline is still ahead, and it is not a closed award with nothing ahead (those are the
dormant awards scripts/refresh_plan.py already skips). Each event carries kind='award' so experiments/finder_reader_test applies the awards rules (the entry or nomination deadline,
the inverted main-call rule). Never writes."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import urlparse

LIVE_STATUS = ("open", "upcoming")
SKIP_HOSTS = ("sessionize.com", "linkedin.com", "facebook.com", "eventbrite.com")


def _host(u: str) -> str:
    return urlparse(u).netloc.lower().removeprefix("www.") if u and u.startswith("http") else ""


def live_awards(db: str | Path, today: str, limit: int = 60) -> list[dict]:
    """Soonest deadline first, live awards without a deadline after. [{event, id, market, home, hosts, control, ours, kind, organizer, country, status, edition}]"""
    con = sqlite3.connect(f"file:{str(db).replace(chr(92), '/')}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute("select event_id, name, url, main_info_url, submission_url, deadline_evidence_url, deadline, status, edition, organizer, country from award_grounding_facts")]
        mk = {r[0]: r[1] for r in con.execute("select award_key, market from award_markets")}
    finally:
        con.close()
    out = []
    for r in rows:
        status = (r["status"] or "").strip().lower()
        deadline = (r["deadline"] or "").strip()
        if status not in LIVE_STATUS and not (deadline and deadline >= today):
            continue
        if (r["edition"] or "") and str(r["edition"]) < today[:4]:
            continue
        home = next((u for u in (r["main_info_url"], r["url"], r["submission_url"], r["deadline_evidence_url"]) if u and u.startswith("http") and _host(u) not in SKIP_HOSTS), "")
        if not home:
            continue
        hosts = sorted({h for h in (_host(u) for u in (r["main_info_url"], r["url"], r["submission_url"], r["deadline_evidence_url"])) if h and h not in SKIP_HOSTS})
        out.append({"event": r["name"], "id": r["event_id"], "market": mk.get(r["event_id"], ""), "home": home, "hosts": hosts, "control": "", "ours": deadline, "kind": "award",
                    "organizer": r["organizer"] or "", "country": r["country"] or "", "status": r["status"] or "", "edition": str(r["edition"] or "")})
    dated = sorted((e for e in out if e["ours"] >= today), key=lambda e: e["ours"])
    undated = [e for e in out if not e["ours"] or e["ours"] < today]
    return (dated + undated)[:limit]
