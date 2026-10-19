"""Sponsorship reader experiment (2026-10-19): does reading a few sponsor-type pages from the event's OWN site (sitemap + menu) prove more sponsorship statements than the single page upstream cited?

    python experiments/sponsor_reader/run.py --out-dir <dir> [--yes 45] [--no 10] [--unknown 10] [--max-pages 4] [--max-minutes 90] [--seed 20261019]

WHY. 211 sponsor-required rows carry no proof. scripts/extract_sponsor_quotes.py read the ONE page upstream cited and proved a sentence for only 13 of 216 rows (6 percent): 122 pages said nothing about
speaking or cost, 64 could not be read. The operator's direction (2026-10-19): do not pay to look for it; add it to the reading we already do, and where a page does not say it, the answer is Unknown
(contract R19.1 and R19.2). This measures how far the reading we already have goes: per event, the cited page (CONTROL) and up to --max-pages sponsor-type pages picked from the sitemap and the home page
menu by URL and link-text words (sponsor, prospectus, partner, exhibit, package, speak, faq...) are each read ALONE by the cheap model with the SAME instruction and the SAME code checks as
extract_sponsor_quotes.choose (the sentence must be copied verbatim from the page, must tie speaking to sponsorship or state a speaking price, a booth or delegate price does not count, a sentence that
denies speaking is refused).
SCORED. Events with a proven sentence from the control page alone, from any page, the extra the finder adds, pages read, readable share, cost (tokens x the model price, an estimate). The proven
sentences are written out in full so a person can read every one: precision is judged by reading them, not assumed.
READ-ONLY. Reads the live database (mode=ro) and the network (2 s apart, no hard anti-bot hosts); writes only under --out-dir. Nothing reaches a row, a file the pages are built from, or a customer."""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import random
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SD = ROOT / "experiments" / "sitemap_discovery"
for p in (ROOT, SD, ROOT / "experiments" / "sentence_picking"):
    sys.path.insert(0, str(p))

LIVE_DB = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor\cfp_monitor.db")
SEED_DIR = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor\market_sheets")

# (word, weight): matched against the URL path and the menu link text. A page named for sponsoring beats one that merely mentions it.
WORDS = (("sponsor", 4), ("prospectus", 4), ("partner", 3), ("exhibit", 2), ("packages", 3), ("package", 2), ("get-involved", 2), ("get involved", 2),
         ("become-a", 2), ("why-", 1), ("speak", 2), ("faq", 2), ("call-for", 1), ("cfp", 1), ("submit", 1), ("brochure", 3), ("media-kit", 3), ("advertis", 2))
AVOID = re.compile(r"(privacy|cookie|terms|login|sign-?in|register|ticket|news|blog|press|past-|previous|archive|gallery|photo|video|career|jobs|contact|sitemap|\.pdf$|\.jpg$|\.png$|\.xml$|wp-json|/tag/|/category/|/author/)", re.I)


def host(u: str) -> str:
    return urlparse(u).netloc.lower().removeprefix("www.") if u and u.startswith("http") else ""


def score(url: str, label: str) -> int:
    t = (urlparse(url).path + " " + (label or "")).lower()
    return sum(w for k, w in WORDS if k in t)


def pick_pages(urls: list[str], labels: dict[str, str], cited: str, k: int) -> list[str]:
    seen, ranked = set(), []
    for u in urls:
        key = u.rstrip("/").lower()
        if key in seen or AVOID.search(urlparse(u).path):
            continue
        seen.add(key)
        s = score(u, labels.get(u, ""))
        if s > 0 and key != (cited or "").rstrip("/").lower():
            ranked.append((s, -len(urlparse(u).path), u))
    ranked.sort(reverse=True)
    return [u for _s, _l, u in ranked[:k]]


