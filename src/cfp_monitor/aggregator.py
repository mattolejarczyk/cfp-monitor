"""Aggregator navigation: when a crawled URL is a directory / organization page that lists
MANY events (not one conference), use the spreadsheet ROW CONTEXT (name, location, dates) to
pick the specific event link and crawl THAT instead. This mirrors what a person does by hand
(e.g. owasp.org -> the German event; securitybsides.com -> BSides Austin).

Pure scoring here; the pipeline wires the detection + one-hop re-crawl.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# Generic words that don't help identify a SPECIFIC event.
_STOP = {"the", "and", "for", "conference", "conferences", "summit", "forum", "expo", "event",
         "events", "global", "annual", "international", "usa", "security", "cyber", "tech"}


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) >= 3}


def _year(s) -> str | None:
    # A 4-digit 20xx not embedded in a longer digit run. Allows letter-glued slug years
    # ("BSidesAustin2015") while rejecting id-like runs ("91156017", "201500").
    m = re.findall(r"(?<!\d)(20\d{2})(?!\d)", str(s or ""))
    return m[0] if m else None


# Social / mirror hosts: never the event's authoritative site, so they lose to its own domain.
_NON_EVENT_HOSTS = {"twitter.com", "x.com", "facebook.com", "linkedin.com", "instagram.com",
                    "youtube.com", "youtu.be", "infosec.exchange", "mastodon.social",
                    "eventbrite.com", "meetup.com", "lu.ma"}


def _host(u: str) -> str:
    h = (urlparse(u).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def score_event_link(href: str, text: str, context: dict) -> float:
    """How well a link matches the target event described by the row context."""
    hay = f"{href} {text}".lower()
    score = 0.0
    # City (first chunk of location) is the strongest signal.
    city = [t for t in _tokens((context.get("location") or "").split(",")[0]) if t not in _STOP]
    if city and any(t in hay for t in city):
        score += 1.5
    # Distinctive name tokens (drop generic conference words).
    name_toks = [t for t in _tokens(context.get("name") or "") if t not in _STOP]
    score += 0.4 * sum(1 for t in name_toks if t in hay)
    # Target year, if the row gives one: reward a match, penalize a clearly stale year
    # (e.g. .../BSidesAustin2015 when the row targets 2026) so old editions lose to current.
    yr = _year(context.get("dates")) or _year(context.get("year"))
    link_yr = _year(hay)
    if yr and link_yr:
        if link_yr == yr:
            score += 0.6
        elif int(link_yr) < int(yr) - 1:
            score -= 1.0
    # Event-ish path (/event/, /events/, /2026/, /conference).
    if re.search(r"/(event|events|conference|20\d{2})(/|$|-)", href.lower()):
        score += 0.3
    # Social / mirror hosts are never the authoritative event site.
    if _host(href) in _NON_EVENT_HOSTS:
        score -= 1.0
    return round(score, 2)


def pick_event_link(links, context: dict, base_url: str, min_score: float = 1.5) -> str | None:
    """Best-matching specific-event link from an aggregator's discovered links, or None."""
    base = _host(base_url)
    best, best_s = None, min_score
    for l in links or []:
        href = (l.get("href") or "").strip()
        if not href.lower().startswith("http"):
            continue
        s = score_event_link(href, l.get("text") or "", context)
        if _host(href) != base:      # slight preference for the event's own site
            s += 0.2
        if s > best_s:
            best, best_s = href, s
    return best


def looks_like_aggregator(has_name: bool, status_basis, num_links: int) -> bool:
    """A weak result (no single conference resolved) on a page with MANY links = a directory."""
    weak = (not has_name) or (status_basis in ("insufficient_evidence", "no_opportunity_found", None))
    return weak and num_links >= 20
