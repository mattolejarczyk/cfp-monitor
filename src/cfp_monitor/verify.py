"""Verify grounding (discovery) claims against evidence, cheapest layer first.

Resolution follows the precedence hierarchy agreed with the discovery layer:

    verified      evidence confirms the claim
    contradicted  evidence states something DIFFERENT  -> we override grounding
    not_found     no evidence either way               -> GROUNDING STANDS, still unverified

"Not found" is never a disproof, so it never removes or rewrites a grounding value.

Three layers, in increasing cost. Each row stops at the first layer that resolves it:

    L0  cross-check against conferences we have ALREADY crawled   (free, instant)
    L1  HTTP reachability of the submission link                  (fast, one request)
    L2  fresh crawl + date-token match on the live page           (slow, minutes/site)

L0 matters more than it sounds: most of a market's rows are usually already covered by our
own crawl history, so the expensive layer only runs on the genuinely unknown remainder.
"""
from __future__ import annotations

import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Optional

# The dateutil-backed parser reads month-name formats ("June 1, 2027") as well as numeric
# ones. verify's inputs are OUR crawled strings, which are overwhelmingly month-name, so the
# numeric-only parser used at import time is not sufficient here. It is equally conservative:
# a full year-month-day must be present or it returns None.
from .filtering import parse_deadline as _parse_date

_MONTHS = ["january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december"]

VERIFIED, CONTRADICTED, NOT_FOUND = "verified", "contradicted", "not_found"


def date_variants(d: date) -> list[str]:
    """Every plausible rendering of a date, normalized for substring matching.

    Deliberately generous: a page may say "March 15, 2026", "15 March 2026", "2026-03-15" or
    "3/15/26". Matching the DATE TOKEN rather than a whole quoted sentence is what makes
    verification robust to HTML whitespace, cookie banners and re-worded copy.
    """
    mon, abbr = _MONTHS[d.month - 1], _MONTHS[d.month - 1][:3]
    out = {
        f"{mon} {d.day}, {d.year}", f"{mon} {d.day} {d.year}",
        f"{d.day} {mon} {d.year}", f"{abbr} {d.day}, {d.year}", f"{abbr} {d.day} {d.year}",
        f"{d.day} {abbr} {d.year}", f"{d.year}-{d.month:02d}-{d.day:02d}",
        f"{d.month}/{d.day}/{d.year}", f"{d.month:02d}/{d.day:02d}/{d.year}",
        f"{d.day}/{d.month}/{d.year}", f"{d.month}/{d.day}/{str(d.year)[2:]}",
    }
    return [normalize_text(v) for v in out]


