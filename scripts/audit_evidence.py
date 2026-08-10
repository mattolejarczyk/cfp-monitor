"""Verify claims against their own cited pages, one page visit at a time.

THE RULE THIS ENFORCES
A claim is checked against THE PAGE IT CITES. Not a fallback, not our cached crawl, not the
homepage. On 2026-08-09 a hand-back was generated in which 15 of 24 deadline disputes had
never fetched a live page at all - they were decided against our own crawl records up to
three weeks old, one of which said "closed" while holding a close date six months in the
future. A customer spot-checked two and found both wrong in minutes.

GROUPED BY PAGE, NOT BY ROW
Evidence is grouped by `source_url`, so each page is fetched ONCE and every claim sourced
from it is checked in that single visit. Re-fetching per row is what made honest verification
look too expensive to do, which is how the cached-crawl shortcut crept in.

THE LADDER IS CLIMBED, NOT SIDESTEPPED
crawl4ai -> Playwright -> CDP. If a page will not load cheaply we escalate; we do NOT fall
back to a different page and report its contents as if they came from this one. A page we
cannot read resolves to `unreadable`, which is an honest verdict and never a disproof
(contract 5.2, 2.1).

VERDICTS, per claim
    verified      the page contains the claimed value
    contradicted  the page carries a different value for this field
    unreadable    we could not read the page - the claim STANDS, unproven
    no_quote      the page loaded but the claimed value is simply absent

`unreadable` and `no_quote` are not failures of the claim. Only `contradicted` is a finding,
and only a `contradicted` verdict earned on the cited page may leave the building.

    python scripts/audit_evidence.py --db cfp_monitor.db --limit 50
    python scripts/audit_evidence.py --db cfp_monitor.db --disputed-only
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cfp_monitor.verify import (                              # noqa: E402
    _parse_date, fetch_text, find_date, other_deadline_dates, page_status,
)

# A page that loads but says "not found" is not a source. amp.org/education/amp-annual-meeting
# returned a soft 404 and its text was mined for a date, which then contradicted a correct
# claim and went into a document for another party.
SOFT_404 = re.compile(
    r"(page not found|404 error|page you (are|were) looking for|no longer available"
    r"|cannot be found|doesn't exist|does not exist)", re.I)


# ---- the outbound standard -------------------------------------------------------------
# A verdict says what the PAGE said. Exportable says whether we may put it in front of another
# party. They are different questions and conflating them is how 24 disputes were assembled of
# which perhaps 3 were defensible.
#
# Three rules, each earned on 2026-08-10:
#
#  1. NO QUOTE, NO DISPUTE. Five of ten surviving disputes asserted a rival date with no
#     sentence behind it. If we cannot show the words, we have a regex hit, not evidence -
#     and nothing to stand on when upstream pushes back.
#
#  2. THE QUOTE MUST NAME THE CALL. One event runs several calls with different deadlines
#     (R10): abstracts, full papers, case studies, posters, workshops, late-breaking. AMP's
#     cited page is `case-study-submission-information` while the claim is probably an
#     abstract deadline. "July 6, 2026" settles nothing; "Case study deadline: July 6, 2026"
#     settles it and says which call we read.
#
#  3. A SHARED PLATFORM CANNOT SOURCE AN EVENT-SPECIFIC CLAIM unless the event names itself
#     beside the date. ras.papercept.net hosts many IEEE conferences on one page; we read
#     TMECH/AIM's deadline and attributed it to IROS. Same failure as citing IBC's Accelerator
#     for a Technical Papers row, one level up: many events on one page.
CALL_LABELS = ("abstract", "full paper", "call for paper", "paper submission", "case study",
               "poster", "workshop", "tutorial", "panel", "late-breaking", "late breaking",
               "lightning", "speaker", "speaking", "presentation", "nomination", "entry",
               "proposal", "talk", "session")

SHARED_PLATFORMS = ("papercept.net", "pretalx.com", "cvent.com", "sessionize.com",
                    "easychair.org", "oxfordabstracts.com", "conftool", "emsecure",
                    "abstractscorecard.com", "hsforms.com", "jotform.com")


def call_label(quote: str) -> str:
    """Which call the quoted sentence is about, if it says."""
    q = (quote or "").lower()
    for lab in CALL_LABELS:
        if lab in q:
            return lab
    return ""


def event_named(quote: str, event_name: str) -> bool:
    """Does the quote name THIS event? Used only on shared platforms, where a page carries
    many events' deadlines side by side."""
    q = (quote or "").lower()
    # The token must be DISTINCTIVE. A first version matched "ieee" and let IROS and
    # Humanoids through on ras.papercept.net - where the quote was TMECH/AIM's deadline and
    # every conference on the page contains "ieee". Publisher and society names identify the
    # platform, never the event.
    generic = {"conference", "annual", "international", "meeting", "summit", "expo",
               "symposium", "congress", "ieee", "acm", "association", "society", "institute",
               "global", "world", "national", "european", "american", "asia", "usa",
               "forum", "workshop", "convention", "exhibition", "show", "event", "2026",
               "2027", "2028"}
    toks = [t for t in re.split(r"[^a-z0-9]+", (event_name or "").lower())
            if len(t) > 3 and t not in generic]
    return any(t in q for t in toks[:6])


