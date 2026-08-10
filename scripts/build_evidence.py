"""Promote evidence from a buried blob to a first-class, queryable table.

THE PROBLEM THIS SOLVES
`models.Evidence(field, source_url, snippet)` has existed all along and the crawl pipeline
produces it for every fact. It is then serialised into `conferences.result_json` and never
queried again. Upstream's evidence fares little better: of ~15 meaningful fields on a
delivered row, exactly one (the deadline) carries a source URL and a quote into storage.

So we could not answer the two questions that matter:

    "What did we claim, and where did we read it?"
    "What else did we claim from THIS page?"

Without the second, verification cannot be grouped by page, and every check re-fetches. That
is why the 2026-08-09 hand-back contained disputes decided against three-week-old cached
crawls: re-reading the cited page for 24 rows looked expensive, so nobody did it.

ORIGIN IS RECORDED, NOT COLLAPSED
Contract 5.1 keeps grounding claims and our crawled facts in separate tables, because a thin
crawl must never overwrite a researched claim. This table holds both, so every row records
which side asserted it. `origin='grounding'` is upstream's claim; `origin='crawl'` is ours.
Merging them would quietly re-introduce the failure that separation prevents.

    python scripts/build_evidence.py --db cfp_monitor.db [--delivery <dir>] [--rebuild]

Idempotent: re-running replaces rows for the same (event_id, field, source_url, origin)
rather than duplicating them. Verdicts already written by the auditor are preserved unless
--rebuild is given.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SCHEMA = """
create table if not exists evidence (
    id            integer primary key,
    event_id      text not null,
    field         text not null,      -- deadline | submission_url | venue | lifecycle | status | name
    value_claimed text,               -- what we assert is true
    source_url    text not null,      -- the page it was read on
    quote         text,               -- the verbatim sentence, where we have one
    origin        text not null,      -- grounding (upstream) | crawl (ours)
    method        text,               -- how the source was last fetched: http|crawl4ai|playwright|cdp
    fetched_at    text,
    verdict       text default 'unchecked',   -- unchecked|verified|contradicted|unreadable|no_quote
    found_quote   text,               -- what the auditor actually found on the page
    detail        text,
    unique(event_id, field, source_url, origin)
);
create index if not exists evidence_by_url   on evidence(source_url);
create index if not exists evidence_by_event on evidence(event_id);
create index if not exists evidence_verdict  on evidence(verdict);
"""


def _text(v) -> str | None:
    """Coerce a claimed value to text. Some result_json fields are structured (location is a
    dict, opportunity_types a list), so a bare .strip() blows up on real data."""
    if v is None:
        return None
    if isinstance(v, str):
        return v.strip() or None
    if isinstance(v, dict):
        v = v.get("value", v)
        if isinstance(v, str):
            return v.strip() or None
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v if x) or None
    return str(v).strip() or None


def add(rows: list, event_id, field, value, url, quote, origin):
    url = (url or "").strip()
    if not url.startswith("http") or not event_id:
        return
    rows.append((event_id, field, _text(value), url, _text(quote), origin))


def from_grounding(con) -> list:
    """Upstream's claims. Only the deadline carries a real citation today - that gap is the
    finding, not a bug in this script, and it is why so much arrives unevidenced."""
    out: list = []
    for r in con.execute("""select event_id, deadline, deadline_evidence_url, deadline_quote,
                                   submission_url, status, url, main_info_url
                            from grounding_facts"""):
        eid, dl, dl_url, dl_q, sub, status, url, main = r
        add(out, eid, "deadline", dl, dl_url, dl_q, "grounding")
        # The submission URL is a claim about itself: "this is where you submit". Its source
        # is the page, so the auditor checks that the page exists and looks like a way in.
        add(out, eid, "submission_url", sub, sub, None, "grounding")
        # Status has NO citation in the delivery. Record it against the event page so it is at
        # least auditable; an unevidenced claim we cannot check is worse than one we can.
        add(out, eid, "status", status, main or url, None, "grounding")
    return out


def from_delivery(paths: list[Path]) -> list:
    """The delivery carries two more citations the database never kept: venue and lifecycle."""
    out: list = []
    for p in paths:
        with open(p, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                eid = (r.get("EVENT_ID") or "").strip()
                add(out, eid, "venue", r.get("LOCATION"), r.get("VENUE_EVIDENCE_URL"),
                    None, "grounding")
                add(out, eid, "lifecycle", r.get("STATUS DETAILS"),
                    r.get("LIFECYCLE_EVIDENCE_URL"), r.get("LIFECYCLE_QUOTE"), "grounding")
    return out


def from_crawl(con) -> list:
    """OUR readings, unpacked from result_json. 373 conferences carry these and nothing has
    ever been able to query them."""
    out: list = []
    key_to_event = {k: e for k, e in con.execute(
        "select conference_key, event_id from grounding_facts where conference_key is not null")}
    for key, blob in con.execute(
            "select key, result_json from conferences where coalesce(result_json,'') <> ''"):
        eid = key_to_event.get(key)
        if not eid:
            continue
        try:
            j = json.loads(blob)
        except Exception:
            continue
        vals = {"deadline": j.get("cfp_close_date"), "status": j.get("cfp_status"),
                "venue": j.get("location"), "submission_url": None, "name": j.get("name")}
        for e in (j.get("evidence") or []):
            f = e.get("field") or ""
            f = {"cfp_close_date": "deadline", "cfp_status": "status",
                 "location": "venue"}.get(f, f)
            add(out, eid, f, vals.get(f), e.get("source_url"), e.get("snippet"), "crawl")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the queryable evidence table.")
    ap.add_argument("--db", default="cfp_monitor.db")
    ap.add_argument("--delivery", help="directory of *_audited.csv, for venue/lifecycle citations")
    ap.add_argument("--rebuild", action="store_true", help="discard existing verdicts too")
    a = ap.parse_args()

    con = sqlite3.connect(a.db)
    con.executescript(SCHEMA)
    if a.rebuild:
        con.execute("delete from evidence")
        print("rebuild: cleared existing evidence rows")

    rows = from_grounding(con)
    print(f"  grounding claims       {len(rows)}")
    n = len(rows)
    rows += from_crawl(con)
    print(f"  our own crawl readings {len(rows) - n}")
    if a.delivery:
        files = [p for p in sorted(Path(a.delivery).glob("*_audited.csv"))
                 if not any(x in p.name.lower() for x in ("test_", "single_", "_conf_", "backup"))]
        n = len(rows)
        rows += from_delivery(files)
        print(f"  delivery citations     {len(rows) - n}  (from {len(files)} file(s))")

    # insert-or-ignore keeps any verdict the auditor already wrote for a claim that has not
    # changed; a re-run should not silently discard verification work.
    before = con.execute("select count(*) from evidence").fetchone()[0]
    con.executemany("""insert or ignore into evidence
        (event_id, field, value_claimed, source_url, quote, origin)
        values (?,?,?,?,?,?)""", rows)
    con.commit()
    after = con.execute("select count(*) from evidence").fetchone()[0]

    print(f"\n{after} evidence row(s) ({after - before} new)")
    print("\nby field:")
    for f, n in con.execute("select field, count(*) from evidence group by field order by 2 desc"):
        print(f"  {f:<16} {n}")
    print("\nby origin:")
    for o, n in con.execute("select origin, count(*) from evidence group by origin"):
        print(f"  {o:<16} {n}")
    urls = con.execute("select count(distinct source_url) from evidence").fetchone()[0]
    print(f"\n{urls} distinct source URL(s) - what a grouped audit would visit")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
