"""Draft the ANSWER KEY: for the 40 benchmark events, what we claim per field and what the event's own pages say, so a person confirms instead of researching.

    python scripts/answer_key_prefill.py [--out docs/qa/answer-key-DRAFT.csv] [--no-network]

WHY (2026-10-03). Only the deadline is ever checked against a page; the other fields (start date, city, country, format, organizer, edition) are trusted, carried, or spot-checked
(3 of 7 events had a wrong city, venue or date). Every method we want to compare (a shorter prompt, a cheap model that reads the page, two models that must agree) needs one
key to be scored on. The key is the same 40 events as the locked benchmark (docs/agents/results/01-benchmark-key.csv: 20 Cybersecurity, 20 Utility) with the fields added.

THIS SCRIPT ONLY DRAFTS. For each event and field it records our claim (the shipped approved row) and a PROOF STATUS from the event's own pages (saved copies in
page_library first, a live fetch for the rest):
  page-states     the page states our claim (a date in an event context, year-specific; a city, organizer or edition year on the page)
  page-differs    the page states a DIFFERENT date for this edition (shown), so one of the two is wrong
  unproven        the page is readable but does not state it (a person looks)
  unreadable      no usable page (walled, script-built, dead): a person reads it in a browser
Nothing is confirmed until a person writes `confirmed_value`, `confirmed_by` and `confirmed_on`; docs/qa/answer-key.csv is the confirmed file. Reuses start_date_arbiter
(year-specific date proof, range expansion) and verify.fetch_text / is_block_page; reads only."""
from __future__ import annotations

import argparse
import csv
import difflib
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
BENCH = ROOT / "docs" / "agents" / "results" / "01-benchmark-key.csv"
LIB = ROOT / "page_library" / "page_library.db"
FIELDS = ("START DATE", "CITY", "COUNTRY", "FORMAT", "ORGANIZER", "EDITION")
URL_COLS = ("CONFERENCE URL", "MAIN_INFO_URL", "VENUE_EVIDENCE_URL", "DEADLINE_EVIDENCE_URL", "CFP_SUBMISSION_URL")
MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
DATE_NEAR = re.compile(rf"(?:(?:{MONTHS})\.?\s+\d{{1,2}}(?:\s*(?:-|\u2013|to)\s*(?:(?:{MONTHS})\.?\s+)?\d{{1,2}})?,?\s+20\d\d|\d{{1,2}}(?:\s*(?:-|\u2013|to)\s*\d{{1,2}})?\s+(?:{MONTHS}),?\s+20\d\d)", re.I)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).strip()


def best_row(name: str, rows: list[dict], cutoff: float = 0.55) -> dict | None:
    """The approved row that is the benchmark event: best name similarity, or None."""
    n = norm(name)
    best, score = None, 0.0
    for r in rows:
        c = norm(r["CONFERENCE"])
        s = difflib.SequenceMatcher(None, n, c).ratio()
        if n in c or c in n:
            s = max(s, 0.9)
        if s > score:
            best, score = r, s
    return best if score >= cutoff else None


