"""Contract v2.4: repair how a delivery WRITES its claims - never what it claims.

    python scripts/mechanical_repairs.py <delivery.csv> [--prior <previous.csv>]
        [--apply] [--db <db> --market <Canonical>] [--no-gate]

Without --apply it reports what it would repair and why, and writes nothing.

WHERE THIS SITS. Between the gate's first verdict and import. It is NOT a second gate: it
judges nothing about acceptance. It repairs the four mechanical classes upstream accepted on
2026-09-12, then hands the repaired file to scripts/accept_delivery.py - the one gate - and
that verdict is the only one that counts. Import only a file the gate ACCEPTED.

THE BOUNDARY (v2.4). A repair never changes a date, a status, IS_PROJECTED except where an R1
withdrawal requires it, an event's identity, or which page is cited, and never introduces a
URL upstream did not send. Anything that would need one of those is reported as needing
upstream, exactly as before v2.4.

    A  quote re-copied from the already-cited page   (check 3 "paraphrase, date IS on page")
    B  upstream's replacement URL carried to every field still holding the identical dead link
    C  plain text in prose fields                    (never a quote field)
    D  R1 withdrawal of a citation dead in a plain fetch AND a real browser

WHY 2026-09-12. Seven hand-back documents crossed that day. The SecureWorld pair alone - a
quote reading "September 19, 2026" on a page that says "2026-09-19" - took three rounds, one
of them a wrong diagnosis of ours, to reach a fix a machine can make in a second.

SAFEGUARDS, all from the amendment:
  - every repair is logged (<delivery>.repairs.md) with before, after and evidence
  - the log is for upstream, who may reverse any repair
  - the repaired file is re-gated
  - the same repair on the same row in an EARLIER cycle is refused and routed to upstream as
    a generator pattern (market_sheets/repair_ledger.txt)
  - NOTES and SUBMISSION DATE VERIFIED are never touched
  - a repair that would itself create a gate failure is not made (the round-3 London
    withdrawal broke check 4; this refuses that shape)
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import rules                                    # noqa: E402
from src.cfp_monitor.verify import date_variants                     # noqa: E402

CUSTOMER_OWNED = ("NOTES", "SUBMISSION DATE VERIFIED")
PROSE_FIELDS = ("STATUS DETAILS", "OVERVIEW", "TRACK", "CATEGORIES")
# Every URL field B may carry a replacement into. LIFECYCLE_EVIDENCE_URL is included for B -
# upstream's own replacement - but deliberately NOT for D: withdrawing a discontinuation's only
# evidence makes the row fail R16, so that stays upstream's call.
URL_FIELDS = ("SUBMISSION URL", "CFP_SUBMISSION_URL", "DEADLINE_EVIDENCE_URL",
              "VENUE_EVIDENCE_URL", "MAIN_INFO_URL", "CONFERENCE URL", "LIFECYCLE_EVIDENCE_URL")
WITHDRAWABLE = ("SUBMISSION URL", "CFP_SUBMISSION_URL", "DEADLINE_EVIDENCE_URL",
                "VENUE_EVIDENCE_URL")
PATTERN_WINDOW_DAYS = 21
LEDGER = ROOT / "market_sheets" / "repair_ledger.txt"

# Words too common to tie a quote to ONE event. Everything else in the row's name is a token
# that can anchor the span - "Twin", "Cities", "Government", "Critical", "Infrastructure".
_GENERIC = {"conference", "conferences", "summit", "expo", "forum", "annual", "international",
            "global", "world", "event", "events", "award", "awards", "series", "congress",
            "week", "show", "symposium", "meeting", "edition", "the", "and", "for", "with"}
_DEADLINE_WORDS = re.compile(r"deadline|due|clos|submi|until|apply|applications?|entr(y|ies)"
                             r"|call for", re.I)
_ANY_FULL_DATE = re.compile(
    r"\b20\d{2}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/20\d{2}\b|"
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+20\d{2}\b|"
    r"\b\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+20\d{2}\b",
    re.I)


@dataclass
class Repair:
    cls: str
    conference: str
    market: str
    field: str
    before: str
    after: str
    why: str
    evidence: str = ""


@dataclass
class Declined:
    cls: str
    conference: str
    field: str
    why: str


@dataclass
class Result:
    repairs: list[Repair] = field(default_factory=list)
    declined: list[Declined] = field(default_factory=list)


def _g(row, f):
    return (row.get(f) or "").strip()


def _norm_quote(text: str) -> str:
    """The gate's own normalisation, imported lazily so this module loads without it."""
    from scripts.accept_delivery import norm
    return norm(text)


