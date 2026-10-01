"""Sentence-picking step, DISCOVERY mode - test runner (design: docs/design/sentence-picking-design.md). Approved budget: <= 60 requests, <= 1 USD, all arms.

   python sentence_pick.py --dry-run          offline: pre-filter, excerpts, prompts, arm A scored. NO requests.
   python sentence_pick.py --run B            arm B (deepseek/deepseek-v4.1-flash): one request per page, hard caps
   python sentence_pick.py --run C            arm C (deepseek/deepseek-chat)
   python sentence_pick.py --score            apply the code gates to saved responses and score all arms against labels.json

Reuses scripts/extract_citations.py unchanged: locate_verbatim (code proves the sentence is on the page), _WRONG_PURPOSE, _SUBMIT_VERB, verify_call_label.
Model calls use httpx against OpenRouter (litellm is not installed). The key is read from the environment and never printed or logged.
Nothing here writes to the database or the deliveries.
"""
import argparse, hashlib, importlib.util, json, os, re, sys, time
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments" / "sitemap_discovery"))
import dates_v2 as d2
from dates_v2 import MONTHS, month_names

_spec = importlib.util.spec_from_file_location("extract_citations", ROOT / "scripts" / "extract_citations.py")
ec = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(ec)       # existing gates, unchanged

PAGES = json.loads((ROOT / "experiments/sitemap_discovery/crawl_pages.json").read_text(encoding="utf-8"))
LABELS = HERE / "labels.json"
LOG = HERE / "llm_log.jsonl"
MODELS = {"B": "deepseek/deepseek-v4.1-flash", "C": "deepseek/deepseek-chat"}
MAX_REQUESTS, MAX_USD = 60, 1.00
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
PROMPT_VERSION = "v1-2026-10-01"

SYSTEM = """You are shown excerpts of ONE web page. List every sentence that states a deadline for SUBMITTING something to a call: a paper, abstract,
proposal, speaker application, nomination, entry or award application. For each, copy the sentence EXACTLY as it appears in the excerpts, as a literal
substring (do not fix, reword, shorten or join). Give:
  "sentence": the exact text, "date_text": the exact date string inside that sentence that is the CLOSING date,
  "call": which call it belongs to (abstract, full paper, poster, awards, trainings, proposals ...), "kind": one of
  submission_deadline | opens | notification | event_dates | registration | other.
Dates for withdrawing, notification, review, registration, hotels, early-bird pricing, booth applications, payments, or the event itself are NOT
submission deadlines: either label them with their kind or leave them out. When a sentence gives a range, the closing date is its END.
If the page states no submission deadline, return {"candidates": []}: an honest blank is correct and always acceptable. Use only the text shown.
Return ONLY JSON: {"candidates": [{"sentence": "...", "date_text": "...", "call": "...", "kind": "..."}]} with at most 8 candidates."""

# ---------------------------------------------------------------- date extraction (returns the date a sentence STATES)
_NAMES = {}
for _lang, _lst in MONTHS.items():
    for _i, _n in enumerate(_lst, 1):
        _NAMES[_n] = _i
for _i in range(1, 13):
    for _n in month_names(_i):
        _NAMES[_n.rstrip(".")] = _i
_ALT = "|".join(sorted((re.escape(n) for n in _NAMES), key=len, reverse=True))
_MDY = re.compile(rf"(?<![a-zäéû])(?P<mon>{_ALT})\.?\s*(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?!\d)", re.I)
_DMY = re.compile(rf"(?<!\d)(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\.?\s+(?:de\s+)?(?P<mon>{_ALT})(?![a-zäéû])\.?", re.I)
_ISO = re.compile(r"(?<!\d)(?P<y>20\d\d)-(?P<m>\d{2})-(?P<d>\d{2})(?!\d)")
_FOLLOW_YEAR = re.compile(r"\D{0,14}?(?P<y>20\d\d)(?!\d)")
_FOLLOW_YY = re.compile(r"\s*\((?P<yy>\d{2})\)")
_RANGE_SEP = re.compile(r"\s*(?:\([^)]{1,12}\))?\s*(?:-|–|—|~|to|through|until)\s*", re.I)


