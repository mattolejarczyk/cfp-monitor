"""Walking a conference site: one implementation, because there were four.

WHY THIS EXISTS
`investigate_event.py`, `find_event_pages.py`, `find_replacement_links.py` and
`auto_trace_r3b_high.py` each grew their own version of "render a page, read its links, decide
where to go next". The same three bugs were then fixed in some copies and not others:

  GUESSES BEFORE LINKS. Seeding the queue with invented paths (/cfp, /call-for-papers) before
      reading a single real href. Fixed in investigate_event on 2026-08-28 after guessing
      reached 3 of 20 pages on embedded world and 1 of 20 on PCIM; reintroduced the next day in
      auto_trace_r3b_high, where it spent 11 of a 12-page budget on paths that did not exist.

  SCORE USED AS A FILTER. Requiring a keyword match to even CONSIDER a link discarded 35 real
      links on worldrobotconference.com and 119 on robotworld.or.kr - their menus read FORUM /
      ATTENDEES / Exhibition Overview - and then fell back to guessing. A relevance score should
      decide what to try FIRST, never what counts as a candidate.

  EXACT-ORIGIN SAME-SITE TEST. robotworld.or.kr serves its menu from eng.robotworld.or.kr while
      the cited URL is www.robotworld.or.kr, so 118 of 119 links were discarded as "external".
      Two-part TLDs (.or.kr, .co.uk) break a naive last-two-labels rule.

All three were invisible in the output: each run reported success while looking somewhere other
than where it claimed. That is the argument for one implementation rather than four.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

# Worth following: the words that appear on links leading to a call, a deadline or a programme.
WORTH_FOLLOWING = re.compile(
    r"cfp|call|paper|abstract|speaker|speak|submit|submission|author|deadline|important|dates|"
    r"programme|program|agenda|session|participat|get[-_ ]?involved|sponsor", re.I)

# Never worth fetching: binaries, contact protocols, and other people's platforms.
#
# The social hosts are anchored to a host boundary on purpose. An unanchored `x\.com` also
# matches matrix.com, phoenix.com and vertex.com - and it silently ate the URLs in this
# module's own first test run, which is how the looseness was found.
NOT_A_PAGE = re.compile(
    r"\.(pdf|jpe?g|png|gif|svg|zip|ics|mp4|docx?|pptx?)($|\?)|mailto:|tel:|javascript:|"
    r"(?://|\.)(?:linkedin|twitter|facebook|instagram|youtube|t)\.(?:com|me)(?:[/?#]|$)", re.I)

# Tried ONLY when a page exposes no internal links at all - a JavaScript nav with no hrefs.
FALLBACK_PATHS = ("call-for-papers", "cfp", "call-for-speakers", "speakers", "abstracts",
                  "submissions", "submit", "important-dates", "programme", "participate")

# Second-level domain labels that are really part of the suffix.
_COMPOUND_TLD = {"or", "co", "com", "ac", "go", "ne", "net", "gov", "edu", "org"}


def registrable(host: str) -> str:
    """The domain two sites must share to count as the same site.

    Handles .or.kr / .co.uk / .com.au, which a plain last-two-labels rule gets wrong.
    """
    parts = (host or "").lower().strip(".").split(".")
    if len(parts) >= 3 and parts[-2] in _COMPOUND_TLD:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def same_site(a: str, b: str) -> bool:
    return registrable(urlparse(a).netloc) == registrable(urlparse(b).netloc)


def relevance(href: str, label: str = "") -> int:
    """How promising is this link? RANKS candidates - never decides which ones qualify.

    The LABEL outweighs the href: a menu item reading "Call for Papers" pointing at /node/482
    is a better lead than /en/cfp-archive, and the label is what a person reads.
    """
    score = 0
    if WORTH_FOLLOWING.search(label or ""):
        score += 3
    if WORTH_FOLLOWING.search(href or ""):
        score += 2
    if re.search(r"deadline|important[-_ ]?dates|submission", f"{label} {href}", re.I):
        score += 2
    return score


def rank_links(anchors, base_url: str) -> list[tuple[int, str, str]]:
    """Every internal link the page offers, best first. Returns (score, url, label).

    EVERY internal link is included. The score orders them; it does not exclude any. A real
    link the site chose to publish always beats a path we invented.
    """
    out, seen = [], set()
    for a in anchors or []:
        href = (a.get("href") or "").strip()
        label = " ".join((a.get("text") or "").split())
        if not href:
            continue
        if not href.lower().startswith(("http://", "https://")):
            href = urljoin(base_url, href)
        if not href.lower().startswith(("http://", "https://")):
            continue
        href = href.split("#")[0]
        if href in seen or NOT_A_PAGE.search(href) or not same_site(href, base_url):
            continue
        seen.add(href)
        out.append((relevance(href, label), href, label[:60]))
    out.sort(key=lambda x: -x[0])
    return out


def origin(url: str) -> str:
    """Scheme and host, no path. `https://www.secureworld.io/events` -> `https://www.secureworld.io`."""
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else ""


def sitemaps_from_robots(robots_text: str, base_url: str) -> list[str]:
    """The sitemaps a site names for itself in robots.txt.

    Asking beats guessing: `events.secureworld.io/robots.txt` names two sitemaps totalling
    11,237 URLs, one of which is the real speaker-submissions page that five separately guessed
    paths all missed.
    """
    out = []
    for line in (robots_text or "").splitlines():
        if line.lower().startswith("sitemap:"):
            u = line.split(":", 1)[1].strip()
            if u.startswith("http"):
                out.append(u)
            elif u:
                out.append(urljoin(origin(base_url) + "/", u.lstrip("/")))
    return out


def sitemap_candidates(base_url: str) -> list[str]:
    """Conventional sitemap locations, for a site whose robots.txt names none.

    These ARE guesses, but of a different kind from `fallback_urls`: a sitemap path is a
    published convention with one right answer, and a wrong guess returns something that does
    not parse as XML rather than a plausible-looking page. Guessing a CONTENT path is what
    produced five soft 404s that each looked like a find.
    """
    o = origin(base_url)
    if not o:
        return []
    return [urljoin(o + "/", p) for p in
            ("sitemap.xml", "sitemap_index.xml", "sitemap-index.xml", "wp-sitemap.xml",
             "sitemap/sitemap.xml")]


def parse_sitemap(xml_text: str) -> tuple[list[str], bool]:
    """Return (urls, is_index). An index points at more sitemaps rather than at pages.

    Namespaced tags are why this matches on the tag's SUFFIX: sitemaps declare
    `xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"`, so ElementTree reports
    `{...}loc` rather than `loc`.
    """
    from xml.etree import ElementTree as ET
    if not (xml_text or "").strip().startswith("<"):
        return [], False
    try:
        root = ET.fromstring(xml_text.encode("utf-8", "ignore"))
    except ET.ParseError:
        return [], False
    locs = [e.text.strip() for e in root.iter()
            if e.tag.endswith("loc") and (e.text or "").strip()]
    return locs, root.tag.endswith("sitemapindex")


def fallback_urls(base_url: str) -> list[str]:
    """Guessed paths. The LAST resort, only when a page exposed no internal links at all.

    A guess here can return HTTP 200 and still be nothing - on 2026-08-31 five of these shapes
    resolved to soft 404s across three SecureWorld hosts, and because each one answered, the
    pipeline believed it had found a call page. Prefer `sitemaps_from_robots` /
    `sitemap_candidates`: a site's own index is authority, a guessed path is resemblance.
    """
    p = urlparse(base_url)
    origin = f"{p.scheme}://{p.netloc}"
    return [urljoin(origin + "/", s + "/") for s in FALLBACK_PATHS]


def plan(anchors, base_url: str) -> tuple[list[str], str]:
    """What to visit next, and an honest description of how we chose it.

    The description matters: "12 links from the page's own navigation" and "guessed paths - the
    page exposed no internal links" are very different runs, and a report that cannot tell them
    apart is how a guess gets mistaken for a search.
    """
    ranked = rank_links(anchors, base_url)
    if ranked:
        scored = sum(1 for s, _u, _l in ranked if s)
        return ([u for _s, u, _l in ranked],
                f"{len(ranked)} link(s) from the page's own navigation "
                f"({scored} keyword-relevant, the rest by proximity)")
    return fallback_urls(base_url), "guessed paths - the page exposed no internal links at all"
