"""PURPOSE AUDIT of stored deadlines (design: docs/design/heading-aware-reader-design.md section 5, Phase 2).

For each stored deadline in the two customer markets: render its evidence / submission page(s) (page loads only, 2 s apart, cached),
cut the page into date-bearing UNITS (table row, list item, labelled line, sentence), give each unit a PURPOSE from its own label words,
then the heading above it, then the legend (deterministic rules, no model), and report where the stored date sits:
  CONFIRMED   a SUB (submission) unit carries the date
  MISMATCH    the date appears only in REG / OPEN / NOTIF / EVENT / NOT_CFP units
  UNCLEAR     the date appears, but no unit's purpose could be decided (UNKNOWN is never guessed)
  ABSENT      the date is not on any page read (alternatives listed when SUB units carry other dates)
  NO_PAGE     no page could be read
Advisory only. Reads the live database read-only; writes only audit_pages.json and purpose_audit.json in this folder.

   python purpose_audit.py --fetch    render pages not yet cached
   python purpose_audit.py --report   classify and write purpose_audit.json (offline)
"""
import asyncio, importlib.util, json, os, re, sqlite3, sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments" / "sentence_picking")); sys.path.insert(0, str(ROOT / "experiments" / "sitemap_discovery"))
import sentence_pick as sp                                                    # noqa: E402  (extract_dates, loads crawl_pages.json)

DB = os.path.join(os.environ.get("LOCALAPPDATA", ""), "CFP-Monitor", "cfp_monitor.db")
STORE = HERE / "audit_pages.json"
OUT = HERE / "purpose_audit.json"
TODAY = date(2026, 10, 1)
MARKETS = ("Cybersecurity", "Utility")

# ---- purpose vocabulary. NOTIF / OPEN override SUB ("paper notification", "submission opens"); REG is SUB only with speaker wording.
NOTIF = re.compile(r"notif|acceptance|accepted|decision|camera[- ]?ready|final (version|paper)|author response|rebuttal|review", re.I)
OPEN = re.compile(r"\bopens?\b|opening|launch|starts?\b|\bfrom\b", re.I)
SPEAKER = re.compile(r"speaker|presenter|author", re.I)
REG = re.compile(r"registration|register|attendee|ticket|early[- ]?bird|\bpass(es)?\b|hotel|accommodation|booking|payment", re.I)
SUB = re.compile(r"submi|proposal|abstract|\bpapers?\b|call for|\bcfp\b|cfs|nominat|\bentr(y|ies)\b|applica|\bapply\b|deadline|closes?|closing|briefing|poster|talks?\b", re.I)
EVENT = re.compile(r"conference dates|event dates|\bheld\b|venue|dates of|exhibition|show dates", re.I)
NOT_CFP = re.compile(r"sponsor|exhibit|booth|vendor|press|media", re.I)
TIER_ONLY = re.compile(r"^\W*(early|regular|late|standard|final|round\s*\d|\d(st|nd|rd|th)|phase\s*\d|launch|stage\s*\d)\W*$", re.I)


def classes(text):
    """Set of purpose classes whose words appear in `text`, after the override rules."""
    t = text or ""
    got = set()
    if NOTIF.search(t):
        got.add("NOTIF")
    if re.search(r"submissions?\s+(open|start)|opens?\s+for\s+submission|call\s+(opens|open)", t, re.I):
        got.add("OPEN")
    elif OPEN.search(t) and not SUB.search(re.sub(r"\bopens?\b|opening|launch|\bfrom\b|starts?\b", "", t, flags=re.I)):
        got.add("OPEN")
    if REG.search(t):
        speaker_reg = SPEAKER.search(t) and re.search(r"registration|register", t, re.I) and not re.search(r"attendee|ticket|early[- ]?bird", t, re.I)
        got.add("SUB" if speaker_reg else "REG")
    if SUB.search(t) and not got & {"NOTIF", "OPEN"} and "REG" not in got:
        got.add("SUB")
    if EVENT.search(t):
        got.add("EVENT")
    if NOT_CFP.search(t) and not SUB.search(t):
        got.add("NOT_CFP")
    return got