def extract_dates(text, numeric=False):
    """[{start,end,month,day,year,year_source}] for every month+day mention in `text`, in order. Year from: explicit 20YY after the date,
    a two-digit '(26)', or the end of a range that shares it. year None when the text does not say."""
    found = []
    for rx in (_MDY, _DMY):
        for m in rx.finditer(text):
            mon = _NAMES.get(m.group("mon").lower().rstrip("."))
            if not mon:
                continue
            found.append({"start": m.start(), "end": m.end(), "month": mon, "day": int(m.group("day")), "year": None, "year_source": ""})
    for m in _ISO.finditer(text):
        found.append({"start": m.start(), "end": m.end(), "month": int(m.group("m")), "day": int(m.group("d")), "year": int(m.group("y")), "year_source": "explicit"})
    if numeric:    # POST-HOC: "8/31", "9/30". Only when one number is above 12, so the order is unambiguous.
        for m in re.finditer(r"(?<![\d/])(?P<a>\d{1,2})\s*/\s*(?P<b>\d{1,2})(?![\d/])", text):
            a_, b_ = int(m.group("a")), int(m.group("b"))
            if b_ > 12 and 1 <= a_ <= 12:
                found.append({"start": m.start(), "end": m.end(), "month": a_, "day": b_, "year": None, "year_source": ""})
            elif a_ > 12 and 1 <= b_ <= 12:
                found.append({"start": m.start(), "end": m.end(), "month": b_, "day": a_, "year": None, "year_source": ""})
    found.sort(key=lambda x: (x["start"], -x["end"]))
    out, last = [], -1
    for f in found:
        if f["start"] < last:
            continue
        last = f["end"]
        out.append(f)
    for f in out:
        if f["year"]:
            continue
        tail = text[f["end"]: f["end"] + 24]
        my = _FOLLOW_YY.match(tail)
        if my:
            f["year"], f["year_source"] = 2000 + int(my.group("yy")), "two-digit"
            continue
        mx = _FOLLOW_YEAR.match(tail)
        if mx:
            f["year"], f["year_source"] = int(mx.group("y")), "explicit"
    for a, b in zip(out, out[1:]):                         # a range shares the year written at its end
        if not a["year"] and b["year"] and _RANGE_SEP.fullmatch(text[a["end"]: b["start"]].split(")")[-1] if False else text[a["end"]: b["start"]]):
            a["year"], a["year_source"] = b["year"], "range"
    return out


def iso(f, year=None):
    y = year or f["year"]
    try:
        return date(y, f["month"], f["day"]).isoformat() if y else None
    except ValueError:
        return None


def nearby_year(page, pos, window=400):
    """The closest year written in the `window` characters BEFORE `pos` (a heading such as 'SecTor 2026'); None if there is none."""
    ys = re.findall(r"(?<!\d)(20[12]\d)(?!\d)", page[max(0, pos - window): pos])
    return int(ys[-1]) if ys else None


# ---------------------------------------------------------------- pre-filter and excerpt
def prefilter(text):
    return bool(text) and d2.any_date_near_call(text)


def excerpt(text, radius=600, cap=6000):
    t = text
    spans = []
    for m in d2.CALLVOC.finditer(t.lower()):
        lo, hi = max(0, m.start() - 200), m.end() + 200
        if d2.ANY_DATE.search(d2._norm(t[lo:hi])) or d2.ANY_DATE.search(t[lo:hi]):
            spans.append((max(0, m.start() - radius), min(len(t), m.end() + radius)))
    merged = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    parts, total = [], 0
    for a, b in merged:
        seg = t[a:b]
        if total + len(seg) > cap:
            seg = seg[: max(0, cap - total)]
        if seg:
            parts.append(seg); total += len(seg)
        if total >= cap:
            break
    return "\n...\n".join(parts)


def build_messages(url, text):
    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    user = f"WEBSITE: {host}\nPAGE URL: {url}\n\nEXCERPTS:\n{excerpt(text)}\n\nReturn ONLY the JSON object."
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


# ---------------------------------------------------------------- the code gates (each rejection counted by reason)
CLOSE_WORD = re.compile(r"clos|due|deadline|until|ends?\b|end:|by\b|through|\bto\b|submit|submission|accept|final|last", re.I)


