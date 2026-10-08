"""INPUT-LIST AUDIT (ACT-59): read-only check of every hint on the research input lists against the row's own pages.

    python scripts/input_list_audit.py --lists <dir holding Cybersecurity_input.csv and Utility_input.csv> --out-dir <scratch> [--limit 10] [--today YYYY-MM-DD] [--max-usd 0.30] [--dry-run]

WHY. The research starts from the hints in Markets/<Market>_input.csv (START DATE, CONFERENCE DATES, LOCATION, SUBMISSION DEADLINE). Our year checks (Y1-Y4, start_date_arbiter) judge
rows of a DELIVERY, never these hints. Decarb Connect Europe 2027 said Hamburg, June 8-10 2027 while the event's page says 14-15 April 2027, Vienna; Nullcon Goa carried the speaker-announcement
date as its deadline. A hint is only as good as a page that states it FOR THAT EDITION.
WHAT IT DOES. Per row, the row's own pages (CONFERENCE URL, SUBMISSION URL: the page library first, then a plain fetch, then a Chrome render when the text has no dates) are read in ONE call by the cheap model
(experiments/read_the_page_pass run.ask_with, own request log and cost cap). A value is accepted only by code: the quote is literally on the page, a date states day, month and the edition's year
(pass_lib.accept; a 2026 date never proves 2027), a deadline states day, month, year and uses call wording and falls in the year of the edition or the year before.
Per field a verdict:
  AGREES       the page proves the same value as the hint
  DIFFERS      the page proves another value (the verbatim quote and page are given)
  UNSUPPORTED  the hint is there but no page states it for this edition (the reason is given: unreadable page, edition not mentioned, field not stated, ...). Unproven, NOT wrong
  FILLS        the hint is blank and the page proves a value
  NO_VALUE     the hint is blank and the page proves nothing
Fields: START DATE, CONFERENCE DATES (first and last day), LOCATION (city and country), SUBMISSION DEADLINE.
OUTPUT (all under --out-dir): input_audit.csv (every row x field), proposed_corrections.csv (for the reviewer, who applies it to the input lists with backups: a correction for DIFFERS and FILLS,
the honest blank for UNSUPPORTED when the page was readable, nothing proposed when no page could be read), input_audit.md (counts and lists), input_audit.json. It also lists rows whose id year is not
the edition (frozen keys by design: upstream's ids never change, so a 2026 id on a 2027 row is not an error).
GUARANTEES. Never writes the input lists or the database, never emails, never sends anything. Reads the network (<= 2 pages per row) and calls the cheap model under its own cap (--max-usd, default 0.30)."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "scripts", ROOT / "experiments" / "sitemap_discovery", ROOT / "experiments" / "sentence_picking"):
    sys.path.insert(0, str(p))

FIELDS = ("START DATE", "CONFERENCE DATES", "LOCATION", "SUBMISSION DEADLINE")
URL_COLS = ("CONFERENCE URL", "SUBMISSION URL")
PAGE_CHARS = 7000
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

SYSTEM = """You read the web page(s) of ONE conference and report facts about ONE edition of it.
You are given the event name and the EDITION YEAR. Report ONLY what the page states for that edition.
For each field return {"value": ..., "quote": ...}. The quote must be copied EXACTLY, as a literal substring of the page text (do not fix, shorten or join).
If the page does not state the field for that edition, return {"value": "", "quote": ""}. NEVER infer, never use another edition's dates or place, never use your own knowledge of the event.
If the page shows a different edition than the one asked (the dates or title are for the previous or the next year), every field is blank.
Fields:
  start_date  ISO YYYY-MM-DD, the first day of the event itself (not a call for papers, registration or sponsor date)
  end_date    ISO YYYY-MM-DD, the last day of the event itself
  city        the city where the event is held (not the venue name)
  country     the country where it is held (if only a state or province is named, quote that sentence and return its country)
  deadline    ISO YYYY-MM-DD, the last day to SUBMIT a talk, paper, abstract, proposal or speaker application for this edition; if there are several rounds report the one that closes next.
              NEVER report registration, early-bird, speaker-announcement, notification, camera-ready or event dates. The quote must be the sentence that states the date.
