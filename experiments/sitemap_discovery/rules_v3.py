"""Crawl-priority rules, version 3 (2026-10-01). Pure functions, no network. Builds on rules_v2 (same structure and budgets).

Changes from v2, each from a defect seen in the v2 samples:
  * STALE YEARS: a page whose path names only years before the current one is dropped (nullcon.net kept CFP pages for
    2014, 2016, 2017). Current year is a parameter, default 2026.
  * NARROWER P2: bare "program" no longer qualifies (sans.org work-study / state-local programs); it counts only with event
    context in the path (conference, summit, expo ...). "programme", "agenda", "schedule", "timetable", "awards", "dates" remain.
  * NOISE TERMS drop a page outright: exam, committee, governance, winners, finalists, membership, course, certification,
    training, scholarship, alumni, archive, past, previous, recap (isc2.org kept exam schedules, a nomination committee and award
    winners).
  * LINK TEXT: a menu link's visible label is scored as well as its address. "Call for Speakers" pointing at /node/482 is a call
    page. A label can RESCUE a page the address rules called "no keyword" and can UPGRADE a tier; it never rescues a page dropped
    as stale, noise, profile, family child, too deep or long slug.
"""
import re
from collections import defaultdict
import rules_v2 as v2
from rules_v2 import (BUDGET, TOTAL_CAP, words, segments, p1_strict, has_phrase, select)   # select works on (url,(verdict,tier))

CURRENT_YEAR = 2026
NOISE = {"exam", "exams", "committee", "governance", "winner", "winners", "finalist", "finalists", "membership", "course",
         "courses", "certification", "training", "scholarship", "scholarships", "alumni", "archive", "archives", "past",
         "previous", "recap", "highlights"}
EVENT_CTX = {"conference", "conferences", "summit", "congress", "expo", "event", "events", "forum", "symposium", "exhibition", "week"}
P2_TOKENS = {"programme", "agenda", "schedule", "timetable", "awards", "award", "prizes", "competition", "dates"}
TIER_ORDER = list(BUDGET)
YEAR = re.compile(r"(?<!\d)(20[12]\d)(?!\d)")

LABEL_P1_TOKENS = {"cfp", "submit", "submission", "submissions", "abstract", "abstracts", "propose", "proposal", "proposals",
                   "deadline", "deadlines", "nominate", "nominations"}
LABEL_P1_PHRASES = [("call", "for"), ("become", "a", "speaker"), ("speaker", "application"), ("speaker", "applications"),
                    ("apply", "to", "speak"), ("apply", "to", "present"), ("important", "dates"), ("key", "dates"),
                    ("for", "authors"), ("present", "with", "us"), ("speak", "at"), ("submit", "your")]
LABEL_P2 = {"agenda", "programme", "schedule", "timetable", "awards", "award"}
LABEL_P3 = {"sponsor", "sponsors", "sponsorship", "sponsoring", "exhibit", "exhibiting", "exhibitors", "prospectus", "partnership"}


def label_tier(label):
    w = [t for t in re.split(r"[^a-z0-9]+", (label or "").lower()) if t]
    if not w or len(w) > 10:
        return ""
    if set(w) & NOISE:
        return ""
    if set(w) & LABEL_P1_TOKENS or any(has_phrase(w, p) for p in LABEL_P1_PHRASES):
        return "P1 call/submission"
    if set(w) & LABEL_P2:
        return "P2 programme/dates/awards"
    if set(w) & LABEL_P3:
        return "P3 sponsorship/exhibit index"
    if {"2027", "2028"} & set(w) or has_phrase(w, ("save", "the", "date")):
        return "P4 next-edition hint"
    return ""


def tier_of(seg_list):
    last = words(seg_list[-1]) if seg_list else []
    both = []
    for s in seg_list[-2:]:
        both += words(s)
    if p1_strict(seg_list):
        return "P1 call/submission"
    allw = {w for s in seg_list for w in words(s)}
    if any(t in P2_TOKENS for t in last) or ("program" in last and allw & EVENT_CTX):
        return "P2 programme/dates/awards"
    if any(t in v2.P3_TOKENS for t in last):
        return "P3 sponsorship/exhibit index"
    if any(t in v2.P4_TOKENS for t in both) or any(has_phrase(both, p) for p in v2.P4_PHRASES):
        return "P4 next-edition hint"
    return ""


def best(a, b):
    if not a:
        return b
    if not b:
        return a
    return a if TIER_ORDER.index(a) <= TIER_ORDER.index(b) else b


def classify_all(urls, labels=None, current_year=CURRENT_YEAR):
    """{url: (verdict, tier_or_reason, via)}; via in {'url','label','both',''}. labels: {url: visible link text}."""
    labels = labels or {}
    base = v2.classify_all(urls)
    out = {}
    for u in urls:
        verdict, why = base[u]
        segs = segments(u)
        lt = label_tier(labels.get(u, ""))
        if verdict == "drop":
            if why == "no keyword" and lt:
                allw = {w for s in segs for w in words(s)}
                yrs = [int(y) for y in YEAR.findall(" ".join(segs))]
                if allw & NOISE:
                    out[u] = ("drop", "noise term", "")
                elif yrs and max(yrs) < current_year:
                    out[u] = ("drop", "stale year", "")
                else:
                    out[u] = ("keep", lt, "label")
            else:
                out[u] = (verdict, why, "")
            continue
        # kept by v2: apply the v3 corrections
        allw = {w for s in segs for w in words(s)}
        yrs = [int(y) for y in YEAR.findall(" ".join(segs))]
        if allw & NOISE:
            out[u] = ("drop", "noise term", ""); continue
        if yrs and max(yrs) < current_year:
            out[u] = ("drop", "stale year", ""); continue
        ut = tier_of(segs)
        if not ut and not lt:
            out[u] = ("drop", "no keyword (v3 narrower)", ""); continue
        t = best(ut, lt)
        via = "both" if (ut and lt) else ("url" if ut else "label")
        out[u] = ("keep", t, via)
    return out


def select3(verdicts):
    return select({u: (v, t) for u, (v, t, _via) in verdicts.items()})
