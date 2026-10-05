"""SHADOW READER for the facts that are not deadlines (ACT-20, 2026-10-05): each live row's own pages are read by the cheap model, in shadow, and every accepted fact is set against what we ship.

    python scripts/shadow_reader.py --markets Cybersecurity Utility [--max-events 60] [--max-minutes 120] [--max-usd 0.60] [--no-email] [--dry-run]

WHY. The one hand read so far (docs/design/field_spotchecks.json) found 3 of 7 upstream events with a wrong city, venue or date. Nothing measures start date, city, country, venue, organizer or
format week by week, so a wrong one stays wrong until a person happens to look. The read-the-page pass (experiments/read_the_page_pass/RESULT.md) proved a quote-checked cheap read makes no
wrong claims in about 70 scored answers; this runs it every Saturday on the live rows, at no risk, and counts agree / differs / reader-only per field. After a few Saturdays the per-field
accuracy is known and a field can move from shadow to second opinion.

WHAT IT DOES. For the live rows of the approved files (STATUS Open or Upcoming, edition not past): the event's own cited pages (the page library first, then a plain fetch, then a real-Chrome
render when the plain text has no dates) are read in ONE call per event; a field is accepted only if pass_lib.accept proves it (the quote is literally on the page, a date states day, month and the
edition's year, a text value is inside its quote). Per field, against the approved row:
  agree        the reader's proven value equals ours
  differs      both have a value and they differ: ONE IS WRONG, a person looks
  reader-only  we ship blank, the page states it with a quote
  ours-only    we ship a value, the pages do not prove any (it may be right: unproven, not wrong)
  none         neither
VENUE has no column of ours: it is compared with LOCATION and is agree (named there) or reader-only, never differs.
Rows are taken least recently read first (history file), so a few Saturdays cover every live row.
GUARANTEES. Read-only: it never opens the database, never edits an approved file; it reads the network (<= 3 pages per event) and calls the cheap model under its OWN request log and cost cap
(--max-usd, default 0.60) and time cap (--max-minutes, default 120; with --run-log it never runs past --total-hours since the weekend job started). It never raises into the weekend job.
It writes only under runs_out/shadow/ (shadow_reader_<stamp>.csv/.md/.json and shadow_reader_history.jsonl), one plain email to CFP_RECAP_TO unless --no-email, and never anything to upstream.
Reuses experiments/read_the_page_pass (pass_lib.accept, run.ask, run.page_text, the budget log), key_candidates.compare, shadow_finder.select/LIVE_STATUS, answer_key_prefill.lib_text, alerts.maybe_send_email."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "scripts", ROOT / "experiments" / "sitemap_discovery", ROOT / "experiments" / "sentence_picking"):
    sys.path.insert(0, str(p))
MARKETS_DIR = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
OUT_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor" / "runs_out" / "shadow"
HISTORY = OUT_DIR / "shadow_reader_history.jsonl"
LIVE_STATUS = ("open", "upcoming")
# (reader key, our column, label)
FIELDS = (("start_date", "START DATE", "start date"), ("city", "CITY", "city"), ("country", "COUNTRY", "country"), ("venue", "LOCATION", "venue"),
          ("organizer", "ORGANIZER", "organizer"), ("format", "FORMAT", "format"))
URL_COLS = ("MAIN_INFO_URL", "CONFERENCE URL", "VENUE_EVIDENCE_URL", "CFP_SUBMISSION_URL")
RELATIONS = ("agree", "differs", "reader-only", "ours-only", "none")
MAX_PAGES, PAGE_CHARS = 3, 7000


def _squash(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())


def compare_field(key: str, ours: str, got: str, quote: str = "") -> str:
    """agree | differs | reader-only | ours-only | none.
    Venue is judged against LOCATION: named there (or the acronym in brackets after the reader's venue name is) = agree, otherwise reader-only (we have no venue column, so it cannot differ).
    A text field the reader 'differs' on is still agree when OUR value is written inside the reader's own quote ('Songdo' in 'Songdo, Incheon, Korea'; 'RX' in 'Reed Exhibitions ("RX")'):
    the page states ours too, so the two are not in conflict. A date is never softened this way."""
    o, g = (ours or "").strip(), (got or "").strip()
    if key == "venue":
        if not g:
            return "none"
        acr = re.findall(r"\(([A-Za-z0-9&]{2,12})\)", g)
        return "agree" if _squash(g) in _squash(o) or any(_squash(a) and _squash(a) in _squash(o).split() for a in acr) else "reader-only"
    from experiments.read_the_page_pass.key_candidates import compare
    rel = compare(key, o, g)
    rel = {"both-blank": "none", "unproven": "ours-only"}.get(rel, rel)
    if rel == "differs" and key != "start_date" and o and _squash(o) in _squash(quote):
        return "agree"
    return rel


def edition_of(row: dict) -> str:
    e = (row.get("EDITION") or "").strip()
    return e or (row.get("START DATE") or "")[:4]


def select_rows(rows: list[dict], today: str, limit: int, last_read: dict[str, str] | None = None) -> list[dict]:
    """Live rows with at least one page to read: STATUS Open/Upcoming, edition not past, start (if any) not past. Least recently read first (never read first), then soonest start."""
    last_read = last_read or {}
    out = []
    for r in rows:
        if (r.get("STATUS") or "").strip().lower() not in LIVE_STATUS:
            continue
        if edition_of(r) and edition_of(r) < today[:4]:
            continue
        if (r.get("START DATE") or "") and r["START DATE"] < today:
            continue
        urls = []
        for c in URL_COLS:
            u = (r.get(c) or "").strip()
            if u.startswith("http") and u not in urls:
                urls.append(u)
        if urls:
            out.append(dict(r, _urls=urls[:MAX_PAGES]))
    out.sort(key=lambda r: (last_read.get(r.get("EVENT_ID", ""), ""), r.get("START DATE") or "9999"))
    return out[:limit]


def read_record(row: dict, fields: dict | None, text: str, pages: list[tuple[str, str]]) -> dict:
    """One event's record: per field the value we ship, the value the reader proved (with quote and page) and their relation. `fields` None = the call failed."""
    from experiments.read_the_page_pass import pass_lib as L
    edition = edition_of(row)
    rec = {"event": row.get("CONFERENCE", ""), "id": row.get("EVENT_ID", ""), "market": row.get("_market", ""), "edition": edition, "pages": [u for u, _t in pages], "fields": {}}
    for key, col, _label in FIELDS:
        ours = (row.get(col) or "").strip()
        if fields is None:
            rec["fields"][key] = {"ours": ours, "reader": "", "relation": "failed", "quote": "", "url": "", "why": "model call failed"}
            continue
        item = fields.get(key) or {}
        got, why = L.accept(key, item, text, edition) if text.strip() else ("", "page unreadable")
        quote = item.get("quote", "") if got else ""
        url = next((u for u, t in pages if quote and L.norm(quote) in L.norm(t)), "") if got else ""
        rec["fields"][key] = {"ours": ours, "reader": got, "relation": compare_field(key, ours, got, quote), "quote": quote, "url": url, "why": why}
    return rec


def summarize(recs: list[dict]) -> dict:
    """Per field: counts of each relation over the events whose call succeeded."""
    out = {}
    for key, _col, label in FIELDS:
        c = Counter(r["fields"][key]["relation"] for r in recs if r["fields"][key]["relation"] != "failed")
        out[key] = {"label": label, **{k: c.get(k, 0) for k in RELATIONS}}
    return out


def report_md(recs: list[dict], summ: dict, meta: dict) -> str:
    lines = [f"# Shadow reader {meta['stamp']} (changes nothing)", "",
             f"{len(recs)} events read of {meta['selected']} selected ({meta['skipped']} skipped, {meta['failed']} model calls failed, {meta['stopped'] or 'finished'}); {meta['minutes']:.0f} minutes; cost {meta['usd']:.4f} USD.", "",
             "| field | agree | differs | reader-only | ours-only | none |", "|---|---|---|---|---|---|"]
    for key, _c, _l in FIELDS:
        s = summ[key]
        lines.append(f"| {s['label']} | " + " | ".join(str(s[k]) for k in RELATIONS) + " |")
    lines += ["", "**differs**: one of the two is wrong, a person looks (the reader's value has a verbatim quote on a real page). **reader-only**: we ship blank and the page states it. "
              "**ours-only** is not an error (unproven, not wrong). Not an accuracy figure yet: it becomes one after a few Saturdays of person checks on the differences.", ""]
    for kind, title in (("differs", "Differs: we ship one value, the page states another"), ("reader-only", "Reader-only: we ship nothing, the page states it")):
        items = [(r, k, f) for r in recs for k, f in r["fields"].items() if f["relation"] == kind]
        if items:
            lines += [f"## {title} ({len(items)})", ""]
            for r, k, f in items:
                lines.append(f"- **{r['event']}** ({r['market']}) {k}: ours {f['ours'] or '(blank)'}, page says **{f['reader']}**")
                lines.append(f"  - {f['url']}  \"{f['quote'][:200]}\"")
            lines.append("")
    return "\n".join(lines)


def csv_rows(recs: list[dict]) -> list[dict]:
    return [{"event": r["event"], "market": r["market"], "id": r["id"], "edition": r["edition"], "field": k, "ours": f["ours"], "reader": f["reader"], "relation": f["relation"],
             "url": f["url"], "quote": f["quote"], "why": f["why"]} for r in recs for k, f in r["fields"].items()]


def load_last_read(path: Path = HISTORY) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            out[r["id"]] = max(out.get(r["id"], ""), r["read_on"])
    except (OSError, ValueError, KeyError):
        pass
    return out


def run(a) -> int:
    global OUT_DIR, HISTORY
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.out_dir:                                                                  # rehearsals and tests write here, never under the live data root
        OUT_DIR, HISTORY = Path(a.out_dir), Path(a.out_dir) / "shadow_reader_history.jsonl"
    import answer_key_prefill as P
    rows = []
    for m in a.markets:
        fin = MARKETS_DIR / f"{m}_audited.final.csv"
        if fin.exists():
            with open(fin, encoding="utf-8-sig", newline="") as fh:
                rows += [dict(r, _market=m) for r in csv.DictReader(fh)]
    events = select_rows(rows, a.today, a.max_events, load_last_read())
    print(f"shadow reader: {len(events)} live events selected from {len(rows)} approved rows", flush=True)
    if a.dry_run:
        for e in events:
            print(f"  {e['_market'][:5]} {e.get('START DATE') or '-':10} {e['CONFERENCE'][:50]:50} {len(e['_urls'])} page(s) {e['_urls'][0][:60]}")
        return 0
    from experiments.read_the_page_pass import run as R
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    R.LOG = OUT_DIR / f"shadow_reader_llm_log_{stamp}.jsonl"                      # its own request log and cap: never the experiments' shared log
    R.MAX_REQUESTS, R.MAX_USD = 2000, a.max_usd
    cache: dict[str, str] = {}
    recs, skipped, failed, stopped, t0 = [], 0, 0, "", time.time()
    for i, ev in enumerate(events, 1):
        if (time.time() - t0) / 60 > a.max_minutes:
            stopped = f"stopped at the {a.max_minutes}-minute limit"
            break
        if R.spent()[1] >= a.max_usd:
            stopped = f"stopped at the {a.max_usd} USD cap"
            break
        try:
            pages = []
            for u in ev["_urls"]:
                t = P.lib_text(u) or R.page_text(u, cache)
                pages.append((u, t or ""))
            text = "\n\n".join(t[:PAGE_CHARS] for _u, t in pages if t)
            if not text.strip():
                skipped += 1
                print(f"  [{i}/{len(events)}] skipped {ev['CONFERENCE'][:50]}: no readable page", flush=True)
                continue
            fields, _cost = R.ask(a.model, ev["CONFERENCE"], edition_of(ev) or a.today[:4], text)
        except SystemExit as e:                                                     # the request log's budget guard
            stopped = f"stopped: {e}"
            break
        except Exception as e:                                                      # noqa: BLE001  one bad site must not end the run
            skipped += 1
            print(f"  [{i}/{len(events)}] skipped {ev['CONFERENCE'][:50]}: {type(e).__name__}: {e}", flush=True)
            continue
        if fields is None:
            failed += 1
        rec = read_record(ev, fields, text, pages)
        recs.append(rec)
        with open(HISTORY, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": rec["id"], "event": rec["event"], "read_on": a.today, "stamp": stamp}) + "\n")
        marks = " ".join(f"{k[:4]}={rec['fields'][k]['relation'][:4]}" for k, _c, _l in FIELDS)
        print(f"  [{i}/{len(events)}] {ev['CONFERENCE'][:44]:44} {marks}", flush=True)
        time.sleep(1)
    meta = {"stamp": stamp, "selected": len(events), "skipped": skipped, "failed": failed, "stopped": stopped, "minutes": (time.time() - t0) / 60, "usd": R.spent()[1]}
    summ = summarize(recs)
    stem = OUT_DIR / f"shadow_reader_{stamp}"
    cr = csv_rows(recs)
    if cr:
        with open(f"{stem}.csv", "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(cr[0]))
            w.writeheader()
            w.writerows(cr)
    md = report_md(recs, summ, meta)
    Path(f"{stem}.md").write_text(md, encoding="utf-8")
    Path(f"{stem}.json").write_text(json.dumps({"meta": meta, "summary": summ, "events": recs}, indent=1, ensure_ascii=False), encoding="utf-8")
    d = sum(s["differs"] for s in summ.values())
    ro = sum(s["reader-only"] for s in summ.values())
    ag = sum(s["agree"] for s in summ.values())
    print(f"SHADOW READER: {len(recs)} events read; facts agree {ag}, differs {d}, reader-only {ro}; {meta['minutes']:.0f} min, {meta['usd']:.3f} USD{'; ' + stopped if stopped else ''} -> {stem}.md")
    if not a.no_email:
        try:
            from src.cfp_monitor.alerts import maybe_send_email
            sent = maybe_send_email(f"CFP shadow reader: {d} differ, {ro} reader-only, {ag} agree", md, to_env="CFP_RECAP_TO")
            print("shadow reader recap emailed" if sent else "shadow reader recap NOT emailed - CFP_RECAP_TO or CFP_SMTP_* not set")
        except Exception as e:                                                      # noqa: BLE001
            print(f"shadow reader recap NOT emailed - {type(e).__name__}: {e}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--markets", nargs="+", default=["Cybersecurity", "Utility"])
    ap.add_argument("--max-events", type=int, default=60)
    ap.add_argument("--max-minutes", type=float, default=120)
    ap.add_argument("--max-usd", type=float, default=0.60)
    ap.add_argument("--model", default="C")
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--run-log", help="the weekend job's log: its creation time is the job's start, used with --total-hours")
    ap.add_argument("--total-hours", type=float, default=4.6, help="with --run-log: never run past this many hours since the job started (the task itself is limited to 5)")
    ap.add_argument("--out-dir", help="write the reports, the request log and the history here instead of runs_out/shadow (use a scratch folder for any rehearsal)")
    ap.add_argument("--no-email", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="list the events it would read; no network, no model")
    a = ap.parse_args()
    if a.run_log and Path(a.run_log).exists():
        left = a.total_hours * 60 - (time.time() - os.path.getctime(a.run_log)) / 60
        if left < 12:
            print(f"SHADOW READER SKIPPED: only {left:.0f} minutes left inside the job's time budget (nothing changed)")
            return 0
        a.max_minutes = min(a.max_minutes, left - 8)
    try:
        return run(a)
    except Exception as e:                                                          # noqa: BLE001  the weekend job must never fail because of the shadow reader
        print(f"SHADOW READER FAILED (nothing was changed): {type(e).__name__}: {e}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
