"""Does the event a customer row is LINKED to agree with what the customer's own row says? (ACT-54, fix b)

One rule, shared by scripts/match_customer_sheet.py (do not certify a link whose place or date disagrees),
scripts/customer_coverage.py (list the links we already hold that disagree) and
scripts/customer_row_answers.py (the one-line answer per customer row).

THE CASE. Hack In The Box: the customer tracks conference.hitb.org, Alila SCBD, Jakarta, 29 Apr 2026. We held a Phuket
event of 24 Aug 2026 on the same website. The matcher called an exact URL 100 percent and linked them; the organiser's
site hosts several events, so the same website is not the same event. Date and place are the facts that tell sibling
events apart, so when the customer's row carries both and they disagree the link is NOT certain.

THE RULE. A link DISAGREES when the customer row has a full start date and the linked event has one and they are more
than DATE_TOLERANCE_DAYS apart, or when both name a place and the customer's place does not name the event's city (or
the other way round). A missing date or place cannot disagree (nothing to compare), and a year alone is not a date.
Pure functions, no I/O."""
from __future__ import annotations

import re
from datetime import date, datetime

DATE_TOLERANCE_DAYS = 30
_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m/%d/%y")


def full_date(text) -> date | None:
    """A complete calendar date from text, else None. A bare year ('2026') is NOT a date: it must never be read as 1 July."""
    if isinstance(text, datetime):
        return text.date()
    if isinstance(text, date):
        return text
    s = (text or "").strip()
    if not s:
        return None
    first = s.split()[0]
    for f in _FORMATS:
        try:
            return datetime.strptime(first, f).date()
        except ValueError:
            pass
    return None


_VENUE_WORDS = {"the", "of", "and", "at", "in", "hotel", "resort", "center", "centre", "convention", "exhibition", "international", "city", "grand", "hyatt", "marriott", "hilton",
                "sheraton", "expo", "park", "bay", "beach", "south", "north", "east", "west", "new", "united", "states", "usa", "uk", "us", "ca", "tx", "ny"}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def place_agrees(their_place: str, our_city: str) -> bool | None:
    """True / False, or None when either side names no place (cannot be judged). The customer's LOCATION is a venue line
    ('Alila SCBD, Jakarta, Indonesia'), so it agrees when it contains our city, or our city contains its first segment."""
    loc, city = _norm(their_place), _norm(our_city)
    if not loc or not city:
        return None
    if city in loc or loc in city:
        return True
    first = _norm((their_place or "").split(",")[0])
    if first and (first in city or city in first):
        return True
    # a shared place word counts ('ATI ONGC, Goa' and 'Grand Hyatt Goa' both name Goa); venue words never do
    return bool((set(loc.split()) & set(city.split())) - _VENUE_WORDS)


def link_disagreement(their_place: str, their_start, our_city: str, our_start, tolerance: int = DATE_TOLERANCE_DAYS) -> str:
    """'' when the link agrees or cannot be judged; otherwise a plain-English reason naming both sides."""
    why = []
    t, o = full_date(their_start), full_date(our_start)
    if t and o:
        gap = abs((t - o).days)
        if gap > tolerance:
            why.append(f"date: customer {t.isoformat()}, linked event {o.isoformat()} ({gap} days apart)")
    if place_agrees(their_place, our_city) is False:
        why.append(f"place: customer '{(their_place or '').strip()}', linked event city '{(our_city or '').strip()}'")
    return "; ".join(why)


def linked_disagreements(con, client_key: str | None = None) -> list[dict]:
    """READ-ONLY revisit of the links we already hold (ACT-54 b). Every client_conferences row with an event_id whose linked
    grounding_facts event disagrees with the customer's own row, with both sides. `con` is any sqlite3 connection (the caller
    opens it mode=ro for the live database); nothing is written. Customer-withdrawn rows are skipped."""
    q = ("select c.client_key, c.their_name, c.their_url, c.location, c.event_start_date, c.event_id, g.name, g.city, g.start_date, g.url "
         "from client_conferences c join grounding_facts g on g.event_id = c.event_id "
         "where coalesce(c.event_id,'') != '' and coalesce(c.withdrawn_by_customer,0) = 0")
    args: tuple = ()
    if client_key:
        q += " and c.client_key = ?"
        args = (client_key,)
    out = []
    for r in con.execute(q + " order by c.client_key, c.their_name", args):
        why = link_disagreement(r[3] or "", r[4] or "", r[7] or "", r[8] or "")
        if why:
            out.append({"client": r[0], "name": r[1], "customer_url": r[2] or "", "customer_place": r[3] or "", "customer_start": r[4] or "",
                        "event_id": r[5], "event_name": r[6] or "", "event_city": r[7] or "", "event_start": r[8] or "", "event_url": r[9] or "", "why": why})
    return out
