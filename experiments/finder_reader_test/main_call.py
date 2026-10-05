"""Which of several accepted deadlines is the MAIN call's? (2026-10-04; the 10-04 finder test found real, quote-proven dates for other calls on the same site: posters, awards.)

Input: candidates = [{"value": "YYYY-MM-DD", "url": ..., "what": the page's own words, "quote": ..., "home": bool}], all already accepted by the code (quote on the page, year-specific,
call wording). Rule, in order:
  1. OTHER calls are set aside: posters, awards/prizes/nominations, workshops, tutorials, sponsors/exhibitors, students/scholarships, demos, and a date only seen on a late/extended round.
  2. From what is left, a page NAMED for the main call (call for papers / speakers / abstracts / submission / cfp / speak, in its address or in the date's own words) beats the home page
     or any other page.
  3. Within that tier, the next date to close on or after today (the earliest open round).
  4. If everything accepted is an other-call date, NO pick (honest blank) and the row says why.
AWARDS (kind="award", ACT-22, 2026-10-05): the rule is INVERTED where the thing itself is an award. An awards row's main call IS a nomination or an entry, so award / prize / nominat / entry /
competition are NOT 'other calls' (their pattern must not contain them); a page named for nominations, entries, applications or the award itself is the main-call page. Still set aside: posters,
workshops, tutorials, sponsors/exhibitors, students/scholarships, demos, late/camera-ready, notification and judging dates. Conference rows are unchanged.
Returns {"pick": date or "", "why": ..., "alternatives": [...], "other_calls": [...], "rounds": n}. Pure function; reads nothing, writes nothing."""
from __future__ import annotations

import re

OTHER = re.compile(r"poster|award|prize|nominat|workshop|tutorial|sponsor|exhibit|student|scholarship|demo|competition|hackathon|late[- ]breaking|camera[- ]ready|notification", re.I)
MAIN_PAGE = re.compile(r"call[-_ ]?for|cfp|cfs|submission|submit|abstract|paper|speak|proposal", re.I)
# awards: nominations, entries and the award itself are the main call; everything else that is a side call stays set aside
OTHER_AWARD = re.compile(r"poster|workshop|tutorial|sponsor|exhibit|student|scholarship|demo|hackathon|late[- ]breaking|camera[- ]ready|notification|judging|shortlist|winners? (?:announce|revealed)", re.I)
MAIN_PAGE_AWARD = re.compile(r"call[-_ ]?for|submission|submit|nominat|entry|entries|enter\b|apply|application|award|prize|competition|cfp|proposal", re.I)


def classify(c: dict, kind: str = "conference") -> str:
    """'other' | 'main-page' | 'main-other' (a main-looking date on a page not named for the call, e.g. the home page)."""
    other, main = (OTHER_AWARD, MAIN_PAGE_AWARD) if kind == "award" else (OTHER, MAIN_PAGE)
    text = f"{c.get('url', '')} {c.get('what', '')} {c.get('quote', '')}"
    if other.search(text):
        return "other"
    if main.search(f"{c.get('url', '')} {c.get('what', '')}"):
        return "main-page"
    return "main-other"


def choose_main(cands: list[dict], today: str, kind: str = "conference") -> dict:
    live = [c for c in cands if c.get("value", "") >= today]
    kinds = [(classify(c, kind), c) for c in live]
    other = [c for k, c in kinds if k == "other"]
    for tier in ("main-page", "main-other"):
        pool = sorted((c for k, c in kinds if k == tier), key=lambda c: c["value"])
        if pool:
            pick = pool[0]
            rounds = sorted({c["value"] for c in pool})
            return {"pick": pick["value"], "why": f"{tier}: {pick.get('url', '')}", "alternatives": rounds[1:], "other_calls": [(c["value"], c.get("url", "")) for c in other],
                    "rounds": len(rounds)}
    return {"pick": "", "why": "only other-call dates found (posters, awards, workshops...)" if other else "no accepted date", "alternatives": [],
            "other_calls": [(c["value"], c.get("url", "")) for c in other], "rounds": 0}
