"""SHADOW RUN of the real-URL deadline finder (2026-10-04): run it beside the weekly grounded research, record both answers and every disagreement, CHANGE NOTHING.

    python scripts/shadow_finder.py --markets Cybersecurity Utility [--max-events 60] [--max-minutes 120] [--max-usd 0.60] [--no-email] [--dry-run]

WHY. Experiments (experiments/finder_reader_test/RESULT.md) found the right deadline for 12 of 14 known events with 0 wrong, against 8 of 14 for the grounded call, and showed the two are complementary
(agreement 7 of 7 right; both disagreements went to the real-URL date). n = 14 and the gold favours the grounded call, so before any weekly row relies on it we collect the evidence on the rows
that actually matter, every Saturday, at no risk.

WHAT IT DOES. For the live rows of the approved files (STATUS Open or Upcoming, edition not past), soonest deadline first, up to --max-events: the home page + sitemap -> frozen v3.1 page rules ->
each selected page and the home page read one at a time by the cheap model -> only code-proven deadlines (quote on the page, day, month and year, call wording) -> main-call rule
(experiments/finder_reader_test/main_call.py). Each event is set against what we ship (the approved file) and what the grounded research returned this week:
  agree        the real-URL pick equals what we ship
  differs      both have a date and they differ: a PERSON LOOKS (the experiment says this is where the value is)
  real-only    we ship no deadline, the pages state one with a quote
  ours-only    we ship one, the pages do not prove any (it may be right: that is what unproven means)
  none         neither
GUARANTEES. Read-only: it never opens the database for writing and never edits an approved file; it reads the network (sitemap, home page, <= 8 pages per event, 2 s apart, no hard anti-bot hosts)
and calls the cheap model under its OWN request log and cost cap. It stops at --max-minutes or --max-usd and reports what it finished; it never raises into the weekend job.
OUTPUT. runs_out/shadow/shadow_<stamp>.csv (one line per event), .md (summary + the disagreements), .json; one plain email (CFP_RECAP_TO) unless --no-email.
Reuses experiments/finder_reader_test (find_and_read, accept_deadline, choose_main), pass/run.ask_with, alerts.maybe_send_email, identity.to_canonical."""
from __future__ import annotations

import argparse
import asyncio
import csv
import importlib.util
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "experiments" / "sitemap_discovery", ROOT / "experiments" / "sentence_picking"):
    sys.path.insert(0, str(p))
MARKETS_DIR = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
OUT_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor" / "runs_out" / "shadow"
LIVE_STATUS = ("open", "upcoming")


def host_of(u: str) -> str:
    return urlparse(u).netloc.lower().removeprefix("www.") if u and u.startswith("http") else ""


def select_events(rows: list[dict], today: str, limit: int) -> list[dict]:
    """The live rows worth a look: STATUS Open/Upcoming, edition not past, start (if any) not past, a page to start from. Soonest deadline first, rows without a deadline after."""
    out = []
    for r in rows:
        if (r.get("STATUS") or "").strip().lower() not in LIVE_STATUS:
            continue
        if (r.get("EDITION") or "") and r["EDITION"] < today[:4]:
            continue
        if (r.get("START DATE") or "") and r["START DATE"] < today:
            continue
        home = (r.get("MAIN_INFO_URL") or r.get("CONFERENCE URL") or r.get("CFP_SUBMISSION_URL") or "").strip()
        if not home.startswith("http"):
            continue
        hosts = sorted({h for h in (host_of(home), host_of(r.get("CFP_SUBMISSION_URL", "")), host_of(r.get("DEADLINE_EVIDENCE_URL", ""))) if h})
        out.append({"event": r.get("CONFERENCE", ""), "id": r.get("EVENT_ID", ""), "market": r.get("_market", ""), "home": home, "hosts": hosts, "control": "",
                    "ours": (r.get("SUBMISSION DEADLINE") or "").strip()})
    dated = sorted((e for e in out if e["ours"] >= today), key=lambda e: e["ours"])
    undated = [e for e in out if not e["ours"] or e["ours"] < today]
    return (dated + undated)[:limit]


def relation(ours: str, pick: str) -> str:
    o, p = (ours or "").strip()[:10], (pick or "").strip()[:10]
    if o and p:
        return "agree" if o == p else "differs"
    if p:
        return "real-only"
    return "ours-only" if o else "none"


def summarize(recs: list[dict]) -> dict:
    from collections import Counter
    c = Counter(r["relation"] for r in recs)
    return {k: c.get(k, 0) for k in ("agree", "differs", "real-only", "ours-only", "none")}


