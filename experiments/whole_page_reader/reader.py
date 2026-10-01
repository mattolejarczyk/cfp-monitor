"""Whole-page model reader (plan: docs/design/whole-page-reader-experiment.md). Approved 2026-10-01: cap 60 requests and 0.50 USD for the whole experiment.

   python reader.py --run dev        15 labelled pages (experiments/sentence_picking/labels.json, locked); the prompt is developed on these ONLY
   python reader.py --run holdout    10 pages (experiments/heading_reader/holdout_labels.json, locked before the reader existed); run once, prompt frozen
   python reader.py --run fresh      fresh set, labels locked in fresh_labels.json before any run
   python reader.py --score dev|holdout|fresh [--only URLFRAGMENT ...]

One request per page to deepseek/deepseek-chat. The model labels every date from a closed list; CODE decides what is accepted:
a date is a submission deadline only if (a) the model said so, (b) its unit text is a literal substring of the page (whitespace normalised),
(c) the date's day and month are written in that unit text, and (d) its year is stated in the unit text (explicit, '(26)', or the range's other end) or in the heading.
Nothing is written to the database. The key is read from the environment and never printed.
"""
import hashlib, json, os, re, sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "sentence_picking")); sys.path.insert(0, str(ROOT / "experiments" / "sitemap_discovery"))
import sentence_pick as sp                                              # noqa: E402  (call_model, extract_dates, iso, score_arm)

MODEL = sp.MODELS["C"]                                                   # deepseek/deepseek-chat
MAX_REQUESTS, MAX_USD = 60, 0.50
LOG = HERE / "llm_log.jsonl"
PAGE_CAP = 16000
TODAY = date(2026, 10, 1)
sp.MAXTOK[0] = 3000

PROMPT_VERSION = "v2b"   # POST-HOC: adds an item cap against runaway output; used only on pages that failed to parse under v2
SYSTEM = """You read ONE web page about a conference. List EVERY date or date range on it.
For each, return:
  "heading": the nearest heading or label line above it, copied exactly;
  "unit_text": the single line, table row or list item that states it, copied EXACTLY as a literal substring of the page (do not fix, shorten or join);
  "closing_date": ISO YYYY-MM-DD. For a range, use its END date. Use the year the page states; a two-digit year in brackets such as (26) means 2026. If no year is stated anywhere for it, use "";
  "label": one of submission_deadline, submission_opens, notification, registration, event_dates, exhibitor_or_payment, other;
  "round": Early, Regular, Late, Round n, or "".
Rules:
- submission_deadline means a deadline for SUBMITTING something to a call: a paper, abstract, proposal, speaker application, nomination, entry or award application. Every round of a call counts, including an Early round ("Launch to 19 June" is the Early round and ends 19 June).
- The heading above a table or list decides what its dates are for. Dates under a registration or ticket heading are registration, not submission.
- Opening dates ("call opens", "submissions open"), notification, review, camera-ready, hotel, booth, exhibitor, sponsor, payment, and post-acceptance upload dates are NOT submission deadlines.
- A date range for the event itself is event_dates. Do NOT list event dates, times of day (such as 10:00 - 17:00), copyright years, or dates of past news items: only dates tied to a call, submission, registration, notification, review, opening, payment, booth or exhibitor activity.
Return at most 40 items and never repeat an item. Return ONLY JSON: {"dates":[{"heading":"","unit_text":"","closing_date":"","label":"","round":""}]}. If the page has no dates, return {"dates":[]}."""


def spent():
    n, usd = 0, 0.0
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            n += 1
            usd += r.get("cost_usd") or 0.0
    return n, usd


def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace(" ", " ")).strip().lower()


def years_in(text):
    return {int(y) for y in re.findall(r"(?<!\d)(20[12]\d)(?!\d)", text or "")}


def gate(page, d):
    """(ok, why). The model's claim is accepted only if the page itself supports it."""
    if d.get("label") != "submission_deadline":
        return False, "not labelled submission_deadline"
    unit = d.get("unit_text") or ""
    if not unit or norm(unit) not in norm(page):
        return False, "unit text not on the page"
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", d.get("closing_date") or "")
    if not m:
        return False, "no ISO date"
    y, mo, da = int(m.group(1)), int(m.group(2)), int(m.group(3))
    found = sp.extract_dates(unit)
    mine = [f for f in found if f["month"] == mo and f["day"] == da]
    if not mine:
        return False, "date not written in the unit text"
    f = mine[-1]
    ystated = f["year"] or None
    if ystated is None:
        hy = years_in(d.get("heading"))
        if y not in hy:
            return False, "year not stated in the unit or its heading"
    elif ystated != y:
        return False, "year differs from the one written"
    return True, ""


