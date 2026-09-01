"""Check cited URLs against what the site itself publishes - its sitemap and its own navigation.

THE GAP THIS CLOSES
`sitewalk.plan` already prefers a page's real navigation and only guesses paths as a last
resort. What nothing does is ask the site for its OWN index. So a stored URL is trusted
indefinitely, and when it rots the pipeline quietly falls back to whatever shallower page still
answers.

That is how the SecureWorld rows broke on 2026-08-31. Two of the three cited candidates were
not real pages:

    events.secureworld.io/speaker-submissions/   404 "Oops! That page can't be found."
    www.secureworld.io/speaker-submission-form   a cookie banner and nothing else

both of which have the SHAPE of a call-for-speakers URL - they look like exactly what
`FALLBACK_PATHS` would guess. With no CFP page reachable, the deadline was taken from
`secureworld.io/events`, a listing where a date beside a conference name is the date it is
HELD. All eight SecureWorld rows ended up with a conference date stored as a submission
deadline. A 404 that returns HTTP 200 with a "not found" body is invisible to a link checker
that only reads the status code, which is why this reads the body too.

WHAT IT ANSWERS, per site
    1. Is the URL we cite actually in the site's sitemap or navigation - or did we invent it?
    2. Does the site publish a call-for-papers page we are not using?
    3. Does the cited page respond with real content, or a soft 404 / consent shell?

It writes nothing and changes nothing. Retargeting a citation is a separate, evidenced step:
a URL existing is not proof it carries the deadline we claim.

    python scripts/check_urls_against_site.py --delivery <csv> [--only NAME] [--max-sites N]
    python scripts/check_urls_against_site.py --site https://www.secureworld.io
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import re
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import fetch as _f                    # noqa: E402
from src.cfp_monitor import sitewalk                       # noqa: E402
from src.cfp_monitor.config import Settings                # noqa: E402

# A page that returns 200 while saying it does not exist. The SecureWorld speaker-submissions
# URL is one of these, which is why status codes alone were not enough.
SOFT_404 = ("page can't be found", "page cannot be found", "page not found", "404 not found",
            "nothing was found at this location", "doesn't exist", "does not exist",
            "no longer available", "oops!")


class _Quiet:
    def log(self, *a, **k) -> None:
        pass


# URL discovery lives in sitewalk, per tests/test_no_reimplemented_crawling.py. This script
# orchestrates fetching and reports; it does not join URLs or parse XML itself.
origin_of = sitewalk.origin


async def _get(url: str, settings):
    """Return (text, ok). Uses the project's own fetch ladder so a JS site is not called dead."""
    try:
        _h, anchors, _st, body, _c = await _f._render_with_consent(url, settings, _Quiet(),
                                                                  prefer_cdp=True)
        return (body or ""), (anchors or [])
    except Exception:                                                  # noqa: BLE001
        return "", []


async def _get_raw(url: str) -> str:
    """Plain HTTP for XML and robots.txt - the browser path mangles them."""
    try:
        import httpx
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as c:
            r = await c.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; cfp-monitor)"})
            if r.status_code == 200:
                return r.text
    except Exception:                                                  # noqa: BLE001
        pass
    return ""


async def sitemap_urls(origin: str, cap: int = 4000) -> tuple[list[str], str]:
    """Every URL the site lists for itself. Returns (urls, how_we_found_them).

    Follows sitemap indexes one level, which is where most large sites keep the real lists.
    """
    robots = await _get_raw(sitewalk.origin(origin) + "/robots.txt")
    seeds = sitewalk.sitemaps_from_robots(robots, origin)
    how = f"robots.txt named {len(seeds)} sitemap(s)"
    if not seeds:
        seeds = sitewalk.sitemap_candidates(origin)
        how = "tried the conventional sitemap paths"

    out: list[str] = []
    queue, seen_maps = list(seeds), set()
    while queue and len(out) < cap and len(seen_maps) < 12:
        sm = queue.pop(0)
        if sm in seen_maps:
            continue
        seen_maps.add(sm)
        locs, is_index = sitewalk.parse_sitemap(await _get_raw(sm))
        if is_index:
            queue.extend(locs[:12])
        else:
            out.extend(locs)
    return out[:cap], how


