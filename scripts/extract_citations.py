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

WHAT THIS CANNOT DO, AND WHY IT MATTERS
It guarantees the date is on the page. It does NOT reliably pick WHICH dated sentence is the
submission deadline, because that is a semantic judgement and this is string matching.

Measured on the 2026-08-11 pilot. CCUS states 1 July 2026 in at least three places: as a
submission deadline, as "the deadline to withdraw your presentation", and inside a paragraph
about abstract formatting. Five selection strategies were tried - first hit, longest, shortest,
label-preferring, and submission-wording-preferring - and each picked a different sentence.
Two of them were verbatim, contained the right date, and stated the wrong fact.

So the guarantee here is narrow and worth stating plainly: **the date is on the page, and the
quote is verbatim.** Whether the sentence describes the submission deadline still needs a
human, or an LLM reading the page text we fetched - which cannot fabricate, because the text
is real and any selection can be checked as a substring of it.

Emits the same shape the merge guard already accepts, so the output flows straight into
`apply_resolutions.py --citations`.

    python scripts/extract_citations.py -i candidate_urls.csv -o citations_extracted.csv
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("_ae", ROOT / "scripts" / "audit_evidence.py")
_ae = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ae)          # escalate / call_label / readable

from src.cfp_monitor.verify import _parse_date, fetch_text          # noqa: E402

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


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract citations from candidate URLs.")
    ap.add_argument("-i", "--input", required=True)
    ap.add_argument("-o", "--output", default="citations_extracted.csv")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()

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

        tried = 0
        for u in cands:
            text = pages.get(u)
            if not text:
                continue
            tried += 1
            quote, call = best_quote(text, rec["SUBMISSION DEADLINE"])
            if quote:
                rec.update({"DEADLINE_EVIDENCE_URL": u, "DEADLINE_QUOTE": quote,
                            "CALL": call, "IS_PROJECTED": "false",
                            "EXTRACTED_FROM": f"candidate {cands.index(u) + 1} of {len(cands)}"})
                break
        if not rec["DEADLINE_EVIDENCE_URL"]:
            rec["NOTE"] = ("none of the candidate pages state that date"
                           if tried else "no candidate page could be read")
        out.append(rec)

    with open(a.output, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_COLUMNS)
        w.writeheader()
        w.writerows(out)

    got = [r for r in out if r["DEADLINE_EVIDENCE_URL"]]
    named = [r for r in got if r["CALL"]]
    print(f"\n{len(got)} of {len(out)} extracted; {len(named)} name the call\n")
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
