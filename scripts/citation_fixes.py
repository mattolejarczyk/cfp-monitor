"""Propose a BETTER CITATION where the one on record cannot support its own claim.

THE PROBLEM
On 2026-08-10 an audit found that `deadline_evidence_url` is identical to `main_info_url` on
42% of cited rows. Those are not wrong readings, they are placeholders - the field was filled
to be non-empty rather than to record where a sentence was found. CFP deadlines are rarely on
a homepage, so such a citation can never confirm anything: we fetch it, the sentence is not
there, and a correct deadline shows as unverified forever.

Telling upstream "52% of your citations are homepages" is true and useless. This produces the
version they can act on: **here is the page that does carry your deadline, and the sentence.**

WHERE THE ANSWER COMES FROM
Our own crawls recorded per-field evidence with deep URLs all along; it sat unqueryable in
`result_json` until `build_evidence.py`. So for many rows we already hold the right page and
have simply never offered it.

THE RULE THAT STOPS THIS BACKFIRING
A better page for THIS EVENT is not automatically a better page for THIS CALL. One event runs
abstracts, full papers, case studies, posters and company presentations with different
deadlines (R10). The MedTech Conference cites `/call-for-sessions/` while our verified page is
`/company-presentations` - offering that would repeat, in the opposite direction, the error
this whole exercise removed.

So a correction is offered only when the call MATCHES:

  * our page's quote must name a call at all - no label, no offer
  * that label must be consistent with the row's opportunity type (speaking / awards /
    exhibiting / registration), taken from the EVENT_ID suffix
  * where the cited URL names a call of its own, ours must agree with it

Anything else is REVIEW: shown to a human, never sent to the other party.

    python scripts/citation_fixes.py --db cfp_monitor.db --out citation_fixes.csv
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("_ae", ROOT / "scripts" / "audit_evidence.py")
_ae = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ae)          # reuse call_label / event_named / SHARED_PLATFORMS

# Which call labels belong to which opportunity. A "nomination" is not a speaking deadline and
# an "exhibit" is not a call for papers; crossing those is how a booth deadline masquerades as
# a call for speakers (contract R5).
OPPORTUNITY_LABELS = {
    "speaking": {"abstract", "full paper", "call for paper", "paper submission", "paper",
                 "case study", "poster", "workshop", "tutorial", "panel", "late-breaking",
                 "late breaking", "lightning", "speaker", "speaking", "presentation",
                 "proposal", "talk", "session"},
    "awards": {"nomination", "entry", "award"},
    "exhibiting": {"exhibit", "booth", "sponsor"},
    "registration": {"register", "registration"},
}


def opportunity_of(event_id: str) -> str:
    """From the EVENT_ID suffix. Speaking is unsuffixed by design (contract section 10)."""
    for opp in ("awards", "exhibiting", "registration"):
        if (event_id or "").endswith("-" + opp):
            return opp
    return "speaking"


def judge(event_id: str, cited_url: str, our_url: str, our_quote: str,
          event_name: str) -> tuple[str, str]:
    """(verdict, why). CONFIRMED may be offered upstream; REVIEW may not."""
    # R3, never substitute a shallower URL. A first run proposed co2-chemistry.eu (the
    # HOMEPAGE) to replace their /call-for-abstracts/ page - the exact inversion of the
    # problem this script exists to fix.
    from urllib.parse import urlparse
    our_path = (urlparse(our_url or "").path or "").rstrip("/")
    cited_path = (urlparse(cited_url or "").path or "").rstrip("/")
    if our_path in ("", "/"):
        return "REVIEW", "our page is the homepage - R3 forbids a shallower substitute"
    if cited_path not in ("", "/") and len(our_path) < len(cited_path) / 2:
        return "REVIEW", "our page is shallower than the one they cite"

    ours = _ae.call_label(our_quote or "")
    if not ours:
        return "REVIEW", "our page does not say WHICH call the date belongs to"

    opp = opportunity_of(event_id)
    if ours not in OPPORTUNITY_LABELS.get(opp, set()):
        return "REVIEW", f"our page names a '{ours}' call but the row is {opp}"

    theirs = _ae.call_label(cited_url or "")
    if theirs and theirs != ours:
        return "REVIEW", f"they cite a '{theirs}' page, ours is '{ours}' - different calls"

    if any(h in (our_url or "").lower() for h in _ae.SHARED_PLATFORMS):
        if not _ae.event_named(our_quote, event_name):
            return "REVIEW", "our page is a shared platform and the quote does not name the event"

    return "CONFIRMED", f"same call ({ours}), quote carries the date"


def main() -> int:
    ap = argparse.ArgumentParser(description="Propose better citations from evidence we hold.")
    ap.add_argument("--db", default="cfp_monitor.db")
    ap.add_argument("--out", default="citation_fixes.csv")
    a = ap.parse_args()

    con = sqlite3.connect(a.db)
    con.row_factory = sqlite3.Row
    try:
        rows = list(con.execute("""
            select g.event_id, f.name, f.deadline, g.source_url as cited, g.verdict as gverdict,
                   c.source_url as ours, c.found_quote, c.call_type
            from evidence g
            join grounding_facts f on f.event_id = g.event_id
            join evidence c on c.event_id = g.event_id
                           and c.field = 'deadline' and c.origin = 'crawl'
                           and c.verdict = 'verified' and c.source_url <> g.source_url
            where g.field = 'deadline' and g.origin = 'grounding'
              and coalesce(g.value_claimed,'') <> ''
              and g.verdict in ('no_quote','unreadable')
            order by f.name"""))
    except sqlite3.OperationalError as exc:
        print(f"ERROR: {exc}. Run build_evidence.py then audit_evidence.py first.")
        return 2

    out, seen = [], set()
    for r in rows:
        if r["event_id"] in seen:
            continue
        seen.add(r["event_id"])
        verdict, why = judge(r["event_id"], r["cited"], r["ours"],
                             r["found_quote"] or "", r["name"] or "")
        out.append({
            "CONFERENCE": r["name"], "EVENT_ID": r["event_id"],
            "DEADLINE CLAIMED": r["deadline"],
            "CITED (cannot confirm)": r["cited"], "WHY IT FAILED": r["gverdict"],
            "BETTER PAGE": r["ours"], "QUOTE ON THAT PAGE": (r["found_quote"] or "").strip(),
            "CALL": r["call_type"] or "", "VERDICT": verdict, "WHY": why,
        })

    if not out:
        print("No candidates. Either citations are confirming, or the audit has not run.")
        return 0

    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    conf = [r for r in out if r["VERDICT"] == "CONFIRMED"]
    rev = [r for r in out if r["VERDICT"] == "REVIEW"]
    print(f"{len(out)} candidate(s): {len(conf)} CONFIRMED, {len(rev)} need review\n")
    for r in conf:
        print(f"  {r['CONFERENCE'][:46]}  [{r['CALL']}]")
        print(f"     cited  : {r['CITED (cannot confirm)'][:68]}")
        print(f"     better : {r['BETTER PAGE'][:68]}")
    if rev:
        print("\nheld back for review - NOT offered upstream:")
        for r in rev:
            print(f"  {r['CONFERENCE'][:44]} - {r['WHY']}")
    print(f"\nwrote {a.out}")
    print("These are citation CORRECTIONS. The deadline value is untouched -")
    print("we are proposing where the sentence lives, not changing what it says.")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
