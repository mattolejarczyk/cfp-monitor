"""Finder + reader, end to end (option 3, 2026-10-04): can real URLs from a site's sitemap and menu, picked by the frozen v3.1 rules and read by the cheap model, find the
submission deadline of a currently-open call -- without being told the answer?

    python experiments/finder_reader_test/run.py [--model C] [--max-pages 8] [--only <text>] [--plan-only]

GOLD (known deadlines still ahead, nobody has to re-verify): the customer-verified live dates that match ours (customer_agreement) + the operator's pinned deadlines.
FINDER   per event: homepage (menu + links with their text, real Chrome) + sitemap (plain HTTP) -> rules_v31.plan -> at most --max-pages pages.
READER   each selected page is read ALONE by the cheap model (deepseek-chat) asked for the submission deadline with a verbatim quote; CODE accepts only if the quote is on the page,
         states that day, month and year, and uses call wording. The model is never told the gold date.
CONTROL  the page the database already cites for the deadline, read the same way: separates a FINDER failure (control states it, plan missed it) from a READER failure.
SCORED   selection recall (a selected page states the gold date), end-to-end recall (an accepted deadline equals gold), WRONG (an accepted deadline differs: looked at by a person,
         it may be another round), pages read, cost. Network: sitemap + homepage + <= max-pages pages per event, 2 s apart, no hard-anti-bot hosts. Nothing is written to the data.
Reuses sitemap_discovery (collect_sitemaps.collect, rules_v31.plan, dates_v2.find_target), pass_lib/run (reader call, budget log), board_metrics (gold). Writes results.json."""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SD = ROOT / "experiments" / "sitemap_discovery"
for p in (ROOT, SD, ROOT / "experiments" / "sentence_picking", ROOT / "experiments" / "sitemap_discovery"):
    sys.path.insert(0, str(p))

CALL_WORDS = re.compile(r"deadline|submit|submission|abstract|proposal|call for|cfp|closes?|closing|due|applications?|nominat", re.I)
SYSTEM = """You read ONE web page about a conference and report the deadline to SUBMIT a talk, paper, abstract, proposal or speaker application for the next upcoming edition, only if the page states it.
Return ONLY JSON: {"deadline": {"value": "YYYY-MM-DD or empty", "quote": "one sentence copied verbatim from the page that states the date"}, "what": "the page's own words for what the date is for"}.
If there are several rounds (early, regular, late), report the one that closes next. Never report registration, early-bird, event, notification or camera-ready dates.
If the page states no submission deadline with its year, return empty value and empty quote. Never guess a year or a date."""


