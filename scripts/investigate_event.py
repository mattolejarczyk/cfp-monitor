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

TWO PASSES, RUN BLIND, THEN COMPARED

  pass 1  regex   cheap and deterministic. Decides which pages are worth a model call, and
                  offers a candidate sentence of its own.
  pass 2  model   reads the pages pass 1 flagged and answers the open question independently.
                  Its answer must be a literal substring of the page (locate_verbatim) or it
                  is discarded, so it can choose a wrong sentence but never invent one.

The passes DO NOT SEE EACH OTHER. Showing the model the regex answer and asking "is this
right?" buys agreement bias, not confirmation - a call spent ratifying our own error.

Agreement raises confidence. Disagreement is a finding, not noise. A scorecard records which
pass answered, because that is the only way to know whether the cheap pass earns its place.

MEASUREMENT ACROSS SIX SITES, 2026-08-20 (Decarb Connect, Carbon Capture Tech Expo, embedded
world, ProMat, International Biomass, PCIM Expo):

    both agreed 7 | disagreed 3 | MODEL ONLY 0 | regex only 5

Read it in two halves. Where the regex pass had an opinion the model shared, it was right 7
times out of 10 - so it is not worthless as an opinion, which the single-site run suggested.
But MODEL ONLY IS ZERO: across six sites there was not one page where the model found the
answer and the regex pass had flagged nothing. Every regex-only hit was still navigation.

So the regex pass is doing its real job - triage - flawlessly, and its candidates are a
sometimes-right second opinion. Keep both, keep reporting both, and revisit if model-only ever
becomes non-zero: that is the number that would prove triage is dropping pages on the floor.

Use the disagreements to improve the regex BY HAND, not automatically: once the cheap pass is
trained on the expensive one, their agreement stops being independent confirmation.

TWO FAILURES THAT ARE NOT "NO FINDINGS", AND ARE REPORTED SEPARATELY
    dead site        no address returns anything. International Biomass. The row needs a new
                     URL; the run says nothing about the call.
    catch-all route  every address returns the SAME page. ProMat. The sections exist but are
                     behind JavaScript, so walking paths cannot reach them.
Both look identical to "we read the site and it says nothing" unless you say so out loud, and
that is exactly the confusion 2.1 exists to prevent.

    python scripts/investigate_event.py --url https://example.com/ [--name "Event 2027"]
    python scripts/investigate_event.py --db <db> --event-id <id>
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import re
import sqlite3
import ssl
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("_ec", ROOT / "scripts" / "extract_citations.py")
_ec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ec)
locate_verbatim = _ec.locate_verbatim

from src.cfp_monitor.config import Settings         # noqa: E402
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


ASK = """You are shown the text of ONE page from a conference website.

Decide whether the page shows that the CALL FOR SPEAKERS (or papers, abstracts, presentations)
is OPEN, CLOSED, or whether the page does not say.

Return ONE sentence COPIED EXACTLY from the page that shows it. Rules:
- Copy character for character. Do not paraphrase, summarise or join fragments.
- Ignore navigation menus and link labels. A menu item reading "Speakers" or "Join the
  Waitlist" says nothing about whether the call is open.
- A list of who spoke last year is not a call. Neither is a registration or ticket deadline.
- If the page does not address it, return an empty sentence. That is a valid answer.

Return ONLY JSON: {"sentence": "...", "verdict": "open" | "closed" | "unclear"}"""


async def llm_read_page(text: str, conference: str, settings) -> tuple[str, str, str]:
    """Ask the model what the page says about the call, then prove the answer is on it.

    Its own prompt, deliberately, rather than calling extract_citations. That selector needs a
    KNOWN DEADLINE and asks "which sentence states this date" - a closed question. This is an
    open one: "is the call open, and where does it say so". Same guarantee, different question.
    What IS shared is locate_verbatim, which is the part that must never diverge.

    Returns (quote, verdict, status). `status` separates a considered blank from an outage.
    """
    try:
        import litellm
    except Exception:
        return "", "", "unavailable"
    messages = [{"role": "system", "content": ASK},
                {"role": "user", "content": "\n".join(
                    [f"CONFERENCE: {conference}", "", "PAGE TEXT:", text[:16000], "",
                     "Return ONLY the JSON object."])}]
    if settings.llm_proxy_url:
        kw = dict(model="openai/cfp-extract", messages=messages,
                  api_base=settings.llm_proxy_url.rstrip("/") + "/v1",
                  api_key=settings.license_key,
                  extra_headers={"X-Client-Version": settings.client_version},
                  temperature=0.0, max_tokens=400)
    else:
        kw = dict(model=settings.llm_provider, messages=messages,
                  api_key=settings.provider_key(), temperature=0.0, max_tokens=400)
    try:
        try:
            r = await litellm.acompletion(**kw, response_format={"type": "json_object"})
        except Exception:
            r = await litellm.acompletion(**kw)
        raw = r.choices[0].message.content or ""
    except Exception:
        return "", "", "unavailable"
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return "", "", "unavailable"
    try:
        d = json.loads(m.group(0))
    except Exception:
        return "", "", "unavailable"
    sent = " ".join((d.get("sentence") or "").split())
    verdict = (d.get("verdict") or "unclear").strip().lower()
    if not sent:
        return "", verdict, "blank"
    found = locate_verbatim(text, sent)
    if found is None:
        return "", verdict, "not-on-page"
    return found, verdict, "ok"