# ============================================================================ class C
_DASHES = {"\u2013": "-", "\u2014": "-", "\u2212": "-"}
_QUOTES = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'}


def plain_text(value: str, *, is_projected: bool) -> str:
    """Class C. Punctuation only; words never change.

    BRACKETS ARE UNWRAPPED ONLY ON A VERIFIED ROW. Contract R4 (v2.0.1 section 7) prescribes
    a bracketed projection form - "[Call for Speakers Pending / Expected Fall 2026]" - so on a
    projected row a bracketed value may be exactly what the contract asks for. On 2026-09-12
    round 2 the brackets were on verified rows, which is the case this repairs.
    """
    out = value
    for a, b in {**_DASHES, **_QUOTES, "\u00a0": " "}.items():
        out = out.replace(a, b)
    s = out.strip()
    if (not is_projected and s.startswith("[") and s.endswith("]")
            and s.count("[") == 1 and s.count("]") == 1):
        out = s[1:-1].strip()
    return out


# A value that is a serialised LIST - "['Cybersecurity', 'CISO Leadership']" - is not prose in
# brackets. Unwrapping it leaves "'Cybersecurity', 'CISO Leadership'", a half-fix that hides a
# generator defect (a JSON array written with str()). Found on 3 imported rows the first time
# this ran, 2026-09-12. Declined and reported, never repaired.
_LIST_LITERAL = re.compile(r"""^\s*\[\s*['"]""")


def repair_prose(row) -> tuple[list[Repair], list[Declined]]:
    projected = _g(row, "IS_PROJECTED").lower() == "true"
    out, declined = [], []
    for f in PROSE_FIELDS:
        before = row.get(f) or ""
        if _LIST_LITERAL.match(before):
            declined.append(Declined("C", _g(row, "CONFERENCE"), f,
                                     "value is a serialised list, not bracketed prose - the "
                                     "generator wrote an array with str(); upstream's to fix"))
            continue
        after = plain_text(before, is_projected=projected)
        if after != before:
            out.append(Repair("C", _g(row, "CONFERENCE"), _g(row, "Market"), f, before, after,
                              "plain text: brackets/dashes/curly quotes/non-breaking spaces"))
    return out, declined


# ============================================================================ class A
def _date_regexes(d: date) -> list[re.Pattern]:
    """Raw-text patterns for every rendering verify.date_variants() recognises.

    date_variants() works on NORMALISED text, where "Sept. 4, 2026" has become "sept 4 2026".
    A repaired quote must be the page's RAW characters, so each variant's tokens are rejoined
    allowing the spaces, commas and full stops normalisation removed.
    """
    pats = []
    for v in set(date_variants(d)):
        toks = v.split(" ")
        body = r"[\s,.]+".join(re.escape(t) for t in toks)
        pats.append(re.compile(r"(?<![0-9A-Za-z])" + body + r"(?![0-9A-Za-z])", re.I))
    return pats


def _occurrences(text: str, d: date) -> list[tuple[int, int]]:
    spans = sorted({m.span() for p in _date_regexes(d) for m in p.finditer(text)})
    merged: list[tuple[int, int]] = []
    for s, e in spans:                     # "September 19, 2026" also contains "19, 2026"-ish hits
        if merged and s < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(e, merged[-1][1]))
        else:
            merged.append((s, e))
    return merged


def _name_tokens(name: str) -> list[str]:
    return [t for t in re.findall(r"[A-Za-z][A-Za-z&.'-]{3,}", name)
            if t.lower() not in _GENERIC]


