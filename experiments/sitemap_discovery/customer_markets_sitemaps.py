"""Sitemap discovery + crawl-priority classification for the TWO customer markets only (Cybersecurity, Utility).

NO PAGE CRAWLING. Network use is limited to robots.txt and sitemap XML files (plain HTTP, 1.5 s between requests, one host at a
time). Reuses sitewalk (sitemaps_from_robots, sitemap_candidates, parse_sitemap, NOT_A_PAGE, origin) and
check_urls_against_site._get_raw. Read-only on the database. Writes customer_markets.json / customer_markets.md here.

Per site it reports: sitemap found (how), URLs listed, URLs that are real pages, URLs dropped as generic, pages that qualify
for crawling by tier, what a 50-page cap would select, and pages naming 2027 (next-edition hint).
"""
import os, asyncio, importlib.util, json, re, sqlite3, sys
from collections import defaultdict
from pathlib import Path
from statistics import median
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("cu", ROOT / "scripts" / "check_urls_against_site.py")
cu = importlib.util.module_from_spec(spec); spec.loader.exec_module(cu)
from src.cfp_monitor import sitewalk                                   # noqa: E402

DB = os.path.join(os.environ.get("LOCALAPPDATA", ""), "CFP-Monitor", "cfp_monitor.db")   # the live database, read-only here
MARKETS = ("Cybersecurity", "Utility")
CAP = 50
MAX_URLS = 20000
MAX_MAPS = 25

# ---- crawl-priority rules (extend sitewalk.WORTH_FOLLOWING; every keyword there is covered by a tier below) ----
TIERS = [
    ("P1 call/submission", 4, re.compile(
        r"cfp|call[-_ ]?for|papers?|abstracts?|speaker[-_ ]?(submission|application|portal|form)|become[-_ ]a[-_ ]speaker|"
        r"submit|submission|propos(al|e)|deadline|important[-_ ]?dates|dates[-_ ]and[-_ ]deadlines|author|apply|nominat", re.I)),
    ("P2 programme/awards", 3, re.compile(
        r"programme|program|agenda|schedule|sessions?|speakers?|tracks?|topics?|themes?|award|prize|competition", re.I)),
    ("P3 sponsor/exhibit", 2, re.compile(r"sponsor|exhibit|partner|booth|vendor", re.I)),
    ("P4 edition/venue", 1, re.compile(r"2027|2026|next[-_ ]year|save[-_ ]the[-_ ]date|venue|location|register|registration|tickets?|about", re.I)),
]
GENERIC = re.compile(
    r"privacy|terms|legal|disclaimer|cookie|imprint|impressum|accessibility|gdpr|code[-_ ]of[-_ ]conduct|"
    r"sitemap|log-?in|sign-?in|sign-?up|my-?account|/account|/cart|checkout|basket|careers?|/jobs?|unsubscribe|"
    r"wp-admin|wp-json|/feed|/tag/|/category/|/author/|/page/\d+|/search|/print|contact|press-release|/news/|/blog/|"
    r"/media/|/gallery|/photos?|/video|/podcast|/shop|/store|login|password|thank-you|confirmation", re.I)
ASSET = re.compile(r"wp-content/uploads|/hubfs/|/assets/|/static/|/_next/|/cdn-cgi/|\.(css|js|json|xml|txt|map)($|\?)", re.I)
LANG = re.compile(r"^/(fr|de|es|it|pt|ja|zh|ko|nl|ru|ar|pl|tr|sv|da|fi|no|cs|hu|th|vi|id|he|el)(/|$)", re.I)


def classify(url):
    """Return (kind, tier_name, score). kind: file | asset | generic | lang | page."""
    if sitewalk.NOT_A_PAGE.search(url):
        return "file", "", 0
    path = urlparse(url).path or "/"
    if ASSET.search(url):
        return "asset", "", 0
    if LANG.search(path):
        return "lang", "", 0
    if GENERIC.search(path):
        return "generic", "", 0
    for name, score, rx in TIERS:
        if rx.search(path):
            return "page", name, score
    return "page", "other", 0


def depth(url):
    return len([s for s in urlparse(url).path.split("/") if s])


async def collect(origin):
    robots = await cu._get_raw(origin + "/robots.txt")
    seeds = sitewalk.sitemaps_from_robots(robots, origin)
    how = f"robots.txt named {len(seeds)} sitemap(s)" if seeds else "conventional path"
    if not seeds:
        seeds = sitewalk.sitemap_candidates(origin)
    out, lastmod, queue, seen = [], 0, list(seeds), set()
    capped = False
    while queue and len(seen) < MAX_MAPS:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        raw = await cu._get_raw(sm)
        await asyncio.sleep(1.5)
        locs, is_index = sitewalk.parse_sitemap(raw)
        lastmod += len(re.findall(r"<lastmod>", raw))
        if is_index:
            queue.extend(locs[:MAX_MAPS])
        else:
            out.extend(locs)
        if len(out) >= MAX_URLS:
            capped = True
            break
    return out[:MAX_URLS], (how if out else "none found"), lastmod > 0, capped, len(seen), bool(robots)