def report_md(recs: list[dict], summ: dict, meta: dict) -> str:
    lines = [f"# Shadow run {meta['stamp']} (changes nothing)", "",
             f"{len(recs)} events read of {meta['selected']} selected ({meta['skipped']} skipped, {meta['stopped'] or 'finished'}); {meta['minutes']:.0f} minutes; cost {meta['usd']:.4f} USD.", "",
             "| agree | differs | real-only | ours-only | none |", "|---|---|---|---|---|",
             "| " + " | ".join(str(summ[k]) for k in ("agree", "differs", "real-only", "ours-only", "none")) + " |", "",
             "**differs** and **real-only** are for a person: the real-URL date has a verbatim quote on a real page. **ours-only** is not an error (unproven, not wrong). Experiment 10-04: when the two paths agreed the date was right 7 of 7;"
             " in both disagreements the real-URL date was right (n = 14).", ""]
    for kind, title in (("differs", "Differs: we ship one date, the pages state another"), ("real-only", "Real-only: we ship no deadline, the pages state one")):
        rows = [r for r in recs if r["relation"] == kind]
        if rows:
            lines += [f"## {title} ({len(rows)})", ""]
            for r in rows:
                lines.append(f"- **{r['event']}** ({r['market']}): ours {r['ours'] or '(blank)'}, grounded this week {r['grounded'] or '(blank)'}, pages say **{r['pick']}** - {r['why']}")
                lines.append(f"  - {r['pick_url']}  \"{r['quote'][:200]}\"")
            lines.append("")
    return "\n".join(lines)


def build_ctx(log_path: Path, max_usd: float) -> SimpleNamespace:
    """The context find_and_read needs (page rules, date reader, reader runner, fetch, sitewalk, sitemap collector, settings), with the reader's request log and cost cap pointed at
    `log_path` / `max_usd` so a caller never spends against the experiments' shared log. Shared by shadow_finder, shadow_reader-style runs and scripts/propose_replacements.py."""
    import dates_v2 as d2
    import rules_v31 as r31
    from experiments.read_the_page_pass import run as R
    from src.cfp_monitor import fetch as _f, sitewalk
    from src.cfp_monitor.config import Settings
    spec = importlib.util.spec_from_file_location("cs", ROOT / "experiments" / "sitemap_discovery" / "collect_sitemaps.py")
    cs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cs)
    R.LOG = Path(log_path)
    R.MAX_REQUESTS, R.MAX_USD = 2000, max_usd
    return SimpleNamespace(d2=d2, r31=r31, R=R, _f=_f, sitewalk=sitewalk, cs=cs, settings=Settings())