def find_quote_span(page: str, conference: str, deadline: date) -> tuple[Optional[str], str]:
    """The page's own text pairing THIS event or call with THIS deadline, or (None, why).

    Declines rather than guesses (contract 2.5) whenever the answer is not unambiguous:
      - the deadline appears on the page zero times, or more than once
      - no name token and no deadline wording sits with it
      - the span also holds a different full date (it could be pairing the wrong line)
      - the span is not unique on the page
    """
    occ = _occurrences(page, deadline)
    if not occ:
        return None, "the deadline is not on the page in a form we can copy exactly"
    if len(occ) > 1:
        return None, f"the deadline appears {len(occ)} times on the page - ambiguous"
    ds, de = occ[0]

    span = None
    # Route 1: anchored on the row's own name - listings such as SecureWorld's, where a
    # deadline sits beside its event's name with no sentence around it.
    tokens = _name_tokens(conference)
    if tokens:
        left = page[max(0, ds - 120):ds]
        hits = [(m.start(), m.end()) for t in tokens
                for m in re.finditer(r"(?<![A-Za-z])" + re.escape(t) + r"(?![A-Za-z])", left)]
        if hits:
            start = max(h[0] for h in hits)
            moved = True
            while moved:                   # extend over adjacent name words: "Twin" + "Cities"
                moved = False
                for hs, he in hits:
                    if hs < start and start - he <= 4:
                        start, moved = hs, True
            span = page[max(0, ds - 120) + start:de]
    # Route 2: a sentence carrying deadline wording - a CFP page's "Submissions close ...".
    if span is None:
        b = max(page.rfind(c, 0, ds) for c in ".!?\n")
        e_candidates = [i for i in (page.find(c, de) for c in ".!?\n") if i != -1]
        e = min(e_candidates) if e_candidates else len(page)
        sentence = page[b + 1:e].strip()
        if len(sentence) <= 220 and _DEADLINE_WORDS.search(sentence):
            span = sentence

    if span is None:
        return None, "nothing on the page ties this date to this event or to a deadline"
    span = re.sub(r"\s+", " ", span).strip()
    if len(span) > 220:
        return None, "the only span tying the date to the event is too long to be a quote"
    others = [m.group(0) for m in _ANY_FULL_DATE.finditer(span)
              if not any(p.fullmatch(m.group(0)) for p in _date_regexes(deadline))]
    if others:
        return None, f"the span also holds another date ({others[0]}) - could be the wrong line"
    if _norm_quote(page).count(_norm_quote(span)) != 1:
        return None, "the span is not unique on the page"
    return span, "ok"


def repair_quote(row, page: Optional[str], status: Optional[int], today: date
                 ) -> tuple[Optional[Repair], Optional[Declined]]:
    """Class A for one row, given the fetched cited page. None, None = nothing to do."""
    name = _g(row, "CONFERENCE")
    url, quote = _g(row, "DEADLINE_EVIDENCE_URL"), _g(row, "DEADLINE_QUOTE")
    d = rules.parse_date(_g(row, "SUBMISSION DEADLINE"))
    # Exactly the scope of gate check 3 (v1.4): a live deadline with a cited page and a quote.
    if not (url and quote and d) or rules.deadline_has_passed(row, today):
        return None, None
    if status in (403, 404, 410) or not page:
        return None, None                  # 403 exempt; dead pages are class D; unread = unknown
    if _norm_quote(quote) in _norm_quote(page):
        return None, None                  # already verbatim
    span, why = find_quote_span(page, name, d)
    if span is None:
        return None, Declined("A", name, "DEADLINE_QUOTE", why)
    i = page.find(span.split(" ")[0])
    ctx = re.sub(r"\s+", " ", page[max(0, i - 60):i + len(span) + 60])
    return Repair("A", name, _g(row, "Market"), "DEADLINE_QUOTE", quote, span,
                  f"quote re-copied from the cited page, which states {d.isoformat()}",
                  evidence=f"{url} ... {ctx} ..."), None


