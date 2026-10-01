"""Second, deeper free pass (no Gemini): for every quote NOT found on its cited page by browser_verify.py, walk the event's own
site with the repo's existing tracer (scripts/trace_quote_to_page.trace - imported, not re-implemented) looking for the exact
sentence, max 5 pages each. Also traces our OWN verified quotes that were not found, as calibration.
Writes browser_trace.json here; nothing else.
"""
import asyncio, importlib.util, json, re, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("tq", ROOT / "scripts" / "trace_quote_to_page.py")
tq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tq)                                   # existing tracer, unchanged
from src.cfp_monitor.config import Settings                   # noqa: E402

MAX_PAGES = 5


async def main():
    settings = Settings()
    sample = json.loads((HERE / "sample.json").read_text(encoding="utf-8"))
    bv = json.loads((HERE / "browser_verify.json").read_text(encoding="utf-8"))
    calls = [json.loads(l) for l in (HERE / "calls.jsonl").read_text(encoding="utf-8").splitlines()
             if json.loads(l)["outcome"] == "ok_searched"]
    jobs, seen = [], set()
    for c, r in zip(calls, bv["rows"]):
        if r["quote_verbatim_on_cited_page"] or not r["ev_rendered"]:
            continue
        m = re.search(r"\{.*\}", c["text"], re.S)
        q = (json.loads(m.group(0)).get("DEADLINE_QUOTE") or "") if m else ""
        k = (r["ev_url"], tq.norm(q))
        if q and k not in seen:
            seen.add(k)
            jobs.append({"kind": r["arm"], "row": r["row"], "url": r["ev_url"], "quote": q})
    for s, cal in zip(sample, bv["calibration"]):
        if not cal["quote_found"]:
            jobs.append({"kind": "OURS", "row": s["row"]["CONFERENCE"], "url": s["truth"]["evidence_url"],
                         "quote": s["truth"]["quote"]})
    print(f"{len(jobs)} traces to run (max {MAX_PAGES} pages each)", flush=True)
    out = []
    for n, j in enumerate(jobs, 1):
        t0 = time.time()
        try:
            found, pages, how = await tq.trace(j["url"], j["quote"], settings, max_pages=MAX_PAGES)
        except Exception as e:                                             # noqa: BLE001
            found, pages, how = None, 0, f"error {type(e).__name__}"
        j.update(found_url=found, pages_read=pages, how=how, secs=round(time.time() - t0, 1))
        out.append(j)
        print(f"[{n}/{len(jobs)}] {j['kind']:<4} found={'YES' if found else 'no ':<3} pages={pages} {j['secs']:>5}s  {j['row'][:34]}", flush=True)
    summ = {}
    for kind in ("A", "E", "OURS"):
        js = [j for j in out if j["kind"] == kind]
        summ[kind] = {"traced": len(js), "quote_found_by_site_walk": sum(bool(j["found_url"]) for j in js),
                      "pages_could_not_be_read": sum(j["pages_read"] == 0 for j in js)}
    (HERE / "browser_trace.json").write_text(json.dumps({"summary": summ, "jobs": out}, indent=1), encoding="utf-8")
    print(json.dumps(summ, indent=1), flush=True)
    try:
        await tq._f.close_fallback_browser()
    except Exception:                                                      # noqa: BLE001
        pass


if __name__ == "__main__":
    asyncio.run(main())
