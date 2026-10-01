"""Crawl-priority rules, version 2 (2026-09-30). Pure functions, no network.

What changed from v1 and why (all from the samples in RESULT.md):
  * WHOLE-TOKEN matching on the last path segments. v1 matched substrings: "cfp" inside `...-cfp-energy`, "author" inside
    `not-authorized`.
  * PROFILE / DETAIL pages are dropped: a page UNDER a directory segment (/speakers/<name>, /exhibitors/<company>,
    /contributor/<name>, /sessions/<title> ...). The directory's own index page is kept.
  * FAMILY COLLAPSE (the structural version of "a person would stop after a few profile pages"): when one parent path has
    8 or more children, the children are dropped whatever they are called, and only the parent index is kept. A short
    strict call/submission child (e.g. /speakers/submit) is exempt.
  * Long slugs (more than 8 words in the last segment) and very deep paths (more than 5 segments) read as articles or
    profiles, not as call pages, and are dropped.
  * Tiers carry a per-site BUDGET instead of one flat cap: P1 call/submission (all, up to 50), P2 programme/dates/awards (10),
    P3 sponsorship/exhibit index (3), P4 next-edition hints (5); never more than 50 in total.
  * 'about', 'venue', 'register' are no longer a tier: they matched everything and answer none of our fields.
"""
import re
from collections import defaultdict
from urllib.parse import urlparse

FILE_EXT = re.compile(r"\.(pdf|jpe?g|png|gif|svg|webp|zip|ics|mp4|mp3|docx?|pptx?|xlsx?|css|js|json|xml|txt|map|woff2?)$", re.I)
ASSET = re.compile(r"wp-content/uploads|/hubfs/|/assets/|/static/|/_next/|/cdn-cgi/|/wp-json|/wp-admin|/feed/?$", re.I)
LANG = {"fr", "de", "es", "it", "pt", "ja", "zh", "ko", "nl", "ru", "ar", "pl", "tr", "sv", "da", "fi", "no", "cs", "hu", "th",
        "vi", "id", "he", "el", "zh-cn", "zh-tw", "pt-br", "es-mx", "fr-ca"}
TRANSPARENT = {"en", "en-us", "en-gb", "en-au", "en-ca", "en-in", "en-sg", "us", "uk", "global"}  # English/region prefix: look past it

GENERIC = {"privacy", "terms", "legal", "disclaimer", "cookie", "cookies", "imprint", "impressum", "accessibility", "gdpr",
           "sitemap", "login", "signin", "signup", "account", "cart", "checkout", "basket", "careers", "career", "jobs", "job",
           "unsubscribe", "tag", "tags", "category", "categories", "search", "print", "contact", "press", "media", "gallery",
           "photos", "photo", "video", "videos", "podcast", "shop", "store", "password", "thank-you", "confirmation", "cookies-policy"}
NEWS = {"news", "blog", "blogs", "insights", "articles", "article", "stories", "story", "posts", "post", "press-release"}
DIRECTORY = {"speaker", "speakers", "exhibitor", "exhibitors", "sponsor", "sponsors", "partner", "partners", "company",
             "companies", "contributor", "contributors", "profile", "profiles", "people", "person", "team", "member", "members",
             "attendee", "attendees", "session", "sessions", "presentation", "presentations", "talk", "talks", "author", "authors",
             "judge", "judges", "jury", "winner", "winners", "finalist", "finalists", "directory", "organisations", "organizations"}

P1_TOKENS = {"cfp", "abstract", "abstracts", "submit", "submission", "submissions", "proposal", "proposals", "deadline",
             "deadlines", "nominate", "nominations", "nomination", "entries"}
P1_PHRASES = [("call", "for"), ("important", "dates"), ("key", "dates"), ("become", "a", "speaker"), ("speaker", "application"),
              ("speaker", "submission"), ("apply", "to", "speak"), ("present", "with", "us"), ("submission", "guidelines"),
              ("author", "instructions"), ("author", "guidelines"), ("for", "authors"), ("authors", "information"),
              ("dates", "and", "deadlines"), ("submit", "your")]
P2_TOKENS = {"programme", "program", "agenda", "schedule", "timetable", "awards", "award", "prizes", "competition", "dates"}
P3_TOKENS = {"sponsor", "sponsors", "sponsorship", "sponsoring", "exhibit", "exhibiting", "exhibitors", "exhibition", "partnership",
             "partnerships", "prospectus", "booth", "booths"}
