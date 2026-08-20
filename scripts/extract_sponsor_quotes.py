"""Produce SPONSOR_QUOTE from the page upstream supplied. Our half of v1.5.

WHY THIS EXISTS
Amendment v1.5 splits the sponsorship claim: upstream populates ORGANIZER, SPONSOR_REQUIRED,
SPONSOR_URL and SPONSOR_COST; SPONSOR_QUOTE is ours (R20a). That mirrors how a deadline already
works - they supply the claim and the page, we fetch the page and prove the sentence is on it.

It is the same division for the same reason. During the citation round, quotes that could not be
verified against their own page reached the customer. Extraction moved to us, where a quote is a
literal substring of a page WE fetched and cannot be a paraphrase.

THE SAFETY PROPERTY, unchanged from extract_citations.py and reused rather than reimplemented:
the model only SELECTS from text we hold, and `locate_verbatim` proves the answer is really in
it. A composed sentence dies there rather than reaching a customer. What gets stored is re-cut
from the page, so it is the page's characters and not the model's rendering of them.

WHY A COST FIGURE GETS THIS TREATMENT
It is the most consequential number in the delivery: it either kills an opportunity or commits
real budget. "$15,000 to speak" with no provable source is worse than no answer at all.

    python scripts/extract_sponsor_quotes.py --db <db> [--apply] [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Reuse, never reimplement: locate_verbatim is the guarantee, and a second copy of it is a
# second thing that can drift from the guarantee.
_spec = importlib.util.spec_from_file_location("_ec", ROOT / "scripts" / "extract_citations.py")
_ec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ec)
locate_verbatim = _ec.locate_verbatim
sentence_with = _ec.sentence_with

from src.cfp_monitor.config import Settings          # noqa: E402
from src.cfp_monitor.verify import fetch_text        # noqa: E402

SELECT_INSTRUCTION = """You are shown the text of a conference's sponsorship or prospectus page.

Return ONE sentence, COPIED EXACTLY from the page, that states either:
  - that speaking or presenting requires sponsorship, or
  - what a sponsorship costs.

Rules:
- Copy the sentence character for character. Do not paraphrase, summarise or join fragments.
- Prefer a sentence that ties SPEAKING to SPONSORSHIP over one that only lists a price.
- A price for a booth, a stand, an exhibit or a delegate pass is NOT a speaking cost.
- If the page does not say either thing, return an empty sentence. That is a valid answer.

Return ONLY JSON: {"sentence": "...", "kind": "requirement" | "cost" | ""}"""

# A price for floor space is not a price for a speaking slot. Cheap pre-filter so an obvious
# exhibitor page never reaches the model, and a post-check so its answer cannot be one either.
NOT_SPEAKING = re.compile(
    r"\b(booth|stand|exhibit\w*|floor space|delegate pass|attendee pass|table top|tabletop)\b",
    re.I)
SPEAKING = re.compile(r"\b(speak\w*|present\w*|session|keynote|panel|thought leader\w*)\b", re.I)


async def choose(text: str, conference: str, cost_hint: str, settings) -> tuple[str, str, str]:
    """Ask which sentence states it, then prove the answer is on the page.

    Returns (quote, kind, status). `status` separates a considered blank from an outage,
    because they deserve opposite treatment: a blank is a result and stands, an outage means
    try again later and must never be recorded as "this page says nothing".
    """
    try:
        import litellm
    except Exception:
        return "", "", "unavailable"

    messages = [
        {"role": "system", "content": SELECT_INSTRUCTION},
        {"role": "user", "content": "\n".join(
            [f"CONFERENCE: {conference}",
             f"COST UPSTREAM REPORTED: {cost_hint or '(none given)'}",
             "", "PAGE TEXT:", text[:16000], "", "Return ONLY the JSON object."])},
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
    kind = (data.get("kind") or "").strip().lower()
    if not sentence:
        return "", "", "blank"

    # THE CHECK THAT MAKES THIS SAFE. A sentence the page does not contain is discarded, and
    # what survives is sliced out of the page rather than taken from the model.
    found = locate_verbatim(text, sentence)
    if found is None:
        return "", "", "not-on-page"

    # ...and a verbatim sentence about a BOOTH is still the wrong answer.
    if NOT_SPEAKING.search(found) and not SPEAKING.search(found):
        return "", "", "not-about-speaking"
    return found, kind, "ok"


def candidates(db: str, limit: int | None) -> list[sqlite3.Row]:
    """Rows where upstream said sponsorship is required, gave a page, and we have no quote."""
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    cols = {r[1] for r in con.execute("pragma table_info(grounding_facts)")}
    if "sponsor_url" not in cols:
        raise SystemExit("REFUSING: this database predates v1.5 - no sponsor columns. "
                         "Open it once through Store() to run the migration.")
    rows = [r for r in con.execute(
        "select event_id, name, sponsor_url, sponsor_cost, sponsor_required, sponsor_quote "
        "from grounding_facts "
        "where lower(coalesce(sponsor_required,'')) = 'yes' "
        "  and coalesce(sponsor_url,'') != '' "
        "  and coalesce(sponsor_quote,'') = ''")]
    con.close()
    return rows[:limit] if limit else rows


async def run(rows, settings, db: str, apply: bool) -> dict:
    tally = {"ok": 0, "blank": 0, "not-on-page": 0, "not-about-speaking": 0,
             "unreadable": 0, "unavailable": 0}
    writes = []
    for i, r in enumerate(rows, 1):
        print(f"  [{i}/{len(rows)}] {r['name'][:46]}")
        try:
            res = fetch_text(r["sponsor_url"])
        except Exception as e:                                   # noqa: BLE001
            print(f"        fetch failed: {type(e).__name__}")
            tally["unreadable"] += 1
            continue
        text = res[0] if isinstance(res, tuple) else res
        if not text:
            print("        page would not load - leaving the quote blank")
            tally["unreadable"] += 1
            continue
        quote, kind, status = await choose(text, r["name"], r["sponsor_cost"] or "", settings)
        tally[status] = tally.get(status, 0) + 1
        if status == "ok":
            print(f"        [{kind}] {quote[:88]}")
            writes.append((quote, r["event_id"]))
        else:
            print(f"        {status}")

    if apply and writes:
        con = sqlite3.connect(db)
        con.executemany("update grounding_facts set sponsor_quote=? where event_id=?", writes)
        con.commit()
        con.close()
    return tally, writes


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract SPONSOR_QUOTE from upstream's page.")
    ap.add_argument("--db", required=True)
    ap.add_argument("--apply", action="store_true", help="write. Reports only without it.")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()

    os.environ.setdefault("CFP_CDP_URL", "http://localhost:9222")
    rows = candidates(a.db, a.limit)
    print("=" * 78)
    print(f"SPONSOR QUOTES  {datetime.now():%Y-%m-%d %H:%M}   "
          f"{'APPLY' if a.apply else 'REPORT ONLY'}")
    print("=" * 78)
    print(f"\n{len(rows)} row(s) need a quote "
          f"(SPONSOR_REQUIRED=Yes, a URL supplied, no quote yet)\n")
    if not rows:
        print("Nothing to do.")
        return 0

    tally, writes = asyncio.run(run(rows, Settings(), a.db, a.apply))
    print("\n  " + "  ".join(f"{k}={v}" for k, v in tally.items() if v))
    if not a.apply:
        print(f"\nREPORT ONLY - {len(writes)} quote(s) would be written. Re-run with --apply.")
    else:
        print(f"\nwrote {len(writes)} quote(s). Run scripts/check_invariants.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
