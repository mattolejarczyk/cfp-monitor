"""Why did a candidate page yield nothing? Classify the wall, do not guess at it.

A row that comes back blank has at least five different causes, and they need opposite
responses. Lumping them together as "no deadline on the page" is how a fetching problem gets
mistaken for a finding about the customer's market:

  consent-wall   the text is behind an Accept/Reject gate -> we need a click, not a better model
  bot-check      Cloudflare/Imperva interstitial returned 200 -> needs the CDP rung
  js-only        the shell loaded and the content never did -> needs a real render
  thin           readable but almost empty -> probably a redirect or a stub
  readable       the page genuinely does not state a submission deadline -> a real finding

Only the last one is evidence about the conference. The other four are evidence about our
fetching, and reporting them as the first would overstate what we know.

    python scripts/diagnose_unread.py -i citations_extracted_93.csv \
        -c candidate_urls_fixed_20260811.csv
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import importlib.util
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("_ae", ROOT / "scripts" / "audit_evidence.py")
_ae = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ae)

from src.cfp_monitor.verify import fetch_text          # noqa: E402

# Wording that identifies a wall rather than a page. Matched on the WHOLE text only when it is
# short - a long article mentioning cookies is a page, a 400-character page that says nothing
# but "we value your privacy" is a gate.
CONSENT = re.compile(
    r"accept all cookies|reject all|manage (your )?(cookie|consent|preferences)"
    r"|we (use|value) (your )?(cookies|privacy)|cookie (policy|banner|settings)"
    r"|consent to the use of cookies|privacy preference cent", re.I)
BOTCHECK = re.compile(
    r"just a moment|checking your browser|verify(ing)? you are (a )?human|are you a robot"
    r"|captcha|cloudflare|ddos protection|access denied|request unsuccessful"
    r"|incapsula|imperva|akamai|bot detection|unusual traffic|security check", re.I)
JS_ONLY = re.compile(
    r"enable javascript|javascript is (required|disabled)|requires javascript"
    r"|please enable js|<noscript>|loading\.\.\.$", re.I)


def classify(text: str) -> str:
    if not text or not text.strip():
        return "empty"
    ok, why = _ae.readable(text)
    if not ok:
        return f"unreadable:{why}"
    n = len(text)
    head = text[:1500]
    # Order matters. A bot-check page often ALSO carries a cookie notice, and the bot-check is
    # the actionable one - it is what the CDP rung exists for.
    if BOTCHECK.search(head):
        return "bot-check"
    if n < 1200 and JS_ONLY.search(head):
        return "js-only"
    if n < 1500 and CONSENT.search(head):
        return "consent-wall"
    if n < 400:
        return "thin"
    return "readable"


def main() -> int:
    ap = argparse.ArgumentParser(description="Classify why candidate pages yielded nothing.")
    ap.add_argument("-i", "--input", required=True, help="citations_extracted output")
    ap.add_argument("-c", "--candidates", required=True, help="the candidate_urls file")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()

    with open(a.input, encoding="utf-8-sig", newline="") as fh:
        out_rows = {r["EVENT_ID"]: r for r in csv.DictReader(fh)}
    with open(a.candidates, encoding="utf-8-sig", newline="") as fh:
        cand_rows = list(csv.DictReader(fh))

    # Only rows that produced no citation AND had somewhere to look.
    targets = []
    for r in cand_rows:
        got = out_rows.get(r["EVENT_ID"], {})
        if got.get("DEADLINE_EVIDENCE_URL"):
            continue
        urls = [u.strip() for u in (r.get("CANDIDATE_URLS") or "").split("|") if u.strip()]
        if urls:
            targets.append((r["CONFERENCE"], urls))
    if a.limit:
        targets = targets[:a.limit]

    wanted = [u for _, urls in targets for u in urls]
    print(f"{len(targets)} blank row(s) with candidates | {len(wanted)} URL(s) to re-read\n")

    pages: dict[str, str] = {}
    unread = []
    for u in wanted:
        t, _ = fetch_text(u)
        (pages if t else {}).setdefault(u, t) if t else unread.append(u)
    if unread:
        print(f"--- escalating {len(unread)} through the browser ---")
        for u, (t, _via) in asyncio.run(_ae.escalate(unread)).items():
            pages[u] = t

    tally: Counter = Counter()
    detail: list[tuple[str, str, str, int]] = []
    for conf, urls in targets:
        # The best outcome across a row's candidates is what the row actually experienced.
        rank = {"readable": 0, "thin": 1, "consent-wall": 2, "js-only": 3, "bot-check": 4}
        best, best_url, best_n = "empty", urls[0], 0
        for u in urls:
            t = pages.get(u, "")
            c = classify(t)
            if rank.get(c, 9) < rank.get(best, 9) or best == "empty":
                best, best_url, best_n = c, u, len(t)
        tally[best] += 1
        detail.append((conf, best, best_url, best_n))

    print(f"\n{'what came back':<22} rows")
    for k, n in tally.most_common():
        print(f"  {k:<20} {n:>4}")

    blocked = sum(n for k, n in tally.items()
                  if k in ("bot-check", "consent-wall", "js-only", "empty")
                  or k.startswith("unreadable"))
    print(f"\n{blocked} of {len(targets)} blank rows were BLOCKED rather than answered.")
    print("Those are not evidence the conference states no deadline.\n")

    for conf, kind, url, n in sorted(detail, key=lambda x: x[1]):
        if kind != "readable":
            print(f"  {kind:<18} {conf[:40]:<40} {n:>6}c  {url[:58]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
