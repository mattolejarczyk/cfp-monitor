"""Read-only inspection (no Gemini): rerun 4 of the tracer jobs with logging, to see WHICH pages it visits and why it misses.
Wraps the existing tracer's renderer to record each URL, how many characters of text came back, how many menu links the page
offered, how many of the quote's words are on the page, and whether the deadline date is on it. Writes trace_inspect.json.
"""
import asyncio, importlib.util, json, re, sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("tq", ROOT / "scripts" / "trace_quote_to_page.py")
tq = importlib.util.module_from_spec(spec); spec.loader.exec_module(tq)
from src.cfp_monitor.config import Settings            # noqa: E402
from src.cfp_monitor import sitewalk                   # noqa: E402
from src.cfp_monitor.verify import find_date           # noqa: E402

PICK = [("OURS", "Commodity Classic 2027"), ("OURS", "European Biomass Conference & Exhibition"),
        ("E", "SecureWorld East 2026"), ("E", "IEEE Custom Integrated Circuits Conference")]
VISITS = []
_orig = tq._render


async def logged(url, settings):
    text, anchors = await _orig(url, settings)
    ranked = sitewalk.rank_links(anchors, url)
    VISITS.append({"url": url, "chars": len(text), "menu_links": len(ranked),
                   "keyword_links": sum(1 for s, _u, _l in ranked if s), "text": text})
    return text, anchors


tq._render = logged


def words(s):
    return [w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(w) > 2]


async def main():
    settings = Settings()
    sample = {s["row"]["CONFERENCE"]: s for s in json.loads((HERE / "sample.json").read_text(encoding="utf-8"))}
    jobs = json.loads((HERE / "browser_trace.json").read_text(encoding="utf-8"))["jobs"]
    out = []
    for kind, name in PICK:
        j = next(x for x in jobs if x["kind"] == kind and x["row"].startswith(name[:30]))
        dd = date.fromisoformat(sample[next(k for k in sample if k.startswith(name[:30]))]["truth"]["deadline"])
        VISITS.clear()
        found, pages, how = await tq.trace(j["url"], j["quote"], settings, max_pages=5)
        qw = set(words(j["quote"]))
        rec = {"kind": kind, "row": j["row"], "start_url": j["url"], "quote": j["quote"], "how": how, "found": bool(found),
               "visits": [{"url": v["url"], "chars": v["chars"], "menu_links": v["menu_links"],
                           "keyword_links": v["keyword_links"],
                           "quote_words_on_page": round(len(qw & set(words(v["text"]))) / max(1, len(qw)), 2),
                           "deadline_date_on_page": bool(v["text"]) and find_date(v["text"], dd)} for v in VISITS]}
        out.append(rec)
        print(f"{kind} {j['row'][:34]} | how: {how}", flush=True)
        for v in rec["visits"]:
            print(f"    {v['chars']:>6} chars  menu={v['menu_links']:>3} kw={v['keyword_links']:>2}  words={v['quote_words_on_page']:.2f}  date={v['deadline_date_on_page']}  {v['url'][:85]}", flush=True)
    (HERE / "trace_inspect.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("DONE", flush=True)
    try:
        await tq._f.close_fallback_browser()
    except Exception:                                                  # noqa: BLE001
        pass


asyncio.run(main())
