"""Date reading for page text, v2 (2026-10-01). Pure functions, no network.

Why: the crawl test missed h2meet's "Speaker Registration - 1st: 7/1 ~ 8/31 - 2nd: 9/1 ~ 9/30" because the existing `verify.find_date` needs a year.
This keeps every form the existing function reads and adds:
  * year-less dates   "Sep. 30", "30 September", "9/30", "30/09"
  * ranges            "9/1 ~ 9/30", "7/1 - 8/31", "Sept 1 to Sept 30"  (each end is a date)
  * East-Asian        "2026年9月30日", "2026년 9월 30일"
  * dotted European   "30.09.2026", "30.9."
  * European months   German, French, Spanish, Italian names
Each match carries a CONFIDENCE so a weak match is never passed off as a strong one:
  with-year      the full date including the year (strong)
  yearless       month and day, and the page also names the target year somewhere (medium)
  yearless-noyr  month and day but no year anywhere on the page (weak)
  ambiguous      numeric d/m vs m/d where both readings are valid dates and the target fits only one (weak, flagged)
"""
import re
from datetime import date
from src.cfp_monitor.verify import find_date, date_variants, normalize_text

MONTHS = {
    "en": ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"],
    "de": ["januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "dezember"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
    "it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"],
}


def month_names(m):
    """Every written form of month m (1-12), lowercase: full names in five languages plus English 3-letter and Sept."""
    names = {MONTHS[l][m - 1] for l in MONTHS}
    en = MONTHS["en"][m - 1]
    names |= {en[:3], en[:3] + "."}
    if m == 9:
        names |= {"sept", "sept."}
    return sorted(names, key=len, reverse=True)


def _norm(t):
    t = (t or "").lower()
    t = t.replace("–", "-").replace("—", "-").replace("~", "-").replace("～", "-").replace("〜", "-")
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", t)
    return re.sub(r"\s+", " ", t)


def find_target(text, target: date):
    """Return (confidence, form) for the best way `target` appears in `text`, or None. Strongest form wins."""
    t = _norm(text)
    if find_date(text, target):
        return "with-year", "with year (existing reader)"
    y, m, d = target.year, target.month, target.day
    # East-Asian: 2026年9月30日 / 2026년 9월 30일 / 2026. 9. 30.
    if re.search(rf"(?<!\d){y}\s*[年년.\-/]\s*0?{m}\s*[月월.\-/]\s*0?{d}(?!\d)", t):
        return "with-year", "East-Asian or dotted year-first"
    # dotted/slashed European with year: 30.09.2026, 30/09/2026
    if re.search(rf"\b0?{d}\s*[./-]\s*0?{m}\s*[./-]\s*{y}\b", t):
        return "with-year", "day-first numeric with year"
    # written month + day, month names in any supported language
    names = "|".join(re.escape(n) for n in month_names(m))
    written = [rf"(?<![a-zäéû])(?:{names})\s*0?{d}(?!\d)", rf"(?<!\d)0?{d}\.?\s+(?:de\s+)?(?:{names})(?![a-zäéû])"]
    has_year = bool(re.search(rf"(?<!\d){y}(?!\d)", t))
    cand = None
    for pat in written:
        for mm in re.finditer(pat, t):
            fy = _following_year(t, mm.end())
            if fy is not None and fy != y:
                continue                      # "March 31st, 2027" is another edition's date, not this one
            if fy == y:
                return "with-year", "written month and day, year follows"
            cand = cand or "written month and day"
    if cand:
        return ("yearless" if has_year else "yearless-noyr"), cand
    # numeric m/d or d/m, as a standalone token or a range end; avoid matching inside longer numbers/times
    pats = [rf"(?<![\d/.:])0?{m}\s*[/.\-]\s*0?{d}(?![\d:]|\s*[/.]\s*\d)"]
    if d != m:
        pats.append(rf"(?<![\d/.:])0?{d}\s*[/.\-]\s*0?{m}(?![\d:]|\s*[/.]\s*\d)")
    for pat in pats:
        for mm in re.finditer(pat, t):
            fy = _following_year(t, mm.end())
            if fy is not None and fy != y:
                continue
            if d > 12:   # a day above 12 can only be a day, so the order is unambiguous
                if fy == y:
                    return "with-year", "numeric month/day, year follows"
                return ("yearless" if has_year else "yearless-noyr"), "numeric month/day (day above 12, order unambiguous)"
            return "ambiguous", "numeric day/month vs month/day (both orders valid)"
    return None


def _following_year(t, end):
    """A four-digit year written within 12 non-digit characters after a date ('Sep. 30 (Wed), 2026'), else None."""
    mm = re.match(r"\D{0,12}?(20\d\d)(?!\d)", t[end:end + 20])
    return int(mm.group(1)) if mm else None


ANY_DATE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*\d{1,2}(?:st|nd|rd|th)?\b"
    r"|\b\d{1,2}(?:st|nd|rd|th)?\.?\s+(?:de\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|januar|märz|mai|juni|juli|oktober|dezember|"
    r"janvier|février|avril|juin|juillet|août|septembre|octobre|novembre|décembre|enero|marzo|mayo|junio|julio|agosto|septiembre|"
    r"gennaio|febbraio|aprile|maggio|giugno|luglio|settembre|ottobre|dicembre)[a-zä]*"
    r"|\b20\d\d-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{1,2}\.\d{1,2}\.(?:\d{2,4})?"
    r"|20\d\d\s*[年년]\s*\d{1,2}\s*[月월]\s*\d{1,2}", re.I)
CALLVOC = re.compile(r"deadline|submission|submit|call for|abstract|proposal|cfp|due|closes?|speaker registration|"
                     r"einreichung|frist|soumission|date limite|plazo|scadenza|제출|마감|締切|截止", re.I)


def any_date_near_call(text, radius=200):
    """True if some date-looking string sits within `radius` characters of call/deadline wording (several languages)."""
    t = _norm(text)
    for m in CALLVOC.finditer(t):
        if ANY_DATE.search(t[max(0, m.start() - radius): m.end() + radius]):
            return True
    return False