def decide(*texts):
    """First text whose classes are exactly one wins; two or more classes in one text = UNKNOWN (conflict). None of them = UNKNOWN."""
    for t in texts:
        if not t or TIER_ONLY.match(t.strip()):
            continue
        c = classes(t)
        if len(c) == 1:
            return next(iter(c)), "text"
        if len(c) > 1:
            return "UNKNOWN", "conflict:" + "+".join(sorted(c))
    return "UNKNOWN", "no purpose words"


# ---- units
def is_heading(line):
    s = line.strip()
    return bool(s) and len(s.split()) <= 7 and len(s) <= 80 and not s.endswith((".", ",", ";")) and not sp.extract_dates(s) and not re.search(r"\d{1,2}[:/]\d", s)


def units(text):
    """[{line, heading, heading2, legend, own, dates:[...], pos}] one per line that carries at least one date."""
    out, heads, legend, pos = [], [], [], 0
    for raw in text.split("\n"):
        line = raw.strip("\t ")
        if not line:
            pos += len(raw) + 1
            continue
        ds = sp.extract_dates(line)
        if ds:
            out.append({"line": re.sub(r"\s*\t+\s*", " | ", line)[:240], "heading": heads[-1] if heads else "", "heading2": heads[-2] if len(heads) > 1 else "",
                        "legend": " ".join(legend)[:300], "dates": ds, "raw": line, "pos": pos})
        elif is_heading(line):
            heads.append(line)
            legend = []
        else:
            legend.append(line)
            legend = legend[-3:]
        pos += len(raw) + 1
    return out


def purpose(u, k):
    """Purpose of the k-th date in unit u: own text around the date, then the line, nearest heading, second heading, legend."""
    raw, ds = u["raw"], u["dates"]
    prev_end = ds[k - 1]["end"] if k else 0
    nxt = ds[k + 1]["start"] if k + 1 < len(ds) else len(raw)
    own = raw[prev_end: ds[k]["end"]] + " " + raw[ds[k]["end"]: nxt][:30]
    p, why = decide(own, raw)
    if p != "UNKNOWN" or why.startswith("conflict"):
        return p, "own:" + why
    for label, t in (("heading", u["heading"]), ("heading2", u["heading2"]), ("legend", u["legend"])):
        p, why = decide(t)
        if p != "UNKNOWN":
            return p, label
    return "UNKNOWN", "none"


def dated(page_text, u, k):
    d = u["dates"][k]
    if d["year"]:
        return sp.iso(d), d["year_source"]
    for t in (u["heading"], u["heading2"]):
        m = re.findall(r"(?<!\d)(20[12]\d)(?!\d)", t)
        if m:
            return sp.iso(d, int(m[-1])), "heading"
    y = sp.nearby_year(page_text, u["pos"])
    return (sp.iso(d, y), "nearby") if y else (None, "needs-year")


def classify_page(text, target):
    found, sub_other = [], []
    for u in units(text):
        for k, d in enumerate(u["dates"]):
            iso_, ysrc = dated(text, u, k)
            p, why = purpose(u, k)
            role = "single" if len(u["dates"]) == 1 else ("end" if k == len(u["dates"]) - 1 else "start")
            hit = (iso_ == target) or (iso_ is None and (d["month"], d["day"]) == (int(target[5:7]), int(target[8:10])))
            rec = {"date": iso_, "year_source": ysrc, "role": role, "purpose": p, "why": why, "heading": u["heading"], "unit": u["line"]}
            if hit:
                found.append(rec)
            elif p == "SUB" and iso_:
                sub_other.append(rec)
    return found, sub_other


def load_rows():
    c = sqlite3.connect(f"file:///{DB.replace(chr(92), '/')}?mode=ro", uri=True)
    q = ("select distinct cm.market, g.conference_key, g.name, g.deadline, g.verify_state, substr(g.verify_detail,1,70), g.deadline_evidence_url, "
         "g.submission_url, g.main_info_url, g.is_projected from conference_markets cm join grounding_facts g on g.conference_key = cm.conference_key "
         f"where cm.market in ({','.join('?' * len(MARKETS))}) and g.deadline is not null and g.deadline != ''")
    rows, seen = [], set()
    for r in c.execute(q, MARKETS):
        if r[1] in seen:
            continue
        seen.add(r[1])
        rows.append(dict(zip(("market", "key", "name", "deadline", "verify_state", "verify_detail", "evidence_url", "submission_url", "main_url", "projected"), r)))
    return rows