# ============================================================================ class B
def replacement_pairs(prior, current) -> tuple[dict[str, str], list[str]]:
    """{old_url: new_url} upstream applied on this row, and any ambiguous old urls."""
    seen: dict[str, set[str]] = {}
    for f in URL_FIELDS:
        p, n = _g(prior, f), _g(current, f)
        if p and n and p != n:
            seen.setdefault(p, set()).add(n)
    pairs = {p: next(iter(ns)) for p, ns in seen.items() if len(ns) == 1}
    return pairs, [p for p, ns in seen.items() if len(ns) > 1]


# ============================================================================ class D
def withdrawal_would_break_prose(row) -> bool:
    """Would setting IS_PROJECTED true put active-call prose on a projected row (check 4)?"""
    from scripts.accept_delivery import ACTIVE_PROSE, DEFUNCT_PHRASES
    prose = _g(row, "STATUS DETAILS")
    return bool(ACTIVE_PROSE.search(prose) and not DEFUNCT_PHRASES.search(prose))


# ============================================================================ ledger
def pattern_seen(ledger_lines: list[str], market: str, conference: str, fld: str, cls: str,
                 today: date) -> Optional[str]:
    """The date of an EARLIER-cycle repair of the same kind on the same row, if any."""
    lo = today - timedelta(days=PATTERN_WINDOW_DAYS)
    for line in ledger_lines:
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 5:
            continue
        d = rules.parse_date(parts[0])
        if d and lo <= d < today and parts[1:5] == [market, conference, fld, cls]:
            return parts[0]
    return None


