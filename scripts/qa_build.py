"""QA report for the BUILD step: what Nicolia's team will see this week, against what they saw last.

    python scripts/qa_build.py                                   # newest two published weeks
    python scripts/qa_build.py --current <page.html> --previous <page.html> [--kind conference]

Run by `weekly_deliverable.py` after it builds, published or not. Writes
`runs_out/qa/<cycle>/build.md` and `.json` (shared shape: src/cfp_monitor/qa_report.py).

READS THE PAGES, NOT THE DATABASE. The page embeds every row it shows as `const DATA = [...]`, so
this reads exactly what the customer receives - which is the whole point of checking this step.
Anything upstream of the page could be right while the page is wrong. It also means past weeks can
be compared from the pages already sent, with no history table needed.

WHAT IT ASKS
    what the page shows    rows by market, edition state, status, confidence, check verdict,
                           dead links, deadlines closing this week / this month
    what changed           rows added or removed, likely renames, moved deadlines, changed status,
                           confidence or verdict, links that died
    what to look at        a deadline that moved EARLIER, a row that disappeared, an Open row
                           whose deadline has passed, a disputed deadline, a dead link on an open call

Counts and row names only. It changes nothing.
"""
from __future__ import annotations

import argparse
import collections
import difflib
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import qa_report                                # noqa: E402
from src.cfp_monitor.grounding import parse_loose_date               # noqa: E402
from src.cfp_monitor.lifecycle import SOON_DAYS, URGENT_DAYS         # noqa: E402

WEEKLY = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\handoff-files\weekly")
KINDS = {"conference": "Conference Review", "awards": "Awards Review"}
# Contract v2.5 (2026-09-14): Registration is not an opportunity. The first report found SIX rows
# on the page Nicolia already had that had moved from Speaking to Registration between Sep 1 and
# Sep 14 - built the morning the label was retired, from a delivery made before it.
RETIRED_OPPORTUNITIES = {"Registration"}


def page_data(path: Path) -> list[dict]:
    """The rows a page shows, read from the page itself."""
    text = Path(path).read_text(encoding="utf-8")
    i = text.index("const DATA = ") + len("const DATA = ")
    rows, _ = json.JSONDecoder().raw_decode(text[i:])
    return rows


def page_date(path: Path) -> date | None:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", Path(path).name)
    return date.fromisoformat(m.group(1)) if m else None


def published_pages(kind: str, weekly: Path = WEEKLY) -> list[Path]:
    """Published pages of one kind, oldest first. Only dated publish folders - never `work_*`,
    which holds pages that may have been refused publication."""
    out = []
    for d in sorted(p for p in weekly.glob("*") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name)):
        out += sorted(d.glob(f"{KINDS[kind]}*.html"))
    return [p for p in out if "(evidence)" not in p.name]


def _key(r: dict) -> tuple:
    return (r.get("m", ""), r.get("n", ""), r.get("op", ""))


def _yes(v) -> bool:
    return str(v).strip().lower() == "true"


def _days(r: dict, field: str, on: date) -> int | None:
    d = parse_loose_date(r.get(field) or "")
    return None if d is None else (d - on).days


def shows(rows: list[dict], on: date) -> dict[str, int]:
    """The numbers a reader of the page would take away, as of the day it was built."""
    c: dict[str, int] = collections.OrderedDict()
    c["Rows"] = len(rows)
    for m, n in sorted(collections.Counter(r.get("m") for r in rows).items()):
        c[f"  market: {m}"] = n
    for label, field in (("edition", "st"), ("status", "s"), ("confidence", "c")):
        for v, n in sorted(collections.Counter(r.get(field) or "(blank)" for r in rows).items()):
            c[f"  {label}: {v}"] = n
    verdicts = collections.Counter(r.get("chk") or "not checked" for r in rows)
    for v, n in sorted(verdicts.items()):
        c[f"  check: {v}"] = n
    c["Closing within 7 days"] = sum(1 for r in rows
                                     if (d := _days(r, "dl", on)) is not None and 0 <= d <= URGENT_DAYS)
    c["Closing within 30 days"] = sum(1 for r in rows
                                      if (d := _days(r, "dl", on)) is not None and 0 <= d <= SOON_DAYS)
    c["Any dead link"] = sum(1 for r in rows if any(_yes(r.get(k)) for k in ("dead", "evdead", "urldead")))
    c["With sponsorship info"] = sum(1 for r in rows if _yes(r.get("spon")))
    c["With lifecycle evidence"] = sum(1 for r in rows if (r.get("lq") or "").strip())
    return c