SEVERAL DATE RANGES: if the page labels separate ranges (training, workshop, hackathon, conference), use only the range the page itself labels as the conference.
Return ONLY JSON: {"start_date":{"value":"","quote":""},"end_date":{...},"city":{...},"country":{...},"deadline":{...}}."""

CALL_WORDS = re.compile(r"deadline|submit|submission|abstract|proposal|call for|cfp|closes?|closing|close\b|due|applications?|speaker|paper", re.I)


# ---------------------------------------------------------------- parsing of OUR hints
def to_iso(s: str) -> str:
    """'1/15/2027' or '2027-01-15' -> '2027-01-15'; anything else -> ''."""
    s = (s or "").strip()
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat()
        except ValueError:
            return ""
    return s[:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", s) else ""


def _mon(w: str) -> int:
    return MONTHS.get((w or "").lower()[:3], 0)


def parse_range(text: str) -> tuple[str, str]:
    """'April 14 - April 15, 2027' / 'June 8-10, 2027' / '8-10 June 2027' / 'November 3, 2026' -> (start ISO, end ISO); ('','') when it cannot be read."""
    t = re.sub(r"\s+", " ", (text or "").replace("–", "-").replace("—", "-")).strip()
    W = r"([A-Za-z]{3,9})\.?"
    try:
        m = re.search(rf"{W} (\d{{1,2}})(?:st|nd|rd|th)?(?:,? (\d{{4}}))? ?(?:-|to) ?{W} (\d{{1,2}})(?:st|nd|rd|th)?,? (\d{{4}})", t)
        if m and _mon(m[1]) and _mon(m[4]):
            y2 = int(m[6])
            return date(int(m[3] or y2), _mon(m[1]), int(m[2])).isoformat(), date(y2, _mon(m[4]), int(m[5])).isoformat()
        m = re.search(rf"{W} (\d{{1,2}})(?:st|nd|rd|th)? ?(?:-|to) ?(\d{{1,2}})(?:st|nd|rd|th)?,? (\d{{4}})", t)
        if m and _mon(m[1]):
            return date(int(m[4]), _mon(m[1]), int(m[2])).isoformat(), date(int(m[4]), _mon(m[1]), int(m[3])).isoformat()
        m = re.search(rf"(\d{{1,2}})(?:st|nd|rd|th)? ?(?:-|to) ?(\d{{1,2}})(?:st|nd|rd|th)? {W},? (\d{{4}})", t)
        if m and _mon(m[3]):
            return date(int(m[4]), _mon(m[3]), int(m[1])).isoformat(), date(int(m[4]), _mon(m[3]), int(m[2])).isoformat()
        m = re.search(rf"{W} (\d{{1,2}})(?:st|nd|rd|th)?,? (\d{{4}})", t)
        if m and _mon(m[1]):
            d = date(int(m[3]), _mon(m[1]), int(m[2])).isoformat()
            return d, d
        m = re.search(rf"(\d{{1,2}})(?:st|nd|rd|th)? {W},? (\d{{4}})", t)
        if m and _mon(m[2]):
            d = date(int(m[3]), _mon(m[2]), int(m[1])).isoformat()
            return d, d
    except ValueError:
        return "", ""
    return "", ""


def edition_of(row: dict) -> str:
    e = (row.get("EDITION") or "").strip()
    if re.fullmatch(r"20\d\d", e):
        return e
    return (to_iso(row.get("START DATE", "")) or "")[:4]


def id_year_mismatch(rows: list[dict]) -> list[dict]:
    """Rows whose id year differs from the edition (frozen keys by design)."""
    out = []
    for r in rows:
        m = re.match(r"(20\d\d)-", r.get("EVENT_ID_CANON") or "")
        ed = edition_of(r)
        if m and ed and m.group(1) != ed:
            out.append({"market": r.get("_market", ""), "id": r["EVENT_ID_CANON"], "conference": r.get("CONFERENCE", ""), "id_year": m.group(1), "edition": ed})
    return out


# ---------------------------------------------------------------- code acceptance of the reader's claims
def accept_deadline(item: dict, page: str, edition: str) -> tuple[str, str]:
    """(ISO value or '', why). Quote on the page, states day+month+year, call wording, year = the edition's or the year before (a call closes before the event)."""
    from experiments.read_the_page_pass import pass_lib as L
    from scripts.start_date_arbiter import expand_ranges
    from src.cfp_monitor.verify import find_date
    value, quote = (item or {}).get("value", ""), (item or {}).get("quote", "")
    if not value or not quote:
        return "", "blank"
    if L.norm(quote) not in L.norm(page):
        return "", "quote is not on the page"
    try:
        d = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return "", "not an ISO date"
    if not find_date(expand_ranges(quote), d):
        return "", "the quote does not state that day, month and year"
    if not CALL_WORDS.search(quote):
        return "", "the quote has no call wording"
    if edition and str(d.year) not in (edition, str(int(edition) - 1)):
        return "", f"deadline year {d.year} is not the edition's year ({edition}) or the year before"
    return value, "ok"


