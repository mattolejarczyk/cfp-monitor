"""Extract the citation ourselves from candidate URLs upstream supplies.

WHY THIS EXISTS
Two pilots asked a grounded model to return both the page AND the sentence on it. Ten rows,
two usable. The failure was consistent: the URL was non-deterministic while the quote stayed
stable, so the model knew the fact and was guessing where it lived. AMP produced a working URL
on one run and a 404 on the next, same sentence both times. AAOS produced two phrasings of a
detail that appears nowhere on the site.

No prompt rule fixes that, because the model is being asked to report what is on a page it may
not have read. So the split changed: upstream finds candidate pages, we read them.

**A quote we extract is on the page by construction.** It cannot be otherwise. That removes
the fabrication surface rather than detecting it after the fact.

WHAT IT DOES
For each row, try each candidate URL in order - plain HTTP, then the browser ladder - and take
the first page carrying a sentence with the claimed date in it. Prefer a sentence that also
names the call (R10), because "July 6, 2026" settles nothing and "Case study deadline: July 6,
2026" settles it.

WHICH SENTENCE, AND WHY THAT NEEDED MORE THAN STRING MATCHING
Finding the date is easy. Deciding which dated sentence is the SUBMISSION deadline is not.
CCUS states 1 July 2026 in three places: as a submission deadline, as "the deadline to withdraw
your presentation", and inside a paragraph about abstract formatting. Five selection strategies
were tried - first hit, longest, shortest, label-preferring, submission-wording-preferring -
and each picked a different sentence. Two were verbatim, correctly dated, and about the wrong
fact. Regex cannot close that gap, because the gap is semantic.

So a model picks the sentence, and the pick is checked rather than trusted:

  we fetch the page  ->  model selects a sentence from THAT text  ->  code proves it is there

`llm_pick_sentence` accepts an answer only if it is a literal substring of the text we supplied,
and then re-cuts the quote from the page, so what we store is the source's own characters
rather than the model's echo of them. A paraphrase, a reformatted date, a composed sentence:
all die at that check. This is the opposite situation to the pilots above - there the model was
asked to report on a page we did not hold, and nothing could check the answer.

`--no-llm` falls back to string matching. It is free and it still guarantees the date is on the
page, but it cannot tell a submission deadline from a withdrawal deadline on the same date.

Before copying this pattern elsewhere, read "Where an LLM is safe, and where it is not" in
docs/operations/market-runbook.md - particularly the part about checking the whole answer. The
CALL label is the one thing the model returns that the substring check does not cover, and it
needed a guard of its own.

Emits the same shape the merge guard already accepts, so the output flows straight into
`apply_resolutions.py --citations`.

    python scripts/extract_citations.py -i candidate_urls.csv -o citations_extracted.csv
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("_ae", ROOT / "scripts" / "audit_evidence.py")
_ae = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ae)          # escalate / call_label / readable

from src.cfp_monitor.config import Settings                        # noqa: E402
from src.cfp_monitor.verify import (                                # noqa: E402
    _parse_date, fetch_text, find_date, is_homepage, other_deadline_dates,
)

SETTINGS = Settings()

# Same shape as verify.normalize_text, minus the ordinal rule, but it also returns where each
# surviving character came from in the original. That map is what lets us answer "yes, this
# sentence is on the page" and then quote the PAGE rather than the answer.
_KEEP = re.compile(r"[a-z0-9/\-: ]")


def _norm_map(s: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(s.lower()):
        c = ch if _KEEP.match(ch) else " "
        if c == " " and (not chars or chars[-1] == " "):
            continue
        chars.append(c)
        idx.append(i)
    while chars and chars[-1] == " ":
        chars.pop(); idx.pop()
    return "".join(chars), idx


def locate_verbatim(page: str, sentence: str) -> str | None:
    """The page's own characters for `sentence`, or None if it is not there.

    Matching is lenient about case and whitespace - page text arrives with HTML spacing and a
    model may re-wrap it - but what we KEEP is always sliced out of the page. So a lowercased
    or re-spaced copy is accepted and then corrected back to the source, and "verbatim" means
    verbatim no matter what came back. Anything the page does not contain still returns None.
    """
    np, idx = _norm_map(page)
    ns, _ = _norm_map(sentence)
    if not ns:
        return None
    at = np.find(ns)
    if at < 0:
        return None
    lo, hi = idx[at], idx[at + len(ns) - 1] + 1
    # Carry a closing full stop along; a quote cut just before its period reads as truncated.
    if hi < len(page) and page[hi] in ".!?":
        hi += 1
    return page[lo:hi].strip()

def deep_first(cands: list[str]) -> list[str]:
    """Deep pages before homepages, upstream's ordering kept inside each group.

    R3 wants the citation to be the page the sentence appears on, and a homepage almost never
    is - it carries a date in a banner with nothing saying which call it belongs to. Upstream's
    shortlist for CCUS was the abstract page AND the bare root of the same site; taking the
    first candidate that happened to yield a quote would have cited whichever we read first.
    Trying every deep candidate before any homepage costs nothing and removes the coin flip.
    """
    return [u for u in cands if not is_homepage(u)] + [u for u in cands if is_homepage(u)]


_MON = {"jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
        "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
        "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
        "nov": 11, "november": 11, "dec": 12, "december": 12}
_MON_RE = "|".join(sorted(_MON, key=len, reverse=True))
_ORD = r"(?:st|nd|rd|th)?"


def month_day_pairs(text: str) -> set[tuple[int, int]]:
    """Every (month, day) the text mentions, YEAR IGNORED.

    Conference pages write "Closes: May 8th" and "Podium Abstract Submissions Due: Monday,
    September 14". A human reads the year off the page around it; our date matching demanded
    the year be in the same sentence, so seven pages that AGREED with upstream were recorded as
    disagreeing. That is the "Sept." blind spot again one level up - a matcher that only knows
    the renderings its author happened to think of.

    Ignoring the year is safe HERE because the row is already scoped to one edition: the risk
    is a page listing last year's date in the same words, which the plausibility window in
    other_deadline_dates exists to catch downstream.
    """
    out: set[tuple[int, int]] = set()
    t = text.lower()
    for m in re.finditer(rf"\b({_MON_RE})\.?\s+(\d{{1,2}}){_ORD}\b", t):
        out.add((_MON[m.group(1)], int(m.group(2))))
    for m in re.finditer(rf"\b(\d{{1,2}}){_ORD}\s+({_MON_RE})\b", t):
        out.add((_MON[m.group(2)], int(m.group(1))))
    for m in re.finditer(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", t):
        out.add((int(m.group(2)), int(m.group(3))))
    # 9-28-2026 and 9/28/2026 - the hyphen form cost us Pittcon. Also 28.9.2026, which is how
    # most of the world outside the US writes it: embedded world's page says "Abstract
    # Submission: 28.9.2026" for a date upstream gives as 2026-09-28, and reading 28 as the
    # month turned exact agreement into a reported contradiction.
    for m in re.finditer(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\b", t):
        a, b = int(m.group(1)), int(m.group(2))
        if a > 12:                       # 28.9 - only day-first can be meant
            out.add((b, a))
        elif b > 12:                     # 9/28 - only month-first can be meant
            out.add((a, b))
        else:
            # 5/8 is genuinely ambiguous and no amount of staring resolves it. Accept BOTH
            # readings: the cost is a contradiction we fail to report, against a false one we
            # send to upstream. Those are not equally bad.
            out.add((a, b))
            out.add((b, a))
    return out


_LABEL_STOP = {"the", "for", "and", "call", "deadline", "submission", "submissions"}


def verify_call_label(page: str, quote: str, call: str, window: int = 1500) -> str:
    """Keep the model's call label only if the page nearby actually uses those words.

    The label is the one thing the model tells us that is NOT in the quote, so the substring
    check does not cover it - and it is load-bearing. R10 makes a citation call-level: "1 July
    2026" settles nothing, "late-breaking poster deadline: 1 July 2026" settles it. A wrong
    label is worse than none, because it looks like precision.

    So it gets the weaker check available: every meaningful word of the label must appear in
    the page text around the quote. That cannot confirm the label is RIGHT, only that it was
    read rather than assumed. A label that fails falls back to what the quote itself says.
    """
    call = (call or "").strip().lower()
    if not call:
        return ""
    at = page.lower().find(quote.lower()[:60])
    seg, _ = _norm_map(page[max(0, at - window): at + window] if at >= 0 else page)
    words = [w for w in re.split(r"[^a-z0-9]+", call) if len(w) > 3 and w not in _LABEL_STOP]
    if words and all(w in seg for w in words):
        return call
    return _ae.call_label(quote)


OUT_COLUMNS = ["EVENT_ID", "CONFERENCE", "Market", "SUBMISSION DEADLINE", "PREVIOUS_DEADLINE",
               "DATE_CHANGED", "DEADLINE_EVIDENCE_URL", "DEADLINE_QUOTE", "CALL", "IS_PROJECTED",
               "EXTRACTED_FROM", "NOTE"]

# A sentence ends at . ! ? or a line break. Deliberately simple: the aim is a readable,
# verbatim fragment a human can check, not perfect linguistics.
_SENT = re.compile(r"[^.!?\n\r]{0,400}[.!?]?")


def date_forms(d) -> list[str]:
    """The ways a human writes this date. Never the bare day number - matching "4" alone once
    captured "2026 Photo Gallery 2025 Photo Booth" as proof of a February deadline."""
    m = d.strftime("%B")
    # Every abbreviation, not just strftime's. "Sept." is at least as common as "Sep" and %b
    # gives only the latter - AMP's page reads "Closes: 11:59 p.m. ET, Friday, Sept. 4, 2026"
    # and was missed twice: once here, once in verify.find_date. Same bug, two implementations.
    abbrs = {m[:3]}
    if d.month == 9:
        abbrs.add("Sept")
    forms = [f"{m} {d.day}", f"{m} {d.day:02d}", f"{d.day} {m}", d.isoformat()]
    for a in abbrs:
        forms += [f"{a} {d.day}", f"{a}. {d.day}", f"{a} {d.day:02d}", f"{a}. {d.day:02d}",
                  f"{d.day} {a}"]
    # Numeric forms built by hand: "%-m/%-d/%Y" is POSIX-only and raises on Windows.
    forms += [f"{d.month:02d}/{d.day:02d}/{d.year}", f"{d.month}/{d.day}/{d.year}",
              f"{d.day}/{d.month}/{d.year}"]
    return forms


# A period only ends a sentence when what follows looks like a new one. Dates and times are
# full of periods that do not: "Sept. 4", "11:59 p.m. ET", "Jan. 15". Splitting naively turned
# the AMP quote into "SUBMISSION DUE DATE Submission: Sept." - technically verbatim, and
# useless as evidence.
# Only a capital letter followed by a lowercase one starts a new sentence. Allowing a DIGIT
# split "Sept. 4" down the middle - the date became its own boundary and the quote ended
# "...Submission: Sept." Allowing a lone capital splits "11:59 p.m. ET".
_BOUNDARY = re.compile(r"[.!?](?=\s+[A-Z][a-z])|[\n\r]")


def sentence_with(text: str, at: int, width: int = 400) -> str:
    """The sentence around position `at`, trimmed to real boundaries.

    Takes an INDEX rather than searching, because the caller already knows where the hit is.
    Searching again meant slicing the text twice - once by the caller, once here - and the
    second cut landed mid-word: "ECTION PROCESS The Selection Committee will consider...".
    """
    lo, hi = max(0, at - width), min(len(text), at + width)
    seg, pos = text[lo:hi], at - lo
    left, right = 0, len(seg)
    for m in _BOUNDARY.finditer(seg):
        if m.end() <= pos:
            left = m.end()
        elif m.start() > pos:
            right = m.end()
            break
    return " ".join(seg[left:right].split()).strip(" -|")


# Dates that are demonstrably about something other than submitting.
_WRONG_PURPOSE = re.compile(
    r"\b(withdraw|cancel|refund|notification|notified|accept(ance)? letter|registration"
    r"|early[- ]bird|hotel|travel|visa|badge|payment|invoice|onsite)\b", re.I)
# Wording that indicates this sentence is about the act of submitting.
_SUBMIT_VERB = re.compile(
    r"\b(submit|submission|closes?|due|deadline to submit|call for|accepted until)\b", re.I)


SELECT_INSTRUCTION = """You are shown the text of ONE web page and a submission deadline date.
Find the single sentence on that page which states the SUBMISSION deadline for this conference
- the date by which a speaker, author or entrant must submit.