def pages_for(r):
    seen, out = set(), []
    for u in (r["evidence_url"], r["submission_url"]):
        if u and u.startswith("http") and u.rstrip("/") not in seen:
            seen.add(u.rstrip("/"))
            out.append(u)
    return out


async def fetch_all(rows):
    from src.cfp_monitor import fetch as _f
    from src.cfp_monitor.config import Settings
    settings = Settings()
    store = json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else {}

    class _Q:
        def log(self, *a, **k):
            pass
    todo = [u for r in rows for u in pages_for(r)]
    for u in dict.fromkeys(todo):
        if u in store or u in sp.PAGES:
            continue
        if _f._force_fallback_domain(u) and not _f.cdp_reachable(getattr(settings, "cdp_url", None)):
            store[u] = {"text": "", "error": "anti-bot"}
            continue
        try:
            html, anchors, status, body, _c = await _f._render_with_consent(u, settings, _Q(), prefer_cdp=True)
            store[u] = {"text": body or "", "status": status}
        except Exception as e:                                                  # noqa: BLE001
            store[u] = {"text": "", "error": type(e).__name__}
        print(f"  {len(store[u]['text']):>6} {store[u].get('error', '')} {u[:90]}", flush=True)
        STORE.write_text(json.dumps(store), encoding="utf-8")
        await asyncio.sleep(2)
    STORE.write_text(json.dumps(store), encoding="utf-8")
    try:
        await _f.close_fallback_browser()
    except Exception:                                                           # noqa: BLE001
        pass


def text_of(u, store):
    for src in (store, sp.PAGES):
        if u in src and (src[u].get("text") or ""):
            return src[u]["text"]
    return ""


def report(rows):
    from collections import Counter
    spec = importlib.util.spec_from_file_location("cu", ROOT / "scripts" / "check_urls_against_site.py")
    cu = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cu)
    store = json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else {}
    res = []
    for r in rows:
        hits, alts, read, shells = [], [], 0, 0
        for u in pages_for(r):
            t = text_of(u, store)
            if not t:
                continue
            if cu.looks_soft_404(t):
                shells += 1
                continue
            read += 1
            f, a = classify_page(t, r["deadline"])
            hits += [dict(h, url=u) for h in f]
            alts += [dict(h, url=u) for h in a]
        sub_hit = [h for h in hits if h["purpose"] == "SUB" and h["role"] in ("end", "single")]
        if not read:
            out = "NO_PAGE"
        elif sub_hit:
            out = "CONFIRMED"
        elif hits and all(h["purpose"] != "UNKNOWN" for h in hits):
            out = "MISMATCH"
        elif hits:
            out = "UNCLEAR"
        else:
            out = "ABSENT"
        res.append({"market": r["market"], "name": r["name"], "stored_deadline": r["deadline"], "passed": r["deadline"] < TODAY.isoformat(),
                    "verify_state": r["verify_state"], "verify_detail": r["verify_detail"], "outcome": out, "pages_read": read, "pages_soft404": shells,
                    "hits": hits[:6], "sub_alternatives": [{k: a[k] for k in ("date", "heading", "unit", "url")} for a in alts[:6]]})
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(Counter(x["outcome"] for x in res))
    print(Counter((x["outcome"], x["passed"]) for x in res))
    print(Counter((x["outcome"], x["verify_state"]) for x in res))
    return res


if __name__ == "__main__":
    rows = load_rows()
    print(len(rows), "stored deadlines;", len({u for r in rows for u in pages_for(r)}), "distinct pages")
    if "--fetch" in sys.argv:
        asyncio.run(fetch_all(rows))
    if "--report" in sys.argv:
        report(rows)