def accept_all(fields: dict | None, text: str, edition: str) -> dict:
    """{key: (value, why, quote)} for start_date, end_date, city, country, deadline."""
    from experiments.read_the_page_pass import pass_lib as L
    out = {}
    for k in ("start_date", "end_date", "city", "country", "deadline"):
        item = (fields or {}).get(k) or {}
        if not text.strip():
            out[k] = ("", "page unreadable", "")
            continue
        got, why = accept_deadline(item, text, edition) if k == "deadline" else L.accept(k, item, text, edition)
        out[k] = (got, why, item.get("quote", "") if got else "")
    return out


def _fmt_us(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.month}/{d.day}/{d.year}"


def _fmt_range(s: str, e: str) -> str:
    a, b = date.fromisoformat(s), date.fromisoformat(e)
    ma, mb = a.strftime("%B"), b.strftime("%B")
    if s == e:
        return f"{ma} {a.day}, {a.year}"
    return f"{ma} {a.day} - {mb} {b.day}, {b.year}"


def _why_none(why: str, text: str, edition: str) -> str:
    """The honest reason a field is UNSUPPORTED."""
    if not text.strip():
        return "no page could be read"
    if not edition or edition in text:
        note = ""
    else:
        seen = sorted(set(re.findall(r"(?<!\d)(20[12]\d)(?!\d)", text)))
        note = f"; the page text never mentions {edition}" + (f" (it shows {', '.join(seen)})" if seen else "")
    return (why if why and why != "blank" else "the page states nothing for this field and edition") + note