def load_sites():
    c = sqlite3.connect(f"file:///{DB.replace(chr(92), '/')}?mode=ro", uri=True)
    q = ("select cm.market, g.name, g.conference_key, g.url, g.main_info_url, g.submission_url, g.deadline_evidence_url "
         "from conference_markets cm join grounding_facts g on g.conference_key = cm.conference_key "
         f"where cm.market in ({','.join('?' * len(MARKETS))})")
    sites = defaultdict(lambda: {"markets": set(), "events": set(), "prefixes": set()})
    for market, name, key, url, main, sub, ev in c.execute(q, MARKETS):
        base = main or url or ev or sub or ("https://" + (key or ""))
        if not str(base).startswith("http"):
            continue
        o = sitewalk.origin(base)
        host = urlparse(o).netloc.lower().removeprefix("www.")
        s = sites[host]
        s.setdefault("origin", o)
        s["markets"].add(market); s["events"].add(name)
        seg = [x for x in urlparse(base).path.split("/") if x]
        if seg:
            s["prefixes"].add("/" + seg[0].lower())
    return sites


async def main():
    sites = load_sites()
    print(f"{len(sites)} distinct sites across {', '.join(MARKETS)}", flush=True)
    results = []
    for n, (host, s) in enumerate(sorted(sites.items()), 1):
        origin = s["origin"]
        try:
            urls, how, has_lastmod, capped, nmaps, has_robots = await collect(origin)
        except Exception as e:                                          # noqa: BLE001
            urls, how, has_lastmod, capped, nmaps, has_robots = [], f"error {type(e).__name__}", False, False, 0, False
        uniq = {}
        for u in urls:
            k = u.split("#")[0].split("?")[0].rstrip("/").lower()
            uniq.setdefault(k, u)
        rows = [(u, *classify(u)) for u in uniq.values()]
        kinds = defaultdict(int)
        for _u, kind, _t, _s in rows:
            kinds[kind] += 1
        pages = [(u, t, sc) for u, kind, t, sc in rows if kind == "page"]
        # a platform hosting many events: scope to this market's own event path prefixes
        scoped = len(uniq) >= 300 and bool(s["prefixes"])
        scope_note = ""
        if scoped:
            pref = tuple(s["prefixes"])
            in_scope = [p for p in pages if urlparse(p[0]).path.lower().startswith(pref)]
            scope_note = f"scoped to {sorted(s['prefixes'])[:3]}: {len(in_scope)} of {len(pages)} pages"
            pages = in_scope if in_scope else pages
            if not in_scope:
                scope_note += " (no page under that path; whole site used)"
        qual = [p for p in pages if p[2] > 0]
        qual.sort(key=lambda p: (-p[2], depth(p[0]), len(p[0])))
        sel = qual[:CAP]
        by_tier = defaultdict(int)
        for _u, t, _sc in qual:
            by_tier[t] += 1
        sel_tier = defaultdict(int)
        for _u, t, _sc in sel:
            sel_tier[t] += 1
        rec = {"site": origin, "markets": sorted(s["markets"]), "events": len(s["events"]), "event_names": sorted(s["events"])[:4],
               "sitemap_found": bool(urls), "how": how, "robots_txt": has_robots, "sitemap_files_read": nmaps,
               "has_lastmod": has_lastmod, "hit_url_cap": capped, "urls_listed": len(uniq),
               "dropped": {k: v for k, v in kinds.items() if k != "page"}, "pages": len(pages), "scope": scope_note,
               "qualifying": len(qual), "by_tier": dict(by_tier), "selected": len(sel), "selected_by_tier": dict(sel_tier),
               "cap_binds": len(qual) > CAP, "pages_naming_2027": sum(bool(re.search(r"2027", p[0])) for p in pages),
               "sample_selected": [p[0] for p in sel[:5]]}
        results.append(rec)
        print(f"[{n}/{len(sites)}] {host[:34]:<34} listed={len(uniq):>5} pages={len(pages):>5} qualify={len(qual):>4} "
              f"select={len(sel):>3} {'CAP ' if rec['cap_binds'] else '    '}{how[:22]}", flush=True)
        (HERE / "customer_markets.json").write_text(json.dumps({"sites": results}, indent=1), encoding="utf-8")

    have = [r for r in results if r["sitemap_found"]]
    qs = sorted(r["qualifying"] for r in have)
    sel = [r["selected"] for r in have]
    summ = {"sites": len(results), "with_sitemap": len(have), "without_sitemap": len(results) - len(have),
            "robots_named": sum(r["how"].startswith("robots") for r in have),
            "with_lastmod": sum(r["has_lastmod"] for r in have),
            "hit_url_cap": sum(r["hit_url_cap"] for r in have),
            "qualifying_per_site": {"min": qs[0] if qs else 0, "median": median(qs) if qs else 0,
                                    "p75": qs[int(len(qs) * .75)] if qs else 0, "max": qs[-1] if qs else 0},
            "sites_zero_qualifying": sum(r["qualifying"] == 0 for r in have),
            "sites_1_to_50": sum(0 < r["qualifying"] <= CAP for r in have),
            "sites_over_50": sum(r["qualifying"] > CAP for r in have),
            "total_pages_selected_at_cap_50": sum(sel), "sites_with_2027_pages": sum(r["pages_naming_2027"] > 0 for r in have)}
    (HERE / "customer_markets.json").write_text(json.dumps({"summary": summ, "sites": results}, indent=1), encoding="utf-8")
    print(json.dumps(summ), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
