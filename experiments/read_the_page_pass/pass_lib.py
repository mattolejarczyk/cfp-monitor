"""Experiment 4 (2026-10-03): the READ-THE-PAGE PASS. Pure logic: the prompt, what code accepts, and how a result is scored against what a person verified.

THE QUESTION. Given the page a person checked (or one the first, grounded pass found), can a cheap model read the event's start date, end date, city, country, venue,
organizer and format, each with a verbatim quote, and stay BLANK when the page does not state it for the edition we ask about (the wrong-edition and no-page traps)?

RULES (code decides, not the model): a field is accepted only if (a) the model returned a value and a quote, (b) the quote is a literal substring of the page text (whitespace
normalised), (c) for a date, the quote states that day and month, in the asked edition's year or with a year the quote states, and (d) for a text field, the value appears in the quote.
Everything else is blank. Nothing here fetches, calls a model or writes data."""
from __future__ import annotations

import re
from datetime import date, datetime

from src.cfp_monitor.verify import fold_punctuation

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
  country     the country where it is held. If the page names only a state or province (for example 'Las Vegas, NV' or 'Toronto, Ontario'), return the country that state or province belongs to and quote the sentence that names the state or province
  venue       the venue or building name, if stated
  organizer   the organization that runs the event, if stated
  format      one of In-Person, Virtual, Hybrid, only if the page states it
SEVERAL DATE RANGES (ACT-23): if the page states ONE range for the whole event ('held September 23-24, 2026'), use that range as stated.
Only when the page states TWO OR MORE SEPARATE date ranges, each introduced by its own label (for example 'Training: June 1-3, 2027' and 'Conference: June 4-5, 2027'), use the range the page itself labels as the conference,
and put that label in the quote. Never use a training, workshop, pre-conference or hackathon range. If several labelled ranges are shown and you cannot tell which is the conference, leave the date blank.
Return ONLY JSON: {"start_date":{"value":"","quote":""},"end_date":{...},"city":{...},"country":{...},"venue":{...},"organizer":{...},"format":{...}}."""


def user_message(event: str, edition: str, page_text: str, cap: int = 12000) -> str:
    return f"EVENT: {event}\nEDITION YEAR TO REPORT: {edition}\n\nPAGE TEXT:\n{page_text[:cap]}"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", fold_punctuation(s)).strip().lower()                 # ACT-49: dashes, quote marks and nbsp folded; never words


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


_EN_MON = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
_DASH = r"\s*(?:-|–|—|to)\s*"
_RANGE = re.compile(rf"(?:{_EN_MON}\s+\d{{1,2}}(?:st|nd|rd|th)?{_DASH}(?:{_EN_MON}\s+)?\d{{1,2}}(?:st|nd|rd|th)?"
                    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+{_EN_MON}{_DASH}\d{{1,2}}(?:st|nd|rd|th)?\s+{_EN_MON}"
                    rf"|\d{{1,2}}(?:st|nd|rd|th)?{_DASH}\d{{1,2}}(?:st|nd|rd|th)?\s+{_EN_MON})", re.I)
# a range that is NOT the main conference, by the page's own label
NOT_MAIN = re.compile(r"training|workshop|course|bootcamp|boot camp|hackathon|tutorial|pre-?conference|pre-?event|pre-?summit|post-?conference|masterclass|certification|exam|capture the flag|\bctf\b", re.I)
MAIN = re.compile(r"\b(?:conference|congress|summit|symposium|expo|exhibition|forum|main event|the event|convention|show|week|festival|meeting|con)\b", re.I)


def date_ranges(text: str, year: int | None = None, require_year: bool = False) -> list[str]:
    """The distinct date ranges written in a text ('June 1-3', '5-6 July', 'June 29 - July 1'), normalised, in order. With `year`, a range written with a DIFFERENT year right after it
    ('April 28-30, 2026' when asking about 2027) belongs to another edition and is not counted; a range with no year after it is counted, unless `require_year` (then only ranges
    that state `year` right after them count)."""
    return [k for _s, _e, k in _range_spans(text or "", year, require_year)]


def _range_spans(text: str, year: int | None, require_year: bool = False) -> list[tuple[int, int, str]]:
    """(start, end, normalised key) of every distinct range in `text` that belongs to `year` (see date_ranges)."""
    out, seen = [], set()
    for m in _RANGE.finditer(text or ""):
        if year is not None:
            ty = re.match(r"\W{0,3}(20[12]\d)", (text or "")[m.end(): m.end() + 8])
            if (ty and int(ty.group(1)) != year) or (require_year and not ty):
                continue
        k = re.sub(r"[^a-z0-9]+", " ", m.group(0).lower()).strip()
        if k not in seen:
            seen.add(k)
            out.append((m.start(), m.end(), k))
    return out


def own_label(window: str, start: int, end: int) -> str:
    """The page's OWN words that introduce or follow a range: up to 40 characters before it and 25 after, cut at the nearest sentence boundary (. ! ? | or a line break)."""
    before = re.split(r"[.!?|\n]", window[max(0, start - 40): start])[-1]
    after = re.split(r"[.!?|\n]", window[end: end + 25])[0]
    return f"{before} {after}".strip()


