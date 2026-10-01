"""Gap 5a experiment: for events that have already run ("Watching"), is next year's edition
already announced on the event's OWN site - findable with no AI?

READ-ONLY. No AI, no database writes. Pages are read through the existing fetch ladder
(verify.fetch_text, then audit_evidence.escalate: crawl4ai -> Playwright -> real Chrome) - no
crawler is re-implemented here. Each site is read once; at most 3 of the row's own pages.

For each Watching row in this week's approved files (as of today):
  pages   CONFERENCE URL / MAIN_INFO_URL (the event's own site) and the submission page
  signal  DATED  - a later year (start year +1 or +2) within ~120 characters of a month + day,
                   or "save the date"
          YEAR   - the later year appears, but no date near it
          NONE   - the page read, nothing about a later edition
          UNREAD - no page could be read
Every signal is kept with the sentence it came from, for a person to judge - a signal is a
lead, not a finding (a "2027" can be a sponsor deck or a copyright line).

    python experiments/gap5_next_edition/gap5a_measure.py
"""
from __future__ import annotations

import asyncio
import csv
import importlib.util
import json
import os
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.cfp_monitor import lifecycle                                  # noqa: E402
from src.cfp_monitor.verify import fetch_text                          # noqa: E402

_s = importlib.util.spec_from_file_location("_ae", ROOT / "scripts" / "audit_evidence.py")
_ae = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_ae)

MARKETS_DIR = Path(os.environ.get("CFP_MARKETS_DIR", "."))   # upstream Markets working folder: set CFP_MARKETS_DIR (kept out of this public repo)
TODAY = date(2026, 9, 28)
OUT = Path(__file__).resolve().parent
MONTH = (r"(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|jun(e)?|jul(y)?|aug(ust)?|"
         r"sep(t(ember)?)?|oct(ober)?|nov(ember)?|dec(ember)?)")
DATE_NEAR = re.compile(rf"\b{MONTH}\.?\s+\d{{1,2}}\b|\b\d{{1,2}}(st|nd|rd|th)?\s+{MONTH}\b", re.I)
SAVE = re.compile(r"save\s+the\s+date", re.I)


def sentence(text: str, i: int, span: int = 160) -> str:
    return " ".join(text[max(0, i - span): i + span].split())


def signal(text: str, start_year: int) -> tuple[str, str]:
    if not text:
        return "UNREAD", ""
    best = ("NONE", "")
    for y in (start_year + 1, start_year + 2):
        for m in re.finditer(rf"\b{y}\b", text):
            window = text[max(0, m.start() - 120): m.end() + 120]
            if re.search(r"©|copyright|all rights reserved", window, re.I):
                continue
            if DATE_NEAR.search(window) or SAVE.search(window):
                return "DATED", sentence(text, m.start())
            if best[0] == "NONE":
                best = ("YEAR", sentence(text, m.start()))
    return best


def main() -> int:
    rows = []
    for m in ("Cybersecurity", "Utility"):
        with open(MARKETS_DIR / f"{m}_audited.final.csv", encoding="utf-8-sig", newline="") as fh:
            rows += [(m, r) for r in csv.DictReader(fh)]
    assess = lifecycle.assess_all([r for _, r in rows], TODAY)
    watching = [(m, r) for m, r in rows if assess[r["EVENT_ID"]].edition_state == "Watching"]
    print(f"{len(watching)} Watching row(s) - reading their own pages (no AI)")

    pages: dict[str, list[str]] = {}
    for m, r in watching:
        urls = [u for u in (r.get("CONFERENCE URL"), r.get("MAIN_INFO_URL"),
                            r.get("CFP_SUBMISSION_URL") or r.get("SUBMISSION URL"))
                if (u or "").startswith("http")]
        pages[r["EVENT_ID"]] = list(dict.fromkeys(urls))[:3]

    text: dict[str, tuple[str, str]] = {}
    for url in sorted({u for us in pages.values() for u in us}):
        t, note = fetch_text(url)
        text[url] = (t or "", "plain" if t else note)
    hard = [u for u, (t, _) in text.items() if not t]
    if hard:
        print(f"{len(hard)} page(s) need the browser ladder ...")
        for u, (t, rung) in asyncio.run(_ae.escalate(hard)).items():
            if t:
                text[u] = (t, rung)

    results, tally = [], Counter()
    for m, r in watching:
        start = (r.get("START DATE") or "")[:4]
        y = int(start) if start.isdigit() else TODAY.year
        best = ("UNREAD", "", "")
        for u in pages[r["EVENT_ID"]]:
            sig, snip = signal(text.get(u, ("", ""))[0], y)
            rank = ["UNREAD", "NONE", "YEAR", "DATED"]
            if rank.index(sig) > rank.index(best[0]):
                best = (sig, snip, u)
        tally[best[0]] += 1
        results.append({"market": m, "conference": r["CONFERENCE"], "ran": r.get("START DATE", ""),
                        "signal": best[0], "page": best[2], "evidence": best[1][:320]})

    (OUT / "gap5a_result.json").write_text(json.dumps({"today": TODAY.isoformat(),
                                                       "watching": len(watching),
                                                       "tally": dict(tally),
                                                       "rows": results}, indent=2),
                                           encoding="utf-8")
    print(dict(tally))
    for x in sorted(results, key=lambda z: ["DATED", "YEAR", "NONE", "UNREAD"].index(z["signal"])):
        print(f"{x['signal']:6} | {x['market'][:5]} | ran {x['ran'][:10]} | {x['conference'][:52]}")
        if x["signal"] in ("DATED", "YEAR"):
            print(f"         {x['page'][:80]}\n         \"{x['evidence'][:230]}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