# ============================================================================ driver
def run(rows: list[dict], prior_rows: Optional[list[dict]], today: date,
        fetch: Callable[[str], tuple[Optional[int], str]],
        browser_dead: Callable[[list[str]], set[str]],
        ledger_lines: list[str]) -> Result:
    """Plan and apply repairs IN MEMORY. Network access is injected, so tests run offline."""
    res = Result()

    def admit(rep: Repair, row) -> bool:
        if rep.field in CUSTOMER_OWNED:
            return False
        seen = pattern_seen(ledger_lines, rep.market, rep.conference, rep.field, rep.cls, today)
        if seen:
            res.declined.append(Declined(rep.cls, rep.conference, rep.field,
                                         f"PATTERN - same repair made {seen}; the generator keeps "
                                         f"producing it, so it goes back to upstream"))
            return False
        row[rep.field] = rep.after
        res.repairs.append(rep)
        return True

    cache: dict[str, tuple[Optional[int], str]] = {}

    def get(url):
        if url not in cache:
            cache[url] = fetch(url)
        return cache[url]

    # C - offline
    for r in rows:
        reps, decs = repair_prose(r)
        res.declined.extend(decs)
        for rep in reps:
            admit(rep, r)

    # Links upstream changed in this delivery - the old ones it replaced and the new ones it
    # sent. D must not withdraw these: amendment v2.4 allows a withdrawal only where upstream
    # "has not supplied a replacement". Where B declines (two different replacements, or one
    # that does not resolve), the question is upstream's, and withdrawing the old link would
    # quietly answer it for them.
    upstream_touched: set[str] = set()

    # B - needs the previous file
    if prior_rows is not None:
        by_name: dict[str, list[dict]] = {}
        for p in prior_rows:
            by_name.setdefault(_g(p, "CONFERENCE"), []).append(p)
        for r in rows:
            prev = by_name.get(_g(r, "CONFERENCE"), [])
            if len(prev) != 1:
                continue
            pairs, ambiguous = replacement_pairs(prev[0], r)
            for f in URL_FIELDS:
                p, n = _g(prev[0], f), _g(r, f)
                if p and n and p != n:
                    upstream_touched |= {p, n}
            for old in ambiguous:
                res.declined.append(Declined("B", _g(r, "CONFERENCE"), "-",
                                             f"{old} was replaced with different URLs in different "
                                             f"fields - which one is meant is upstream's call"))
            for old, new in pairs.items():
                targets = [f for f in URL_FIELDS if _g(r, f) == old]
                if not targets:
                    continue
                if get(old)[0] not in rules.NEEDS_BROWSER_STATUS or old not in browser_dead([old]):
                    res.declined.append(Declined("B", _g(r, "CONFERENCE"), ",".join(targets),
                                                 f"{old} is not dead in both a plain fetch and a "
                                                 f"real browser - nothing to carry"))
                    continue
                code = get(new)[0]
                if not (code and (200 <= code < 400 or code == 403)):
                    res.declined.append(Declined("B", _g(r, "CONFERENCE"), ",".join(targets),
                                                 f"upstream's replacement {new} does not resolve "
                                                 f"(HTTP {code})"))
                    continue
                for f in targets:
                    admit(Repair("B", _g(r, "CONFERENCE"), _g(r, "Market"), f, old, new,
                                 "upstream's replacement for the identical dead link, carried "
                                 "to a field it had not reached"), r)

    # A - fetch the cited pages
    for r in rows:
        url = _g(r, "DEADLINE_EVIDENCE_URL")
        if not url:
            continue
        code, text = get(url)
        rep, dec = repair_quote(r, text, code, today)
        if dec:
            res.declined.append(dec)
        if rep:
            admit(rep, r)

    # D - withdraw what is dead in a plain fetch AND a browser, on live or blank deadlines
    suspects: dict[str, list[tuple[dict, str]]] = {}
    for r in rows:
        if rules.deadline_has_passed(r, today):
            continue                       # v2.2: expected decay, not a defect
        for f in WITHDRAWABLE:
            u = _g(r, f)
            if not u.startswith("http") or get(u)[0] not in rules.NEEDS_BROWSER_STATUS:
                continue
            if u in upstream_touched:
                res.declined.append(Declined("D", _g(r, "CONFERENCE"), f,
                                             f"{u} is dead, but upstream changed this link in this "
                                             f"delivery - what replaces it is upstream's call"))
                continue
            suspects.setdefault(u, []).append((r, f))
    dead = browser_dead(list(suspects)) if suspects else set()
    for u, where in suspects.items():
        for r, f in where:
            name = _g(r, "CONFERENCE")
            if u not in dead:
                res.declined.append(Declined("D", name, f, f"{u} is HTTP {get(u)[0]} to a script but "
                                                           f"not confirmed dead in a real browser (5.2)"))
                continue
            if f == "DEADLINE_EVIDENCE_URL":
                if withdrawal_would_break_prose(r):
                    res.declined.append(Declined(
                        "D", name, f, f"{u} is dead, but R1 makes the row projected and its "
                                      f"STATUS DETAILS asserts an active call (check 4) - the "
                                      f"prose is upstream's, so the withdrawal is too"))
                    continue
                for wf, wv in rules.withdrawal_changes(r, fetched=True, today=today).items():
                    if _g(r, wf) != wv:
                        admit(Repair("D", name, _g(r, "Market"), wf, _g(r, wf), wv,
                                     f"R1 withdrawal - {u} is dead in a real browser "
                                     f"(plain fetch HTTP {get(u)[0]})"), r)
            elif _g(r, f) == u:
                admit(Repair("D", name, _g(r, "Market"), f, u, "",
                             f"R1 withdrawal - dead in a real browser (plain fetch HTTP "
                             f"{get(u)[0]})"), r)
    return res


def _live_fetch(url: str) -> tuple[Optional[int], str]:
    from src.cfp_monitor.verify import fetch_text, link_status
    code, _ = link_status(url)
    text = ""
    if code not in (404, 410):
        text, _ = fetch_text(url)
    return code, text or ""


def _live_browser_dead(urls: list[str]) -> set[str]:
    if not urls:
        return set()
    from scripts.recheck_dead_links import browser_check
    results = asyncio.run(browser_check(urls))
    return {u for u, (verdict, _s, _c) in results.items() if verdict == "dead"}


