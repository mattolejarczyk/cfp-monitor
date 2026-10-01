"""Grounding reliability, experiment E: does a NARROW prompt ground more reliably than the full one?

ONE variable: the prompt. Arm A = today's production conference prompt. Arm E = the same scaffold
(identity + rule 0 anti-echo guard) with a short rule set asking only the customer-critical fields.
Model, temperature, JSON mime type, google_search tool, timeout and pacing are identical, and every
call is a SINGLE attempt (no retries) so raw success is what gets measured.

Nothing here writes to the database, the deliveries or the research inputs. Outputs stay in this
folder. Plan: docs/design/grounding-reliability-test-plan.md (arm E). Budget agreed 2026-09-30: at
most 48 requests, ~$4, hard stop at $4.50 estimated.

    python probe_narrow.py --build-sample          # read-only DB read -> sample.json
    python probe_narrow.py --dry-run               # prompts + counts, NO API calls
    python probe_narrow.py --run                   # the spend
    python probe_narrow.py --score                 # free: checks answers against known truth
"""
import argparse, json, os, random, re, sqlite3, sys, time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARKETS = Path(os.environ.get("CFP_MARKETS_DIR", "."))   # the upstream Markets working folder: set CFP_MARKETS_DIR (kept out of this public repo)
DB = os.path.join(os.environ.get("LOCALAPPDATA", ""), "CFP-Monitor", "cfp_monitor.db")   # the live database, read-only here
SAMPLE = HERE / "sample.json"
CALLS = HERE / "calls.jsonl"
TODAY = "2026-09-30"

MAX_CALLS = 48
COST_STOP = 4.50            # estimated dollars; the agreed budget is ~$4
SEARCH_PRICE = 0.014        # $ per search query, Gemini 3 (billing report, 2026-09)
IN_PRICE, OUT_PRICE = 0.50e-6, 3.00e-6   # gemini-3-flash-preview $/token
PACE_SECONDS = 16

# Arm E rules. Deliberately short. Keeps the two rules whose absence caused real incidents:
# the verbatim quote, and never asserting that an event has ended without citing it (6a).
CORE_RULES = """    1. STATUS relative to {today}: "Closed" if the event or its call closed before today;
       "Open" if the deadline is after today or the form is rolling; "Upcoming" if the event is in
       the future but this edition's call is not published; "Needs Verification" if unconfirmed.
    2. Dates are YYYY-MM-DD. If the page does not confirm a date, return it EMPTY and IS_PROJECTED true.
    3. DEADLINE_EVIDENCE_URL is the exact page where you read the submission deadline.
       DEADLINE_QUOTE is text copied character-for-character from that page containing the deadline.
    4. Never say an event has ended without a page that says so. If you cannot confirm the next
       edition, use STATUS "Needs Verification" - that is not the same as "ended".
    5. RETURN ONLY A VALID JSON OBJECT with exactly these keys: CONFERENCE, STATUS, STATUS_DETAILS,
       SUBMISSION_DEADLINE, START_DATE, CFP_SUBMISSION_URL, DEADLINE_EVIDENCE_URL, DEADLINE_QUOTE,
       IS_PROJECTED."""


def load_audit_module():
    sys.path.insert(0, str(MARKETS))
    os.environ.setdefault("GEMINI_API_KEY", "dry-run-placeholder")
    import run_market_audit as r          # imported, never edited
    return r


def build_sample():
    c = sqlite3.connect(f"file:///{DB.replace(chr(92), '/')}?mode=ro", uri=True)
    q = ("select name, coalesce(nullif(main_info_url,''), url), city, state_province, country, "
         "edition, deadline, deadline_quote, deadline_evidence_url, start_date "
         "from grounding_facts where verify_state='verified' and deadline >= '2026-10-01' "
         "and deadline_quote != '' and deadline_evidence_url != '' order by deadline")
    picked, hosts = [], {}
    for name, url, city, st, country, ed, dl, quote, ev, sd in c.execute(q):
        h = re.sub(r"^https?://(www\.)?", "", ev).split("/")[0]
        if hosts.get(h, 0) >= 2:
            continue
        hosts[h] = hosts.get(h, 0) + 1
        loc = ", ".join(x for x in (city, st, country) if x)
        picked.append({"row": {"CONFERENCE": name, "CONFERENCE URL": url, "LOCATION": loc,
                               "PRIORITY": "High", "EDITION": str(ed or "")},
                       "truth": {"deadline": dl, "quote": quote, "evidence_url": ev, "start_date": sd}})
        if len(picked) == 12:
            break
    SAMPLE.write_text(json.dumps(picked, indent=1), encoding="utf-8")
    print(f"sample.json: {len(picked)} rows with a verified future deadline (of which hosts capped at 2)")
    for p in picked:
        print("  ", p["row"]["CONFERENCE"][:50], p["truth"]["deadline"])