def canon_url(u: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", (u or "").lower()).split("#")[0].split("?")[0].rstrip("/")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


from experiments.finder_reader_test.main_call import choose_main      # noqa: E402


def accept_deadline(item: dict, page: str, today: str) -> tuple[str, str]:
    """(value or '', why). The model's claim stands only if the page itself supports it (quote on the page, date year-specific, call wording)."""
    from scripts.start_date_arbiter import expand_ranges
    from src.cfp_monitor.verify import find_date
    value, quote = (item or {}).get("value", ""), (item or {}).get("quote", "")
    if not value or not quote:
        return "", "blank"
    if norm(quote) not in norm(page):
        return "", "quote is not on the page"
    try:
        d = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return "", "not an ISO date"
    if not find_date(expand_ranges(quote), d):
        return "", "the quote does not state that day, month and year"
    if not CALL_WORDS.search(quote):
        return "", "the quote has no call wording"
    if value < (date.fromisoformat(today) - timedelta(days=30)).isoformat():
        return "", "date is long past"
    return value, "ok"


def gold_events(today: str) -> list[dict]:
    from scripts.board_metrics import LIVE_DB, customer_agreement
    from scripts.pinned_rows import load_pins
    db = str(LIVE_DB)
    gold = {}
    for d in customer_agreement(db, today)["detail"]:
        if d["live"] and d["class"] == "agree":
            gold[d["event_id"]] = {"event": d["name"], "gold": d["ours"], "source": "customer-verified, matches ours"}
    for p in load_pins():
        v = str(p["set"].get("SUBMISSION DEADLINE", "")).strip()
        if v and v >= today:
            gold[p["canonical"]] = {"event": p["event"], "gold": v, "source": "operator pin"}
    con = sqlite3.connect(db)
    out = []
    for eid, g in gold.items():
        r = con.execute("select url, main_info_url, submission_url, deadline_evidence_url from grounding_facts where event_id=?", (eid,)).fetchone()
        if not r:
            continue
        url, main, sub, ev = r
        home = main or url or sub or ev or ""
        if not str(home).startswith("http"):
            continue
        out.append({"id": eid, **g, "home": home, "control": ev or sub or "", "hosts": sorted({urlparse(u).netloc.lower().removeprefix("www.") for u in (home, sub, ev) if u and str(u).startswith("http")})})
    return out


class _Q:
    def log(self, *a, **k):
        pass


async def render(url, settings, _f):
    try:
        html, anchors, st, body, _c = await _f._render_with_consent(url, settings, _Q(), prefer_cdp=True)
        return (body or ""), [((a.get("href") or ""), (a.get("text") or "")[:80]) for a in (anchors or [])][:600]
    except Exception:                                                  # noqa: BLE001
        return "", []


async def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="C")
    ap.add_argument("--max-pages", type=int, default=8)
    ap.add_argument("--only", default="")
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--today", default=date.today().isoformat())
    a = ap.parse_args()
    import dates_v2 as d2
    import rules_v31 as r31
    from experiments.read_the_page_pass import run as R
    from src.cfp_monitor import fetch as _f, sitewalk
    from src.cfp_monitor.config import Settings
    cs_spec = importlib.util.spec_from_file_location("cs", SD / "collect_sitemaps.py")
    cs = importlib.util.module_from_spec(cs_spec)
    cs_spec.loader.exec_module(cs)
    R.MAX_REQUESTS, R.MAX_USD = 600, 0.30
    settings = Settings()
    events = [e for e in gold_events(a.today) if a.only.lower() in e["event"].lower()]
    pages_cache = json.loads((HERE / "pages.json").read_text(encoding="utf-8")) if (HERE / "pages.json").exists() else {}
    results = []
    for ev in events:
        print(f"\n=== {ev['event']}  gold {ev['gold']} ({ev['source']})  {ev['home']}", flush=True)
        urls, labels = [], {}
        origin = sitewalk.origin(ev["home"])
        blocked = _f._force_fallback_domain(ev["home"]) if hasattr(_f, "_force_fallback_domain") else False
        if blocked:
            print("  hard anti-bot host: skipped without touching the network", flush=True)
            results.append({**ev, "skipped": "anti-bot host"})
            continue
        try:
            pages, how, _capped, _n, _r = await cs.collect(origin)
            urls += [u for u, _lm in pages]
        except Exception as e:                                         # noqa: BLE001
            how = type(e).__name__
        body, anchors = await render(ev["home"], settings, _f)
        if not anchors:                                                # a flaky render (AAIML, run 1): one more try before the finder gives up
            await asyncio.sleep(3)
            body, anchors = await render(ev["home"], settings, _f)
        base = ev["home"]
        for href, text in anchors:
            u = urljoin(base, href).split("#")[0]
            if urlparse(u).netloc.lower().removeprefix("www.") in ev["hosts"] and u.startswith("http"):
                urls.append(u)
                if text:
                    labels[u] = text
        urls = list(dict.fromkeys(urls))
        plan = r31.plan(urls, labels)[:a.max_pages]
        print(f"  sitemap: {how}; {len(urls)} candidate URLs ({len(labels)} with menu text) -> {len(plan)} pages selected", flush=True)
        rec = {**ev, "candidates": len(urls), "selected": len(plan), "pages": [], "selection_hit": None, "reader_hit": None, "reader_wrong": []}
        if a.plan_only:
            for u, t in plan:
                print("   ", t[:2], u[:100])
            results.append(rec)
            continue
        gold_d = date.fromisoformat(ev["gold"])
        targets = [(i + 1, u, t) for i, (u, t) in enumerate(plan)]
        if not any(canon_url(u) == canon_url(ev["home"]) for u, _t in plan):
            targets.append((-1, ev["home"], "home"))                     # the home page is always read: the date is often only there (ICRAI, AAIML)
        if ev["control"]:
            targets.append((0, ev["control"], "control"))
        cands = []
        for rank, u, tier in targets:
            text = pages_cache.get(u) or (await render(u, settings, _f))[0]
            pages_cache[u] = text
            states = bool(text) and bool(d2.find_target(text, gold_d))
            got, why, what, quote = "", "page unreadable", "", ""
            if text.strip():
                fields, _c = R.ask_with(SYSTEM, a.model, ev["event"], text) if hasattr(R, "ask_with") else (None, None)
                fields = fields or {}
                got, why = accept_deadline(fields.get("deadline", {}), text, a.today)
                what, quote = str(fields.get("what", "")), str((fields.get("deadline") or {}).get("quote", ""))
            rec["pages"].append({"rank": rank, "tier": tier[:2], "url": u, "chars": len(text), "states_gold": states, "accepted": got, "why": why, "what": what})
            if got and rank != 0:                                        # the control is the database's own page: a finder would not have it
                cands.append({"value": got, "url": u, "what": what, "quote": quote, "home": rank == -1})
            if rank and states and rec["selection_hit"] is None:
                rec["selection_hit"] = rank
            if rank and got == ev["gold"] and rec["reader_hit"] is None:
                rec["reader_hit"] = rank
            if rank and got and got != ev["gold"]:
                rec["reader_wrong"].append({"rank": rank, "url": u, "accepted": got})
            print(f"   {rank:>2} {tier[:2]:3} chars={len(text):>6} states-gold={'Y' if states else '-'} reader={got or why[:30]:<12} {urlparse(u).path[:56]}", flush=True)
            (HERE / "pages.json").write_text(json.dumps(pages_cache, ensure_ascii=False), encoding="utf-8")
            await asyncio.sleep(2)
        pick = choose_main(cands, a.today)
        rec["pick"] = pick
        rec["pick_correct"] = pick["pick"] == ev["gold"]
        ctl = [p for p in rec["pages"] if p["rank"] == 0]
        rec["control_states_gold"] = bool(ctl and ctl[0]["states_gold"])
        rec["control_reader"] = ctl[0]["accepted"] if ctl else ""
        print(f"  => selection {'HIT rank %s' % rec['selection_hit'] if rec['selection_hit'] else 'MISS'} | reader {'HIT rank %s' % rec['reader_hit'] if rec['reader_hit'] else 'MISS'}"
              f" | MAIN-CALL PICK {pick['pick'] or 'none'} {'= gold' if rec['pick_correct'] else ('!= gold ' + ev['gold'] if pick['pick'] else '')} ({pick['why'][:60]}; other calls set aside {len(pick['other_calls'])}) | control states gold: {rec['control_states_gold']}, reader on control: {rec['control_reader'] or '-'}", flush=True)
        results.append(rec)
        (HERE / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    try:
        await _f.close_fallback_browser()
    except Exception:                                                  # noqa: BLE001
        pass
    done = [r for r in results if "pages" in r and r["pages"]]
    print(f"\nMAIN-CALL PICK correct for {sum(1 for r in done if r.get('pick_correct'))} of {len(done)} events; picked a WRONG date for {sum(1 for r in done if r.get('pick', {}).get('pick') and not r.get('pick_correct'))}; "
          f"no pick (honest blank) for {sum(1 for r in done if not r.get('pick', {}).get('pick'))}")
    print(f"\nEVENTS {len(done)}: selection hit {sum(1 for r in done if r['selection_hit'])}, reader hit {sum(1 for r in done if r['reader_hit'])}, "
          f"events with a wrong accepted date {sum(1 for r in done if r['reader_wrong'])}; spent so far {R.spent()[1]:.4f} USD (all experiments)")


if __name__ == "__main__":
    asyncio.run(main())
