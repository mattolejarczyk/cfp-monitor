"""Sitemap availability on the real sites from the grounding-reliability sample. Plain HTTP only: robots.txt + sitemap files.
No browser, no AI. Reuses scripts/check_urls_against_site.py (sitemap_urls, cfp_like, _get_raw) and src/cfp_monitor/sitewalk.
Asks, per site: does it publish a sitemap; how many pages; do entries carry <lastmod>; how many look like a call page; is the
page we already hold as verified evidence listed; do other year-2027-looking pages exist. Writes measure.json here.
"""
import asyncio, importlib.util, json, re, sys
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("cu", ROOT / "scripts" / "check_urls_against_site.py")
cu = importlib.util.module_from_spec(spec); spec.loader.exec_module(cu)
from src.cfp_monitor import sitewalk                              # noqa: E402

GR = ROOT / "experiments" / "grounding_reliability"


async def main():
    sample = json.loads((GR / "sample.json").read_text(encoding="utf-8"))
    bv = json.loads((GR / "browser_verify.json").read_text(encoding="utf-8"))
    cited = {}   # origin -> {"verified": set(), "model": set()}
    for s in sample:
        o = sitewalk.origin(s["truth"]["evidence_url"])
        cited.setdefault(o, {"verified": set(), "model": set(), "names": set()})["verified"].add(s["truth"]["evidence_url"])
        cited[o]["names"].add(s["row"]["CONFERENCE"][:30])
    for r in bv["rows"]:
        for u in (r["ev_url"], r["cfp_url"]):
            o = sitewalk.origin(u) if u.startswith("http") else ""
            if o and not re.search(r"facebook|linkedin", o):
                cited.setdefault(o, {"verified": set(), "model": set(), "names": set()})["model"].add(u)
    print(f"{len(cited)} sites", flush=True)
    out = []
    for o, d in sorted(cited.items()):
        robots = await cu._get_raw(o + "/robots.txt")
        named = sitewalk.sitemaps_from_robots(robots, o)
        urls, how = await cu.sitemap_urls(o)
        raw0 = await cu._get_raw(named[0] if named else o + "/sitemap.xml") if (named or urls) else ""
        lastmod = len(re.findall(r"<lastmod>", raw0))
        pages = [u for u in urls if not sitewalk.NOT_A_PAGE.search(u)]
        call = cu.cfp_like(pages)
        known = {u.rstrip("/").lower() for u in urls}
        ver_in = [u.rstrip("/").lower() in known for u in d["verified"]]
        mod_in = [u.rstrip("/").lower() in known for u in d["model"]]
        rec = {"site": o, "events": sorted(d["names"]), "robots_txt": bool(robots), "robots_names_sitemap": len(named),
               "how": how, "sitemap_urls": len(urls), "pages_not_files": len(pages),
               "first_sitemap_has_lastmod": lastmod > 0, "lastmod_entries_in_first_sitemap": lastmod,
               "call_like_pages": len(call), "top_call_like": [u for _s, u in call[:3]],
               "verified_evidence_url_in_sitemap": f"{sum(ver_in)}/{len(ver_in)}",
               "model_cited_urls_in_sitemap": f"{sum(mod_in)}/{len(mod_in)}",
               "urls_mentioning_2027": sum(bool(re.search(r"2027", u)) for u in pages)}
        out.append(rec)
        print(f"{o[8:40]:<32} sitemap={len(urls):>5} call-like={len(call):>3} lastmod={'Y' if lastmod else 'n'} "
              f"verified-in-map={rec['verified_evidence_url_in_sitemap']} model-in-map={rec['model_cited_urls_in_sitemap']} 2027={rec['urls_mentioning_2027']}", flush=True)
        await asyncio.sleep(1.5)
    n = len(out)
    summ = {"sites": n, "with_sitemap": sum(r["sitemap_urls"] > 0 for r in out),
            "robots_names_a_sitemap": sum(r["robots_names_sitemap"] > 0 for r in out),
            "with_lastmod": sum(r["first_sitemap_has_lastmod"] for r in out),
            "with_call_like_pages": sum(r["call_like_pages"] > 0 for r in out),
            "sites_listing_2027_pages": sum(r["urls_mentioning_2027"] > 0 for r in out),
            "median_pages": sorted(r["pages_not_files"] for r in out)[n // 2]}
    (HERE / "measure.json").write_text(json.dumps({"summary": summ, "sites": out}, indent=1), encoding="utf-8")
    print(json.dumps(summ), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