def judge(row: dict, acc: dict, text: str, edition: str, pages: list[str]) -> dict:
    """{field: {verdict, ours, page, quote, url, why}} for the four fields of one row."""
    from scripts.shadow_reader import compare_field
    from src.cfp_monitor.regions import country_matches
    res = {}

    def mk(field, verdict, ours, page_val="", quote="", why=""):
        url = ""
        if quote:
            from experiments.read_the_page_pass import pass_lib as L
            url = next((u for u, t in _PAGES.get(row.get("_key", ""), []) if L.norm(quote) in L.norm(t)), pages[0] if pages else "")
        res[field] = {"verdict": verdict, "ours": ours, "page": page_val, "quote": quote, "url": url, "why": why}

    # START DATE
    ours = to_iso(row.get("START DATE", ""))
    got, why, q = acc["start_date"]
    if got:
        mk("START DATE", "AGREES" if ours == got else ("DIFFERS" if ours else "FILLS"), row.get("START DATE", ""), got, q, why)
    else:
        mk("START DATE", "UNSUPPORTED" if ours else "NO_VALUE", row.get("START DATE", ""), why=_why_none(why, text, edition))
    # CONFERENCE DATES
    ours_txt = (row.get("CONFERENCE DATES") or "").strip()
    os_, oe = parse_range(ours_txt) if ours_txt else ("", "")
    gs, whys, qs = acc["start_date"]
    ge, whye, qe = acc["end_date"]
    if gs and ge:
        pv = f"{gs} to {ge}"
        if not ours_txt:
            mk("CONFERENCE DATES", "FILLS", "", pv, qs if qs == qe else f"{qs} || {qe}", "ok")
        elif not os_:
            mk("CONFERENCE DATES", "UNSUPPORTED", ours_txt, pv, qs, "our text could not be parsed into days; compare by hand")
        else:
            mk("CONFERENCE DATES", "AGREES" if (os_, oe) == (gs, ge) else "DIFFERS", ours_txt, pv, qs if qs == qe else f"{qs} || {qe}", "ok")
    elif gs and not ge and os_ and gs != os_:
        mk("CONFERENCE DATES", "DIFFERS", ours_txt, f"{gs} to ?", qs, "first day differs; last day not proven")
    else:
        part = f"; first day {'proven' if gs else 'not proven'}, last day {'proven' if ge else 'not proven'}" if (gs or ge) else ""
        mk("CONFERENCE DATES", "UNSUPPORTED" if ours_txt else "NO_VALUE", ours_txt, why=_why_none(whye if not ge else whys, text, edition) + part)
    # LOCATION
    ours_loc = (row.get("LOCATION") or "").strip()
    city, wc, qc = acc["city"]
    ctry, wy, qy = acc["country"]
    if city or ctry:
        parts, bad = [], []
        if city:
            rel = compare_field("city", ours_loc, city, qc)
            parts.append(f"city {city}")
            if rel == "differs":
                bad.append("city")
        if ctry:
            last = [x.strip() for x in ours_loc.split(",") if x.strip()][-1] if ours_loc else ""
            ok_c = bool(last) and (country_matches(ctry, last) or country_matches(last, ctry) or re.sub(r"[^a-z]", "", ctry.lower()) in re.sub(r"[^a-z]", "", ours_loc.lower()))
            alias = {"usa": "united states", "us": "united states", "uk": "united kingdom"}
            if not ok_c and alias.get(re.sub(r"[^a-z ]", "", last.lower()).strip(), "") == ctry.lower():
                ok_c = True
            parts.append(f"country {ctry}")
            if ours_loc and not ok_c:
                bad.append("country")
        quote = qc if qc and (not qy or qc == qy) else (f"{qc} || {qy}" if qc and qy else (qc or qy))
        if not ours_loc:
            mk("LOCATION", "FILLS", "", ", ".join(parts), quote, "ok")
        elif bad:
            mk("LOCATION", "DIFFERS", ours_loc, ", ".join(parts), quote, "differs in " + " and ".join(bad))
        elif city and ctry:
            mk("LOCATION", "AGREES", ours_loc, ", ".join(parts), quote, "ok")
        else:
            mk("LOCATION", "UNSUPPORTED", ours_loc, ", ".join(parts), quote, "only the " + ("city" if city else "country") + " is proven (it agrees); the other part is not")
    else:
        mk("LOCATION", "UNSUPPORTED" if ours_loc else "NO_VALUE", ours_loc, why=_why_none(wc, text, edition))
    # SUBMISSION DEADLINE
    ours_d = to_iso(row.get("SUBMISSION DEADLINE", ""))
    gd, wd, qd = acc["deadline"]
    if gd:
        mk("SUBMISSION DEADLINE", "AGREES" if ours_d == gd else ("DIFFERS" if ours_d else "FILLS"), row.get("SUBMISSION DEADLINE", ""), gd, qd, wd)
    else:
        mk("SUBMISSION DEADLINE", "UNSUPPORTED" if ours_d else "NO_VALUE", row.get("SUBMISSION DEADLINE", ""), why=_why_none(wd, text, edition))
    return res