P4_TOKENS = {"2027", "2028"}
P4_PHRASES = [("save", "the", "date"), ("next", "year")]
BUDGET = {"P1 call/submission": 50, "P2 programme/dates/awards": 10, "P3 sponsorship/exhibit index": 3, "P4 next-edition hint": 5}
TOTAL_CAP = 50
FAMILY_MIN = 8


def words(seg):
    return [t for t in re.split(r"[-_+. ]+", seg.lower()) if t]


def has_phrase(toks, phrase):
    n = len(phrase)
    return any(tuple(toks[i:i + n]) == phrase for i in range(len(toks) - n + 1))


def segments(url):
    segs = [s for s in urlparse(url).path.split("/") if s]
    while segs and segs[0].lower() in TRANSPARENT:
        segs = segs[1:]
    return segs


def p1_strict(seg_list):
    """True if the last two segments carry a whole-token call/submission signal."""
    toks = []
    for s in seg_list[-2:]:
        toks += words(s)
    return any(t in P1_TOKENS for t in toks) or any(has_phrase(toks, p) for p in P1_PHRASES)


def tier_of(seg_list):
    last = words(seg_list[-1]) if seg_list else []
    both = []
    for s in seg_list[-2:]:
        both += words(s)
    if p1_strict(seg_list):
        return "P1 call/submission"
    if any(t in P2_TOKENS for t in last):
        return "P2 programme/dates/awards"
    if any(t in P3_TOKENS for t in last):
        return "P3 sponsorship/exhibit index"
    if any(t in P4_TOKENS for t in both) or any(has_phrase(both, p) for p in P4_PHRASES):
        return "P4 next-edition hint"
    return ""


def classify_all(urls):
    """{url: (verdict, tier_or_reason)} for one site's URLs. verdict: keep | drop."""
    out, kids = {}, defaultdict(list)
    info = {}
    for u in urls:
        path = urlparse(u).path or "/"
        segs_raw = [s for s in path.split("/") if s]
        if FILE_EXT.search(path):
            out[u] = ("drop", "file"); continue
        if ASSET.search(u):
            out[u] = ("drop", "asset"); continue
        if segs_raw and segs_raw[0].lower() in LANG:
            out[u] = ("drop", "other-language"); continue
        segs = segments(u)
        if not segs:
            out[u] = ("drop", "homepage"); continue
        allw = {w for s in segs for w in words(s)}
        if allw & GENERIC:
            out[u] = ("drop", "generic"); continue
        if allw & NEWS:
            out[u] = ("drop", "news/blog"); continue
        if len(segs) > 5:
            out[u] = ("drop", "too deep"); continue
        if len(words(segs[-1])) > 8:
            out[u] = ("drop", "long slug (article/profile)"); continue
        info[u] = segs
        kids["/".join(s.lower() for s in segs[:-1])].append(u)
    # Families exist under a NAMED parent only. The site root always has many children (the whole menu), and collapsing
    # those would delete /agenda/, /speakers/, /sponsorship/ themselves.
    # A parent holding most of the site's pages is the site's HOME FOLDER (h2meet.com serves everything under /html/ko/), not a
    # directory of profiles. Without this guard the whole site collapsed to nothing (found 2026-10-01 in the crawl test).
    total_pages = max(1, len(info))
    big = {p for p, v in kids.items()
           if p and len(v) >= FAMILY_MIN
           and not (len(v) / total_pages > 0.6 and not ({w for seg in p.split("/") for w in words(seg)} & DIRECTORY))}
    for u, segs in info.items():
        strict = p1_strict(segs) and len(words(segs[-1])) <= 4
        parent = "/".join(s.lower() for s in segs[:-1])
        under_dir = any(words(s) and (set(words(s)) & DIRECTORY) and (set(words(s)) <= DIRECTORY | {"our", "all", "the"})
                        for s in segs[:-1])
        if under_dir and not strict:
            out[u] = ("drop", "profile/detail page"); continue
        if parent in big and not strict:
            out[u] = ("drop", "family child (8+ siblings)"); continue
        t = tier_of(segs)
        out[u] = ("keep", t) if t else ("drop", "no keyword")
    return out


def select(verdicts):
    """Apply the per-tier budgets, then the total cap. Returns [(url, tier)] in priority order."""
    by = defaultdict(list)
    for u, (v, t) in verdicts.items():
        if v == "keep":
            by[t].append(u)
    chosen = []
    for t in BUDGET:
        us = sorted(by[t], key=lambda u: (len(segments(u)), len(u)))
        chosen += [(u, t) for u in us[:BUDGET[t]]]
    return chosen[:TOTAL_CAP]
