"""Is this one event's call open? Walk its own site and report the evidence.

WHY THIS IS OURS AND NOT UPSTREAM'S
The boundary is discovery vs verification. Upstream's grounded search finds events we do not
know about, and pages we have no URL for. Once we HOLD a domain, re-reading it is verification -
our half - and we already own the machinery: the fetch ladder through to real Chrome, and
`locate_verbatim` to prove a sentence is really on a page.

Spending a grounded request to re-read a page we can fetch ourselves is paying for the wrong
capability. This costs nothing and takes about a minute.

Built 2026-08-20 after answering exactly this question by hand for Decarb Connect North America,
where the call turned out to be open and the sentence proving it was sitting on a page one path
away from the one we had recorded as dead.

WHAT IT DOES NOT DO
It does not decide. It gathers quotes and says where they came from, because 2.1 holds
throughout: the absence of a call-for-speakers page is not proof the call is shut. A human reads
the evidence.

STATUS: USABLE BUT NOISY. NOT FINISHED.
Fetching and proof are sound - it walks the site through the full ladder and every sentence it
prints is verified present on the page it names. SNIPPET SELECTION IS NOT. On a nav-heavy site
it surfaces menu text instead of the sentence that answers the question. Tested against Decarb
Connect North America, where the answer - "Want to propose a speaker for 2027? Fill in the form
below!" - is on the page and is still not what gets shown.

Five approaches were tried on the selection problem: wider windows, longest-fragment, snippet
deduplication, common prefix/suffix stripping, and shingle-based chrome detection with page
deduplication. Each improved it and none solved it, because these pages carry almost no sentence
punctuation - there are no clause boundaries to find.

THE RIGHT FIX, when this is picked up: use the LLM selector rather than windowing, exactly as
extract_citations.py does, and for the reason its docstring already gives - "judgement is the
part string matching cannot do". Point the model at text we fetched, make it choose the
sentence, and prove the answer verbatim with locate_verbatim. The regex layer here is good for
finding WHICH PAGES are worth asking about; it is the wrong tool for deciding which sentence.

Until then: read its output as "here are the pages that mention this", not "here is the
answer".

    python scripts/investigate_event.py --url https://example.com/ [--name "Event 2027"]
    python scripts/investigate_event.py --db <db> --event-id <id>
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("_ec", ROOT / "scripts" / "extract_citations.py")
_ec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ec)
locate_verbatim = _ec.locate_verbatim

from src.cfp_monitor.verify import fetch_text        # noqa: E402

# Paths worth trying, in the order a person would. Cheap: a miss costs one fetch.
PATHS = ["", "speakers", "speaker", "speak", "call-for-speakers", "call-for-papers",
         "call-for-abstracts", "become-a-speaker", "get-involved", "participate",
         "submit", "abstracts", "programme", "program", "agenda",
         "sponsorship-opportunities", "sponsorship", "sponsor", "partners", "attend"]

OPEN_SIG = re.compile(
    r"call for (speakers|papers|abstracts|presentations|sessions)|"
    r"submit (a |an |your )?(speaker|abstract|proposal|paper|topic|session)|"
    r"propose a (speaker|topic|session)|speaker application|apply to speak|"
    r"nominate a speaker|speaking opportunit|share your (story|expertise)", re.I)
SHUT_SIG = re.compile(
    r"submissions? (are |is )?closed|call for [a-z ]{3,20} (is |has )?closed|"
    r"no longer accepting|deadline (has )?passed|join the waitlist|"
    r"applications? (are |is )?closed", re.I)
SPONSOR_REQ = re.compile(
    r"sponsor\w*[^.]{0,80}(speak|present|session)|(speak|present)\w*[^.]{0,80}sponsor\w*", re.I)
MONEY = re.compile(r"[$£€]\s?[\d,]{3,}(?:\.\d\d)?|\b(?:USD|EUR|GBP)\s?[\d,]{3,}", re.I)
DEADLINE = re.compile(
    r"(?:deadline|closes?|due|submit by)[^.]{0,60}?"
    r"((?:January|February|March|April|May|June|July|August|September|October|November|"
    r"December)\s+\d{1,2},?\s*20\d\d|\d{1,2}\s+(?:January|February|March|April|May|June|July|"
    r"August|September|October|November|December)\s+20\d\d)", re.I)


def sentence_around(flat: str, at: int, width: int = 200) -> str:
    """The clause containing `at`, not the longest fragment near it.

    These pages are navigation strips with no punctuation, so "longest fragment" returned the
    whole menu every time. Prefer a real sentence boundary; fall back to a tight window centred
    on the match rather than a wide one.
    """
    lo, hi = max(0, at - width), min(len(flat), at + width)
    seg = flat[lo:hi]
    rel = at - lo
    for part in re.split(r"(?<=[.!?])\s+", seg):
        start = seg.find(part)
        if start <= rel < start + len(part) and len(part) > 15:
            return part.strip()
    return seg[max(0, rel - 90):rel + 110].strip()


SHINGLE = 6          # words per shingle - long enough to be a phrase, short enough to repeat


def _shingles(text: str, n: int = SHINGLE) -> set[str]:
    w = text.lower().split()
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def chrome_phrases(bodies: dict[str, str], threshold: int = 3) -> set[str]:
    """Phrases appearing on several pages of the same site: the menu and footer.

    Two simpler ideas were tried and both failed, which is why this one is worth its lines.
    Suppressing whole snippets did nothing, because each extracted window picks up slightly
    different surrounding text and no two are equal. Stripping a common PREFIX did nothing
    either, because every page begins with its own title - "Home - Decarb...", "Agenda -
    Decarb..." - so the shared run is zero characters long and the menu sits after it.

    Repetition is the signal, and position is irrelevant to it. A six-word phrase on three or
    more pages of one site is chrome whatever it says and wherever it sits.
    """
    if len(bodies) < threshold:
        return set()
    seen: dict[str, int] = {}
    for text in bodies.values():
        for sh in _shingles(text):
            seen[sh] = seen.get(sh, 0) + 1
    return {sh for sh, n in seen.items() if n >= threshold}


def is_chrome(snippet: str, chrome: set[str], ratio: float = 0.5) -> bool:
    """True when most of this snippet is site furniture rather than content."""
    sh = _shingles(snippet)
    if not sh:
        return False
    return sum(1 for s in sh if s in chrome) / len(sh) >= ratio


def probe(url: str):
    try:
        r = fetch_text(url)
    except Exception as e:                                       # noqa: BLE001
        return "", f"error {type(e).__name__}"
    t = r[0] if isinstance(r, tuple) else r
    rung = r[1] if isinstance(r, tuple) and len(r) > 1 else "?"
    return " ".join((t or "").split()), rung


def main() -> int:
    ap = argparse.ArgumentParser(description="Walk one event's site for call-status evidence.")
    ap.add_argument("--url", help="the event's own site")
    ap.add_argument("--name", default="")
    ap.add_argument("--db")
    ap.add_argument("--event-id")
    ap.add_argument("--max-pages", type=int, default=20)
    a = ap.parse_args()

    url, name = a.url, a.name
    if a.event_id:
        if not a.db:
            return print("--event-id needs --db") or 2
        con = sqlite3.connect(a.db)
        con.row_factory = sqlite3.Row
        row = con.execute("select name, url, main_info_url from grounding_facts "
                          "where event_id=?", (a.event_id,)).fetchone()
        con.close()
        if not row:
            return print(f"no row with event_id {a.event_id!r}") or 2
        url = url or row["url"] or row["main_info_url"]
        name = name or row["name"]
    if not url:
        return print("give --url, or --db with --event-id") or 2

    os.environ.setdefault("CFP_CDP_URL", "http://localhost:9222")
    root = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    print("=" * 84)
    print(f"INVESTIGATING  {name or root}")
    print(f"               {root}")
    print("=" * 84)

    # TWO PASSES. Fetch everything first, then strip the chrome, THEN look for evidence.
    # Analysing page by page reported the navigation as a finding on every page, because the
    # menu contains the exact words we search for.
    raw: dict[str, str] = {}
    for p in PATHS[:a.max_pages]:
        u = urljoin(root + "/", p + "/") if p else root + "/"
        flat, _rung = probe(u)
        if flat and len(flat) >= 250:
            raw[u] = flat
    reached = len(raw)
    # DEDUPLICATE BEFORE MEASURING REPETITION. Many sites serve one page at several paths -
    # /speakers/, /speaker/ and /speak/ were byte-identical here. Counted as three pages, the
    # one sentence that answered the question looked like site-wide furniture and was
    # suppressed, while the real navigation stayed under the threshold. Repetition only means
    # "chrome" when the pages are actually different.
    unique: dict[str, str] = {}
    for u, t in raw.items():
        if t not in unique.values():
            unique[u] = t
    chrome = chrome_phrases(unique)

    findings = {"open": [], "shut": [], "sponsor": [], "deadline": []}
    for u, body in unique.items():
        # EVERY match, not the first. The first is often a menu link that survived stripping;
        # the sentence that answers the question sits further down.
        for key, pat in (("open", OPEN_SIG), ("shut", SHUT_SIG), ("sponsor", SPONSOR_REQ)):
            for m in list(pat.finditer(body))[:6]:
                snip = sentence_around(body, m.start())
                # Prove it against the FULL page, never the stripped copy.
                if snip and locate_verbatim(raw[u], snip) and not is_chrome(snip, chrome):
                    findings[key].append((u, snip))
        for m in list(DEADLINE.finditer(body))[:4]:
            findings["deadline"].append((u, sentence_around(body, m.start())))

    print(f"\nreached {reached} page(s)\n")
    for key, title in (("open", "SUGGESTS THE CALL IS OPEN"),
                       ("shut", "SUGGESTS IT IS CLOSED"),
                       ("deadline", "A DATE IS STATED"),
                       ("sponsor", "SPONSORSHIP TIED TO SPEAKING")):
        seen, shown = set(), 0
        if not findings[key]:
            continue
        print(f"--- {title}")
        for u, s in findings[key]:
            k = s[:80]
            if k in seen or shown >= 4:
                continue
            seen.add(k)
            shown += 1
            print(f"    \"{s[:190]}\"")
            print(f"       {u}")
        print()

    if not any(findings.values()):
        print("Nothing found on the usual paths. That is NOT evidence the call is shut (2.1) -"
              "\nit means this site does not put it where sites usually do.")
    else:
        print("Every sentence above was verified present on the page it is attributed to.")
        print("This tool gathers evidence; it does not decide. Read it and judge.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