_PAGES: dict[str, list[tuple[str, str]]] = {}


def propose(row: dict, field: str, v: dict, text_readable: bool) -> dict | None:
    """One line of proposed_corrections.csv or None."""
    verdict = v["verdict"]
    base = {"market": row.get("_market", ""), "id": row.get("EVENT_ID_CANON", ""), "conference": row.get("CONFERENCE", ""), "field": field, "current": v["ours"], "verdict": verdict,
            "quote": v["quote"], "url": v["url"], "why": v["why"]}
    if verdict in ("DIFFERS", "FILLS"):
        pv = v["page"]
        if field in ("START DATE", "SUBMISSION DEADLINE") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", pv):
            new = _fmt_us(pv)
        elif field == "CONFERENCE DATES" and re.fullmatch(r"\d{4}-\d{2}-\d{2} to \d{4}-\d{2}-\d{2}", pv):
            a, b = pv.split(" to ")
            new = _fmt_range(a, b)
        else:
            new = pv
        note = "venue text of the old value is not kept; the reviewer edits by hand" if field == "LOCATION" else ""
        return dict(base, action="REPLACE" if verdict == "DIFFERS" else "FILL", proposed=new, strength="page states another value, verbatim quote" if verdict == "DIFFERS" else "page states a value for a blank", note=note)
    if verdict == "UNSUPPORTED":
        if not text_readable:
            return dict(base, action="KEEP-UNVERIFIED", proposed="", strength="no page could be read: nothing to propose", note="")
        return dict(base, action="BLANK", proposed="", strength="weak: the page was read and does not state it for this edition; it may still be right", note="the honest blank for a hint nothing supports")
    return None


# ---------------------------------------------------------------- driver
def load_rows(lists_dir: Path, markets: list[str]) -> list[dict]:
    rows = []
    for m in markets:
        with open(lists_dir / f"{m}_input.csv", encoding="utf-8-sig", newline="") as fh:
            rows += [dict(r, _market=m) for r in csv.DictReader(fh)]
    return rows


def urls_of(row: dict, extra: dict[str, list[str]] | None = None) -> list[str]:
    """The row's own pages (CONFERENCE URL, SUBMISSION URL) plus any page the reviewer named for this id with --extra-pages (a row's listed pages can be stale: nullcon.net/cfp shows 2025)."""
    out = []
    for u in [(row.get(c) or "").strip() for c in URL_COLS] + list((extra or {}).get(row.get("EVENT_ID_CANON", ""), [])):
        if u.startswith("http") and u not in out:
            out.append(u)
    return out


