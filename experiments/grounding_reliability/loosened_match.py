"""Free, no-AI loosened quote check on the 27 jobs the strict tracer missed. No Gemini, no LLM.

Renders each distinct CITED page once with the repo's renderer (trace_quote_to_page._render) and caches the text in
page_cache.json so the later AI step does not re-render. Then tests each stored quote at three tiers, reported separately so
a weaker tier is never passed off as a stronger one:

  T1  the whole quote is on the page after ignoring case, spacing, punctuation, apostrophes, garbled characters (U+FFFD),
      smart quotes/dashes and ordinals ("13th" == "13").
  T2  the deadline date is on the page in any common format WITH its year (verify.find_date + extra formats), and at least
      75% of the quote's other words appear within 400 characters of that date. (Catches table layouts / re-wrapped rows.)
  T3  as T2 but the date has no year ("October 19", "19 Oct", "Oct. 19th") - weaker, because a year-less date can belong to
      another edition.
Writes loosened_match.json. Nothing else is touched.
"""
import asyncio, importlib.util, json, re, sys, unicodedata
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("tq", ROOT / "scripts" / "trace_quote_to_page.py")
tq = importlib.util.module_from_spec(spec); spec.loader.exec_module(tq)
from src.cfp_monitor.config import Settings                      # noqa: E402
from src.cfp_monitor.verify import date_variants, normalize_text  # noqa: E402

CACHE = HERE / "page_cache.json"
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]


def norm2(s):
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"['`�]", "", s)                          # apostrophes and garbled characters vanish
    s = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", s)              # 13th -> 13
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def yearless_patterns(d):
    mon = MONTHS[d.month - 1]
    abbr = {mon[:3]} | ({"sept"} if d.month == 9 else set())
    names = "|".join(sorted({mon} | abbr, key=len, reverse=True))
    day = rf"0?{d.day}"
    return [re.compile(rf"\b(?:{names}) {day}\b"), re.compile(rf"\b{day} (?:{names})\b")]


def other_tokens(quote, d):
    mon = set(MONTHS) | {m[:3] for m in MONTHS} | {"sept"}
    return [w for w in norm2(quote).split() if len(w) > 2 and not w.isdigit() and w not in mon]


def window_overlap(text_n, positions, toks, radius=400):
    if not toks:
        return 0.0
    best = 0.0
    for p in positions:
        win = set(text_n[max(0, p - radius): p + radius].split())
        best = max(best, sum(t in win for t in toks) / len(toks))
    return best


def tier(page, quote, d):
    pn, qn = norm2(page), norm2(quote)
    if qn and qn in pn:
        return "T1"
    toks = other_tokens(quote, d)
    # dates with a year: existing variants, compared in the same normalisation as the page
    pos = []
    for v in date_variants(d):
        vn = norm2(v)
        pos += [m.start() for m in re.finditer(re.escape(vn), pn)] if vn else []
    if pos and window_overlap(pn, pos, toks) >= 0.75:
        return "T2"
    pos = [m.start() for pat in yearless_patterns(d) for m in pat.finditer(pn)]
    if pos and window_overlap(pn, pos, toks) >= 0.75:
        return "T3"
    return "none"


async def main():
    settings = Settings()
    sample = {s["row"]["CONFERENCE"]: s for s in json.loads((HERE / "sample.json").read_text(encoding="utf-8"))}
    jobs = json.loads((HERE / "browser_trace.json").read_text(encoding="utf-8"))["jobs"]
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    for u in sorted({j["url"] for j in jobs} - set(cache)):
        text, _a = await tq._render(u, settings)
        cache[u] = text
        CACHE.write_text(json.dumps(cache), encoding="utf-8")
        print(f"rendered {len(text):>7} chars  {u[:90]}", flush=True)
        await asyncio.sleep(2)
    out = []
    for j in jobs:
        row = next(k for k in sample if k.startswith(j["row"][:30]))
        d = date.fromisoformat(sample[row]["truth"]["deadline"])
        out.append({"kind": j["kind"], "row": j["row"], "url": j["url"], "deadline": d.isoformat(),
                    "page_chars": len(cache.get(j["url"], "")), "tier": tier(cache.get(j["url"], ""), j["quote"], d)})
    summ = {}
    for kind in ("A", "E", "OURS"):
        js = [o for o in out if o["kind"] == kind]
        summ[kind] = {"jobs": len(js), **{t: sum(o["tier"] == t for o in js) for t in ("T1", "T2", "T3", "none")}}
    (HERE / "loosened_match.json").write_text(json.dumps({"summary": summ, "jobs": out}, indent=1), encoding="utf-8")
    print(json.dumps(summ), flush=True)
    for o in out:
        print(f"{o['kind']:<4} {o['tier']:<4} chars={o['page_chars']:>6}  {o['row'][:38]}", flush=True)
    try:
        await tq._f.close_fallback_browser()
    except Exception:                                                  # noqa: BLE001
        pass


if __name__ == "__main__":
    asyncio.run(main())