def exportable(verdict: str, quote: str, source_url: str, event_name: str) -> tuple[int, str]:
    """(may_export, reason_if_not). Only a contradiction can ever be exported."""
    if verdict != "contradicted":
        return 0, "not a contradiction"
    if not (quote or "").strip():
        return 0, "no quote captured - cannot be defended if challenged"
    if any(h in (source_url or "").lower() for h in SHARED_PLATFORMS):
        if not event_named(quote, event_name):
            return 0, "shared submission platform and the quote does not name this event"
    if not call_label(quote):
        return 0, "quote does not say WHICH call the date belongs to (R10)"
    return 1, ""


def readable(text: str) -> tuple[bool, str]:
    if not text:
        return False, "page could not be read"
    if len(text.strip()) < 200:
        return False, f"page returned almost no text ({len(text.strip())} chars)"
    head = text[:1500]
    if SOFT_404.search(head):
        m = SOFT_404.search(head)
        return False, f'soft 404 - page says "{m.group(0)}"'
    return True, ""


def quote_for(text: str, needle: str, width: int = 160) -> str:
    """The sentence we actually found, so a verdict can be read without re-visiting.

    The quote IS the evidence, so a bad one is worse than none. A first version searched for
    the bare day number ("4"), which matched the first stray digit on the page and captured
    "2026 Photo Gallery 2025 Photo Booth" as proof of a February deadline.
    """
    if not needle or len(str(needle).strip()) < 3:
        return ""
    i = text.lower().find(str(needle).lower())
    if i < 0:
        return ""
    s, e = max(0, i - width // 2), min(len(text), i + width // 2)
    # Snap to a sentence if one is nearby, else to whole words. A fixed character window
    # produced "ognition associated with participation..." in a document meant to go to
    # another party - a quote that starts mid-word reads as careless and undercuts the
    # evidence it exists to support.
    seg = text[s:e]
    dot = seg.find(". ")
    if 0 <= dot < width // 3:
        seg = seg[dot + 2:]
    elif s > 0 and " " in seg:
        seg = seg.split(" ", 1)[1]
    if not seg.endswith(".") and " " in seg:
        seg = seg.rsplit(" ", 1)[0]
    return " ".join(seg.split()).strip()


def date_quote(text: str, d, width: int = 160) -> str:
    """Find the DATE as a human wrote it - "February 4, 2027", "4 Feb 2027", "2027-02-04" -
    never as a bare day number."""
    if not d:
        return ""
    month = d.strftime("%B")
    forms = [f"{month} {d.day}", f"{month} {d.day:02d}", f"{d.strftime('%b')} {d.day}",
             f"{d.day} {month}", f"{d.day} {d.strftime('%b')}", d.isoformat(),
             d.strftime("%m/%d/%Y"), d.strftime("%d/%m/%Y")]
    for f in forms:
        q = quote_for(text, f, width)
        if q:
            return q
    return ""


def check(field: str, claimed: str, text: str) -> tuple[str, str, str]:
    """(verdict, detail, found_quote) for one claim against one page's text."""
    claimed = (claimed or "").strip()
    if not claimed:
        return "no_quote", "nothing claimed for this field", ""

    if field == "deadline":
        d = _parse_date(claimed)
        if d and find_date(text, d):
            return "verified", f"page states {claimed}", date_quote(text, d)
        said = page_status(text)
        others = other_deadline_dates(text, exclude=d) if d else []
        if others:
            return ("contradicted",
                    "page gives a different deadline: " + ", ".join(others[:3]),
                    quote_for(text, others[0]))
        if said == "closed":
            return "contradicted", "page states the call is closed", quote_for(text, "closed")
        return "no_quote", "deadline not stated on this page - claim stands", ""

    if field == "status":
        said = page_status(text)
        if not said:
            return "no_quote", "page does not state a call status", ""
        if said == claimed.lower():
            return "verified", f"page states the call is {said}", quote_for(text, said)
        return "contradicted", f"page states the call is {said}, claim says {claimed}", \
            quote_for(text, said)

    # Everything else: does the claimed text actually appear on the page?
    probe = claimed[:60]
    if probe.lower() in text.lower():
        return "verified", "claimed value appears on the page", quote_for(text, probe)
    return "no_quote", "claimed value not found on this page", ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify claims against their cited pages.")
    ap.add_argument("--db", default="cfp_monitor.db")
    ap.add_argument("--limit", type=int, help="max distinct PAGES to visit")
    ap.add_argument("--disputed-only", action="store_true",
                    help="only pages cited by rows we currently dispute")
    ap.add_argument("--field", help="restrict to one field, e.g. deadline")
    ap.add_argument("--recheck", action="store_true", help="re-audit rows already checked")
    a = ap.parse_args()

    con = sqlite3.connect(a.db)
    con.row_factory = sqlite3.Row
    for ddl in ("alter table evidence add column call_type text",
                "alter table evidence add column exportable integer default 0",
                "alter table evidence add column export_block text"):
        try:
            con.execute(ddl)
        except sqlite3.OperationalError:
            pass            # already present
    con.commit()
    where = ["1=1"]
    params: list = []
    if not a.recheck:
        where.append("verdict = 'unchecked'")
    if a.field:
        where.append("field = ?"); params.append(a.field)
    if a.disputed_only:
        where.append("""event_id in (select event_id from grounding_facts
                        where verify_state='contradicted'
                          and verify_detail not like '%404%')""")
    rows = [dict(r) for r in con.execute(
        f"select * from evidence where {' and '.join(where)}", params)]

    names = {e: n for e, n in con.execute("select event_id, name from grounding_facts")}

    by_url: dict[str, list] = defaultdict(list)
    for r in rows:
        by_url[r["source_url"]].append(r)
    urls = list(by_url)
    if a.limit:
        urls = urls[:a.limit]

    print(f"{sum(len(by_url[u]) for u in urls)} claim(s) across {len(urls)} page(s)")
    print("one visit per page; the ladder is climbed on failure\n")

    tally: dict[str, int] = defaultdict(int)
    now = datetime.now().isoformat(timespec="seconds")
    for i, url in enumerate(urls, 1):
        claims = by_url[url]
        text, note = fetch_text(url)
        ok, why = readable(text)
        method = "http"
        if not ok:
            # TODO(ladder): escalate to Playwright then CDP here. Until that lands, an
            # unreadable page is recorded as unreadable - which is the honest verdict and
            # leaves every claim standing, rather than guessing from another page.
            for c in claims:
                con.execute("""update evidence set verdict='unreadable', detail=?, method=?,
                               fetched_at=?, found_quote=null where id=?""",
                            (why or note, method, now, c["id"]))
                tally["unreadable"] += 1
            print(f"[{i}/{len(urls)}] {url[:66]}\n        unreadable - {why or note}")
            continue

        print(f"[{i}/{len(urls)}] {url[:66]}  ({len(claims)} claim(s))")
        for c in claims:
            verdict, detail, found = check(c["field"], c["value_claimed"], text)
            exp, block = exportable(verdict, found, url, names.get(c["event_id"], ""))
            con.execute("""update evidence set verdict=?, detail=?, found_quote=?, method=?,
                           fetched_at=?, call_type=?, exportable=?, export_block=?
                           where id=?""",
                        (verdict, detail, found or None, method, now,
                         call_label(found) or None, exp, block or None, c["id"]))
            if verdict == "contradicted" and not exp:
                tally["blocked_from_export"] += 1
            tally[verdict] += 1
            mark = {"verified": "ok", "contradicted": "XX", "no_quote": "--",
                    "unreadable": "??"}.get(verdict, "??")
            print(f"        {mark} {c['field']:<16} {c['origin']:<9} {detail[:58]}")
        con.commit()
    con.commit()

    print("\n--- verdicts ---")
    for k in ("verified", "contradicted", "no_quote", "unreadable"):
        if tally.get(k):
            print(f"  {k:<14} {tally[k]}")
    print("\nOnly `contradicted` is a finding. `unreadable` and `no_quote` leave the claim")
    print("standing - they are things WE could not establish, not things upstream got wrong.")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
