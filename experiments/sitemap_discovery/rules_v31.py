"""Rules v3.1: v3 plus four small fixes, each switchable so its effect can be measured alone.
  F1 noise terms "board", "review", "reviewers"   (nullcon /about/cfp-review-board/, gartner /products/proposal-review)
  F2 de-duplicate address variants before selection (blackhat listed one call page twice)
  F3 link-text phrases "join as a speaker", "contribution(s)" (h2meet.com, troopers.de)
  F4 two-digit edition years (nullcon-goa-15) read as the year 2015 => stale
"""
import re
import rules_v2 as v2
import rules_v3 as r3
from rules_v2 import words, segments, BUDGET, TOTAL_CAP

NOISE_EXTRA = {"board", "review", "reviews", "reviewer", "reviewers"}
TWO_DIGIT = re.compile(r"(?:^|[-_])(1\d|2[0-5])$")
FOUR_DIGIT = re.compile(r"(?<!\d)(20[12]\d)(?!\d)")


def label_tier(label, flags):
    t = r3.label_tier(label)
    if t or "F3" not in flags:
        return t
    w = [x for x in re.split(r"[^a-z0-9]+", (label or "").lower()) if x]
    if not w or len(w) > 10 or set(w) & r3.NOISE:
        return ""
    if v2.has_phrase(w, ("join", "as", "a", "speaker")) or {"contribution", "contributions"} & set(w):
        return "P1 call/submission"
    return ""


def canon(u):
    p = re.sub(r"^https?://(www\.)?", "", u.lower()).split("?")[0].split("#")[0]
    p = re.sub(r"/(index)?(\.html?|\.php)?$", "", p)
    return re.sub(r"\.(html?|php)$", "", p).rstrip("/")


def classify_all(urls, labels=None, flags=frozenset()):
    out = r3.classify_all(urls, labels)
    labels = labels or {}
    for u, (verdict, tier, via) in list(out.items()):
        segs = segments(u)
        if verdict == "keep":
            allw = {w for s in segs for w in words(s)}
            if "F1" in flags and allw & NOISE_EXTRA:
                out[u] = ("drop", "noise term (v3.1)", ""); continue
            if "F4" in flags and not FOUR_DIGIT.search(" ".join(segs)):
                if any(len(words(s)) >= 2 and TWO_DIGIT.search(s.lower()) for s in segs):
                    out[u] = ("drop", "stale two-digit year", ""); continue
        elif "F3" in flags and tier == "no keyword":
            lt = label_tier(labels.get(u, ""), flags)
            if lt:
                allw = {w for s in segs for w in words(s)}
                if not (allw & r3.NOISE) and not (("F1" in flags) and allw & NOISE_EXTRA):
                    out[u] = ("keep", lt, "label")
    return out


def select31(verdicts, flags=frozenset()):
    kept = {u: (v, t) for u, (v, t, _x) in verdicts.items()}
    chosen = v2.select(kept)
    if "F2" not in flags:
        return chosen
    seen, out = set(), []
    # re-select with duplicates removed BEFORE the budgets are applied, so a duplicate does not use up a slot
    uniq = {}
    for u, (v, t) in kept.items():
        if v == "keep":
            k = canon(u)
            if k not in uniq or len(u) < len(uniq[k]):
                uniq[k] = u
    keep_urls = set(uniq.values())
    return v2.select({u: ((v, t) if (v != "keep" or u in keep_urls) else ("drop", "duplicate")) for u, (v, t) in kept.items()})


ALL_FIXES = frozenset({"F1", "F2", "F3", "F4"})


def plan(urls, labels=None):
    """THE v3.1 SELECTION (all four fixes on): [(url, tier)] in crawl priority order, within the per-tier budgets."""
    return select31(classify_all(urls, labels, ALL_FIXES), ALL_FIXES)
