"""Experiment 4 (2026-10-03): the READ-THE-PAGE PASS. Pure logic: the prompt, what code accepts, and how a result is scored against what a person verified.

THE QUESTION. Given the page a person checked (or one the first, grounded pass found), can a cheap model read the event's start date, end date, city, country, venue,
organizer and format, each with a verbatim quote, and stay BLANK when the page does not state it for the edition we ask about (the wrong-edition and no-page traps)?

RULES (code decides, not the model): a field is accepted only if (a) the model returned a value and a quote, (b) the quote is a literal substring of the page text (whitespace
normalised), (c) for a date, the quote states that day and month, in the asked edition's year or with a year the quote states, and (d) for a text field, the value appears in the quote.
Everything else is blank. Nothing here fetches, calls a model or writes data."""
from __future__ import annotations

import re
from datetime import date, datetime

FIELDS = ("start_date", "end_date", "city", "country", "venue", "organizer", "format")
SYSTEM = """You read ONE web page about a conference or event and report facts about ONE edition of it.
You are given the event name and the EDITION YEAR to report. Report ONLY what the page states for that edition.
For each field return {"value": ..., "quote": ...}. The quote must be copied EXACTLY, as a literal substring of the page text (do not fix, shorten or join). If the page does not state the field
for that edition, return {"value": "", "quote": ""}. NEVER infer, never use another edition's dates, never use your own knowledge of the event.
If the page shows a different edition than the one asked (for example the page title or dates are for the next or the previous year), every date field is blank.
Fields:
  start_date  ISO YYYY-MM-DD, the first day of the event itself (not a call for papers, registration or sponsor date)
  end_date    ISO YYYY-MM-DD, the last day of the event itself
  city        the city where it is held (not the venue name)
  country     the country where it is held
  venue       the venue or building name, if stated
  organizer   the organization that runs the event, if stated
  format      one of In-Person, Virtual, Hybrid, only if the page states it
Return ONLY JSON: {"start_date":{"value":"","quote":""},"end_date":{...},"city":{...},"country":{...},"venue":{...},"organizer":{...},"format":{...}}."""


def user_message(event: str, edition: str, page_text: str, cap: int = 12000) -> str:
    return f"EVENT: {event}\nEDITION YEAR TO REPORT: {edition}\n\nPAGE TEXT:\n{page_text[:cap]}"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace(" ", " ")).strip().lower()


def year_from_heading(page: str, quote: str, window: int = 400) -> str:
    """The nearest year (2010-2029) written EARLIER on the page than the quote, within `window` characters; '' if none or the quote is not on the page."""
    p, q = norm(page), norm(quote)
    i = p.find(q)
    if i < 0:
        return ""
    years = re.findall(r"(?<!\d)(20[12]\d)(?!\d)", p[max(0, i - window): i])
    return years[-1] if years else ""


_MONTH_WORDS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|janu|febr|marz|mars|mai|mayo|juni|juli|okto|dezem|janvier|fevrier|avril|juin|juillet|aout|septembre|octobre|novembre|decembre|enero|febrero|marzo|abril|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|gennaio|febbraio|aprile|maggio|giugno|luglio|settembre|ottobre|dicembre)[a-z]*"


def looks_dateless(text: str) -> bool:
    """True if the text has no date with a year in it (no month name or numeric date near a 2010-2029 year). Used to decide a plain fetch is not enough and the page
    should be rendered in a real browser (script-built pages print their dates after the page loads)."""
    from src.cfp_monitor.verify import normalize_text
    low = normalize_text(text)                # punctuation and accents stripped, like the date reader
    if len(low) < 300:
        return True
    if re.search(rf"{_MONTH_WORDS}[ a-z0-9\-]{{0,22}}20[12]\d|20[12]\d[ a-z0-9\-]{{0,22}}{_MONTH_WORDS}", low):
        return False
    return not re.search(r"(?<!\d)\d{1,2}[ ./-]\d{1,2}[ ./-]20[12]\d", low)


