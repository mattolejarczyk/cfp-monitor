"""Where our record and the customer's sheet disagree, and why a row of theirs is not in ours.

NOT "THEIR ERRORS". Every item here is a DISAGREEMENT between two records, and on today's data
we are the wrong one at least twice - we hold a 2025 deadline for a conference their sheet has
in 2026, and a passed 2026 date for Troopers where they hold 2027. Naming the category after
the customer's mistakes would be wrong on the facts and would repeat the framing that put our
own coverage gap on them on 2026-08-31.

MATCHING COMES FROM THE MATCHER. `client_conferences.event_id` is written by
`resolve_client_matches.py` against MATCHING-METHODOLOGY.md. A name-prefix join was tried first
and reported "27 rows we do not track" - a number that included ESF MENA, which we plainly do
track. That was measuring the join failing, not coverage. Where the matcher left `event_id`
blank, its `match_confidence` says WHY, and the three causes need different actions:

    confidence >= 70   we hold the event; the match was never promoted   -> promote it
    confidence 1-69    genuinely ambiguous                               -> a human decides
    confidence 0       no candidate at all                               -> discovery, or out of scope

That third group is the only one that means "not in our database", and it is much smaller than
the raw unmatched count suggests.

HOW TO KEY `our_rows` - THE ANSWER WAS ALREADY WRITTEN DOWN

    delivery EVENT_ID  --_seed_map-->  our canonical id  ==  client_conferences.event_id

    87 of 87 matched client rows resolve. Zero fail.

`scripts/apply_resolutions._seed_map(store)` returns that mapping, and `build_review_page.py`
and `export_checks.py` both already use it. `docs/operations/customer-sheet-matching.md` states
it plainly: "The delivery's EVENT_ID column is UPSTREAM's, not ours (contract 5.4). The matcher
maps through the seed map to our canonical id. Never copy that column straight across."

A caller MUST map through it. Without that step the delivery's ids and the matcher's ids are two
different namespaces and nothing lines up.

WHAT NOT TO CONCLUDE FROM A BAD MEASUREMENT (2026-09-01)
A first version of this docstring recorded, as measured fact, that the matcher's own event_id
was the WORST of three joins - 43 of 111, against a name prefix at 38 and a URL host at 97 -
and recommended the URL host. Every number was real and the conclusion was wrong: the 43 came
from joining to the `conferences` TABLE instead of the delivery, and skipping the seed map. The
correct join scores 87 of 87.

The failure worth remembering is not the arithmetic. It is that the mechanism was documented,
the doc was not read, and the resulting numbers were persuasive enough to be written down as a
finding about the system. **A measurement can be arithmetically perfect and still be measuring
your own mistake** - and a confident table of three options is exactly how that gets believed.
"""
from __future__ import annotations

import re
from datetime import date

# Their pipeline states that mean the deadline no longer bites.
SETTLED = ("submitted", "accepted", "declined", "client declined", "rejected", "withdrawn",
           "closed", "not pursuing", "passed", "no longer")

PROMOTE_AT = 70.0


def _date(s) -> date | None:
    s = (s or "").strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    m = re.match(r"^(\d{4})-(\d\d)-(\d\d)$", s)
    if m:
        try:
            return date(*map(int, m.groups()))
        except ValueError:
            return None
    return None


def settled(status: str) -> bool:
    s = (status or "").strip().lower()
    return any(s.startswith(w) for w in SETTLED)


def url_year_conflict(url: str, edition: str) -> str:
    """Their link names one year, the row is another edition.

    The Global Energy Show case: their sheet points at `/conferences/2026-call-for-submissions/`
    while the live page is the 2027 one. Only the LAST year in the path is considered - a host
    or campaign id can carry an unrelated number.
    """
    u, ed = (url or "").strip(), (edition or "").strip()
    if not u.startswith("http") or not re.fullmatch(r"(19|20)\d{2}", ed):
        return ""
    years = re.findall(r"(?<!\d)(20\d{2})(?!\d)", u)
    if not years or years[-1] == ed:
        return ""
    return f"their link points at {years[-1]}, this row is the {ed} edition"


def why_unmatched(confidence) -> tuple[str, str]:
    """(cause, what to do) for a client row the matcher could not link."""
    try:
        c = float(confidence or 0)
    except (TypeError, ValueError):
        c = 0.0
    if c >= PROMOTE_AT:
        return ("match not promoted",
                "we hold this event - the match scored high and was never confirmed")
    if c > 0:
        return ("ambiguous match",
                "more than one candidate, or a weak one - needs a person to decide")
    return ("no candidate found",
            "nothing in our lists resembles it - either a discovery gap or out of scope")


def reconcile(client_rows, our_by_event_id, today: date) -> list[dict]:
    """Every disagreement worth a customer's attention, as flat dicts.

    `our_by_event_id` maps the matcher's event_id to our delivery row.
    """
    out = []
    for c in client_rows:
        name = (c.get("their_name") or "").strip()
        ck = c.get("client_key") or ""
        eid = (c.get("event_id") or "").strip()
        ours = our_by_event_id.get(eid) if eid else None
        acted = settled(c.get("status"))

        if not eid or ours is None:
            cause, what = why_unmatched(c.get("match_confidence"))
            out.append({"client": ck, "name": name, "eid": eid, "kind": "coverage",
                        "cat": cause, "detail": what,
                        "theirs": (c.get("status") or ""), "ours": "",
                        "ours_wrong": False, "acted": acted})
            continue

        # A deadline we both hold and disagree on.
        td, od = _date(c.get("their_deadline")), _date(ours.get("SUBMISSION DEADLINE"))
        if td and od and td != od:
            # If ours has already passed and theirs has not, ours is the stale one.
            ours_wrong = od < today <= td
            out.append({"client": ck, "name": name, "eid": eid, "kind": "conflict",
                        "cat": "deadline conflict",
                        "detail": ("our date has passed and theirs has not - likely ours"
                                   if ours_wrong else
                                   "the two records disagree; neither is proven wrong"),
                        "theirs": td.isoformat(), "ours": od.isoformat(),
                        "ours_wrong": ours_wrong, "acted": acted})

        # Their link names a different edition year.
        for col in ("their_submission_url", "their_url"):
            why = url_year_conflict(c.get(col), ours.get("EDITION"))
            if why:
                out.append({"client": ck, "name": name, "eid": eid, "kind": "conflict",
                            "cat": "link points at another edition", "detail": why,
                            "theirs": (c.get(col) or "").strip(), "ours": "",
                            "ours_wrong": False, "acted": acted})
                break
    return out