def load(setname):
    if setname == "dev":
        Lp = ROOT / "experiments" / "sentence_picking"
        assert hashlib.sha256((Lp / "labels.json").read_bytes()).hexdigest() == (Lp / "labels.sha256").read_text().split()[0], "dev key changed"
        return sp.PAGES, json.loads((Lp / "labels.json").read_text(encoding="utf-8"))["pages"]
    if setname == "holdout":
        h = ROOT / "experiments" / "heading_reader"
        assert hashlib.sha256((h / "holdout_labels.json").read_bytes()).hexdigest() == (h / "holdout_labels.sha256").read_text().split()[0], "holdout key changed"
        return json.loads((h / "holdout_pages.json").read_text(encoding="utf-8")), json.loads((h / "holdout_labels.json").read_text(encoding="utf-8"))["pages"]
    if setname == "fresh":
        assert hashlib.sha256((HERE / "fresh_labels.json").read_bytes()).hexdigest() == (HERE / "fresh_labels.sha256").read_text().split()[0], "fresh key changed"
        pages = json.loads((ROOT / "experiments" / "purpose_audit" / "audit_pages.json").read_text(encoding="utf-8"))
        return pages, json.loads((HERE / "fresh_labels.json").read_text(encoding="utf-8"))["pages"]
    raise SystemExit("set must be dev, holdout or fresh")


def run(setname, only=None):
    pages, labels = load(setname)
    done = set()
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["set"] == setname and r["prompt"] == PROMPT_VERSION and r.get("content"):
                done.add(r["url"])
    for url in labels:
        if only and not any(o in url for o in only):
            continue
        if url in done:
            continue
        text = (pages.get(url) or {}).get("text") or ""
        if not text:
            print("no text:", url[-60:]); continue
        n, usd = spent()
        if n >= MAX_REQUESTS or usd >= MAX_USD:
            print(f"CAP REACHED: {n} requests, ${usd:.4f}"); return
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "URL: " + url + "\n\nPAGE TEXT:\n" + text[:PAGE_CAP]}]
        r, secs = sp.call_model(MODEL, msgs)
        try:
            j = r.json()
            content = j["choices"][0]["message"]["content"]
            cost = (j.get("usage") or {}).get("cost") or 0.0
        except Exception:                                                  # noqa: BLE001
            content, cost = None, 0.0
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"set": setname, "prompt": PROMPT_VERSION, "url": url, "secs": secs, "cost_usd": cost, "content": content}) + "\n")
        print(f"{setname} {url[-55:]:<55} {secs:>5}s ${cost:.5f}", flush=True)


def parse_items(content, tolerant=False):
    """The model's date items. tolerant=True (POST-HOC) recovers the complete leading objects when the output was cut off mid-string."""
    try:
        return json.loads(content)["dates"]
    except Exception:                                                      # noqa: BLE001
        if not tolerant or not content:
            return None
    items, dec, i = [], json.JSONDecoder(), content.find("[")
    i = i + 1 if i >= 0 else 0
    while True:
        j = content.find("{", i)
        if j < 0:
            break
        try:
            obj, end = dec.raw_decode(content, j)
        except Exception:                                                  # noqa: BLE001
            break
        items.append(obj); i = end
    return items or None


def latest(setname):
    out = {}
    for line in (LOG.read_text(encoding="utf-8").splitlines() if LOG.exists() else []):
        r = json.loads(line)
        if r["set"] == setname:
            out[r["url"]] = r                                              # a later run of the same page replaces the earlier
    return out


def score(setname):
    pages, labels = load(setname)
    runs = latest(setname)
    acc, rejects, unparse, tiers = {}, {}, 0, {}
    for url, r in runs.items():
        data = parse_items(r["content"], tolerant="--tolerant" in sys.argv)
        if data is None:
            unparse += 1; continue
        text = (pages.get(url) or {}).get("text") or ""
        keep = []
        for d in data:
            ok, why = gate(text, d)
            if ok:
                keep.append({"date": d["closing_date"], "quote": d["unit_text"], "round": d.get("round", "")})
            elif d.get("label") == "submission_deadline":
                rejects[why] = rejects.get(why, 0) + 1
        acc[url] = keep
    rep = sp.score_arm({u: acc.get(u, []) for u in labels if u in runs}, labels)
    rep.update(set=setname, pages_run=len(runs), unparseable=unparse, rejected_model_submission_claims=rejects)
    n, usd = spent()
    rep.update(total_requests_so_far=n, total_usd_so_far=round(usd, 4), prompt=PROMPT_VERSION)
    (HERE / f"scored_{setname}.json").write_text(json.dumps({"report": rep, "accepted": acc}, indent=1), encoding="utf-8")
    print(json.dumps(rep, indent=1))
    return rep


if __name__ == "__main__":
    a = sys.argv
    only = a[a.index("--only") + 1:] if "--only" in a else None
    if "--run" in a:
        run(a[a.index("--run") + 1], only)
    if "--score" in a:
        score(a[a.index("--score") + 1])