def _plain(name: str) -> str:
    """A name without its bracketed gloss, case or punctuation."""
    n = re.sub(r"\([^)]*\)", " ", (name or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


def same_event(gone: list[tuple], new: list[tuple], pb: dict, cb: dict) -> list[tuple]:
    """Pair rows that left the page with rows that arrived, when they are one event renamed.

    Name similarity alone reported 11 of 13 renames on the 2026-09-14 page as a removal plus an
    addition - "ADIPEC 2026 (Abu Dhabi International Petroleum Exhibition & Conference)" became
    "ADIPEC 2026", "CyberTech" became "Cybertech". A report that cries wolf eleven times is not
    read the twelfth. So, in order of strength, within one market, one-to-one:
        the same conference website; the same name once the bracketed gloss, case and punctuation
        are gone, or one such name starting the other; a close match on those plain names.
    Opportunity type is deliberately NOT required to agree: v2.5 retired a label mid-series.
    """
    pairs, used = [], set()
    for test in ("url", "plain", "close"):
        for g in gone:
            if any(g == a for a, _ in pairs):
                continue
            cands = [k for k in new if k[0] == g[0] and k not in used]
            hit = None
            if test == "url":
                u = (pb[g].get("url") or "").strip().rstrip("/").lower()
                hit = next((k for k in cands
                            if u and (cb[k].get("url") or "").strip().rstrip("/").lower() == u), None)
            elif test == "plain":
                pg = _plain(g[1])
                hit = next((k for k in cands if pg and (_plain(k[1]) == pg or _plain(k[1]).startswith(pg)
                                                        or pg.startswith(_plain(k[1])))), None)
            else:
                m = difflib.get_close_matches(_plain(g[1]), [_plain(k[1]) for k in cands], 1, 0.75)
                hit = next((k for k in cands if m and _plain(k[1]) == m[0]), None)
            if hit:
                pairs.append((g, hit))
                used.add(hit)
    return pairs


def compare(cur_rows: list[dict], prev_rows: list[dict] | None, on: date, kind: str) -> dict:
    report_rows, flags, changes = [], [], []
    now = shows(cur_rows, on)
    before = shows(prev_rows, on) if prev_rows is not None else {}
    for k in list(now) + [k for k in before if k not in now]:
        report_rows.append([k, before.get(k, 0 if prev_rows is not None else None), now.get(k, 0),
                            qa_report.change(before.get(k, 0) if prev_rows is not None else None,
                                             now.get(k, 0))])

    label = KINDS[kind]
    # Open, deadline passed - what gate check 6 refuses in a delivery, measured on the page itself.
    for r in cur_rows:
        d = _days(r, "dl", on)
        if r.get("s") == "Open" and d is not None and d < 0:
            flags.append(f"{label}: {r['n']} ({r['m']}) shows Open with a deadline {-d} day(s) past")
        if r.get("chk") == "contradicted":
            flags.append(f"{label}: {r['n']} ({r['m']}) - its cited page DISPUTES the deadline")
        if r.get("s") == "Open" and _yes(r.get("urldead")):
            flags.append(f"{label}: {r['n']} ({r['m']}) is Open but its submission link is dead")
        if (r.get("op") or "") in RETIRED_OPPORTUNITIES:
            flags.append(f"{label}: {r['n']} ({r['m']}) is labelled '{r['op']}', which contract "
                         f"v2.5 retired - it is not an opportunity")

    if prev_rows is not None:
        pb = {_key(r): r for r in prev_rows}
        cb = {_key(r): r for r in cur_rows}
        gone = [k for k in pb if k not in cb]
        new = [k for k in cb if k not in pb]
        renamed = same_event(gone, new, pb, cb)
        r_from = {a for a, _ in renamed}
        r_to = {b for _, b in renamed}
        for k in new:
            if k not in r_to:
                changes.append([k[1], k[0], "added", "", ""])
        for k in gone:
            if k not in r_from:
                changes.append([k[1], k[0], "REMOVED", "", ""])
                flags.append(f"{label}: {k[1]} ({k[0]}) was on last week's page and is gone")
        for a, b in renamed:
            if a[1] != b[1]:
                changes.append([b[1], b[0], "renamed", a[1], b[1]])
            if a[2] != b[2]:
                # Same event, different opportunity label - it-sa and SIEW on 2026-09-14, after
                # v2.5 retired Registration. Not a rename, and worth naming as what it is.
                changes.append([b[1], b[0], "opportunity type", a[2] or "(blank)", b[2] or "(blank)"])
        pairs = [(k, k) for k in cb if k in pb] + [(a, b) for a, b in renamed]
        for a, b in pairs:
            p, c = pb[a], cb[b]
            for field, what in (("dl", "deadline"), ("s", "status"), ("c", "confidence"),
                                ("chk", "check"), ("st", "edition")):
                if (p.get(field) or "") != (c.get(field) or ""):
                    changes.append([c["n"], c["m"], what, p.get(field) or "(blank)",
                                    c.get(field) or "(blank)"])
            pd_, cd_ = parse_loose_date(p.get("dl") or ""), parse_loose_date(c.get("dl") or "")
            if pd_ and cd_ and cd_ < pd_:
                flags.append(f"{label}: {c['n']} ({c['m']}) deadline moved EARLIER, "
                             f"{pd_.isoformat()} -> {cd_.isoformat()}")
            if pd_ and not cd_:
                flags.append(f"{label}: {c['n']} ({c['m']}) lost its deadline "
                             f"({pd_.isoformat()} last week)")
            for k, what in (("urldead", "submission link"), ("evdead", "evidence link")):
                if not _yes(p.get(k)) and _yes(c.get(k)):
                    changes.append([c["n"], c["m"], f"{what} died", "", ""])
    return {"counts": report_rows, "changes": changes, "flags": flags}


def build(pairs: list[tuple[str, Path, Path | None]], on: date, published: bool | None) -> dict:
    rep = qa_report.new_report("build", on)
    rep["published"] = published
    if published is False:
        rep["flags"].append("NOT PUBLISHED - the build was DEGRADED; these pages must not be sent")
    for kind, cur, prev in pairs:
        cur_rows = page_data(cur)
        prev_rows = page_data(prev) if prev else None
        res = compare(cur_rows, prev_rows, page_date(cur) or on, kind)
        was = page_date(prev).isoformat() if prev else "none"
        now = (page_date(cur) or on).isoformat()
        rep["sections"].append({
            "title": f"{KINDS[kind]} - what the page shows",
            "note": f"This page: `{Path(cur).name}`  \nCompared with: `{Path(prev).name if prev else 'none - first page'}`",
            "columns": ["", f"Previous page ({was})", f"This page ({now})", "Change"],
            "rows": res["counts"], "flags": []})
        rep["sections"].append({
            "title": f"{KINDS[kind]} - what changed for the reader",
            "columns": ["Conference", "Market", "What changed", "Was", "Now"],
            "rows": sorted(res["changes"], key=lambda x: (x[2], x[1], x[0])),
            "flags": res["flags"]})
        rep["flags"] += res["flags"]
    return qa_report.finish(rep, "nothing on the pages needs a look before sending")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--current", nargs="*", help="page(s) built this week")
    ap.add_argument("--previous", nargs="*", help="the matching previous page(s), same order")
    ap.add_argument("--weekly", default=str(WEEKLY))
    ap.add_argument("--published", choices=["yes", "no"], help="did this week's build publish?")
    ap.add_argument("--on", default="", help="date the pages describe (default: from file name)")
    ap.add_argument("--out", default=str(qa_report.QA_ROOT))
    a = ap.parse_args()

    pairs: list[tuple[str, Path, Path | None]] = []
    if a.current:
        prevs = a.previous or []
        for i, c in enumerate(a.current):
            kind = "awards" if Path(c).name.startswith(KINDS["awards"]) else "conference"
            p = Path(prevs[i]) if i < len(prevs) and prevs[i] else None
            if p is None:
                earlier = [x for x in published_pages(kind, Path(a.weekly))
                           if (page_date(x) or date.min) < (page_date(Path(c)) or date.max)]
                p = earlier[-1] if earlier else None
            pairs.append((kind, Path(c), p))
    else:
        for kind in KINDS:
            pages = published_pages(kind, Path(a.weekly))
            if pages:
                pairs.append((kind, pages[-1], pages[-2] if len(pages) > 1 else None))
    if not pairs:
        print("no pages found to report on")
        return 0

    on = date.fromisoformat(a.on) if a.on else (page_date(pairs[0][1]) or date.today())
    rep = build(pairs, on, None if a.published is None else a.published == "yes")
    md = qa_report.to_markdown(rep, "Build QA - what the customer will see")
    print(md)
    try:
        print(f"wrote {qa_report.write(rep, md, Path(a.out))}")
    except OSError as exc:
        print(f"could not write QA report: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
