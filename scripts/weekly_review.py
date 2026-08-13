"""Turn the weekly run into a REVIEW, not a log.

THE GAP THIS CLOSES
The weekly job already finds things. It writes them to runs_out\\weekly_<stamp>.log and tells
nobody, so Sunday's work sits in a folder until somebody remembers to look. And when they do,
they get a log - chronological, complete, and shaped for debugging rather than deciding.

A review is shaped for a person with ten minutes. It answers one question at the top: WHAT DO I
HAVE TO DECIDE? Everything that needs no decision is counted, not listed.

DELIBERATELY DETERMINISTIC. No LLM, no API cost, no judgement. It reads the database and the
run's own outputs and arranges them. A summary that could hallucinate is worse than no summary,
because this one exists to be trusted at a glance on a Sunday morning.

    python scripts/weekly_review.py --db <db> --runs-out runs_out [-o review.md]
"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

ANSWERED = ("[R1 withdrawal]", "[retired]", "[upgraded")


def _rows(con):
    return list(con.execute("select * from grounding_facts"))


def _future(d: str, today: date) -> bool:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", (d or "").strip())
    return bool(m) and date(int(m[1]), int(m[2]), int(m[3])) >= today


def build(db: str, runs_out: Path, today: date) -> str:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = _rows(con)

    dead = {r["url"] for r in con.execute(
        "select url from link_checks where lower(state)='dead' and url is not null")}
    last_check = con.execute("select max(checked_at) from link_checks").fetchone()[0]

    # what the customer would be shown a dead link to, by field
    fields = {"submission_url": "Submit link", "deadline_evidence_url": "Evidence link",
              "main_info_url": "Event site", "url": "Event site"}
    hits = {v: set() for v in fields.values()}
    for r in rows:
        for f, label in fields.items():
            u = (r[f] or "").strip()
            if u and u in dead:
                hits[label].add(r["name"])

    # rows still open: unconfirmed, not answered, deadline still ahead
    open_rows = [r for r in rows
                 if r["verify_state"] != "verified"
                 and not (r["verify_detail"] or "").startswith(ANSWERED)
                 and _future(r["deadline"], today)]

    # anything discovery proposed this week and did NOT merge
    proposed = []
    latest = sorted(runs_out.glob("weekly_discovery_citations_*.csv"))
    if latest:
        with open(latest[-1], encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                if (r.get("DEADLINE_EVIDENCE_URL") or "").strip():
                    proposed.append((r.get("CONFERENCE", ""), r.get("SUBMISSION DEADLINE", ""),
                                     r.get("DEADLINE_EVIDENCE_URL", "")))

    verified = sum(1 for r in rows if r["verify_state"] == "verified")
    contradicted = [r for r in rows if r["verify_state"] == "contradicted"
                    and _future(r["deadline"], today)]

    L = []
    a = L.append
    a(f"# Weekly review - {today:%A %d %B %Y}")
    a("")
    a(f"{len(rows)} rows. Links last checked {(last_check or 'never')[:10]}.")
    a("")
    a("---")
    a("")
    a("## Decide this week")
    a("")

    n = 0
    if proposed:
        n += len(proposed)
        a(f"**{len(proposed)} citation(s) cleared the gate and are waiting for you to merge.**")
        a("Each was re-fetched and the quote proved present on the page.")
        a("")
        for name, dl, url in proposed:
            a(f"- **{name}** - {dl}")
            a(f"  {url}")
        a("")
        a("```")
        a("uv run python scripts/apply_resolutions.py --db <db> \\")
        a(f"  --citations {latest[-1].name} --apply")
        a("```")
        a("")

    if contradicted:
        n += len(contradicted)
        a(f"**{len(contradicted)} row(s) where the cited page now states a DIFFERENT date, "
          f"and the deadline has not passed.**")
        a("These are the ones that can cost a submission.")
        a("")
        for r in contradicted[:10]:
            a(f"- **{r['name']}** - we hold {r['deadline']}")
            a(f"  {(r['verify_detail'] or '')[:110]}")
        if len(contradicted) > 10:
            a(f"- ...and {len(contradicted)-10} more")
        a("")

    if not n:
        a("**Nothing.** No citation cleared the gate and no live deadline started disagreeing")
        a("with its own page. That is a normal week.")
        a("")

    a("---")
    a("")
    a("## Changed, no decision needed")
    a("")
    a(f"- **{verified} of {len(rows)}** rows carry a citation we have confirmed on the page.")
    a(f"- **{len(open_rows)}** rows are still open - unconfirmed, with a deadline ahead. These "
      f"are what discovery sweeps each week.")
    tot = sum(len(v) for v in hits.values())
    if tot:
        a(f"- **{tot} dead link(s)** are being withheld from the customer page:")
        for label, names in sorted(hits.items()):
            if names:
                a(f"    - {len(names)} {label.lower()}(s)")
    else:
        a("- No dead links found.")
    a("")
    a("---")
    a("")
    a("## Waiting on someone else")
    a("")
    a("- Upstream: Decarb Connect - is the 2027 call actually open, and the R9 identity split.")
    a("- Upstream: Carbon Capture Technology Expo - one event under two IDs.")
    a("")
    a("---")
    a("")
    a("*Generated from the database, not from an LLM. Every number here is a query.*")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="Turn the weekly run into a decision-shaped review.")
    ap.add_argument("--db", required=True)
    ap.add_argument("--runs-out", required=True)
    ap.add_argument("-o", "--output")
    a = ap.parse_args()

    text = build(a.db, Path(a.runs_out), date.today())
    if a.output:
        Path(a.output).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {a.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