def normalize_text(text: str) -> str:
    """Collapse case, whitespace and punctuation noise so date tokens compare reliably."""
    t = (text or "").lower()
    t = t.replace("–", "-").replace("—", "-").replace(" ", " ")
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", t)      # 15th -> 15
    t = re.sub(r"[^a-z0-9/\-: ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def find_date(haystack: str, target: date) -> bool:
    """True if `target` appears in the text in any common rendering."""
    hay = normalize_text(haystack)
    return any(v in hay for v in date_variants(target))


def other_deadline_dates(haystack: str, exclude: Optional[date] = None,
                         today: Optional[date] = None) -> list[str]:
    """Deadline-labelled dates on the page that are NOT the target, restricted to dates that
    could PLAUSIBLY be the deadline being checked.

    Without the plausibility window this over-fires badly: a page's archive links, copyright
    lines and past-edition notices sit near deadline wording and produced "contradictions"
    citing 2018 and 2025 dates. Since a contradiction OVERRIDES the discovery layer, weak
    evidence here is worse than no evidence -- so anything outside roughly the current cycle
    is discarded and the row falls through to not_found instead.
    """
    today = today or date.today()
    lo, hi = date(today.year - 1, 1, 1), date(today.year + 3, 12, 31)
    hay = normalize_text(haystack)
    found: list[str] = []
    for m in re.finditer(r"(deadline|closes?|due|submit by|submissions? close)[^.]{0,80}", hay):
        seg = m.group(0)
        for dm in re.finditer(
                r"((" + "|".join(_MONTHS) + r")\s+\d{1,2},?\s+20\d{2}|20\d{2}-\d{2}-\d{2}"
                r"|\d{1,2}/\d{1,2}/20\d{2})", seg):
            token = dm.group(0)
            if exclude and token in " ".join(date_variants(exclude)):
                continue
            parsed = _parse_date(token)
            if parsed is None or not (lo <= parsed <= hi):
                continue                       # archive/copyright noise, not this cycle
            found.append(token)
    return sorted(set(found))


@dataclass
class Outcome:
    state: str
    detail: str
    layer: str


# ------------------------------------------------------------------- layer 0 --
def cross_check(claim_deadline: str, claim_status: str, crawled: dict,
                today: Optional[date] = None, edition: str = "") -> Optional[Outcome]:
    """Resolve against a conference we have already crawled -- no network needed.

    DELIBERATELY CONSERVATIVE about contradicting. Our stored deadline is only trustworthy
    enough to override grounding when it is a real, current, well-crawled date. In practice
    much of our history is not: some rows hold prose ("closed"), a yearless fragment
    ("May 8th"), or a date from an edition that has since rolled over ("November 24, 2024").
    Overriding a current grounding claim with our own stale value would make the data WORSE,
    so every one of those cases declines (None) and defers to the live-page layer.

    Confirmation is safe in all cases: if our crawl text contains their date, that is
    agreement no matter how messy the surrounding string is.
    """
    today = today or date.today()
    ours_raw = (crawled.get("cfp_close_date") or "").strip()
    theirs = _parse_date(claim_deadline)
    if not ours_raw or not theirs:
        return None
    # The quality gate comes FIRST, before confirmation as well as contradiction. A failed or
    # thin crawl left no independent evidence, and such a row may have been populated from the
    # discovery layer itself -- in which case "our record agrees" is grounding confirming
    # grounding. Circular self-confirmation is worse than no answer, so decline outright.
    if crawled.get("quality") not in ("PASS",):
        return None
    if find_date(ours_raw, theirs):
        return Outcome(VERIFIED, f"our crawl of the page also reports {claim_deadline}", "L0")

    ours = _parse_date(ours_raw)
    if ours is None:
        # Prose or a yearless fragment: not firm enough to disprove anything.
        return None
    ed = (edition or "").strip()[:4]
    if ed.isdigit() and ours.year < int(ed):
        return None                     # our value predates the edition in question -> stale
    if ours < today:
        return None                     # our value has already passed -> probably last cycle
    return Outcome(CONTRADICTED,
                   f"our crawl of the page reports {ours_raw!r}, not {claim_deadline!r}", "L0")


# ------------------------------------------------------------------- layer 1 --
def _ctx() -> ssl.SSLContext:
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def link_status(url: str, timeout: int = 12) -> tuple[Optional[int], str]:
    """(status_code, note). A HEAD that fails is retried as GET, because plenty of sites
    reject HEAD outright. 403 means real-but-blocked, NOT dead -- only 404/410 disprove."""
    if not (url or "").startswith("http"):
        return None, "no url"
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method,
                                         headers={"User-Agent": "Mozilla/5.0"})
            return urllib.request.urlopen(req, timeout=timeout, context=_ctx()).status, method
        except urllib.error.HTTPError as e:
            if method == "GET":
                return e.code, "http error"
        except Exception as e:                        # DNS, TLS, timeout, connection reset
            if method == "GET":
                return None, type(e).__name__
    return None, "unreachable"


def check_link(url: str) -> Optional[Outcome]:
    """Only ever returns a NEGATIVE finding: a 404/410 proves the link is dead. Anything
    else (200, 403, timeout) is not evidence about the DEADLINE, so it declines."""
    code, note = link_status(url)
    if code in (404, 410):
        return Outcome(CONTRADICTED, f"submission link returns {code} - page does not exist", "L1")
    return None


# ------------------------------------------------------------------- layer 2 --
_TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)


def fetch_text(url: str, timeout: int = 20, max_bytes: int = 900_000) -> tuple[str, str]:
    """Plain HTTP GET reduced to visible text. Returns (text, note).

    Verification only needs to know whether a DATE appears, so this deliberately skips the
    browser and the LLM -- seconds per URL instead of minutes. Sites that block us (403) or
    need JavaScript simply yield no text, which resolves to not_found and leaves the
    grounding value standing rather than wrongly disproving it.
    """
    if not (url or "").startswith("http"):
        return "", "no url"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "text/html,application/xhtml+xml"})
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as resp:
            raw = resp.read(max_bytes)
        html = raw.decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return "", f"HTTP {e.code}"
    except Exception as e:
        return "", type(e).__name__
    html = _TAG.sub(" ", html)
    text = re.sub(r"<[^>]+>", " ", html)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&#8217;", "'").replace("&#8211;", "-"))
    return re.sub(r"\s+", " ", text), "ok"


def verify_against_page(page_text: str, claim_deadline: str) -> Outcome:
    """Resolve a claimed deadline against the live page text."""
    theirs = _parse_date(claim_deadline)
    if not page_text:
        return Outcome(NOT_FOUND, "page could not be read", "L2")
    if not theirs:
        return Outcome(NOT_FOUND, "no parseable deadline to check", "L2")
    if find_date(page_text, theirs):
        return Outcome(VERIFIED, f"page states {claim_deadline}", "L2")
    others = other_deadline_dates(page_text, exclude=theirs)
    if others:
        return Outcome(CONTRADICTED,
                       "page gives a different deadline: " + ", ".join(others[:3]), "L2")
    return Outcome(NOT_FOUND, "deadline not stated on the page - grounding value stands", "L2")