def load_extra(path: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    if path:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                out.setdefault(r["id"].strip(), []).append(r["url"].strip())
    return out


def summarize(results: list[dict]) -> dict:
    out = {}
    for f in FIELDS:
        c = Counter(r["fields"][f]["verdict"] for r in results)
        out[f] = {k: c.get(k, 0) for k in ("AGREES", "DIFFERS", "UNSUPPORTED", "FILLS", "NO_VALUE")}
    return out


def report_md(results: list[dict], summ: dict, meta: dict, mism: list[dict]) -> str:
    tot = Counter()
    for s in summ.values():
        tot.update(s)
    L = [f"# Input-list audit {meta['stamp']} (read-only; changes nothing)", "",
         f"{len(results)} rows audited ({meta['skipped']} skipped as duplicates or already marked DUP_OF); {meta['no_page']} rows with no readable page; cost {meta['usd']:.4f} USD; {meta['minutes']:.0f} minutes. Today {meta['today']}.", "",
         f"**DIFFERS: {tot['DIFFERS']} fields. UNSUPPORTED: {tot['UNSUPPORTED']} fields.** AGREES {tot['AGREES']}, FILLS {tot['FILLS']}, NO_VALUE {tot['NO_VALUE']}.", "",
         "| field | AGREES | DIFFERS | UNSUPPORTED | FILLS | NO_VALUE |", "|---|---|---|---|---|---|"]
    for f in FIELDS:
        L.append(f"| {f} | " + " | ".join(str(summ[f][k]) for k in ("AGREES", "DIFFERS", "UNSUPPORTED", "FILLS", "NO_VALUE")) + " |")
    L += ["", "DIFFERS: the page states another value for THIS edition (verbatim quote); one of the two is wrong and a person looks. UNSUPPORTED: no page of this edition states the hint; unproven, NOT wrong. "
          "A date of another year never counts for the edition.", ""]
    for kind in ("DIFFERS", "FILLS"):
        items = [(r, f, v) for r in results for f, v in r["fields"].items() if v["verdict"] == kind]
        if items:
            L += [f"## {kind} ({len(items)})", ""]
            for r, f, v in items:
                L.append(f"- **{r['conference']}** ({r['market']}, edition {r['edition']}) {f}: ours `{v['ours'] or '(blank)'}`, page `{v['page']}`; {v['why']}")
                L.append(f"  - {v['url']}  \"{v['quote'][:240]}\"")
            L.append("")
    L += [f"## Rows whose id year differs from the edition ({len(mism)}); frozen keys by design, NOT errors", ""]
    for m in mism:
        L.append(f"- {m['id']}  ({m['conference']}, {m['market']}): id year {m['id_year']}, edition {m['edition']}")
    return "\n".join(L) + "\n"


def write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def run(a) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = load_rows(Path(a.lists), a.markets)
    mism = id_year_mismatch(rows)
    todo, skipped = [], 0
    for r in rows:
        if (r.get("DUP_OF") or "").strip():
            skipped += 1
            continue
        todo.append(r)
    if a.only:
        todo = [r for r in todo if a.only.lower() in r["CONFERENCE"].lower()]
    if a.limit:
        todo = todo[: a.limit]
    print(f"input-list audit: {len(todo)} rows selected of {len(rows)} ({skipped} DUP_OF skipped); {len(mism)} rows with id year != edition", flush=True)
    if a.dry_run:
        for r in todo:
            print(f"  {r['_market'][:5]} {edition_of(r)} {r['CONFERENCE'][:55]:55} {len(urls_of(r, load_extra(a.extra_pages)))} page(s)")
        return 0
    extra = load_extra(a.extra_pages)
    import answer_key_prefill as P
    from experiments.read_the_page_pass import run as R
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    R.RENDER["on"] = not a.no_render
    R.LOG = out / f"input_audit_llm_log_{stamp}.jsonl"
    R.MAX_REQUESTS, R.MAX_USD = 2000, a.max_usd
    cache: dict[str, str] = {}
    results, no_page, t0, stopped = [], 0, time.time(), ""
    for i, r in enumerate(todo, 1):
        if (time.time() - t0) / 60 > a.max_minutes:
            stopped = f"stopped at the {a.max_minutes}-minute limit"
            break
        if R.spent()[1] >= a.max_usd:
            stopped = f"stopped at the {a.max_usd} USD cap"
            break
        ed = edition_of(r)
        pages = []
        for u in urls_of(r, extra):
            try:
                t = P.lib_text(u) or R.page_text(u, cache)
            except Exception as e:                                                   # noqa: BLE001  one bad site must not end the run
                print(f"    page {u[:60]}: {type(e).__name__}: {e}", flush=True)
                t = ""
            pages.append((u, t or ""))
        r["_key"] = r["EVENT_ID_CANON"] + "|" + r["_market"]
        _PAGES[r["_key"]] = pages
        text = "\n\n".join(t[:PAGE_CHARS] for _u, t in pages if t)
        fields, err = None, ""
        if text.strip():
            try:
                fields, _c = R.ask_with(SYSTEM + f"\nEDITION YEAR TO REPORT: {ed}", a.model, r["CONFERENCE"] + f" (edition {ed})", text, cap=len(text) + 10)
                if fields is None:
                    err = "model call failed"
            except SystemExit as e:
                stopped = f"stopped: {e}"
                break
        else:
            no_page += 1
        acc = accept_all(fields, text, ed)
        fj = judge(r, acc, text, ed, [u for u, _t in pages])
        if err:
            for f in fj.values():
                if f["verdict"] == "UNSUPPORTED":
                    f["why"] = err
        results.append({"conference": r["CONFERENCE"], "market": r["_market"], "id": r["EVENT_ID_CANON"], "edition": ed, "pages": [u for u, _t in pages], "readable": bool(text.strip()), "fields": fj})
        print(f"  [{i}/{len(todo)}] {r['CONFERENCE'][:46]:46} " + " ".join(f"{f[:5]}={fj[f]['verdict'][:4]}" for f in FIELDS), flush=True)
        time.sleep(0.5)
    meta = {"stamp": stamp, "today": a.today, "skipped": skipped, "no_page": no_page, "stopped": stopped, "minutes": (time.time() - t0) / 60, "usd": R.spent()[1], "model": a.model}
    summ = summarize(results)
    by_key = {r["EVENT_ID_CANON"] + "|" + r["_market"]: r for r in todo}
    audit_rows, prop_rows = [], []
    for res in results:
        row = by_key[res["id"] + "|" + res["market"]]
        for f, v in res["fields"].items():
            audit_rows.append({"market": res["market"], "id": res["id"], "conference": res["conference"], "edition": res["edition"], "field": f, "verdict": v["verdict"], "ours": v["ours"],
                               "page_value": v["page"], "quote": v["quote"], "url": v["url"], "why": v["why"]})
            p = propose(row, f, v, res["readable"])
            if p:
                prop_rows.append(p)
    write_csv(out / "input_audit.csv", audit_rows, ["market", "id", "conference", "edition", "field", "verdict", "ours", "page_value", "quote", "url", "why"])
    write_csv(out / "proposed_corrections.csv", prop_rows, ["market", "id", "conference", "field", "current", "verdict", "action", "proposed", "strength", "quote", "url", "why", "note"])
    (out / "input_audit.md").write_text(report_md(results, summ, meta, mism), encoding="utf-8")
    (out / "input_audit.json").write_text(json.dumps({"meta": meta, "summary": summ, "rows": results, "id_year_not_edition": mism}, indent=1, ensure_ascii=False), encoding="utf-8")
    d = sum(s["DIFFERS"] for s in summ.values())
    u = sum(s["UNSUPPORTED"] for s in summ.values())
    print(f"INPUT AUDIT: {len(results)} rows; DIFFERS {d}, UNSUPPORTED {u} (fields); {meta['usd']:.3f} USD{'; ' + stopped if stopped else ''} -> {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lists", required=True, help="folder holding Cybersecurity_input.csv and Utility_input.csv (use a scratch COPY)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--markets", nargs="+", default=["Cybersecurity", "Utility"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="")
    ap.add_argument("--no-render", action="store_true", help="plain fetch only (skip the real-Chrome render of dateless pages)")
    ap.add_argument("--max-minutes", type=float, default=150)
    ap.add_argument("--extra-pages", default="", help="CSV id,url: more pages to read for an id (the listed pages can be stale)")
    ap.add_argument("--model", default="C")
    ap.add_argument("--max-usd", type=float, default=0.30)
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        return run(a)
    except Exception as e:                                                           # noqa: BLE001
        print(f"INPUT AUDIT FAILED (nothing was changed): {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
