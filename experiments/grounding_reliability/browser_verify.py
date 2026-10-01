"""Free (no Gemini) live-page check of the answers saved by probe_narrow.py.

For every distinct (cited evidence page, quote) and every distinct CFP_SUBMISSION_URL in calls.jsonl, render the page with
the repo's OWN browser rung (fetch._render_with_consent, prefer_cdp - the same call trace_quote_to_page.py uses; never
re-implemented) and test:
  - the quote appears on the page, word for word after whitespace/case normalisation (full match only);
  - the deadline date appears on the page (verify.find_date);
  - the page rendered at all.
Calibration: our OWN verified quote against our OWN verified page, so a failure to find text is not blamed on the model.
Each URL is rendered once (cached). Writes browser_verify.json here; nothing else.
"""
import asyncio, json, re, sys, time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from src.cfp_monitor import fetch as _f                      # noqa: E402
from src.cfp_monitor.config import Settings                  # noqa: E402
from src.cfp_monitor.verify import find_date                 # noqa: E402

CALLPAGE = re.compile(r"call for|speaker|submit|submission|abstract|proposal|cfp|present", re.I)
norm = lambda s: re.sub(r"\s+", " ", str(s or "")).strip().lower()


class _Quiet:
    def log(self, *a, **k):
        pass


async def render(url, settings, cache):
    if url in cache:
        return cache[url]
    t0 = time.time()
    try:
        _h, _a, status, body, _c = await _f._render_with_consent(url, settings, _Quiet(), prefer_cdp=True)
        cache[url] = {"text": norm(body), "status": status, "err": ""}
    except Exception as e:                                                # noqa: BLE001
        cache[url] = {"text": "", "status": None, "err": type(e).__name__}
    print(f"  rendered {len(cache[url]['text']):>7} chars {time.time()-t0:5.1f}s  {url[:90]}", flush=True)
    await asyncio.sleep(2)
    return cache[url]


async def main():
    settings = Settings()
    sample = json.loads((HERE / "sample.json").read_text(encoding="utf-8"))
    calls = [json.loads(l) for l in (HERE / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    ok = [c for c in calls if c["outcome"] == "ok_searched"]
    answers = []
    for c in ok:
        m = re.search(r"\{.*\}", c["text"], re.S)
        d = json.loads(m.group(0)) if m else {}
        answers.append((c, d))
    urls = {s["truth"]["evidence_url"] for s in sample}
    for c, d in answers:
        for k in ("DEADLINE_EVIDENCE_URL", "CFP_SUBMISSION_URL"):
            if (d.get(k) or "").startswith("http"):
                urls.add(d[k])
    print(f"{len(urls)} distinct pages to render (plus calibration on the {len(sample)} verified pages)", flush=True)
    cache = {}

    cal = []
    for s in sample:
        r = await render(s["truth"]["evidence_url"], settings, cache)
        dd = date.fromisoformat(s["truth"]["deadline"])
        cal.append({"row": s["row"]["CONFERENCE"], "rendered": len(r["text"]) > 200,
                    "quote_found": bool(norm(s["truth"]["quote"])) and norm(s["truth"]["quote"]) in r["text"],
                    "date_found": bool(r["text"]) and find_date(r["text"], dd)})

    rows = []
    for c, d in answers:
        s = sample[c["i"]]
        dd = date.fromisoformat(s["truth"]["deadline"])
        ev, q, cfp = d.get("DEADLINE_EVIDENCE_URL") or "", norm(d.get("DEADLINE_QUOTE")), d.get("CFP_SUBMISSION_URL") or ""
        er = await render(ev, settings, cache) if ev.startswith("http") else {"text": ""}
        cr = await render(cfp, settings, cache) if cfp.startswith("http") else {"text": ""}
        rows.append({"arm": c["arm"], "row": c["row"], "ev_url": ev, "cfp_url": cfp,
                     "ev_rendered": len(er["text"]) > 200,
                     "quote_verbatim_on_cited_page": bool(q) and q in er["text"],
                     "deadline_date_on_cited_page": bool(er["text"]) and find_date(er["text"], dd),
                     "cfp_rendered": len(cr["text"]) > 200,
                     "cfp_looks_like_call_page": bool(CALLPAGE.search(cr["text"][:60000])),
                     "cfp_same_as_ours": cfp.rstrip("/") == (s["truth"].get("evidence_url") or "").rstrip("/")})
    summ = {}
    for arm in ("A", "E"):
        rs = [r for r in rows if r["arm"] == arm]
        summ[arm] = {"grounded_calls": len(rs)}
        for k in ("ev_rendered", "quote_verbatim_on_cited_page", "deadline_date_on_cited_page",
                  "cfp_rendered", "cfp_looks_like_call_page"):
            summ[arm][k] = sum(bool(r[k]) for r in rs)
    summ["calibration_our_own_verified_pages"] = {"pages": len(cal), "rendered": sum(x["rendered"] for x in cal),
                                                   "quote_found": sum(x["quote_found"] for x in cal),
                                                   "date_found": sum(x["date_found"] for x in cal)}
    (HERE / "browser_verify.json").write_text(json.dumps({"summary": summ, "calibration": cal, "rows": rows}, indent=1),
                                              encoding="utf-8")
    print(json.dumps(summ, indent=1))
    try:
        await _f.close_fallback_browser()
    except Exception:                                                     # noqa: BLE001
        pass


if __name__ == "__main__":
    asyncio.run(main())