def prompts_for(r, row):
    a = r.build_grounding_prompt(row, TODAY)
    e = r._prompt_scaffold(row, TODAY, "Conference", CORE_RULES.format(today=TODAY))
    return {"A": a, "E": e}


def plan_order():
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    rnd = random.Random(20260930)
    order = []
    for rep in (1, 2):
        pairs = [(i, arm) for i in range(len(sample)) for arm in ("A", "E")]
        rnd.shuffle(pairs)
        order += [(rep, i, arm) for i, arm in pairs]
    return sample, order


def dry_run():
    r = load_audit_module()
    sample, order = plan_order()
    p = prompts_for(r, sample[0]["row"])
    print(f"rows {len(sample)}, planned calls {len(order)} (cap {MAX_CALLS}); NO API calls made")
    print(f"prompt size, chars: A={len(p['A'])}  E={len(p['E'])}")
    print("first 6 in order:", order[:6])
    print("\n--- ARM E PROMPT (row 0) ---" + p["E"])


def run():
    r = load_audit_module()
    if not os.environ.get("GEMINI_API_KEY") or os.environ["GEMINI_API_KEY"] == "dry-run-placeholder":
        sys.exit("GEMINI_API_KEY missing")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                          http_options=types.HttpOptions(timeout=120_000,
                                                         retry_options=types.HttpRetryOptions(attempts=1)))
    config = types.GenerateContentConfig(tools=[{"google_search": {}}], temperature=0.1,
                                         response_mime_type="application/json")
    sample, order = plan_order()
    done = set()
    if CALLS.exists():
        for l in CALLS.read_text(encoding="utf-8").splitlines():
            d = json.loads(l); done.add((d["rep"], d["i"], d["arm"]))
    est, quota, n = 0.0, 0, 0
    for l in (CALLS.read_text(encoding="utf-8").splitlines() if CALLS.exists() else []):
        est += json.loads(l).get("est_cost", 0)
    last = 0.0
    for rep, i, arm in order:
        if (rep, i, arm) in done:
            continue
        if len(done) + n >= MAX_CALLS:
            print("CALL CAP reached"); break
        if est >= COST_STOP:
            print(f"COST STOP: estimated ${est:.2f}"); break
        gap = time.time() - last
        if last and gap < PACE_SECONDS:
            time.sleep(PACE_SECONDS - gap)
        last = time.time()
        row = sample[i]["row"]
        prompt = prompts_for(r, row)[arm]
        t0 = time.time()
        rec = {"ts": datetime.now().isoformat(timespec="seconds"), "hour": datetime.now().hour,
               "rep": rep, "i": i, "arm": arm, "row": row["CONFERENCE"], "prompt_chars": len(prompt)}
        try:
            resp = client.models.generate_content(model=r.DEFAULT_MODEL, contents=prompt, config=config)
            g = r.grounding_summary(resp)
            um = getattr(resp, "usage_metadata", None)
            tok = {k: getattr(um, k, None) for k in ("prompt_token_count", "candidates_token_count",
                                                      "thoughts_token_count", "tool_use_prompt_token_count")} if um else {}
            rec.update(outcome="ok_searched" if g["searched"] else "nosearch", queries=g["queries"],
                       n_queries=len(g["queries"]), sources=[s["uri"] for s in g["sources"]],
                       finish_reason=g["finish_reason"], tokens=tok, text=getattr(resp, "text", "") or "")
            in_t = (tok.get("prompt_token_count") or 0) + (tok.get("tool_use_prompt_token_count") or 0)
            out_t = (tok.get("candidates_token_count") or 0) + (tok.get("thoughts_token_count") or 0)
            rec["est_cost"] = len(g["queries"]) * SEARCH_PRICE + in_t * IN_PRICE + out_t * OUT_PRICE
        except Exception as e:                                             # noqa: BLE001
            s = str(e)
            oc = ("http_504" if ("504" in s or "DEADLINE_EXCEEDED" in s) else
                  "quota" if ("429" in s or "RESOURCE_EXHAUSTED" in s) else
                  "http_503" if ("503" in s or "UNAVAILABLE" in s) else "other_error")
            rec.update(outcome=oc, error=s[:300], est_cost=0.0)
            quota = quota + 1 if oc == "quota" else 0
        rec["latency_s"] = round(time.time() - t0, 1)
        est += rec.get("est_cost", 0); n += 1
        with CALLS.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        print(f"[{len(done)+n}/{MAX_CALLS}] rep{rep} {arm} {rec['outcome']:<12} {rec['latency_s']:>6}s "
              f"q={rec.get('n_queries','-')} est_total=${est:.2f}  {rec['row'][:40]}", flush=True)
        if quota >= 2:
            print("STOP: two quota errors in a row"); break
    print(f"finished. calls this session {n}, estimated spend ${est:.2f}")


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip().lower()


