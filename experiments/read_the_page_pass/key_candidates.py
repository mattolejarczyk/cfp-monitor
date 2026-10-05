"""Answer-key CANDIDATES: run the read-the-page pass over the benchmark events nobody has confirmed yet, so a person confirms only what is left.

    python experiments/read_the_page_pass/key_candidates.py [--model C] [--limit 40]

WHY (2026-10-04). The answer key holds only what the operator verified (15 events). Growing it by hand is the cost the operator wants to avoid. For each of the 40 locked
benchmark events that is not in docs/qa/answer-key.csv and whose edition is still ahead, this reads the event's own pages (answer_key_prefill.get_pages: saved copies first,
live fetch and Chrome render for the rest) with the cheap reader (deepseek-chat) and keeps ONLY what pass_lib.accept proves (the quote is on the page, the date is year-specific
for the edition, a text value is inside its quote). It then sets each accepted value against OUR claim:
  agree        reader and our shipped value are the same, with a quote: two independent routes agree
  differs      both have a value and they differ: ONE IS WRONG, a person looks (this is where the money is)
  reader-only  we ship blank, the page states it: a completeness gap
  unproven     we ship a value, the reader cannot prove it from the pages: a person looks, or it stays unconfirmed
Writes docs/qa/answer-key-CANDIDATES.csv. NOTHING is confirmed here: docs/qa/answer-key.csv gains a row only when a person says so. Reuses pass_lib, run.ask/page_text
(their request/cost cap applies: 0.50 USD)."""
from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

FIELD_MAP = (("start_date", "START DATE"), ("city", "CITY"), ("country", "COUNTRY"), ("organizer", "ORGANIZER"), ("format", "FORMAT"))
COUNTRY_SAME = {"usa": "united states", "us": "united states", "united states of america": "united states", "uk": "united kingdom", "uae": "united arab emirates"}


def _n(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).strip()
    return COUNTRY_SAME.get(s, s)


def compare(field: str, claimed: str, got: str) -> str:
    """agree | differs | reader-only | unproven | both-blank"""
    c, g = (claimed or "").strip(), (got or "").strip()
    if not c and not g:
        return "both-blank"
    if not c:
        return "reader-only"
    if not g:
        return "unproven"
    if field == "start_date":
        return "agree" if c[:10] == g[:10] else "differs"
    nc, ng = _n(c), _n(g)
    return "agree" if nc == ng or nc in ng or ng in nc else "differs"


def in_scope(row: dict, today: str) -> bool:
    """Events whose pages should now describe the edition we ship: start (or edition year) not already past."""
    s = (row.get("START DATE") or "").strip()
    if s:
        return s >= today
    return (row.get("EDITION") or "") >= today[:4]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="C")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--today", default=date.today().isoformat())
    a = ap.parse_args()
    from experiments.read_the_page_pass import pass_lib as L
    from experiments.read_the_page_pass import run as R
    import answer_key_prefill as P
    R.MAX_REQUESTS = 400                                    # the 0.50 USD cap still applies
    P.load_cache()
    rows = []
    for m in ("Cybersecurity", "Utility"):
        with open(P.MARKETS / f"{m}_audited.final.csv", encoding="utf-8-sig", newline="") as fh:
            rows += [dict(r, _market=m) for r in csv.DictReader(fh)]
    from scripts.answer_key import PERSON, _tier
    # only a PERSON's ruling takes an event off the candidate list; a page-proven line (tier 2) is exactly what this run produced
    have = {P.norm(r["event"]) for r in csv.DictReader(open(ROOT / "docs" / "qa" / "answer-key.csv", encoding="utf-8")) if _tier(r) == PERSON}
    bench = list(csv.DictReader(open(P.BENCH, encoding="utf-8-sig")))
    cache = {}
    out, skipped, spent_before = [], [], R.spent()[1]
    for b in bench[:a.limit]:
        name = b["event_name"]
        if any(P.norm(name) in h or h in P.norm(name) for h in have):
            skipped.append((name, "already confirmed by the operator"))
            continue
        row = P.best_row(name, [r for r in rows if r["_market"] == b["market"]])
        if not row:
            skipped.append((name, "no row in the approved file"))
            continue
        if not in_scope(row, a.today):
            skipped.append((name, f"edition already past (start {row.get('START DATE') or 'blank'}): its pages now show the next edition"))
            continue
        pages = P.get_pages(row, True)
        text = "\n\n".join(t[:7000] for _u, t in pages if t)
        urls = [u for u, _t in pages]
        if not text.strip():
            fields = {}
        else:
            text = text if not L.looks_dateless(text) else text
            fields, _cost = R.ask(a.model, row["CONFERENCE"], row.get("EDITION") or a.today[:4], text)
            fields = fields or {}
        for key, col in FIELD_MAP:
            got, why = L.accept(key, fields.get(key, {}), text, row.get("EDITION") or "") if text.strip() else ("", "page unreadable")
            status = compare(key, row.get(col, ""), got)
            out.append({"id": b["id"], "market": b["market"], "event": row["CONFERENCE"], "field": col, "claimed": row.get(col, ""), "reader_value": got,
                        "status": status, "quote": (fields.get(key) or {}).get("quote", "") if got else "", "why": why if not got else "ok", "pages": " | ".join(urls[:3])})
        print(f"  {b['id']} {row['CONFERENCE'][:48]:48} pages {len(pages)} text {len(text)}", flush=True)
    P.save_cache()
    dest = ROOT / "docs" / "qa" / "answer-key-CANDIDATES.csv"
    with open(dest, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]) if out else ["id"])
        w.writeheader()
        w.writerows(out)
    from collections import Counter
    c = Counter(o["status"] for o in out)
    print(f"\n{len({o['event'] for o in out})} events read, {len(out)} facts: {dict(c)}; skipped {len(skipped)}; spent {R.spent()[1] - spent_before:.4f} USD -> {dest}")
    for n, why in skipped:
        print(f"  skipped: {n[:50]} - {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