def agrees(a: str, b: str) -> bool:
    """Do the two passes point at the same thing? Overlap of content words, not equality.

    The passes see the page differently - one windows around a match, the other picks a
    sentence - so identical strings are not the test. Half the content words in common means
    they found the same statement.
    """
    wa = {w for w in re.findall(r"[a-z0-9]+", a.lower()) if len(w) > 3}
    wb = {w for w in re.findall(r"[a-z0-9]+", b.lower()) if len(w) > 3}
    if not wa or not wb:
        return False
    return len(wa & wb) / min(len(wa), len(wb)) >= 0.5


LINK_WORTH = re.compile(
    r"speak|paper|abstract|call[-_ ]?for|submit|present|programme|program|agenda|session|"
    r"sponsor|partner|participat|get[-_ ]?involved|cfp", re.I)
SKIP_LINK = re.compile(r"\.(pdf|jpg|jpeg|png|gif|svg|zip|ics|mp4)($|\?)|mailto:|tel:|"
                       r"linkedin|twitter|facebook|instagram|youtube", re.I)


def discover_links(root: str, limit: int = 14) -> list[str]:
    """Read the homepage's own links instead of guessing at paths.

    Guessing was the weak link. embedded world reached 3 of 20 guessed paths and PCIM reached
    1, because real sites use /en/programme/ or /conference/call-for-papers rather than the
    tidy /speakers/ a guesser tries. The site already lists its own structure in its menu.

    Deliberately a plain HTTP fetch rather than the ladder: we only need hrefs, and the ladder
    strips tags. Content still goes through the ladder afterwards.

    Returns same-host URLs whose href or anchor text suggests a call, best first.
    """
    try:
        req = urllib.request.Request(root, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=20, context=ssl._create_unverified_context()) as r:
            html = r.read(900_000).decode("utf-8", "ignore")
    except Exception:
        return []

    host = urlparse(root).netloc.lower()
    scored: dict[str, int] = {}
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html,
                         re.I | re.S):
        href, label = m.group(1), re.sub(r"<[^>]+>", " ", m.group(2))
        if SKIP_LINK.search(href):
            continue
        full = urljoin(root, href.strip())
        if urlparse(full).netloc.lower() != host or full.rstrip("/") == root.rstrip("/"):
            continue
        full = full.split("#")[0]
        # Anchor text is the better signal - a menu reading "Call for Papers" pointing at
        # /conference/2027/ would be missed by looking at the path alone.
        score = (2 if LINK_WORTH.search(label) else 0) + (1 if LINK_WORTH.search(href) else 0)
        if score:
            scored[full] = max(scored.get(full, 0), score)
    return [u for u, _ in sorted(scored.items(), key=lambda kv: -kv[1])][:limit]


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
    ap.add_argument("--max-llm", type=int, default=6,
                    help="ceiling on model calls per event - a spike means a data "
                         "problem, not a site with forty speaker pages")
    ap.add_argument("--no-llm", action="store_true",
                    help="regex only. Faster and free, but it is the pass that "
                         "reports navigation as evidence - read the output knowing that.")
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
    # THE SITE'S OWN LINKS BEAT OUR GUESSES. Guessed paths reached 3 of 20 on embedded world
    # and 1 of 20 on PCIM, because real sites use /en/programme/ and /conference/call-for-papers
    # rather than the tidy /speakers/ a guesser tries. Fall back to guessing only when the menu
    # yields nothing - a JavaScript-rendered nav has no hrefs to read.
    found_links = discover_links(root, limit=a.max_pages)
    targets = [root + "/"] + found_links
    if len(found_links) < 3:
        targets += [urljoin(root + "/", p + "/") for p in PATHS if p]
    seen_u: set[str] = set()

    raw: dict[str, str] = {}
    for u in targets[:a.max_pages + 1]:
        if u in seen_u:
            continue
        seen_u.add(u)
        flat, _rung = probe(u)
        if flat and len(flat) >= 250:
            raw[u] = flat
    reached = len(raw)
    how = (f"{len(found_links)} link(s) from the menu"
           if len(found_links) >= 3 else "guessed paths - the menu gave us nothing to follow")

    # A DEAD SITE AND AN UNINFORMATIVE ONE MUST NOT LOOK THE SAME. Reporting "no findings" for
    # a domain that no longer resolves reads exactly like "we looked and it says nothing",
    # which is the confusion 2.1 exists to prevent.
    if reached == 0:
        print(f"\nNo page on {root} could be read at all - not one of "
              f"{len(seen_u)} address(es) returned content.")
        print("That is a DEAD OR UNREACHABLE SITE, not an event with nothing to say. It tells")
        print("you nothing about whether the call is open, and the row needs a new URL.")
        return 0
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

    # CATCH-ALL ROUTING. ProMat returned the SAME page for all 20 addresses - twenty fetches
    # spent to read one page, and nothing said so. Saying it matters: the answer may exist
    # behind JavaScript navigation this approach cannot reach, which is a different problem
    # from the site having no call.
    if reached >= 4 and len(unique) == 1:
        print(f"\nAll {reached} addresses returned the SAME page. This site routes everything to "
              f"one place,\nso walking paths cannot reach its sections - they are probably behind "
              f"JavaScript.\nWhatever is below is from that single page; absence here proves "
              f"nothing (2.1).\n")

    # ---- PASS 1: regex. Cheap, deterministic, and it also decides which pages are worth
    # spending a model call on. It offers a candidate; it does not get the last word.
    regex_pick: dict[str, tuple[str, str]] = {}          # url -> (snippet, kind)
    interesting: list[str] = []
    deadlines: list[tuple[str, str]] = []
    for u, body in unique.items():
        best = None
        for kind, pat in (("open", OPEN_SIG), ("shut", SHUT_SIG)):
            for m in list(pat.finditer(body))[:6]:
                snip = sentence_around(body, m.start())
                if snip and locate_verbatim(raw[u], snip) and not is_chrome(snip, chrome):
                    best = best or (snip, kind)
        if best:
            regex_pick[u] = best
        if best or SPONSOR_REQ.search(body) or DEADLINE.search(body):
            interesting.append(u)
        for m in list(DEADLINE.finditer(body))[:3]:
            deadlines.append((u, sentence_around(body, m.start())))

    # ---- PASS 2: the model, on the pages pass 1 flagged as worth reading.
    # DELIBERATELY BLIND TO PASS 1. Showing it the regex answer and asking "is this right?"
    # buys agreement bias, not confirmation - you spend a call to ratify your own error.
    llm_pick: dict[str, tuple[str, str, str]] = {}       # url -> (quote, verdict, status)
    if not a.no_llm and interesting:
        settings = Settings()

        async def _all():
            for u in interesting[:a.max_llm]:
                llm_pick[u] = await llm_read_page(unique[u], name or root, settings)

        asyncio.run(_all())

    # ---- COMPARE. Agreement is confirmation; disagreement is a finding in itself.
    print(f"\nreached {reached} page(s) via {how}, {len(unique)} distinct; "
          f"regex flagged {len(interesting)}, model read {len(llm_pick)}\n")

    agreed = differed = only_llm = only_regex = 0
    for u in sorted(set(regex_pick) | set(llm_pick)):
        r_snip, r_kind = regex_pick.get(u, ("", ""))
        l_quote, l_verdict, l_status = llm_pick.get(u, ("", "", "skipped"))
        if r_snip and l_quote:
            same = agrees(r_snip, l_quote)
            agreed += same
            differed += not same
            tag = "BOTH AGREE" if same else "PASSES DISAGREE"
        elif l_quote:
            only_llm += 1
            tag = "MODEL ONLY (regex missed it)"
        elif r_snip:
            only_regex += 1
            tag = "REGEX ONLY (model saw nothing)"
        else:
            continue
        print(f"--- {tag}   {u}")
        if l_quote:
            print(f"    model  [{l_verdict}] \"{l_quote[:180]}\"")
        if r_snip:
            print(f"    regex  [{r_kind}] \"{r_snip[:180]}\"")
        print()

    if deadlines:
        print("--- A DATE IS STATED")
        for u, d in deadlines[:4]:
            print(f"    \"{d[:170]}\"\n       {u}")
        print()

    # The point of running both: which pass is earning its place.
    print("--- PASS SCORECARD")
    print(f"    both agreed        {agreed}")
    print(f"    passes disagreed   {differed}")
    print(f"    model only         {only_llm}    regex missed these")
    print(f"    regex only         {only_regex}    model saw nothing - usually chrome that "
          f"slipped the filter")
    blanks = sum(1 for v in llm_pick.values() if v[2] == "blank")
    out = sum(1 for v in llm_pick.values() if v[2] == "unavailable")
    if blanks or out:
        print(f"    model blank {blanks}   model unavailable {out}"
              f"   (a blank is an answer; an outage is not)")
    print("\n  Disagreements and model-only rows are the material for improving the regex.")
    print("  Tune it by hand from those, not automatically: once the cheap pass is trained on")
    print("  the expensive one, their agreement stops being independent confirmation.")

    if not (regex_pick or llm_pick):
        print("\nNothing found on the usual paths. That is NOT evidence the call is shut (2.1) -")
        print("it means this site does not put it where sites usually do.")
    else:
        print("\nEvery sentence above was verified present on the page it is attributed to.")
        print("This gathers evidence; it does not decide. Read it and judge.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