async def run(a) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    today = a.today
    rows, grounded = [], {}
    from src.cfp_monitor.identity import seed_map, to_canonical
    from scripts.board_metrics import LIVE_DB
    up_to_canon, _roots = seed_map(str(LIVE_DB))
    global OUT_DIR
    if a.out_dir:                                                          # rehearsals write here, never under the live data root
        OUT_DIR = Path(a.out_dir)
    for m in [m for m in a.markets if m != "Awards"]:
        fin = MARKETS_DIR / f"{m}_audited.final.csv"
        if fin.exists():
            with open(fin, encoding="utf-8-sig", newline="") as fh:
                rows += [dict(r, _market=m) for r in csv.DictReader(fh)]
        raw = MARKETS_DIR / f"{m}_audited.csv"
        if raw.exists():
            with open(raw, encoding="utf-8-sig", newline="") as fh:
                for r in csv.DictReader(fh):
                    grounded[to_canonical(r.get("EVENT_ID", ""), up_to_canon)] = (r.get("SUBMISSION DEADLINE") or "").strip()
    events = select_events(rows, today, a.max_events) if rows else []
    if "Awards" in a.markets:
        # ACT-22: the live awards (kind='award': the entry or nomination deadline, the inverted main-call rule). There is no approved awards file; they come from the table, read-only.
        from scripts.awards_shadow import live_awards
        events += live_awards(a.db or LIVE_DB, today, a.max_events)
    stem_name = "shadow_awards" if a.markets == ["Awards"] else "shadow"
    print(f"shadow: {len(events)} live events selected from {len(rows)} approved rows{' plus the awards table' if 'Awards' in a.markets else ''}", flush=True)
    if a.dry_run:
        for e in events:
            print(f"  {e['market'][:5]} {e['ours'] or '-':10} {e['event'][:50]:50} {e['home'][:70]}")
        return 0
    from experiments.finder_reader_test import run as F
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ctx = build_ctx(OUT_DIR / f"shadow_llm_log_{stamp}.jsonl", a.max_usd)      # its own request log and cap: never the experiments' shared log
    R, _f = ctx.R, ctx._f
    recs, skipped, stopped, t0 = [], 0, "", time.time()
    for i, ev in enumerate(events, 1):
        if (time.time() - t0) / 60 > a.max_minutes:
            stopped = f"stopped at the {a.max_minutes}-minute limit"
            break
        if R.spent()[1] >= a.max_usd:
            stopped = f"stopped at the {a.max_usd} USD cap"
            break
        try:
            quiet = lambda *x, **k: None                                  # noqa: E731
            rec = await F.find_and_read(ev, ctx, 8, "C", today, {}, say=quiet)
        except SystemExit as e:                                           # the request log's budget guard
            stopped = f"stopped: {e}"
            break
        except Exception as e:                                            # noqa: BLE001  one bad site must not end the run
            rec = {"skipped": f"{type(e).__name__}: {e}"}
        if rec.get("skipped") or "pick" not in rec:
            skipped += 1
            print(f"  [{i}/{len(events)}] skipped {ev['event'][:50]}: {rec.get('skipped')}", flush=True)
            continue
        pick = rec["pick"]
        pu = next((p for p in rec["pages"] if p["accepted"] == pick["pick"] and p["rank"] != 0), {}) if pick["pick"] else {}
        out = {"event": ev["event"], "market": ev["market"], "id": ev["id"], "ours": ev["ours"], "grounded": grounded.get(ev["id"], ""), "pick": pick["pick"],
               "relation": relation(ev["ours"], pick["pick"]), "why": pick["why"], "pick_url": pu.get("url", ""), "quote": pu.get("quote", ""),
               "other_calls_set_aside": len(pick["other_calls"]), "rounds": pick["rounds"], "home": ev["home"]}
        recs.append(out)
        print(f"  [{i}/{len(events)}] {out['relation']:9} ours {out['ours'] or '-':10} pages {out['pick'] or '-':10} {ev['event'][:50]}", flush=True)
    try:
        await _f.close_fallback_browser()
    except Exception:                                                     # noqa: BLE001
        pass
    meta = {"stamp": stamp, "selected": len(events), "skipped": skipped, "stopped": stopped, "minutes": (time.time() - t0) / 60, "usd": R.spent()[1]}
    summ = summarize(recs)
    stem = OUT_DIR / f"{stem_name}_{stamp}"
    if recs:
        with open(f"{stem}.csv", "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(recs[0]))
            w.writeheader()
            w.writerows(recs)
    md = report_md(recs, summ, meta)
    Path(f"{stem}.md").write_text(md, encoding="utf-8")
    Path(f"{stem}.json").write_text(json.dumps({"meta": meta, "summary": summ, "events": recs}, indent=1, ensure_ascii=False), encoding="utf-8")
    line = (f"SHADOW: {len(recs)} events read; agree {summ['agree']}, differs {summ['differs']}, real-only {summ['real-only']}, ours-only {summ['ours-only']}, none {summ['none']}; "
            f"{meta['minutes']:.0f} min, {meta['usd']:.3f} USD{'; ' + stopped if stopped else ''} -> {stem}.md")
    print(line)
    if not a.no_email:
        try:
            from src.cfp_monitor.alerts import maybe_send_email
            subject = f"CFP {'awards ' if stem_name == 'shadow_awards' else ''}shadow run: {summ['differs']} differ, {summ['real-only']} real-only, {summ['agree']} agree"
            sent = maybe_send_email(subject, md, to_env="CFP_RECAP_TO")
            print("shadow recap emailed" if sent else "shadow recap NOT emailed - CFP_RECAP_TO or CFP_SMTP_* not set")
        except Exception as e:                                            # noqa: BLE001
            print(f"shadow recap NOT emailed - {type(e).__name__}: {e}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--markets", nargs="+", default=["Cybersecurity", "Utility"])
    ap.add_argument("--max-events", type=int, default=60)
    ap.add_argument("--max-minutes", type=float, default=120)
    ap.add_argument("--max-usd", type=float, default=0.60)
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--run-log", help="the weekend job's log: its creation time is the job's start, used with --total-hours")
    ap.add_argument("--total-hours", type=float, default=4.25, help="with --run-log: never run past this many hours since the job started (the task itself is limited to 5)")
    ap.add_argument("--db", help="the database the awards come from (read-only; default the live one)")
    ap.add_argument("--out-dir", help="write the reports and the request log here instead of runs_out/shadow (a rehearsal uses a scratch folder)")
    ap.add_argument("--no-email", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="list the events it would read; no network, no model")
    a = ap.parse_args()
    if a.run_log and Path(a.run_log).exists():
        left = a.total_hours * 60 - (time.time() - os.path.getctime(a.run_log)) / 60
        if left < 15:
            print(f"SHADOW RUN SKIPPED: only {left:.0f} minutes left inside the job's time budget (nothing changed)")
            return 0
        a.max_minutes = min(a.max_minutes, left - 10)
    try:
        return asyncio.run(run(a))
    except Exception as e:                                                # noqa: BLE001  the weekend job must never fail because of the shadow run
        print(f"SHADOW RUN FAILED (nothing was changed): {type(e).__name__}: {e}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
