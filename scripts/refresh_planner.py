"""Which saved pages are due for a refresh this week, by the lifecycle of the event each page belongs to. REPORT ONLY.

    python scripts/refresh_planner.py [--db <live db>] [--library page_library/page_library.db] [--today YYYY-MM-DD]
        [--out report.md] [--limit N]

Implements docs/design/page-refresh-policy.md (settled with the operator 2026-10-01) as the "one shadow week" it asks for:
it reads the database and the page library, writes a plan, and fetches NOTHING, changes NOTHING. After a week the plan
is compared with what the weekend research actually looked at, then the scheduler is built.

CATEGORIES (latest edition of each conference in the Cybersecurity and Utility markets)
  A  call open, deadline still ahead              weekly (7 days)
  B  event within 6 months, call closed/no date   every 14 days; weekly when no deadline is stored
  C1 event ended <= 60 days ago (or on now)       no fetch until 45 days after the event ends, then monthly
  C2 event ended > 60 days ago                    monthly (30 days): the next edition's first sign
  D  event > 6 months away, call closed/no date   monthly when a deadline is stored; when none is stored, wait 45 days
                                                  from when we first loaded it, then every 14 days until known
  E  event date unknown / TBD                     NOT a schedule: an EXCEPTION BATCH a person works weekly
  F  discontinued (a lifecycle claim is stored)   quarterly (91 days); never again once the event is > 2 years old

OVERLAYS
  customer   skip a row only when NO customer who tracks it still has it open (every tracking customer: Submitted,
             Accepted, Client Declined, Not Appropriate, or withdrawn). Any customer marking it Urgent raises it one step.
  back-off   a page whose content hash did not change on its last 3 fetches moves one step slower; it snaps back the first
             time it changes. (Pages fetched fewer than 4 times have no history yet, so this does nothing in week one.)

APPROXIMATIONS, stated so nobody trusts them more than they deserve: the database holds a START date but no end date, so an
event is treated as ended 2 days after it starts; "dates known" for category D means a deadline is stored.
Pages are mapped to events by host (the conference key's host, www. removed). A host with several events takes the
SHORTEST interval among them. Pages on hosts no event maps to are listed as unmapped, never silently dropped.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE_DB = Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor" / "cfp_monitor.db"
LIBRARY = ROOT / "page_library" / "page_library.db"
MARKETS = ("Cybersecurity", "Utility")
EVENT_LEN_DAYS = 2           # no end date stored: treat an event as over this many days after it starts
HORIZON_DAYS = 183           # "within 6 months"
COOLING_DAYS = 45
DONE_STATUSES = {"submitted", "accepted", "client declined", "not appropriate"}
STEPS = [7, 14, 30]          # the ladder the back-off and the Urgent raise move along


def parse_day(s: str | None) -> date | None:
    try:
        return date.fromisoformat((s or "").strip()[:10])
    except ValueError:
        return None


def step_slower(days: int) -> int:
    return next((s for s in STEPS if s > days), days)


def step_faster(days: int) -> int:
    lower = [s for s in STEPS if s < days]
    return lower[-1] if lower else days


def customer_state(rows: list[dict]) -> tuple[bool, bool]:
    """(someone_still_has_it_open, anyone_marked_urgent) from the customers who track an event. No customers: (True, False),
    because an event nobody tracks is not 'done' for anyone and keeps its category rate."""
    if not rows:
        return True, False
    still_open = any(not r.get("withdrawn_by_customer") and (r.get("status") or "").strip().lower() not in DONE_STATUSES
                     for r in rows)
    urgent = any((r.get("priority") or "").strip().lower() == "urgent" for r in rows if not r.get("withdrawn_by_customer"))
    return still_open, urgent


def classify(ev: dict, today: date, customers: list[dict]) -> dict:
    """One event -> {category, interval_days (or None), not_before (date or None), reason}. Pure: no database, no clock."""
    start = parse_day(ev.get("start_date"))
    deadline = parse_day(ev.get("deadline"))
    first_loaded = parse_day(ev.get("imported_at"))
    still_open, urgent = customer_state(customers)
    if not still_open:
        return {"category": "SKIP", "interval_days": None, "not_before": None,
                "reason": "every customer who tracks it has submitted, been accepted, declined or withdrawn"}

    def out(cat, interval, reason, not_before=None):
        if urgent and interval:
            interval = step_faster(interval)
            reason += "; raised one step (a customer marked it Urgent)"
        return {"category": cat, "interval_days": interval, "not_before": not_before, "reason": reason}

    if (ev.get("lifecycle_quote") or "").strip():                       # F: a discontinuation claim is stored
        if start and (today - start).days > 730:
            return {"category": "F", "interval_days": None, "not_before": None,
                    "reason": "discontinued and more than 2 years old: never crawl again"}
        return out("F", 91, "discontinued: quarterly")
    if start is None:                                                    # E: nothing to schedule from
        return {"category": "E", "interval_days": None, "not_before": None,
                "reason": "no event date stored: exception batch, find out why"}
    end = start + timedelta(days=EVENT_LEN_DAYS)
    call_open = deadline is not None and deadline >= today
    if call_open:                                                        # A
        return out("A", 7, f"call open, deadline {deadline.isoformat()}")
    if today > end:                                                      # the event is over
        since = (today - end).days
        if since <= 60:
            return out("C1", 30, f"event ended {since} days ago: no fetch until {COOLING_DAYS} days after it ends",
                       not_before=end + timedelta(days=COOLING_DAYS))
        return out("C2", 30, f"event ended {since} days ago: monthly, watching for the next edition")
    days_to = (start - today).days
    if days_to <= HORIZON_DAYS:                                          # B
        if deadline is None:
            return out("B", 7, f"event in {days_to} days, no deadline stored: weekly")
        return out("B", 14, f"event in {days_to} days, call closed: every 2 weeks")
    if deadline is not None:                                             # D, dates known
        return out("D", 30, f"event in {days_to} days, dates known: monthly")
    wait_until = (first_loaded + timedelta(days=COOLING_DAYS)) if first_loaded else None
    return out("D", 14, f"event in {days_to} days, dates unknown: wait {COOLING_DAYS} days from first load, then every 2 weeks",
               not_before=wait_until)


def due(interval_days: int | None, not_before: date | None, last_fetched: date | None, today: date,
        unchanged_fetches: bool = False) -> tuple[bool, str]:
    """Is a page with this interval due today? Returns (due, why)."""
    if interval_days is None:
        return False, "not scheduled"
    if unchanged_fetches:
        interval_days = step_slower(interval_days)
    if not_before and today < not_before:
        return False, f"cooling off until {not_before.isoformat()}"
    if last_fetched is None:
        return True, "never fetched"
    age = (today - last_fetched).days
    return (age >= interval_days), f"fetched {age} days ago, interval {interval_days}"


# ----------------------------------------------------------------------------------------------- data access
def load_events(db: str) -> tuple[list[dict], dict[str, list[dict]]]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        marks = ",".join("?" * len(MARKETS))
        rows = [dict(r) for r in con.execute(
            "select g.event_id, g.conference_key, g.name, g.start_date, g.deadline, g.url, g.key_year, g.imported_at, "
            "g.lifecycle_quote from grounding_facts g where g.conference_key in "
            f"(select conference_key from conference_markets where market in ({marks}))", MARKETS)]
        cust: dict[str, list[dict]] = defaultdict(list)
        for r in con.execute("select event_id, client_key, status, priority, withdrawn_by_customer from client_conferences "
                             "where event_id is not null"):
            cust[r["event_id"]].append(dict(r))
    finally:
        con.close()
    latest: dict[str, dict] = {}                                          # latest edition of each conference
    for r in rows:
        k = r["conference_key"]
        if k not in latest or (r.get("key_year") or "") > (latest[k].get("key_year") or ""):
            latest[k] = r
    return list(latest.values()), cust


def host_of(key_or_url: str) -> str:
    s = (key_or_url or "").lower().strip()
    s = s.split("://", 1)[-1].split("/", 1)[0]
    return s[4:] if s.startswith("www.") else s


def load_pages(library: str) -> list[dict]:
    con = sqlite3.connect(library)
    con.row_factory = sqlite3.Row
    try:
        pages = [dict(r) for r in con.execute("select url, host, tier, last_fetched_at, fetches, sha256 from pages")]
        versions: dict[str, set] = defaultdict(set)
        try:
            for url, sha in con.execute("select url, sha256 from page_versions"):
                versions[url].add(sha)
        except sqlite3.OperationalError:
            pass
    finally:
        con.close()
    for p in pages:
        p["distinct_hashes"] = len(versions.get(p["url"], {p["sha256"]}))
    return pages


def make_plan(db: str, library: str, today: date) -> dict:
    events, cust = load_events(db)
    classified = []
    by_host: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        c = classify(ev, today, cust.get(ev["event_id"], []))
        row = {**ev, **c}
        classified.append(row)
        by_host[host_of(ev["conference_key"])].append(row)
        if host_of(ev["url"]) != host_of(ev["conference_key"]):
            by_host[host_of(ev["url"])].append(row)
    pages = load_pages(library)
    plan, unmapped = [], []
    for p in pages:
        evs = by_host.get(host_of(p["host"] or p["url"]), [])
        scheduled = [e for e in evs if e["interval_days"]]
        if not evs:
            unmapped.append(p)
            continue
        e = min(scheduled, key=lambda x: x["interval_days"]) if scheduled else evs[0]
        last = parse_day(p["last_fetched_at"])
        stale = (p["fetches"] or 0) >= 4 and p["distinct_hashes"] == 1
        ok, why = due(e["interval_days"] if scheduled else None,
                      e["not_before"] if scheduled else None, last, today, unchanged_fetches=stale)
        plan.append({"url": p["url"], "host": p["host"], "category": e["category"], "interval_days": e["interval_days"],
                     "due": ok, "why": why, "event": e["name"], "tier": p["tier"]})
    return {"events": classified, "pages": plan, "unmapped": unmapped}


def render(plan: dict, today: date, limit: int) -> str:
    ev, pg = plan["events"], plan["pages"]
    cats = defaultdict(int)
    for e in ev:
        cats[e["category"]] += 1
    due_now = [p for p in pg if p["due"]]
    lines = [f"# Refresh plan (shadow, report only) - {today.isoformat()}", "",
             f"{len(ev)} conferences (latest edition each) in {', '.join(MARKETS)}; {len(pg)} saved pages mapped to them, "
             f"{len(plan['unmapped'])} pages on hosts no event maps to.", "",
             "## Events by category", ""]
    names = {"A": "call open", "B": "event within 6 months", "C1": "just ended (cooling off)", "C2": "ended > 60 days ago",
             "D": "event > 6 months away", "E": "date unknown (exception batch)", "F": "discontinued", "SKIP": "every customer done"}
    for k in ("A", "B", "C1", "C2", "D", "E", "F", "SKIP"):
        if cats.get(k):
            lines.append(f"- **{k}** {names[k]}: {cats[k]}")
    byc = defaultdict(int)
    for p in due_now:
        byc[p["category"]] += 1
    lines += ["", f"## Pages due this week: {len(due_now)} of {len(pg)}", "",
              "By category: " + (", ".join(f"{k} {v}" for k, v in sorted(byc.items())) or "none"),
              f"At about 100 minutes per 364 pages through real Chrome, that is roughly {round(len(due_now) * 100 / 364)} minutes of fetching.", ""]
    e_rows = [e for e in ev if e["category"] == "E"]
    if e_rows:
        lines += ["## Exception batch (category E): work these by hand or agent", ""]
        lines += [f"- {e['name']} ({e['event_id']}): {e['reason']}" for e in e_rows]
        lines.append("")
    a_rows = [e for e in ev if e["category"] == "A"]
    if a_rows:
        lines += ["## Open calls (category A), weekly", ""]
        lines += [f"- {e['name']}: {e['reason']}" for e in sorted(a_rows, key=lambda x: x["deadline"])]
        lines.append("")
    lines += [f"## First {limit} due pages", ""]
    lines += [f"- [{p['category']}] {p['url']} ({p['why']})" for p in due_now[:limit]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--library", default=str(LIBRARY))
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--out")
    ap.add_argument("--limit", type=int, default=25)
    a = ap.parse_args(argv)
    today = date.fromisoformat(a.today)
    text = render(make_plan(a.db, a.library, today), today, a.limit)
    print(text)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