def sample(a) -> list[dict]:
    from scripts.check_invariants import CUSTOMER_MARKETS, delivered_ids
    ids, _ = delivered_ids(SEED_DIR, CUSTOMER_MARKETS)
    con = sqlite3.connect(f"file:{LIVE_DB.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("select event_id, name, url, main_info_url, sponsor_required, sponsor_url, sponsor_cost, status, start_date from grounding_facts")]
    con.close()
    rows = [r for r in rows if r["event_id"] in ids and (r["main_info_url"] or r["url"]) and str(r["status"] or "").lower() != "retired"]
    rnd = random.Random(a.seed)
    yes = [r for r in rows if str(r["sponsor_required"]).lower() == "yes" and r["sponsor_url"]]
    no = [r for r in rows if str(r["sponsor_required"]).lower() == "no"]
    unk = [r for r in rows if str(r["sponsor_required"]).lower() not in ("yes", "no")]
    out = []
    for grp, n in ((yes, a.yes), (no, a.no), (unk, a.unknown)):
        rnd.shuffle(grp)
        out += grp[:n]
    return out


async def render(url, ctx):
    try:
        html, anchors, st, body, _c = await ctx._f._render_with_consent(url, ctx.settings, _Q(), prefer_cdp=True)
        return (body or ""), [((x.get("href") or ""), (x.get("text") or "")[:80]) for x in (anchors or [])][:600]
    except Exception:                                                  # noqa: BLE001
        return "", []


class _Q:
    def log(self, *a, **k):
        pass


async def one(r, ctx, esq, max_pages, cache, say):
    home = r["main_info_url"] or r["url"]
    hosts = {host(home), host(r["sponsor_url"] or "")} - {""}
    rec = {"event_id": r["event_id"], "name": r["name"], "ours": r["sponsor_required"], "cited": r["sponsor_url"] or "", "home": home, "pages": [], "skipped": ""}
    if hasattr(ctx._f, "_force_fallback_domain") and ctx._f._force_fallback_domain(home):
        rec["skipped"] = "anti-bot host"
        return rec
    urls, labels = [], {}
    try:
        pages, how, _cap, _n, _r = await ctx.cs.collect(ctx.sitewalk.origin(home))
        urls += [u for u, _lm in pages]
    except Exception as e:                                             # noqa: BLE001
        how = type(e).__name__
    body, anchors = await render(home, ctx)
    cache[home] = body
    for href, text in anchors:
        u = urljoin(home, href).split("#")[0]
        if host(u) in hosts and u.startswith("http"):
            urls.append(u)
            if text:
                labels[u] = text
    urls = list(dict.fromkeys(urls))
    chosen = pick_pages(urls, labels, r["sponsor_url"] or "", max_pages)
    rec["candidates"], rec["chosen"] = len(urls), chosen
    targets = ([("control", r["sponsor_url"])] if r["sponsor_url"] else []) + [("found", u) for u in chosen]
    for tier, u in targets:
        text = cache.get(u) or (await render(u, ctx))[0]
        cache[u] = text
        q, kind, status = ("", "", "unreadable")
        if text.strip():
            q, kind, status = await esq.choose(text, r["name"], r["sponsor_cost"] or "", ctx.settings)
        rec["pages"].append({"tier": tier, "url": u, "chars": len(text), "status": status, "kind": kind, "quote": q})
        say(f"     {tier:7} {status:18} {kind:11} {urlparse(u).path[:50]}")
        await asyncio.sleep(2)
    return rec


async def main(a):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("esq", ROOT / "scripts" / "extract_sponsor_quotes.py")
    esq = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(esq)
    from scripts.shadow_finder import build_ctx
    ctx = build_ctx(out / "reader_log.jsonl", 1.0)
    evs = sample(a)
    print(f"sample: {len(evs)} events ({sum(1 for e in evs if str(e['sponsor_required']).lower() == 'yes')} Yes, {sum(1 for e in evs if str(e['sponsor_required']).lower() == 'no')} No, "
          f"{sum(1 for e in evs if str(e['sponsor_required']).lower() not in ('yes', 'no'))} Unknown)")
    t0, cache, results = time.time(), {}, [None] * len(evs)
    sem = asyncio.Semaphore(a.concurrency)                                  # events run side by side, each on its OWN site; within one event the pages are still read 2 s apart

    async def work(i, r):
        async with sem:
            if (time.time() - t0) / 60 > a.max_minutes:
                results[i] = {"event_id": r["event_id"], "name": r["name"], "ours": r["sponsor_required"], "pages": [], "skipped": "time limit"}
                return
            tag = f"[{i + 1}/{len(evs)}] {r['name'][:40]}"
            print(f"{tag}  (ours: {r['sponsor_required']})")
            try:
                results[i] = await one(r, ctx, esq, a.max_pages, cache, lambda m, tag=tag: print(f"   {tag[:14]} {m.strip()}"))
            except Exception as e:                                         # noqa: BLE001
                print(f"   {tag} error {type(e).__name__}: {e}")
                results[i] = {"event_id": r["event_id"], "name": r["name"], "ours": r["sponsor_required"], "pages": [], "skipped": f"error {type(e).__name__}"}
            done = [x for x in results if x]
            (out / "results.json").write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")

    await asyncio.gather(*(work(i, r) for i, r in enumerate(evs)))
    results = [x for x in results if x]
    summarize(results, out, a)


def summarize(results, out, a):
    read = [r for r in results if not r.get("skipped")]
    def proven(r, tiers):
        return [p for p in r["pages"] if p["tier"] in tiers and p["status"] == "ok"]
    yes = [r for r in read if str(r["ours"]).lower() == "yes"]
    L = ["# Sponsorship reader experiment (" + datetime.now().strftime("%Y-%m-%d %H:%M") + ")", "",
         f"Events read: {len(read)} of {len(results)} (skipped: {sum(1 for r in results if r.get('skipped'))}). Pages read: {sum(len(r['pages']) for r in read)}; "
         f"unreadable pages: {sum(1 for r in read for p in r['pages'] if p['status'] == 'unreadable')}.", ""]
    for label, grp in (("Rows upstream says Yes", yes), ("Rows upstream says No", [r for r in read if str(r['ours']).lower() == 'no']), ("Rows with no answer", [r for r in read if str(r['ours']).lower() not in ('yes', 'no')])):
        ctl = sum(1 for r in grp if proven(r, ("control",)))
        anyp = sum(1 for r in grp if proven(r, ("control", "found")))
        fnd = sum(1 for r in grp if proven(r, ("found",)))
        L.append(f"- {label}: {len(grp)} events | proven from the cited page alone: {ctl} | proven from ANY page read: {anyp} | proven only by the pages the finder picked: {anyp - ctl} (finder pages alone: {fnd})")
    pages = sum(len(r['pages']) for r in read)
    L += ["", f"Estimated cost: {pages} page reads x about 0.0006 USD = about {pages * 0.0006:.2f} USD (tokens x the model price, an estimate).", "", "## Every proven sentence (read each one)", ""]
    for r in read:
        for p in proven(r, ("control", "found")):
            L.append(f"- **{r['name']}** (upstream: {r['ours']}) [{p['tier']}, {p['kind']}] {p['url']}\n  > {p['quote']}")
    (out / "RESULT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:12]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--yes", type=int, default=45)
    ap.add_argument("--no", type=int, default=10)
    ap.add_argument("--unknown", type=int, default=10)
    ap.add_argument("--max-pages", type=int, default=4)
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--max-minutes", type=float, default=90)
    ap.add_argument("--seed", type=int, default=20261019)
    asyncio.run(main(ap.parse_args()))
