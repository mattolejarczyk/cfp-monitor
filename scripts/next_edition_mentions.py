"""Closed rows whose event has ended and whose own text announces a NEXT EDITION with dates (ACT-33, 2026-10-11). Free: reads two files and the database, makes no request, changes nothing.

    python scripts/next_edition_mentions.py [--today YYYY-MM-DD] [--markets-dir <dir>] [--db <db>] [--out-dir <dir>]

WHY. The conference refresh policy researches an ended event once, two to three weeks after it ends, and then only on a slow rotation. The one thing that makes an ended row worth another
look sooner is the organiser saying when the NEXT edition is. A rough scan on 2026-10-11 found 13 of 55 ended rows doing so. This lists them for the operator: the sentence, the row id, and
whether a SUCCESSOR row (same conference_key, a later edition) already exists in the database, which is the cheap answer to 'did we already pick it up'. A row with no successor is the
candidate for docs/operations/refresh_overrides.txt or for a new row on the research list.

WHAT COUNTS. A row is read when STATUS is Closed and the event END (the end of CONFERENCE DATES, else START DATE) is before today. A sentence of STATUS DETAILS, NOTES, OVERVIEW or LIFECYCLE_QUOTE is
a mention when it carries a next-edition cue (next edition, next year, returns, will be held, save the date, a later year than the event's own, 'edition' with a later year) AND a date (a month with
a day, or a month with a later year). Sentences about the event that just ended are not listed. It is a rough text scan: a person reads each sentence; nothing here is a fact about the event.
OUTPUT runs_out/qa/<date>/next_editions.md and .csv; one summary line `NEXT-EDITIONS: ...`. Always exits 0."""
from __future__ import annotations

import argparse
import csv
import os
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
LIVE = Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor"
FIELDS = ("STATUS DETAILS", "NOTES", "OVERVIEW", "LIFECYCLE_QUOTE")
MON = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
CUE = re.compile(r"next (?:edition|year|event|iteration)|returns?\b|returning|will (?:be held|take place|return|be back)|save the date|upcoming edition|announced for|scheduled for|set for|dates? (?:for|announced)|"
                 r"\b20\d\d (?:edition|event)|edition (?:in|of) 20\d\d", re.I)
DAYMON = re.compile(rf"(?:\b{MON}\s+\d{{1,2}}\b|\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{MON}\b)", re.I)
MONYEAR = re.compile(rf"\b{MON}\s+(20\d\d)\b", re.I)


def sentences(text: str) -> list[str]:
    t = " ".join((text or "").split())
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\[\"(])", t) if s.strip()]


WORD = re.compile(r"edition|annual|promoting|summit|congress|forum|conference|event|expo|dates|location|coming soon", re.I)


def mentions(text: str, event_year: int, with_dates: bool = True) -> list[str]:
    """The sentences of `text` that announce a later edition. with_dates=True: ones that also give a date (a month with a day, or a month with a later year). with_dates=False: the
    sentences that name a later year in a next-edition context but give NO date ('the site now promotes the 2027 edition', 'dates coming soon')."""
    out = []
    for s in sentences(text):
        years = [int(y) for y in re.findall(r"\b(20\d\d)\b", s)]
        later = [y for y in years if y > event_year]
        has_date = bool(DAYMON.search(s)) or any(int(m.group(1)) > event_year for m in MONYEAR.finditer(s))
        if with_dates:
            if has_date and (CUE.search(s) or later) and (later or re.search(r"next (?:edition|year)|save the date|returns?\b|will return", s, re.I)):
                out.append(s)
        elif later and not has_date and (CUE.search(s) or WORD.search(s)):
            out.append(s)
    return out