def write_report(path: Path, delivery: Path, res: Result, today: date) -> None:
    lines = [f"# Mechanical repairs - {delivery.name}", "",
             f"    DATE:      {today.isoformat()}",
             f"    AUTHORITY: Joint Pipeline Contract amendment v2.4",
             f"    REPAIRED:  {len(res.repairs)}    NOT REPAIRED: {len(res.declined)}", "",
             "Every change below is to how a claim is written, never to what it claims. "
             "Upstream may reverse any of them.", ""]
    if res.repairs:
        lines += ["## Repairs made", "", "| Class | Row | Field | Before | After | Why |",
                  "|---|---|---|---|---|---|"]
        for r in res.repairs:
            cell = lambda s: (s or "(blank)").replace("|", "/").replace("\n", " ")[:120]  # noqa: E731
            lines.append(f"| {r.cls} | {cell(r.conference)} | {r.field} | {cell(r.before)} | "
                         f"{cell(r.after)} | {cell(r.why)} |")
        ev = [r for r in res.repairs if r.evidence]
        if ev:
            lines += ["", "### Evidence for re-copied quotes", ""]
            lines += [f"- **{r.conference}**: {r.evidence}" for r in ev]
    if res.declined:
        lines += ["", "## Not repaired - these still need upstream", "",
                  "| Class | Row | Field | Why not |", "|---|---|---|---|"]
        for d in res.declined:
            lines.append(f"| {d.cls} | {d.conference} | {d.field} | {d.why} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("delivery")
    ap.add_argument("--prior", help="the previous version of this delivery (enables class B)")
    ap.add_argument("--apply", action="store_true", help="write the repaired file and report")
    ap.add_argument("--db", help="passed to the gate for criteria 7 and 8")
    ap.add_argument("--market", help="canonical market, passed to the gate")
    ap.add_argument("--no-gate", action="store_true", help="do not run the gate afterwards")
    ap.add_argument("--today", help="YYYY-MM-DD, for tests and replays")
    ap.add_argument("--ledger", default=str(LEDGER),
                    help="repair history for the pattern rule. Point a REPLAY at a scratch file: "
                         "replaying into the real ledger makes next cycle's genuine repairs look "
                         "like repeats and routes them to upstream")
    a = ap.parse_args()

    today = date.fromisoformat(a.today) if a.today else date.today()
    src = Path(a.delivery)
    with open(src, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        cols, rows = reader.fieldnames, list(reader)
    prior = None
    if a.prior:
        with open(a.prior, encoding="utf-8-sig", newline="") as fh:
            prior = list(csv.DictReader(fh))
    ledger = Path(a.ledger)
    ledger_lines = ledger.read_text(encoding="utf-8").splitlines() if ledger.exists() else []

    res = run(rows, prior, today, _live_fetch, _live_browser_dead, ledger_lines)

    print(f"\n{src.name}: {len(res.repairs)} repair(s), {len(res.declined)} not repaired\n")
    for r in res.repairs:
        print(f"  [{r.cls}] {r.conference[:40]:40} {r.field:24} {r.before[:30]!r} -> {r.after[:40]!r}")
    for d in res.declined:
        print(f"  [{d.cls}] NOT REPAIRED  {d.conference[:40]:40} {d.field:24} {d.why}")

    if not a.apply:
        print("\nReport only - nothing written. Re-run with --apply.")
        return 0

    out = src.with_name(src.stem + ".repaired.csv")
    report = src.with_name(src.stem + ".repairs.md")
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)
    write_report(report, src, res, today)
    if res.repairs:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with open(ledger, "a", encoding="utf-8") as fh:
            for r in res.repairs:
                fh.write("\t".join([today.isoformat(), r.market, r.conference, r.field, r.cls,
                                    r.before.replace("\t", " ")[:200],
                                    r.after.replace("\t", " ")[:200], src.name]) + "\n")
    print(f"\nwrote {out.name} and {report.name}")

    if a.no_gate:
        print("Gate NOT run (--no-gate). Run scripts/accept_delivery.py on the repaired file "
              "before importing it.")
        return 0
    cmd = [sys.executable, str(ROOT / "scripts" / "accept_delivery.py"), str(out)]
    if a.db:
        cmd += ["--db", a.db]
    if a.market:
        cmd += ["--market", a.market]
    print("\nRe-gating the repaired file (v2.4 safeguard 3):\n")
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    sys.exit(main())
