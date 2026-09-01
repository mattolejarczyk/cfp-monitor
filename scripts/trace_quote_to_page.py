"""Find the page that actually carries a cited quote, or withdraw the citation honestly.

THE PROBLEM IT SOLVES
A row claims a submission deadline and cites a page. Criterion 3 fetches that page and the
sentence is not there. Two very different things cause that, and the fix differs:

    the sentence moved      the call is live and the quote sits on a deeper page we can find
    the citation is unsound nothing on the site says it, so the claim has no evidence

This walks the event's own site looking for the sentence. Found: retarget the citation. Not
found: withdraw under R1 through `rules.withdrawal_changes`, which keeps the deadline, flips
IS_PROJECTED, downgrades the confidence label and decides the SOURCE_AS_OF stamp - all four,
because doing three of them was a defect twice on 2026-08-29.

WHAT IT IS NOT FOR: A PARAPHRASE
This retargets or withdraws. It has no re-extract path, so a quote that IS on the page in
slightly different characters gets withdrawn when it should be recut. On 2026-08-31 it
withdrew the Nineteenth International Conference on Climate Change, whose stored quote read
`Late, 20 October (26) to 20 December (26).` while the page carries the same row of a table as
`Late<tab><tab>20 October (26) to 20 December (26)`. The rounds table is genuinely there; our
copy of it had been reformatted.

    withdrawal      no evidence exists
    re-extraction   evidence exists and our copy of it is wrong  ->  extract_citations.py

Send a paraphrase here and a sound citation is lost. Check which problem you have first: the
acceptance gate distinguishes them, reporting "paraphrase, date IS on page" separately from
"quote and date both absent".

WHAT IT WILL NOT DO
`rules.may_withdraw_citation` refuses to withdraw when no page could be read, and when the
deadline has already passed. A call-for-papers page is routinely taken down after its deadline;
the sentence being gone then says nothing about whether the citation was sound when made. On
2026-08-29 an earlier version of this script proposed 18 withdrawals of which 14 were that case,
one with a deadline 317 days old. That output was discarded and the rule was written.

    python scripts/trace_quote_to_page.py --delivery <in.csv> --out <out.csv>
                                          [--rows <subset.csv>] [--only NAME]
                                          [--max-pages 14] [--dry-run]

`--rows` narrows to a subset by EVENT_ID or CONFERENCE - the usual input is a gate failure list.
Without it, every row carrying both a deadline and a citation is considered.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import re
import shutil
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import fetch as _f              # noqa: E402
from src.cfp_monitor import rules, sitewalk          # noqa: E402
from src.cfp_monitor.config import Settings          # noqa: E402

V15 = ["ORGANIZER", "SPONSOR_REQUIRED", "SPONSOR_URL", "SPONSOR_COST", "SPONSOR_QUOTE"]


def norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


class _Quiet:
    def log(self, *a, **k) -> None:
        pass


async def _render(url: str, settings):
    """The browser rung. `verify.fetch_text` deliberately skips the browser, which is right for
    checking dates at scale and wrong here: a quote on a JavaScript-rendered page would look
    absent, and this script DELETES a citation when it cannot find one."""
    try:
        _h, anchors, _st, body, _c = await _f._render_with_consent(url, settings, _Quiet(),
                                                                  prefer_cdp=True)
        return norm(body), anchors or []
    except Exception:                                                 # noqa: BLE001
        return "", []


async def trace(start_url: str, quote: str, settings, max_pages: int = 14):
    """Return (url_carrying_the_quote | None, pages_read, how).

    `pages_read` is what `rules.may_withdraw_citation` needs to tell "we looked and it is not
    there" from "we could not look" - the distinction this project keeps having to relearn.

    Only a FULL normalised match counts. An earlier version accepted a 35-character prefix,
    which would attach a citation to whichever page happened to share an opening phrase -
    worse than no citation, because it looks verified.
    """
    want = norm(quote)
    if not want:
        return None, 0, "no quote to trace"

    text, anchors = await _render(start_url, settings)
    seen, read_any = {start_url}, bool(text)
    if text and want in text:
        return start_url, 1, "on the cited page itself"

    queue, how = sitewalk.plan(anchors, start_url)
    while queue and len(seen) < max_pages:
        u = queue.pop(0)
        if u in seen:
            continue
        seen.add(u)
        t, anch = await _render(u, settings)
        if not t:
            continue
        read_any = True
        if want in t:
            return u, len(seen), f"found via {how}"
        for _sc, href, _lab in sitewalk.rank_links(anch, u)[:6]:
            if href not in seen and href not in queue:
                queue.append(href)
    return None, (len(seen) if read_any else 0), how


def _wanted(df: pd.DataFrame, rows_csv: str | None, only: str) -> pd.Series:
    sel = (df["DEADLINE_EVIDENCE_URL"].str.strip() != "") & \
          (df["DEADLINE_QUOTE"].str.strip() != "")
    if rows_csv:
        with open(rows_csv, encoding="utf-8-sig", newline="") as fh:
            subset = list(csv.DictReader(fh))
        ids = {(r.get("EVENT_ID") or "").strip() for r in subset} - {""}
        names = {(r.get("CONFERENCE") or "").strip().lower() for r in subset} - {""}
        sel &= (df["EVENT_ID"].isin(ids) | df["CONFERENCE"].str.lower().isin(names))
    if only:
        sel &= df["CONFERENCE"].str.contains(only, case=False, na=False, regex=False)
    return sel


async def main() -> int:
    ap = argparse.ArgumentParser(description="Trace cited quotes to the page carrying them.")
    ap.add_argument("--delivery", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rows", help="CSV of EVENT_ID/CONFERENCE to narrow to, e.g. a gate list")
    ap.add_argument("--only", default="", help="substring match on CONFERENCE")
    ap.add_argument("--max-pages", type=int, default=14)
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    a = ap.parse_args()
    today = date.fromisoformat(a.today)

    df = pd.read_csv(a.delivery, dtype=str, keep_default_na=False)
    stamps_before = df["SOURCE_AS_OF"].tolist()
    sel = _wanted(df, a.rows, a.only)
    targets = df[sel]
    print(f"{len(targets)} row(s) to trace out of {len(df)}\n")

    settings = Settings()
    traced = withdrawn = left = 0
    try:
        for n, (idx, row) in enumerate(targets.iterrows(), 1):
            r = row.to_dict()
            print(f"[{n}/{len(targets)}] {r['CONFERENCE'][:52]}   deadline "
                  f"{r['SUBMISSION DEADLINE'] or '(none)'}")
            deep, pages, how = await trace(r["DEADLINE_EVIDENCE_URL"], r["DEADLINE_QUOTE"],
                                           settings, a.max_pages)
            # R22 BEFORE the page content, on BOTH paths. Until 2026-08-31 this script asked
            # `may_withdraw_citation` - which enforces R22 - only when the quote was NOT found.
            # Finding it short-circuited straight to "traced", so an inadmissible host was
            # CONFIRMED for carrying the sentence. On the first real run that retained
            # `facebook.com/ACTExpo/` as evidence for a submission deadline, which is precisely
            # what R22 exists to forbid.
            #
            # A social post is not the organiser on the record whether or not the sentence is
            # on it. What the page says was never the question.
            if deep:
                ok, why22 = rules.citation_source_admissible(deep)
                if not ok:
                    deep = None
                    print(f"    REFUSED the page carrying the quote - {why22}")
            if deep:
                traced += 1
                df.at[idx, "DEADLINE_EVIDENCE_URL"] = deep
                df.at[idx, "SOURCE_AS_OF"] = today.isoformat()
                print(f"    TRACED -> {deep[:74]}\n           {how}\n")
                continue
            may, why = rules.may_withdraw_citation(r, quote_found=False, pages_read=pages,
                                                   today=today)
            if not may:
                left += 1
                print(f"    LEFT ALONE - {why}\n")
                continue
            withdrawn += 1
            for k, v in rules.withdrawal_changes(r, fetched=pages > 0, today=today).items():
                df.at[idx, k] = v
            print(f"    withdrawn (R1) - {why}\n")
    finally:
        try:
            await _f.close_fallback_browser()
        except Exception:                                             # noqa: BLE001
            pass

    df = df[[c for c in df.columns if c not in V15] + V15]
    moved = sum(1 for x, y in zip(stamps_before, df["SOURCE_AS_OF"]) if x != y)
    print("=" * 74)
    print(f"traced to a deeper page : {traced}")
    print(f"withdrawn under R1      : {withdrawn}")
    print(f"left alone by the rules : {left}")
    print(f"SOURCE_AS_OF advanced on {moved} row(s) - inspected rows only")
    if a.dry_run:
        print("DRY RUN - nothing written")
        return 0
    src = Path(a.delivery)
    shutil.copy2(src, src.with_suffix(".bak.csv"))
    df.to_csv(a.out, index=False, quoting=csv.QUOTE_ALL)
    print(f"wrote {a.out}; input backed up as {src.with_suffix('.bak.csv').name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