def _tokens(name: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", re.sub(r"\b\d+(?:st|nd|rd|th)?\b", " ", (name or "").lower())) if len(w) > 1 and w not in ("the", "and", "annual", "conference", "summit", "global")}


def same_series(a: str, b: str) -> bool:
    """Two edition names are one series when they share at least 75 percent of the longer name's distinctive words (years and filler words ignored)."""
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and len(ta & tb) / max(len(ta), len(tb)) >= 0.75


def successors(db: Path, conference_key: str, event_id: str, key_year: str, end: date, name: str = "") -> list[dict]:
    """Rows of the database with the same conference_key, a LATER edition (key_year above this one; when a key_year is blank, a start in a later year) and the same series name
    (a host that runs many events, such as SecureWorld, shares one conference_key)."""
    con = sqlite3.connect(f"file:{str(db).replace(chr(92), '/')}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        out = []
        for r in con.execute("select event_id, name, start_date, key_year from grounding_facts where conference_key = ? and event_id != ?", (conference_key, event_id)):
            ky, sd = (r["key_year"] or ""), (r["start_date"] or "")
            later = int(ky) > int(key_year) if (ky.isdigit() and key_year.isdigit()) else sd[:4].isdigit() and int(sd[:4]) > end.year
            if later and (not name or same_series(name, r["name"] or "")):
                out.append({"event_id": r["event_id"], "name": r["name"], "start_date": sd, "key_year": ky})
        return out
    finally:
        con.close()


def scan(rows: list[dict], market: str, today: date, db: Path, up_to_canon: dict[str, str], input_rows: list[dict] | None = None) -> tuple[list[dict], int]:
    """(findings, ended_rows). One finding per ended Closed row that mentions a next edition."""
    from scripts.refresh_plan import event_dates
    from src.cfp_monitor.identity import to_canonical
    con = sqlite3.connect(f"file:{str(db).replace(chr(92), '/')}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    info = {r["event_id"]: dict(r) for r in con.execute("select event_id, conference_key, key_year from grounding_facts")}
    con.close()
    findings, ended = [], 0
    for r in rows:
        if (r.get("STATUS") or "").strip().lower() != "closed":
            continue
        start, end, _why = event_dates(r)
        if end is None or end >= today:
            continue
        ended += 1
        canon = to_canonical((r.get("EVENT_ID") or "").strip(), up_to_canon)
        hits = []
        for f in FIELDS:
            hits += [(f, s) for s in mentions(r.get(f, ""), end.year)]
        weak = [] if hits else [(f, s) for f in FIELDS for s in mentions(r.get(f, ""), end.year, with_dates=False)]
        if not hits and not weak:
            continue
        d = info.get(canon) or {}
        succ = successors(db, d["conference_key"], canon, d.get("key_year") or "", end, r.get("CONFERENCE", "")) if d.get("conference_key") else []
        # the research list may already hold the next edition before the database does (a new event waiting for its first load)
        listed = [x.get("CONFERENCE", "") for x in (input_rows or []) if same_series(r.get("CONFERENCE", ""), x.get("CONFERENCE", ""))
                  and (to_canonical((x.get("EVENT_ID_CANON") or "").strip(), up_to_canon) != canon)
                  and any(int(y) > end.year for y in re.findall(r"(20[0-9][0-9])", (x.get("CONFERENCE", "") + " " + (x.get("EDITION") or ""))))]
        findings.append({"market": market, "canonical": canon, "conference": r.get("CONFERENCE", ""), "ended": end.isoformat(), "hits": hits or weak, "tier": "dates" if hits else "no dates",
                         "successors": succ, "listed": listed, "known": bool(d)})
    return findings, ended


def report(findings: list[dict], ended: int, today: date) -> tuple[str, str]:
    dated = [f for f in findings if f["tier"] == "dates"]
    no_succ = [f for f in findings if not f["successors"] and not f["listed"]]
    line = (f"NEXT-EDITIONS: {len(dated)} of {ended} ended Closed rows mention a next edition WITH dates and {len(findings) - len(dated)} more name a later year without dates; "
            f"{len(no_succ)} of the {len(findings)} have no successor row in the database or on the research list (candidates for refresh_overrides.txt or a new research row)")
    md = [f"# Next editions mentioned by ended Closed rows ({today})", "", line, "",
          "A rough text scan; a person reads each sentence. It makes no request and changes nothing. 'Successor row' = the database holds another edition of the same conference_key that is later.", ""]
    for f in sorted(findings, key=lambda x: (x["tier"] != "dates", bool(x["successors"]), x["market"], x["conference"])):
        md.append(f"## {f['conference']} ({f['market']}, id `{f['canonical']}`, ended {f['ended']}; next edition: {f['tier'] if f['tier'] == 'dates' else 'named, no dates given'})")
        md.append("- successor row: " + ("; ".join(f"{s['name']} ({s['event_id']}, starts {s['start_date'] or 'unknown'})" for s in f["successors"]) if f["successors"]
                                          else "**NONE** - no later edition of this conference_key in the database"))
        if f["listed"] and not f["successors"]:
            md.append("- on the research list, not yet in the database: " + "; ".join(f["listed"]))
        for fld, s in f["hits"]:
            md.append(f"- {fld}: {s}")
        md.append("")
    return line, "\n".join(md)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--db", default=str(LIVE / "cfp_monitor.db"))
    ap.add_argument("--out-dir", default="")
    a = ap.parse_args(argv)
    try:
        today = date.fromisoformat(a.today)
        out_dir = Path(a.out_dir) if a.out_dir else LIVE / "runs_out" / "qa" / today.isoformat()
        from src.cfp_monitor.identity import seed_map
        up_to_canon, _ = seed_map(a.db)
        findings, ended = [], 0
        for m in ("Cybersecurity", "Utility"):
            p = Path(a.markets_dir) / f"{m}_audited.final.csv"
            if not p.exists():
                continue
            inp = Path(a.markets_dir) / f"{m}_input.csv"
            input_rows = []
            if inp.exists():
                with open(inp, encoding="utf-8-sig", newline="") as fh:
                    input_rows = list(csv.DictReader(fh))
            with open(p, encoding="utf-8-sig", newline="") as fh:
                f_, e_ = scan(list(csv.DictReader(fh)), m, today, Path(a.db), up_to_canon, input_rows)
            findings += f_
            ended += e_
        line, md = report(findings, ended, today)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "next_editions.md").write_text(md + "\n", encoding="utf-8")
        with open(out_dir / "next_editions.csv", "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, quoting=csv.QUOTE_ALL)
            w.writerow(["market", "canonical_id", "conference", "ended", "tier", "successor_row", "field", "sentence"])
            for f in findings:
                for fld, s in f["hits"]:
                    w.writerow([f["market"], f["canonical"], f["conference"], f["ended"], f["tier"], "; ".join(x["event_id"] for x in f["successors"]) or ("LISTED: " + "; ".join(f["listed"]) if f["listed"] else "NONE"), fld, s])
        print(line)
        print(f"  report: {out_dir / 'next_editions.md'}")
    except Exception as e:                                           # noqa: BLE001  a free report must never stop anything
        print(f"NEXT-EDITIONS: UNKNOWN - {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
