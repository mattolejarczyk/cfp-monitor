"""How much is behind a menu link we currently throw away?

MEASURES AN OPPORTUNITY, CHANGES NOTHING. Before building link-following, find out whether the
links are there. `fetch_text` reduces a page to visible text with `re.sub(r"<[^>]+>", " ")`,
which keeps the words "Call for Papers" and destroys the href attached to them. So a page can
advertise exactly the page we need and we cannot follow it, because by the time anything reads
the page the address is gone.

This re-fetches the still-blank rows keeping (anchor text -> href) pairs, and counts the rows
that carry a submission-shaped link we are not already trying. That number is the size of the
prize; if it is small, link-following is not worth building.

    python scripts/probe_menu_links.py -i citations_extracted_93.csv -c candidate_urls.csv
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor.verify import _ctx                # noqa: E402

# Anchor wording that points at a submission page. Deliberately narrow: this is measuring an
# opportunity, and an inflated count would argue for building something that does not pay.
WANTED = re.compile(
    r"call for (papers|abstracts|speakers|sessions|presentations|submissions|proposals|posters)"
    r"|submit (an |your )?(abstract|paper|proposal|session|talk|poster)"
    r"|abstract submission|paper submission|speaker application|present at"
    r"|cfp\b|call for participation|submission guidelines|important dates|key dates",
    re.I)

_A = re.compile(r"<a\b[^>]*href\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
_TAGS = re.compile(r"<[^>]+>")


def links_plain(url: str) -> list[tuple[str, str]]:
    """(anchor text, absolute href) over plain HTTP, or [] if the page cannot be read."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "text/html,application/xhtml+xml"})
        with urllib.request.urlopen(req, timeout=20, context=_ctx()) as resp:
            html = resp.read(900_000).decode("utf-8", "ignore")
    except Exception:
        return []
    out = []
    for m in _A.finditer(html):
        href, label = m.group(1), " ".join(_TAGS.sub(" ", m.group(2)).split())
        if label and href and not href.startswith(("#", "mailto:", "tel:", "javascript:")):
            out.append((label, urljoin(url, href)))
    return out


async def links_browser(urls: list[str]) -> dict[str, list[tuple[str, str]]]:
    """Same, through the ladder. The rung that can actually see a JS-built menu.

    The plain-HTTP probe measured 4 of 46, and was blind to exactly the pages that blocked us
    in the first place - a JS-only site serves an empty shell to urllib, menu included. So the
    first number was a floor, not an answer.

    Uses the fetch layer directly rather than audit_evidence.escalate, because escalate returns
    TEXT and the whole question here is about hrefs. PageFetch already carries `.links` as
    classified {href, text} pairs; nothing new has to be parsed.
    """
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

    from src.cfp_monitor.config import Settings
    from src.cfp_monitor.fetch import fetch_page
    from src.cfp_monitor.trace import Tracer

    settings = Settings()
    cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, verbose=False,
                           remove_consent_popups=settings.remove_consent_popups,
                           remove_overlay_elements=settings.remove_overlay_elements,
                           magic=settings.crawl_magic,
                           page_timeout=settings.primary_page_timeout_s * 1000)
    tracer = Tracer()
    out: dict[str, list[tuple[str, str]]] = {}
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        for i, url in enumerate(urls, 1):
            try:
                pf = await asyncio.wait_for(fetch_page(crawler, url, cfg, settings, tracer),
                                            timeout=settings.per_site_timeout_s)
            except Exception as exc:
                print(f"  [{i}/{len(urls)}] {url[:56]} -> {type(exc).__name__}", flush=True)
                continue
            found = [(a.get("text", ""), a.get("href", ""))
                     for a in pf.links.get("internal", []) if a.get("href")]
            out[url] = found
            print(f"  [{i}/{len(urls)}] {url[:56]} -> {pf.via} ({len(found)} internal)",
                  flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Size the menu-link opportunity. Writes nothing.")
    ap.add_argument("-i", "--input", required=True)
    ap.add_argument("-c", "--candidates", required=True)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--plain", action="store_true",
                    help="plain HTTP only - blind to JS-built menus, reports a floor")
    a = ap.parse_args()

    with open(a.input, encoding="utf-8-sig", newline="") as fh:
        done = {r["EVENT_ID"]: r for r in csv.DictReader(fh)}
    with open(a.candidates, encoding="utf-8-sig", newline="") as fh:
        cands = list(csv.DictReader(fh))

    targets = []
    for r in cands:
        if done.get(r["EVENT_ID"], {}).get("DEADLINE_EVIDENCE_URL"):
            continue
        urls = [u.strip() for u in (r.get("CANDIDATE_URLS") or "").split("|") if u.strip()]
        if urls:
            targets.append((r["CONFERENCE"], urls))
    if a.limit:
        targets = targets[:a.limit]

    print(f"{len(targets)} still-blank row(s) with a page to look at\n")
    every = [u for _, urls in targets for u in urls]
    if a.plain:
        pages = {u: links_plain(u) for u in every}
    else:
        print(f"--- reading {len(every)} page(s) through the ladder ---")
        pages = asyncio.run(links_browser(every))
        # Union with plain HTTP. A static site hands urllib every anchor, while a render can
        # drop links hidden behind a collapsed menu - neither rung dominates the other.
        for u in every:
            pages[u] = sorted({(t, h) for t, h in pages.get(u, [])} | set(links_plain(u)))
        print()

    hits, rows_with, seen_any = [], 0, 0
    for conf, urls in targets:
        tried = {u.rstrip("/") for u in urls}
        found: list[tuple[str, str]] = []
        if any(pages.get(u) for u in urls):
            seen_any += 1
        for u in urls:
            for label, href in pages.get(u, []):
                if not WANTED.search(label):
                    continue
                # Only count links we are NOT already trying, and stay on the event's own site.
                if href.rstrip("/") in tried:
                    continue
                if urlparse(href).netloc != urlparse(u).netloc:
                    continue
                if href not in [h for _, h in found]:
                    found.append((label, href))
        if found:
            rows_with += 1
            hits.append((conf, found[:3]))

    print(f"{rows_with} of {len(targets)} blank rows advertise a submission link "
          f"we are not following")
    print(f"({seen_any} of {len(targets)} rows yielded ANY links at all - the rest could not "
          f"be read, so they count neither for nor against)\n")
    for conf, found in hits:
        print(f"  {conf[:52]}")
        for label, href in found:
            print(f"      \"{label[:38]:<38}\" -> {href[:78]}")
    print("\nNothing was written. This only measures whether link-following would pay.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