# ACT-62: German main-conference labels (R-001). 'vom 23.-24. September 2026' has no English month, so _RANGE never sees it and the labelled-range rule above never engaged; the German page
# states its main day in labels (Konferenz - Donnerstag 24.09.; Am 24. September ... Conference Day; Hauptveranstaltungstag (24.09.2026)). Read BY CODE, from the page text.
_DE_MONTHS = {"januar": 1, "februar": 2, "marz": 3, "maerz": 3, "märz": 3, "april": 4, "mai": 5, "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12}
_DE_MON = "(" + "|".join(sorted(_DE_MONTHS, key=len, reverse=True)) + ")"
_DE_WD = r"(?:(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)\s*,?\s*)?"
_DE_LAB = r"(?:hauptkonferenz|konferenztag|konferenz|hauptveranstaltungstag|hauptveranstaltung|kongresstag|kongress|conference day|main conference)"
_DE_RANGE = [re.compile(rf"(?<!\d)(\d{{1,2}})\.?\s*(?:-|bis)\s*(\d{{1,2}})\.\s*{_DE_MON}(?:\s+(20[12]\d))?"),                # 23.-24. September 2026
             re.compile(rf"(?<!\d)(\d{{1,2}})\.\s*{_DE_MON}\s*(?:-|bis)\s*(\d{{1,2}})\.\s*{_DE_MON}(?:\s+(20[12]\d))?")]        # 30. September - 2. Oktober 2026
_DE_NUM_RANGE = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.?\s*(?:-|bis)\s*(\d{1,2})\.(\d{1,2})\.(20[12]\d)?")                          # 23.09.-24.09.2026
_DE_MAIN_DAY = [re.compile(rf"{_DE_LAB}[\s:\-(]{{0,6}}{_DE_WD}\(?(\d{{1,2}})\.(\d{{1,2}})\.(20[12]\d)?"),                              # Konferenz - Donnerstag 24.09.
                re.compile(rf"{_DE_LAB}\s+(?:am|ist am|findet am)\s+{_DE_WD}(\d{{1,2}})\.\s*{_DE_MON}(?:\s+(20[12]\d))?"),            # Konferenztag am 24. September
                re.compile(rf"(?:^|[.!?]\s+)am\s+(\d{{1,2}})\.\s*{_DE_MON}(?:\s+(20[12]\d))?[^.!?]{{0,40}}?{_DE_LAB}")]               # Am 24. September erwartet euch der Conference Day


def _de_ranges(quote: str, year: int) -> list[tuple[date, date]]:
    out = []
    try:
        for m in _DE_RANGE[0].finditer(quote):
            y = int(m.group(4) or year); mo = _DE_MONTHS[m.group(3)]
            out.append((date(y, mo, int(m.group(1))), date(y, mo, int(m.group(2)))))
        for m in _DE_RANGE[1].finditer(quote):
            y = int(m.group(5) or year)
            out.append((date(y, _DE_MONTHS[m.group(2)], int(m.group(1))), date(y, _DE_MONTHS[m.group(4)], int(m.group(3)))))
        for m in _DE_NUM_RANGE.finditer(quote):
            y = int(m.group(5) or year)
            out.append((date(y, int(m.group(2)), int(m.group(1))), date(y, int(m.group(4)), int(m.group(3)))))
    except ValueError:
        return []
    return out


def _de_main_days(page: str, year: int) -> set[date]:
    out = set()
    for k, rx in enumerate(_DE_MAIN_DAY):
        for m in rx.finditer(page):
            try:
                if k == 0:
                    out.add(date(int(m.group(3) or year), int(m.group(2)), int(m.group(1))))
                else:
                    out.add(date(int(m.group(3) or year), _DE_MONTHS[m.group(2)], int(m.group(1))))
            except ValueError:
                pass
    return out


def german_label_verdict(page: str, quote: str, value: date | None) -> tuple[bool, str]:
    """ACT-62. If the quote is a GERMAN-written range that contains `value` and the page, in German labels, names a main-conference day inside that range, `value` must not be EARLIER than the
    first such day (R-001: the start is the first main-conference day; an earlier day is a training / pre-day). Anything else, including a German range with no recognised label, returns
    (True, 'ok'): exactly as before, nothing is rejected on a guess. English text never matches these patterns."""
    if value is None:
        return True, "ok"
    mains = _de_main_days(page, value.year)
    if not mains:
        return True, "ok"
    for lo, hi in _de_ranges(quote, value.year):
        inside = sorted(d for d in mains if lo <= d <= hi)
        if lo <= value <= hi and inside and value < inside[0]:
            return False, (f"the page labels {inside[0].isoformat()} as its main-conference day inside the range {lo.isoformat()} to {hi.isoformat()}; "
                           f"{value.isoformat()} is before it (a training or pre-day)")
    return True, "ok"


def label_verdict(page: str, quote: str, value: date | None, year: int | None = None) -> tuple[bool, str]:
    """ACT-23: when the page shows TWO OR MORE separate date ranges and at least one OTHER range carries a label of its own (training, workshop... or conference, summit...), the range the
    reader used must carry the page's own conference label, read BY CODE from the page text beside that range (not from the model). A page with one range, or whose other ranges carry no
    label word (an 'early bird June 1-15'), is accepted as before. `page` and `quote` are normalised text; the range used = the one inside the quote whose first day is `value`'s day.
    Ranges of another year are not rivals; with a year in the quote a year-less range is not either (the heading-year case, not a rival)."""
    i = page.find(quote)
    if i < 0 or value is None:
        return True, "ok"
    ok_de, why_de = german_label_verdict(page, quote, value)                 # ACT-62: German main-day labels; only ever rejects, never loosens
    if not ok_de:
        return False, why_de
    quote_has_year = bool(year) and bool(re.search(rf"(?<!\d){year}(?!\d)", quote))
    spans = _range_spans(page, year, require_year=quote_has_year)
    if len(spans) < 2:
        return True, "ok"
    mine = None
    for s, e, k in spans:
        first = re.search(r"\d{1,2}", k)
        if i <= s and e <= i + len(quote) and first and int(first.group(0)) == value.day and (not re.search(r"[a-z]{3}", k) or value.strftime("%b").lower() in k):
            mine = (s, e, k)
            break
    if mine is None:
        return True, "ok"
    rivals = [(k, own_label(page, s, e)) for s, e, k in spans if k != mine[2]]
    if not any(NOT_MAIN.search(l) or MAIN.search(l) for _k, l in rivals):
        return True, "ok"                                                  # the other ranges say nothing about what they are: nothing to tell apart
    lab = own_label(page, mine[0], mine[1])
    if NOT_MAIN.search(lab) and not MAIN.search(lab):
        return False, f"the page shows {len(spans)} date ranges and labels this one '{lab}': a training or side range, not the conference"
    if MAIN.search(lab) and not NOT_MAIN.search(lab):
        return True, f"{len(spans)} ranges on the page; this one is labelled '{lab}' by the page"
    return False, f"the page shows {len(spans)} date ranges and nothing labels this one as the conference"


def accept(field: str, item: dict, page: str, edition: str) -> tuple[str, str]:
    """(value or '', why). The model's claim is accepted only if the page itself supports it."""
    value, quote = (item or {}).get("value", ""), (item or {}).get("quote", "")
    if not value or not quote:
        return "", "blank"
    if norm(quote) not in norm(page):
        return "", "quote is not on the page"
    if field == "country" and norm(value) not in norm(quote):
        # ACT-23: the page names a state or province, not the country ('Las Vegas, NV'). Accepted only when a CHECKED lookup puts that region in the claimed country.
        from src.cfp_monitor.regions import country_from_region, country_matches
        hit = country_from_region(quote)
        if hit and country_matches(value, hit[0]):
            return value, f"ok (country from {hit[1]} named in the quote)"
        return "", "the value is not in the quote"
    if field in ("start_date", "end_date"):
        from scripts.start_date_arbiter import expand_ranges
        from src.cfp_monitor.verify import find_date
        try:
            d = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return "", "not an ISO date"
        ok_label, label_why = label_verdict(norm(page), norm(quote), d, d.year)
        if not ok_label:
            return "", label_why
        q = expand_ranges(quote)
        how = "ok" if label_why == "ok" else f"ok ({label_why})"
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
    if field == "country":                                                  # 'USA' and 'United States' are the same answer (ACT-23: the lookup returns the long form)
        from src.cfp_monitor.regions import COUNTRY_ALIASES
        g, w = " ".join(re.sub(r"[^a-z ]+", " ", got.lower()).split()), " ".join(re.sub(r"[^a-z ]+", " ", gold.lower()).split())
        if any(g in al and w in al for al in COUNTRY_ALIASES.values()):
            return True
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