def snippet(text: str, needle: str, width: int = 110) -> str:
    i = text.lower().find(needle.lower())
    if i < 0:
        return ""
    return re.sub(r"\s+", " ", text[max(0, i - width // 2): i + len(needle) + width // 2]).strip()


def other_dates_for_year(pages: list[tuple[str, str]], year: str, limit: int = 3, require_context: bool = True) -> list[str]:
    """Date mentions of THIS edition's year on the pages: in an event context (what the page says when it does not say our claim), or, with
    require_context=False, anywhere (a heading often prints the dates with no 'held' or 'takes place' beside them; a person judges those)."""
    from src.cfp_monitor.self_heal import EVENT_CONTEXT
    seen: list[str] = []
    for _u, text in pages:
        for m in DATE_NEAR.finditer(text or ""):
            if year not in m.group(0):
                continue
            ctx = text[max(0, m.start() - 140): m.end() + 140]
            if (not require_context or EVENT_CONTEXT.search(ctx)) and m.group(0) not in seen:
                seen.append(re.sub(r"\s+", " ", m.group(0)))
            if len(seen) >= limit:
                return seen
    return seen


def field_proof(field: str, claim: str, pages: list[tuple[str, str]], row: dict) -> dict:
    """{status, url, quote, note} for one claimed field against the readable pages."""
    readable = [(u, t) for u, t in pages if t and len(t) > 300]
    claim = (claim or "").strip()
    if not claim:
        return {"status": "no claim", "url": "", "quote": "", "note": ""}
    if not readable:
        return {"status": "unreadable", "url": "", "quote": "", "note": "no page read"}
    if field == "START DATE":
        from datetime import datetime
        from scripts.start_date_arbiter import proven
        try:
            d = datetime.strptime(claim, "%Y-%m-%d").date()
        except ValueError:
            return {"status": "unproven", "url": "", "quote": "", "note": "claim is not an ISO date"}
        ok, url, quote = proven(readable, d)
        if ok:
            return {"status": "page-states", "url": url, "quote": quote[:200], "note": ""}
        others = other_dates_for_year(readable, str(d.year))
        if others:
            return {"status": "page-differs", "url": readable[0][0], "quote": "", "note": "page says: " + "; ".join(others)}
        loose = other_dates_for_year(readable, str(d.year), 6, require_context=False)
        from scripts.start_date_arbiter import first_date
        for m in loose:
            fd = first_date(m)
            if fd == d:
                return {"status": "page-states", "url": readable[0][0], "quote": m, "note": "the date is printed on the page with no 'held' or 'takes place' word beside it"}
        note = f"no date in {d.year} beside an event word" + (f"; dates of {d.year} on the page: " + "; ".join(loose) if loose else "; no date of that year on the page")
        return {"status": "unproven", "url": readable[0][0], "quote": "", "note": note}
    if field == "EDITION":
        for u, t in readable:
            head = t[:600]
            if claim in head:
                return {"status": "page-states", "url": u, "quote": snippet(head, claim), "note": "edition year in the page heading"}
        return {"status": "unproven", "url": readable[0][0], "quote": "", "note": "edition year not in the first 600 characters"}
    if field == "FORMAT":
        low = " ".join(t.lower() for _u, t in readable)
        counts = {k: low.count(k) for k in ("virtual", "online", "hybrid", "in-person", "in person")}
        return {"status": "unproven", "url": readable[0][0], "quote": "", "note": "words on the pages: " + ", ".join(f"{k} {v}" for k, v in counts.items() if v)}
    # CITY, COUNTRY, ORGANIZER: the claim should be named on the page
    token = claim.split(",")[0].strip()
    for u, t in readable:
        if token and token.lower() in t.lower():
            return {"status": "page-states", "url": u, "quote": snippet(t, token), "note": "named on the page"}
    return {"status": "unproven", "url": readable[0][0], "quote": "", "note": f"{token!r} not found on the readable pages"}


def lib_text(url: str) -> str | None:
    if not LIB.exists() or not url:
        return None
    con = sqlite3.connect(f"file:{LIB}?mode=ro", uri=True)
    try:
        r = con.execute("select text from pages where url=? and coalesce(blocked,0)=0 order by last_fetched_at desc limit 1", (url,)).fetchone()
    finally:
        con.close()
    return r[0] if r and r[0] else None


_CACHE: dict[str, str] = {}
CACHE_FILE = ROOT / "experiments" / "purpose_audit" / "answer_key_pages.json"


def load_cache() -> None:
    import json
    if CACHE_FILE.exists():
        _CACHE.update(json.loads(CACHE_FILE.read_text(encoding="utf-8")))


def save_cache() -> None:
    import json
    CACHE_FILE.write_text(json.dumps(_CACHE, ensure_ascii=False), encoding="utf-8")


def get_pages(row: dict, network: bool) -> list[tuple[str, str]]:
    urls = []
    for c in URL_COLS:
        u = (row.get(c) or "").strip()
        if u.startswith("http") and u not in urls:
            urls.append(u)
    out = []
    for u in urls:
        t = lib_text(u)
        if t is None and u in _CACHE:
            t = _CACHE[u]
        elif t is None and network:
            from src.cfp_monitor.verify import fetch_text, is_block_page
            try:
                t, _n = fetch_text(u)
            except Exception:                                                  # noqa: BLE001
                t = ""
            if t and is_block_page(t):
                t = ""
            _CACHE[u] = t or ""
        out.append((u, t or ""))
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "docs" / "qa" / "answer-key-DRAFT.csv"))
    ap.add_argument("--no-network", action="store_true")
    a = ap.parse_args()
    load_cache()
    approved = {m: list(csv.DictReader(open(MARKETS / f"{m}_audited.final.csv", encoding="utf-8-sig", newline=""))) for m in ("Cybersecurity", "Utility")}
    bench = list(csv.DictReader(open(BENCH, encoding="utf-8", newline="")))
    rows_out, unmatched = [], []
    for b in bench:
        row = best_row(b["event_name"], approved[b["market"]])
        if row is None:
            unmatched.append(b["event_name"])
            rows_out.append({"id": b["id"], "market": b["market"], "event": b["event_name"], "field": "(event not in the approved file)", "claimed": "", "proof": "no claim",
                             "proof_url": "", "proof_quote": "", "note": "", "confirmed_value": "", "confirmed_by": "", "confirmed_on": ""})
            continue
        pages = get_pages(row, not a.no_network)
        for f in FIELDS:
            p = field_proof(f, row.get(f, ""), pages, row)
            rows_out.append({"id": b["id"], "market": b["market"], "event": b["event_name"], "field": f, "claimed": row.get(f, ""), "proof": p["status"], "proof_url": p["url"],
                             "proof_quote": p["quote"], "note": p["note"], "confirmed_value": "", "confirmed_by": "", "confirmed_on": ""})
        rows_out.append({"id": b["id"], "market": b["market"], "event": b["event_name"], "field": "DEADLINE (benchmark key: " + b["call_status"] + ")",
                         "claimed": row.get("SUBMISSION DEADLINE", ""), "proof": "see benchmark", "proof_url": b["evidence_url"], "proof_quote": "", "note": b["notes"][:160],
                         "confirmed_value": b["submission_deadline"], "confirmed_by": "benchmark key", "confirmed_on": "2026-10-02"})
    save_cache()
    with open(a.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()), quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows_out)
    from collections import Counter
    c = Counter(r["proof"] for r in rows_out if r["field"] in FIELDS)
    print(f"{len(bench)} events, {len(rows_out)} lines -> {a.out}")
    print("field proof status:", dict(c))
    if unmatched:
        print("events with no approved row (claims missing):", unmatched)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