def cfp_like(urls: list[str]) -> list[tuple[int, str]]:
    """Score only things that could BE a page.

    `sitewalk.relevance` matches on the path, so `/hubfs/speakers/Aaron-Jentzen.jpg` scores as
    call-for-speakers-like. `rank_links` never sees that because it applies `NOT_A_PAGE` first;
    a sitemap is not filtered for us, so apply it here or the answer to "does this site publish
    a call page" is a list of headshots.
    """
    out = []
    for u in urls:
        if sitewalk.NOT_A_PAGE.search(u):
            continue
        s = sitewalk.relevance(u)
        if s > 0:
            out.append((s, u))
    return sorted(set(out), key=lambda x: (-x[0], x[1]))


def looks_soft_404(body: str) -> str:
    low = re.sub(r"\s+", " ", body or "").lower()
    if not low.strip():
        return "empty body"
    for m in SOFT_404:
        if m in low:
            return f"soft 404 - page says {m!r}"
    # Short AND saying nothing about a call. Length alone is the wrong test: a real
    # call-for-papers page can be three sentences, and calling that a shell would push someone
    # to abandon a sound citation - the same over-reach as the withdrawal defect. A page that
    # talks about deadlines is content however short it is.
    if len(low) < 400 and not any(w in low for w in
                                  ("deadline", "submission", "submit", "call for", "abstract",
                                   "cfp", "proposal", "due ", "closes")):
        return f"almost no content ({len(low)} chars) and no mention of a call - likely a shell"
    return ""


async def check_site(origin: str, cited: list[tuple[str, str]], settings) -> None:
    print("=" * 78)
    print(origin)
    smap, how = await sitemap_urls(origin)
    home_body, home_anchors = await _get(origin, settings)
    nav = [u for _s, u, _l in sitewalk.rank_links(home_anchors, origin)]
    print(f"  sitemap : {len(smap)} url(s)  ({how})")
    print(f"  nav     : {len(nav)} link(s) from the homepage")

    known = {u.rstrip("/").lower() for u in smap + nav}

    print(f"\n  CITED BY US ({len(cited)}):")
    for url, why in cited:
        in_site = url.rstrip("/").lower() in known
        body, _a = await _get(url, settings)
        bad = looks_soft_404(body)
        mark = "ok " if in_site and not bad else "BAD"
        print(f"    [{mark}] {url[:70]}")
        print(f"          {why}")
        print(f"          in the site's own sitemap/nav : {'YES' if in_site else 'NO'}"
              f"{'' if in_site else '  <- we may have guessed this path'}")
        if bad:
            print(f"          content: {bad}")

    cands = cfp_like(smap + nav)
    print(f"\n  WHAT THE SITE PUBLISHES that looks like a call ({len(cands)}):")
    if not cands:
        print("    none - no sitemap or nav URL scores as call-for-papers-like")
    for score, u in cands[:12]:
        star = "  <- not cited by us" if u.rstrip("/").lower() not in {
            c.rstrip("/").lower() for c, _ in cited} else ""
        print(f"    {score:>3}  {u[:70]}{star}")
    print()


async def main() -> int:
    ap = argparse.ArgumentParser(description="Check cited URLs against a site's own map.")
    ap.add_argument("--delivery")
    ap.add_argument("--site", help="check one origin directly")
    ap.add_argument("--only", default="", help="substring match on CONFERENCE")
    ap.add_argument("--max-sites", type=int, default=6)
    a = ap.parse_args()
    settings = Settings()

    sites: dict[str, list[tuple[str, str]]] = {}
    if a.site:
        sites[origin_of(a.site)] = []
    if a.delivery:
        cols = ["DEADLINE_EVIDENCE_URL", "CFP_SUBMISSION_URL", "SUBMISSION URL",
                "MAIN_INFO_URL", "CONFERENCE URL"]
        with open(a.delivery, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                name = (r.get("CONFERENCE") or "").strip()
                if a.only and a.only.lower() not in name.lower():
                    continue
                for c in cols:
                    u = (r.get(c) or "").strip()
                    if not u.startswith("http"):
                        continue
                    o = origin_of(u)
                    if not o:
                        continue
                    pairs = sites.setdefault(o, [])
                    if not any(p[0] == u for p in pairs):
                        pairs.append((u, f"{c} for {name[:40]}"))

    if not sites:
        print("nothing to check")
        return 0
    print(f"{len(sites)} site(s); checking up to {a.max_sites}\n")
    try:
        for o in list(sites)[:a.max_sites]:
            await check_site(o, sites[o], settings)
    finally:
        try:
            await _f.close_fallback_browser()
        except Exception:                                              # noqa: BLE001
            pass
    print("Read-only. A URL existing is not proof it carries the deadline we claim -")
    print("retargeting a citation is a separate, evidenced step.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