Rules:
1. Copy the sentence EXACTLY as it appears in the page text. Do not fix typos, expand
   abbreviations, reword, or join fragments. It must be a literal substring of the text.
2. It must contain the date given. If the page states that date only for something else -
   withdrawing, notification, registration, hotels, early-bird pricing - return an empty
   sentence. A date used for a different purpose is not this deadline.
3. Prefer a sentence that names WHICH call it belongs to (abstract, full paper, case study,
   poster, workshop). One event runs several with different deadlines, and co-located or
   partner programmes run their own: a page may show "ISE 2027 - Call for Presenters
   Deadline: 2 October" and "CEDIA - Call for Presenters Deadline: 7 September" side by side.
   Both are real. Put the owning call in the "call" field so the two can be told apart.
4. NOMINATION COUNTS AS SUBMITTING. At some events the way onto the programme is to be
   nominated rather than to submit through an open call, and "Nomination Deadline: January 23,
   2026" is then the submission deadline, not a different fact. Treat nominate, apply, propose
   and enter as submitting.
5. If no sentence on this page states that submission deadline, return an empty sentence. An
   honest blank is the correct answer and is always acceptable.

6. Do not renumber or skip: answer for the date given, not the nearest date you can find.

Return ONLY JSON: {"sentence": "...", "call": "...", "confident": true|false}"""


async def llm_pick_sentence(text: str, deadline: str, conference: str,
                            settings) -> tuple[str, str, str]:
    """Ask a model WHICH sentence states the deadline, then check it really is on the page.

    THE SAFETY PROPERTY: the model only ever SELECTS from text we fetched ourselves, and we
    verify its answer is a literal substring of that text. It cannot invent a sentence - if it
    tries, the substring check fails and we discard the answer. That is what makes an LLM safe
    here where it was not safe upstream: upstream was asked to REPORT what a page said, which
    is unverifiable; this is asked to POINT AT something we already hold.

    Judgement is the part string matching cannot do. Five heuristics were tried on the CCUS
    page, which carries 1 July 2026 as a submission deadline, as a withdrawal deadline, and
    inside a formatting paragraph; each picked a different sentence and two were about the
    wrong thing.

    Returns (quote, call, status). Status separates "the model answered no" from "the model
    did not answer", because those deserve opposite treatment: a considered blank is a result
    and must stand, while an outage should fall back to the heuristic.
    """
    try:
        import litellm
    except Exception:
        return "", "", "unavailable"

    body = text[:16000]
    messages = [
        {"role": "system", "content": SELECT_INSTRUCTION},
        {"role": "user", "content": "\n".join(
            [f"CONFERENCE: {conference}", f"DEADLINE: {deadline}", "", "PAGE TEXT:", body,
             "", "Return ONLY the JSON object."])},
    ]
    if settings.llm_proxy_url:
        kwargs = dict(model="openai/cfp-extract", messages=messages,
                      api_base=settings.llm_proxy_url.rstrip("/") + "/v1",
                      api_key=settings.license_key,
                      extra_headers={"X-Client-Version": settings.client_version},
                      temperature=0.0, max_tokens=400)
    else:
        kwargs = dict(model=settings.llm_provider, messages=messages,
                      api_key=settings.provider_key(), temperature=0.0, max_tokens=400)
    try:
        try:
            resp = await litellm.acompletion(**kwargs, response_format={"type": "json_object"})
        except Exception:
            resp = await litellm.acompletion(**kwargs)
        raw = resp.choices[0].message.content or ""
    except Exception:
        return "", "", "unavailable"

    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return "", "", "unavailable"
    try:
        data = json.loads(m.group(0))
    except Exception:
        return "", "", "unavailable"
    sentence = " ".join((data.get("sentence") or "").split())
    call = (data.get("call") or "").strip().lower()
    if not sentence:
        return "", "", "blank"

    # THE CHECK THAT MAKES THIS SAFE. If a model ever composes a plausible sentence instead of
    # copying one - the exact failure that cost two upstream pilots - it dies here rather than
    # reaching a customer. What survives is re-cut from the page, so the stored quote is the
    # page's characters and not the model's rendering of them.
    found = locate_verbatim(text, sentence)
    if found is None:
        return "", "", "not-on-page"
    sentence = found
    # PURPOSE BEFORE DATE. NAMM's page says "you will be notified ... by October 30, 2026" - a
    # real date about a different fact. Testing the date first labelled that a contradiction
    # with the submission deadline when it is not about submitting at all.
    if _WRONG_PURPOSE.search(sentence):
        # Belt and braces on rule 2. The model is asked to refuse these; if it does not, the
        # regex still catches the ones we can name.
        return "", "", "wrong-purpose"

    d = _parse_date(deadline or "")
    if not d:
        # NO TARGET, NO CITATION. Every check below compares the sentence against this date, so
        # a deadline we cannot read turns all of them into no-ops and the first plausible
        # sentence on the page becomes evidence. Found 2026-08-11: upstream sent
        # SUBMISSION DEADLINE = "The Call for Speakers for All-Energy show floor theatres is
        # now closed." - prose in a date column - and "Our keynote stage returns for a fifth
        # year." was accepted as its citation. A guard that only works on well-formed input is
        # not a guard.
        return "", "", "unparseable-target"

    pairs = month_day_pairs(sentence)
    if (d.month, d.day) not in pairs:
        if pairs:
            # A DIFFERENT date for the thing we asked about: a CONTRADICTION, not an absence,
            # and the most valuable thing this pipeline finds. The sentence comes back so it
            # can be reported; callers gate on status, so it can never become a citation.
            return sentence, "", "no-date"
        # No date at all. RSNA's "all abstracts must be submitted online by the posted
        # deadlines" is true, verbatim, and settles nothing. Silence, not disagreement -
        # calling it a contradiction would manufacture a finding out of a vague sentence.
        return "", "", "undated"
    return sentence, verify_call_label(text, sentence, call) or _ae.call_label(sentence), "ok"


def best_quote(text: str, deadline: str) -> tuple[str, str]:
    """(quote, call_label). Prefers a sentence that names the call."""
    d = _parse_date(deadline or "")
    if not d:
        return "", ""
    # Look at EVERY occurrence of every rendering, not just the first. A page states its dates
    # in several places - a summary table, a paragraph, a sidebar - and only one of them tends
    # to name the call. Taking the first hit gave "SUBMISSION DUE DATE Submission: Sept." when
    # the usable sentence, further down, was "Case Study Submission Closes: ... Sept. 4, 2026."
    hits: list[str] = []
    low = text.lower()
    for form in [f for f in date_forms(d) if f]:
        start = 0
        while True:
            i = low.find(form.lower(), start)
            if i < 0:
                break
            q = sentence_with(text, i)
            # THE QUOTE MUST CONTAIN THE DATE. Boundary-trimming can cut it off, and a
            # navigation blob can carry the label without the date at all - both produce a
            # confident-looking sentence that proves nothing. This is the one property the
            # quote exists to have, so it is checked rather than assumed.
            if q and form.lower() in q.lower() and q not in hits:
                hits.append(q)
            start = i + 1
    if not hits:
        return "", ""
    # The same date often appears on a page for a DIFFERENT purpose. CCUS states 1 July 2026 as
    # "the deadline to withdraw your presentation" - a real sentence, verbatim, containing the
    # right date, and the wrong fact entirely. Drop the ones we can recognise as not-a-submission.
    hits = [q for q in hits if not _WRONG_PURPOSE.search(q)] or hits

    # A sentence naming the call beats one that only carries the date (R10). Among those,
    # prefer one that also uses submission wording, then the shortest - a tight
    # "Case Study Submission Closes: ... Sept. 4, 2026" beats a run of menu items.
    def rank(q: str) -> tuple:
        return (0 if _SUBMIT_VERB.search(q) else 1, len(q))

    labelled = sorted((q for q in hits if _ae.call_label(q)), key=rank)
    q = labelled[0] if labelled else min(hits, key=rank)
    return q, _ae.call_label(q)


async def fill_row(rec: dict, cands: list[str], pages: dict[str, str],
                   use_llm: bool, stats: dict) -> None:
    """Take the first candidate page that yields a usable quote, and record how we got it."""
    tried = 0
    contra: tuple[str, str] | None = None      # (url, sentence stating a different date)
    for u in deep_first(cands):
        text = pages.get(u)
        if not text:
            continue
        tried += 1
        quote = call = how = ""
        status = "off"
        if use_llm:
            quote, call, status = await llm_pick_sentence(
                text, rec["SUBMISSION DEADLINE"], rec["CONFERENCE"], SETTINGS)
            stats[status] = stats.get(status, 0) + 1
            # GATE ON STATUS, NOT ON TRUTHINESS. no-date now returns its sentence so the
            # contradiction can be reported, and `if quote:` would have promoted a sentence
            # carrying the WRONG date into a citation.
            if status == "ok" and quote:
                how = "llm"
            else:
                if status == "no-date" and quote and contra is None:
                    contra = (u, quote)
                quote, call = "", ""
        # Fall back ONLY when the model did not answer. A considered blank is a result: it
        # means the date is on the page for something other than submitting, which is exactly
        # the judgement we brought it in to make. Re-running the heuristic there would
        # reinstate the sentence the model just rejected and quietly overrule it.
        if not quote and status in ("off", "unavailable"):
            quote, call = best_quote(text, rec["SUBMISSION DEADLINE"])
            if quote:
                how = "heuristic"
        if quote:
            rec.update({"DEADLINE_EVIDENCE_URL": u, "DEADLINE_QUOTE": quote,
                        "CALL": call, "IS_PROJECTED": "false",
                        "EXTRACTED_FROM": (f"candidate {cands.index(u) + 1} of {len(cands)}"
                                           f"; selected by {how}")})
            if is_homepage(u):
                # Say so rather than hide it. The quote is real, but a homepage cannot show
                # WHICH call the date belongs to, and the merge guard will not let it displace
                # a deeper citation we already hold.
                rec["NOTE"] = "homepage - no deeper candidate carried the date"
            return
    if contra:
        # Deliberately leaves the citation fields BLANK. A sentence that disagrees with the
        # claimed date is evidence the date is wrong, not evidence for a new one - taking it as
        # a citation would silently move a customer-facing deadline on a model's say-so.
        # It goes back to upstream as a question (contract 2.5: decline rather than guess).
        url, sentence = contra
        others = other_deadline_dates(sentence) or ["unclear"]
        rec["NOTE"] = (f"CONTRADICTION - page states {', '.join(others[:2])}, "
                       f"not {rec['SUBMISSION DEADLINE']}: \"{sentence[:180]}\" <- {url}")
    elif tried:
        rec["NOTE"] = ("no sentence on the candidate pages states that submission deadline"
                       if use_llm else "none of the candidate pages state that date")
    else:
        rec["NOTE"] = "no candidate page could be read"


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract citations from candidate URLs.")
    ap.add_argument("-i", "--input", required=True)
    ap.add_argument("-o", "--output", default="citations_extracted.csv")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--no-llm", action="store_true",
                    help="string matching only. Faster and free, but cannot tell a submission "
                         "deadline from a withdrawal deadline on the same date.")
    a = ap.parse_args()
    use_llm = not a.no_llm
    stats: dict[str, int] = {}

    with open(a.input, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if a.limit:
        rows = rows[:a.limit]

    # Pass 1 cheap, pass 2 browser - the same economics as the auditor. Collect every candidate
    # first so one browser session covers all of them.
    wanted: list[str] = []
    for r in rows:
        for u in (r.get("CANDIDATE_URLS") or "").split("|"):
            u = u.strip()
            if u.startswith("http") and u not in wanted:
                wanted.append(u)

    print(f"{len(rows)} row(s), {len(wanted)} distinct candidate URL(s)\n")
    pages: dict[str, str] = {}
    unread: list[str] = []
    for u in wanted:
        t, _ = fetch_text(u)
        ok, _why = _ae.readable(t)
        if ok:
            pages[u] = t
        else:
            unread.append(u)
    if unread:
        print(f"--- escalating {len(unread)} page(s) through the browser ---")
        for u, (t, _via) in asyncio.run(_ae.escalate(unread)).items():
            ok, _why = _ae.readable(t)
            if ok:
                pages[u] = t

    out = []
    for r in rows:
        rec = {k: (r.get(k) or "") for k in
               ("EVENT_ID", "CONFERENCE", "Market", "SUBMISSION DEADLINE",
                "PREVIOUS_DEADLINE", "DATE_CHANGED")}
        rec.update({"DEADLINE_EVIDENCE_URL": "", "DEADLINE_QUOTE": "", "CALL": "",
                    "IS_PROJECTED": "true", "EXTRACTED_FROM": "", "NOTE": ""})
        cands = [u.strip() for u in (r.get("CANDIDATE_URLS") or "").split("|") if u.strip()]
        if not cands:
            rec["NOTE"] = "no candidate URLs supplied"
            out.append(rec); continue

        asyncio.run(fill_row(rec, cands, pages, use_llm, stats))
        out.append(rec)

    with open(a.output, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_COLUMNS)
        w.writeheader()
        w.writerows(out)

    got = [r for r in out if r["DEADLINE_EVIDENCE_URL"]]
    named = [r for r in got if r["CALL"]]
    print(f"\n{len(got)} of {len(out)} extracted; {len(named)} name the call\n")
    if stats:
        # Worth printing every time. "not-on-page" is the count of sentences a model composed
        # rather than copied - the number that has to stay at zero in what we ship, and the
        # only direct measure we have of whether the substring check is earning its place.
        order = ["ok", "blank", "undated", "wrong-purpose", "no-date", "not-on-page",
                 "unavailable"]
        line = "  ".join(f"{k}={stats[k]}" for k in order if k in stats)
        print(f"  model calls: {line}\n")
    for r in out:
        if r["DEADLINE_EVIDENCE_URL"]:
            print(f"  OK   {r['CONFERENCE'][:44]:<44} [{r['CALL'] or 'no label'}]")
            print(f"         {r['DEADLINE_EVIDENCE_URL'][:74]}")
            print(f"         \"{r['DEADLINE_QUOTE'][:88]}\"")
        else:
            print(f"  --   {r['CONFERENCE'][:44]:<44} {r['NOTE']}")
    print(f"\nwrote {a.output}")
    print("Feed it to: apply_resolutions.py --citations <file>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