WORDING_POSTHOC = re.compile(r"deadline|cfp|cft|ends?\b|end:|call for|due|clos|submit|submission|abstract|propos|nominat|apply|application|entry|entries", re.I)


def gate(page, cand, posthoc=False):
    """-> (accepted_dict | None, reject_reason). Every gate must pass. The model's date_text is only a POINTER into the verified sentence."""
    sentence = " ".join((cand.get("sentence") or "").split())
    if not sentence:
        return None, "empty"
    if (cand.get("kind") or "") != "submission_deadline":
        return None, "model-kind-not-submission"
    quote = ec.locate_verbatim(page, sentence)
    if quote is None:
        return None, "not-on-page"
    if ec._WRONG_PURPOSE.search(quote):
        return None, "wrong-purpose"
    if posthoc:
        if not WORDING_POSTHOC.search(quote):
            return None, "no-submit-wording"
    elif not ec._SUBMIT_VERB.search(quote) and not re.search(r"nominat|apply|application|entry|propos", quote, re.I):
        return None, "no-submit-wording"
    dt = " ".join((cand.get("date_text") or "").split())
    at = quote.lower().find(dt.lower()) if dt else -1
    if at < 0:
        return None, "date-text-not-in-sentence"
    mentions = extract_dates(quote, numeric=posthoc)
    pick = next((f for f in mentions if f["start"] <= at + len(dt) and f["end"] >= at), None)
    if pick is None:
        return None, "undated"
    if not CLOSE_WORD.search(quote[max(0, pick["start"] - 90): pick["start"] + 6]):
        return None, "no-closing-wording"
    year, source = pick["year"], pick["year_source"]
    if not year:
        pos = page.find(quote)
        ny = nearby_year(page, pos + pick["start"]) if pos >= 0 else None
        if ny:
            year, source = ny, "nearby-heading"
    if not year:
        return None, "no-year"
    iso_date = iso(pick, year)
    if not iso_date:
        return None, "invalid-date"
    call = ec.verify_call_label(page, quote, (cand.get("call") or "").strip().lower()) if cand.get("call") else ""
    return {"date": iso_date, "quote": quote, "call": call or "", "year_source": source,
            "confidence": "strong" if source in ("explicit", "two-digit", "range") else "medium (year inferred)"}, ""


# ---------------------------------------------------------------- arm A: deterministic baseline (no model)
def baseline(page, numeric=False):
    """Every sentence with submit wording and no wrong-purpose wording that contains a date. The generous rules-only arm."""
    cands, seen = [], set()
    t = page
    for m in d2.CALLVOC.finditer(t.lower()):
        s = ec.sentence_with(t, m.start())
        if not s or s in seen:
            continue
        seen.add(s)
        if ec._WRONG_PURPOSE.search(s) or not ec._SUBMIT_VERB.search(s):
            continue
        for f in extract_dates(s, numeric=numeric):
            cands.append({"sentence": s, "date_text": s[f["start"]:f["end"]], "call": "", "kind": "submission_deadline", "_pick": f})
    return cands


# ---------------------------------------------------------------- scoring against the locked labels
def load_labels():
    L = json.loads(LABELS.read_text(encoding="utf-8"))["pages"]
    sha_line = (HERE / "labels.sha256").read_text(encoding="utf-8").split()[0]
    assert hashlib.sha256(LABELS.read_bytes()).hexdigest() == sha_line, "labels.json changed after it was locked"
    return L


def score_arm(arm_results, L):
    tp = wrong = unl = 0
    recovered, total_sub = 0, 0
    wrong_detail, unl_detail = [], []
    for url, accepted in arm_results.items():
        labs = L.get(url, {}).get("labels", [])
        sub = {l["date"] for l in labs if l["class"] == "SUB"}
        non = {l["date"]: l["class"] for l in labs if l["class"] not in ("SUB", "SUB_RECURRING")}
        got = {a["date"] for a in accepted}
        total_sub += len(sub); recovered += len(sub & got)
        for a in accepted:
            if a["date"] in sub:
                tp += 1
            elif a["date"] in non:
                wrong += 1; wrong_detail.append((url.split("/", 3)[-1][:36], a["date"], non[a["date"]]))
            else:
                unl += 1; unl_detail.append((url.split("/", 3)[-1][:36], a["date"], a["quote"][:70]))
    n = tp + wrong + unl
    return {"accepted": n, "correct": tp, "wrong_purpose": wrong, "unlabelled": unl,
            "precision_strict": round(tp / n, 3) if n else None, "recall": f"{recovered}/{total_sub}",
            "wrong_detail": wrong_detail, "unlabelled_detail": unl_detail}