def score():
    import urllib.request
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    calls = [json.loads(l) for l in CALLS.read_text(encoding="utf-8").splitlines()]
    page_cache = {}

    def fetch(url):
        if url not in page_cache:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as rs:
                    page_cache[url] = (rs.status, norm(rs.read(2_000_000).decode("utf-8", "ignore")))
            except Exception as e:                                         # noqa: BLE001
                page_cache[url] = (getattr(e, "code", 0), "")
        return page_cache[url]

    for c in calls:
        if c["outcome"] != "ok_searched":
            continue
        t = sample[c["i"]]["truth"]
        try:
            m = re.search(r"\{.*\}", c["text"], re.S)
            d = json.loads(m.group(0)) if m else {}
        except Exception:                                                   # noqa: BLE001
            d = {}
        c["parsed"] = bool(d)
        c["deadline_ok"] = (d.get("SUBMISSION_DEADLINE") or "") == t["deadline"]
        ev = d.get("DEADLINE_EVIDENCE_URL") or ""
        q = d.get("DEADLINE_QUOTE") or ""
        if ev.startswith("http"):
            code, body = fetch(ev)
            c["evidence_http"] = code
            c["quote_on_page"] = bool(q) and norm(q) in body
            c["evidence_in_sources"] = any(ev.split("/")[2] in s for s in c["sources"]) if c["sources"] else False
        else:
            c["evidence_http"], c["quote_on_page"], c["evidence_in_sources"] = None, False, False

    out = {}
    for arm in ("A", "E"):
        cs = [c for c in calls if c["arm"] == arm]
        ok = [c for c in cs if c["outcome"] == "ok_searched"]
        lat = sorted(c["latency_s"] for c in cs)
        out[arm] = {
            "calls": len(cs),
            "grounded": len(ok),
            "grounded_pct": round(100 * len(ok) / max(1, len(cs))),
            "http_504": sum(c["outcome"] == "http_504" for c in cs),
            "no_search": sum(c["outcome"] == "nosearch" for c in cs),
            "other": sum(c["outcome"] not in ("ok_searched", "http_504", "nosearch") for c in cs),
            "median_latency_s": lat[len(lat) // 2] if lat else None,
            "mean_searches_when_grounded": round(sum(c["n_queries"] for c in ok) / max(1, len(ok)), 1),
            "deadline_correct_of_grounded": sum(bool(c.get("deadline_ok")) for c in ok),
            "evidence_url_resolves": sum(bool(c.get("evidence_http") and c["evidence_http"] < 400) for c in ok),
            "quote_found_on_page": sum(bool(c.get("quote_on_page")) for c in ok),
            "usable_end_to_end": sum(bool(c.get("deadline_ok") and c.get("quote_on_page")) for c in ok),
            "est_spend": round(sum(c.get("est_cost", 0) for c in cs), 2),
        }
    (HERE / "scored.json").write_text(json.dumps({"summary": out, "calls": calls}, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    for f in ("build-sample", "dry-run", "run", "score"):
        ap.add_argument(f"--{f}", action="store_true")
    a = ap.parse_args()
    if a.build_sample: build_sample()
    elif a.dry_run: dry_run()
    elif a.run: run()
    elif a.score: score()
    else: ap.print_help()