def accept(field: str, item: dict, page: str, edition: str) -> tuple[str, str]:
    """(value or '', why). The model's claim is accepted only if the page itself supports it."""
    value, quote = (item or {}).get("value", ""), (item or {}).get("quote", "")
    if not value or not quote:
        return "", "blank"
    if norm(quote) not in norm(page):
        return "", "quote is not on the page"
    if field in ("start_date", "end_date"):
        from scripts.start_date_arbiter import expand_ranges
        from src.cfp_monitor.verify import find_date
        try:
            d = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return "", "not an ISO date"
        q = expand_ranges(quote)
        how = "ok"
        if not find_date(q, d):
            # LIMITER 3 (2026-10-03): a block such as 'ODSC AI East 2026 ... Join us April 28-30' states the year in the heading, not beside the date. The year may be taken from the
            # nearest EARLIER year on the page (within 400 characters) only when the quote itself states no year, and only if it is the date's year.
            y = year_from_heading(page, quote)
            if (not y) or re.search(r"20[12]\d", quote) or str(d.year) != y or not find_date(expand_ranges(f"{quote} {y}"), d):
                return "", "the quote does not state that day, month and year"
            how = f"ok (year {y} taken from the nearest earlier year on the page)"
        if edition and str(d.year) != str(edition) and not (field == "end_date" and abs(d.year - int(edition)) <= 1):
            return "", "date is not in the asked edition's year"
        return value, how
    if norm(value) not in norm(quote):
        return "", "the value is not in the quote"
    if field == "format" and value not in ("In-Person", "Virtual", "Hybrid"):
        return "", "format is not one of the three"
    return value, "ok"


def _first_iso(text: str) -> str:
    from scripts.start_date_arbiter import first_date
    d = first_date(text or "")
    return d.isoformat() if d else ""


def gold_facts(pins: list[dict]) -> list[dict]:
    """One gold fact per (event, field) a person verified. A pinned blank means 'the page states nothing': the pass must stay blank."""
    out = []
    for p in pins:
        s = p.get("set", {})
        mapping = {"START DATE": "start_date", "CITY": "city", "COUNTRY": "country"}
        for k, f in mapping.items():
            if k in s:
                out.append({"event": p["event"], "canonical": p["canonical"], "field": f, "gold": s[k], "links": p.get("links", []), "tier": "person-confirmed"})
        if "CONFERENCE DATES" in s and s["CONFERENCE DATES"]:
            iso = _first_iso(s["CONFERENCE DATES"])
            if iso and not any(o["canonical"] == p["canonical"] and o["field"] == "start_date" for o in out):
                out.append({"event": p["event"], "canonical": p["canonical"], "field": "start_date", "gold": iso, "links": p.get("links", []), "tier": "person-confirmed"})
    return out


def same(field: str, got: str, gold: str) -> bool:
    if field in ("start_date", "end_date"):
        return got == gold
    return norm(gold) in norm(got) or norm(got) in norm(gold)


def score(items: list[dict]) -> dict:
    """items: {event, field, gold, accepted ('' = blank)}. Precision, recall, blank-correct and false-accept counts.
    The READER is scored only on person-confirmed facts (ACT-04/ACT-21): an item whose `tier` is anything else raises. An item with no tier (a trap fixture, a page
    a person read) is taken as person-confirmed, as before."""
    from scripts.answer_key import assert_reader_tier
    assert_reader_tier(items, "reader score")
    failed = sum(1 for i in items if i.get("call_failed"))
    items = [i for i in items if not i.get("call_failed")]            # a failed call says nothing about the model: it is reported, not scored
    acc = [i for i in items if i["accepted"]]
    non_blank_gold = [i for i in items if i["gold"]]
    blank_gold = [i for i in items if not i["gold"]]
    correct = [i for i in acc if i["gold"] and same(i["field"], i["accepted"], i["gold"])]
    found = [i for i in non_blank_gold if i["accepted"] and same(i["field"], i["accepted"], i["gold"])]
    wrong = [i for i in acc if i["gold"] and not same(i["field"], i["accepted"], i["gold"])]
    false_accept = [i for i in blank_gold if i["accepted"]]
    return {"calls_failed": failed, "facts": len(items), "accepted": len(acc), "correct": len(correct), "wrong": len(wrong), "found_of_gold": f"{len(found)} of {len(non_blank_gold)}",
            "blank_gold": len(blank_gold), "blank_kept_blank": len(blank_gold) - len(false_accept), "false_accept": len(false_accept),
            "precision": round(len(correct) / len(acc), 3) if acc else None,
            "recall": round(len(found) / len(non_blank_gold), 3) if non_blank_gold else None}
