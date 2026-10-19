"""Collect the page TEXT needed to judge 'does speaking require paying?' for a sample of events (2026-10-19, read-only, writes only under --out-dir).

    python experiments/sponsor_reader/collect.py --out-dir <dir> [--n 40] [--seed 20261020] [--concurrency 5]

For each event: the home page, the page upstream cited for sponsorship, up to 3 sponsor-type pages and up to 3 CALL-FOR-SPEAKERS pages (picked from the site's sitemap and menu by URL and link-text
words). The question is a CROSS-PAGE one (is there an open call anyone can submit to, AND does the sponsorship page sell or promise speaking slots), so a one-page-at-a-time sentence hunt cannot answer it.
Output: <out-dir>/pages/<n>.json per event {event, ours, cost, pages:[{kind, url, text}]} and index.json. Network: sitemap, home page, <= 7 pages per event, 2 s apart, no hard anti-bot hosts."""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import random
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("sr", HERE / "run.py")
sr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sr)

CALL_WORDS = (("call-for", 4), ("call for", 4), ("cfp", 4), ("speaker", 3), ("speak", 2), ("submit", 2), ("abstract", 3), ("proposal", 3), ("paper", 2), ("present", 1), ("nominat", 1), ("apply", 1))


def call_score(url: str, label: str) -> int:
    t = (urlparse(url).path + " " + (label or "")).lower()
    return sum(w for k, w in CALL_WORDS if k in t)


def pick_call(urls, labels, exclude, k):
    seen, ranked = set(exclude), []
    for u in urls:
        key = u.rstrip("/").lower()
        if key in seen or sr.AVOID.search(urlparse(u).path):
            continue
        seen.add(key)
        s = call_score(u, labels.get(u, ""))
        if s > 0:
            ranked.append((s, -len(urlparse(u).path), u))
    ranked.sort(reverse=True)
    return [u for _s, _l, u in ranked[:k]]


async def one(r, ctx, cache):
    home = r["main_info_url"] or r["url"]
    hosts = {sr.host(home), sr.host(r["sponsor_url"] or "")} - {""}
    rec = {"event_id": r["event_id"], "name": r["name"], "ours": r["sponsor_required"], "cost": r["sponsor_cost"] or "", "home": home, "pages": [], "skipped": ""}
    if hasattr(ctx._f, "_force_fallback_domain") and ctx._f._force_fallback_domain(home):
        rec["skipped"] = "anti-bot host"
        return rec
    urls, labels = [], {}
    try:
        pages, _how, _cap, _n, _r = await ctx.cs.collect(ctx.sitewalk.origin(home))
        urls += [u for u, _lm in pages]
    except Exception:                                                  # noqa: BLE001
        pass
    body, anchors = await sr.render(home, ctx)
    cache[home] = body
    for href, text in anchors:
        u = urljoin(home, href).split("#")[0]
        if sr.host(u) in hosts and u.startswith("http"):
            urls.append(u)
            if text:
                labels[u] = text
    urls = list(dict.fromkeys(urls))
    spons = sr.pick_pages(urls, labels, r["sponsor_url"] or "", 3)
    calls = pick_call(urls, labels, set(u.rstrip("/").lower() for u in spons + [home, r["sponsor_url"] or ""]), 3)
    targets = [("home", home)] + ([("cited-sponsor", r["sponsor_url"])] if r["sponsor_url"] else []) + [("sponsor", u) for u in spons] + [("call", u) for u in calls]
    for kind, u in targets:
        text = cache.get(u)
        if text is None:
            text = (await sr.render(u, ctx))[0]
            cache[u] = text
            await asyncio.sleep(2)
        rec["pages"].append({"kind": kind, "url": u, "text": text[:40000]})
    return rec


async def main(a):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out = Path(a.out_dir)
    (out / "pages").mkdir(parents=True, exist_ok=True)
    from scripts.shadow_finder import build_ctx
    ctx = build_ctx(out / "reader_log.jsonl", 1.0)
    a.yes, a.no, a.unknown = a.n, 0, 0                                  # sample() draws Yes rows first; the mix is balanced below
    evs = sr.sample(a)
    rnd = random.Random(a.seed)
    rnd.shuffle(evs)
    evs = evs[: a.n]
    sem, cache, index = asyncio.Semaphore(a.concurrency), {}, []

    async def work(i, r):
        async with sem:
            try:
                rec = await one(r, ctx, cache)
            except Exception as e:                                     # noqa: BLE001
                rec = {"event_id": r["event_id"], "name": r["name"], "ours": r["sponsor_required"], "pages": [], "skipped": f"error {type(e).__name__}"}
            (out / "pages" / f"{i:03d}.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            index.append({"n": i, "name": r["name"], "pages": [(p["kind"], len(p["text"])) for p in rec["pages"]], "skipped": rec.get("skipped", "")})
            print(f"[{i + 1}/{len(evs)}] {r['name'][:50]}: " + ", ".join(f"{p['kind']}={len(p['text'])}" for p in rec["pages"]), flush=True)
    await asyncio.gather(*(work(i, r) for i, r in enumerate(evs)))
    (out / "index.json").write_text(json.dumps(sorted(index, key=lambda x: x["n"]), ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20261020)
    ap.add_argument("--concurrency", type=int, default=5)
    asyncio.run(main(ap.parse_args()))