def pass_pages():
    return [u for u, p in PAGES.items() if prefilter(p["text"] or "") and u in json.loads(LABELS.read_text(encoding="utf-8"))["pages"]]


# ---------------------------------------------------------------- model calls with hard caps
def spent():
    reqs, usd = 0, 0.0
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            r = json.loads(line); reqs += 1; usd += r.get("cost_usd") or 0.0
    return reqs, usd


MAXTOK = [1500]


def call_model(model, messages, want_json=True):
    import httpx
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("OPENROUTER_API_KEY missing")
    body = {"model": model, "messages": messages, "temperature": 0, "max_tokens": MAXTOK[0], "usage": {"include": True}}
    if want_json:
        body["response_format"] = {"type": "json_object"}
    body.update(json.loads(os.environ.get("SP_EXTRA", "{}")))      # POST-HOC option, e.g. {"reasoning": {"effort": "low"}}
    t0 = time.time()
    r = httpx.post(OPENROUTER, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=body, timeout=90)
    return r, round(time.time() - t0, 1)


def run_arm(arm, retry_unparseable=False, max_tokens=1500):
    model = MODELS[arm]
    L = load_labels()
    pages = pass_pages()
    consecutive_429 = 0
    MAXTOK[0] = max_tokens
    if retry_unparseable:      # POST-HOC DEVIATION: re-ask only the pages whose answer was cut off, with a larger token limit
        latest = {}
        for line in LOG.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["arm"] == arm and r.get("final"):
                latest[r["url"]] = r
        pages = [u for u, r in latest.items() if parse_cands(r.get("content")) is None]
        print(f"retrying {len(pages)} unparseable page(s) for arm {arm} with max_tokens={max_tokens}", flush=True)
    for url in pages:
        if (not retry_unparseable) and LOG.exists() and any(json.loads(l).get("arm") == arm and json.loads(l).get("url") == url and json.loads(l).get("final") for l in LOG.read_text(encoding="utf-8").splitlines()):
            continue
        for attempt in range(1, 4):
            reqs, usd = spent()
            if reqs >= MAX_REQUESTS or usd >= MAX_USD:
                print(f"STOP: caps reached (requests {reqs}/{MAX_REQUESTS}, ${usd:.4f}/{MAX_USD})"); return
            r, secs = call_model(model, build_messages(url, PAGES[url]["text"]), want_json=(attempt == 1))
            rec = {"ts": datetime.now().isoformat(timespec="seconds"), "arm": arm, "model": model, "url": url, "attempt": attempt, "status": r.status_code,
                   "secs": secs, "prompt_version": PROMPT_VERSION, "final": False, "max_tokens": MAXTOK[0], "retry": retry_unparseable}
            try:
                j = r.json()
            except Exception:
                j = {}
            u = j.get("usage") or {}
            rec.update(prompt_tokens=u.get("prompt_tokens"), completion_tokens=u.get("completion_tokens"), cost_usd=u.get("cost"))
            if r.status_code == 200:
                rec["content"] = ((j.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                rec["final"] = True
                consecutive_429 = 0
            else:
                rec["error"] = (j.get("error") or {}).get("message", r.text[:200]) if isinstance(j, dict) else r.text[:200]
            with LOG.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
            print(f"[{arm}] {r.status_code} {secs:>5}s tokens {rec['prompt_tokens']}/{rec['completion_tokens']} cost {rec['cost_usd']} {url.split('/',3)[-1][:44]}", flush=True)
            if r.status_code == 200:
                break
            if r.status_code == 429:
                consecutive_429 += 1
                if consecutive_429 >= 2:
                    print("STOP: two 429s in a row"); return
                time.sleep(8 * attempt); continue
            if r.status_code in (400, 404) and attempt == 1 and "model" in (rec.get("error") or "").lower():
                print("STOP arm: model rejected:", rec["error"][:200]); return
            if r.status_code >= 500:
                time.sleep(6 * attempt); continue
            if r.status_code == 400 and attempt == 1:
                continue                                  # retry once without response_format
            break
    reqs, usd = spent(); print(f"arm {arm} done: total requests {reqs}, spend ${usd:.4f}")


def parse_cands(content):
    m = re.search(r"\{.*\}", content or "", re.S)
    if not m:
        return None
    try:
        return (json.loads(m.group(0)).get("candidates") or [])
    except Exception:
        return None


def score_all(posthoc=False):
    L = load_labels()
    pages = pass_pages()
    report = {}
    # arm A
    a = {}
    rej_a = {}
    for u in pages:
        acc = []
        for c in baseline(PAGES[u]["text"], numeric=posthoc):
            f = c["_pick"]; yr = f["year"] or nearby_year(PAGES[u]["text"], PAGES[u]["text"].find(c["sentence"]))
            dt = iso(f, yr)
            if dt:
                acc.append({"date": dt, "quote": c["sentence"], "year_source": "baseline"})
        a[u] = acc
    report["A"] = score_arm(a, L)
    for arm in ("B", "C"):
        results, rejects, unavailable, n_req, usd, secs = {}, {}, 0, 0, 0.0, 0.0
        latest = {}
        for line in (LOG.read_text(encoding="utf-8").splitlines() if LOG.exists() else []):
            r = json.loads(line)
            if r["arm"] != arm:
                continue
            n_req += 1; usd += r.get("cost_usd") or 0.0
            if r.get("final"):
                latest[r["url"]] = r                      # a retry replaces the earlier answer for that page
        for r in latest.values():
            secs += r.get("secs") or 0
            cands = parse_cands(r.get("content"))
            if cands is None:
                unavailable += 1; continue
            acc = []
            for c in cands:
                ok, why = gate(PAGES[r["url"]]["text"], c, posthoc=posthoc)
                if ok:
                    acc.append(ok)
                else:
                    rejects[why] = rejects.get(why, 0) + 1
            results.setdefault(r["url"], []).extend(acc)
        if not n_req:
            continue
        rep = score_arm({u: results.get(u, []) for u in pages}, L)
        rep.update(requests=n_req, cost_usd=round(usd, 4), unparseable=unavailable, rejections=rejects, mean_secs=round(secs / max(1, len(results)), 1))
        report[arm] = rep
    (HERE / ("scored_posthoc.json" if posthoc else "scored.json")).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: {x: y for x, y in v.items() if x not in ("wrong_detail", "unlabelled_detail")} for k, v in report.items()}, indent=1))
    for k, v in report.items():
        print(f"\n[{k}] wrong-purpose accepted: {v['wrong_detail']}\n[{k}] unlabelled accepted: {v['unlabelled_detail']}")


def dry_run():
    L = load_labels()
    pages = pass_pages()
    sizes = [len(excerpt(PAGES[u]["text"])) for u in pages]
    print(f"labels verified against locked sha256 | pages passing the pre-filter and labelled: {len(pages)} | excerpt chars min/mean/max {min(sizes)}/{sum(sizes)//len(sizes)}/{max(sizes)}")
    print(f"requests planned: {len(pages)} per model arm x 2 arms = {2 * len(pages)} (cap {MAX_REQUESTS}); no request is made in a dry run")
    print("\nsample prompt (user part), page 1:\n", build_messages(pages[0], PAGES[pages[0]]["text"])[1]["content"][:900])
    score_all()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--score", action="store_true"); ap.add_argument("--run")
    ap.add_argument("--posthoc", action="store_true"); ap.add_argument("--retry"); ap.add_argument("--max-tokens", type=int, default=1500)
    a = ap.parse_args()
    if a.dry_run: dry_run()
    elif a.score: score_all(posthoc=a.posthoc)
    elif a.retry: run_arm(a.retry.upper(), retry_unparseable=True, max_tokens=a.max_tokens)
    elif a.run: run_arm(a.run.upper())
    else: ap.print_help()
