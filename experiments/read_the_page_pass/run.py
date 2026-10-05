"""Experiment 4 runner: the read-the-page pass, scored on what the operator verified plus the trap cases.

    python experiments/read_the_page_pass/run.py --models B C          # B = deepseek-v4.1-flash, C = deepseek-chat; budget cap 60 requests / 0.50 USD

Gold = the pinned operator verifications (docs/operations/pinned_rows.json): start dates, cities, countries, and the pinned BLANKS (events whose page states nothing for the
asked edition). Pages = the pages the operator verified on (pin links), fetched with the plain reader (verify.fetch_text); a walled or dead page is reported as unreadable and
the pass must stay blank. Plus the trap cases that are pages (docs/qa/trap-cases.json T01, T02, T09) and the real ODSC East page (gold read by Claude, not the operator). Nothing is written to the database or the pipeline.
Writes: results.json, llm_log.jsonl (every call, tokens, cost), pages.json (cache, git-ignored). The key is read from the environment and never printed."""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments" / "sentence_picking"))
sys.path.insert(0, str(ROOT / "experiments" / "sitemap_discovery"))
import sentence_pick as sp                                                    # noqa: E402  (call_model, MODELS)
from experiments.read_the_page_pass import pass_lib as L                      # noqa: E402
from scripts.pinned_rows import load_pins                                     # noqa: E402
from src.cfp_monitor.verify import fetch_text, is_block_page                  # noqa: E402

MAX_REQUESTS, MAX_USD = 150, 0.50          # raised from 60 on 2026-10-03: three repeats per model; the whole experiment still costs cents
LOG = HERE / "llm_log.jsonl"
PAGES = HERE / "pages.json"
sp.MAXTOK[0] = 3000
os.environ.setdefault("SP_EXTRA", json.dumps({"reasoning": {"effort": "low"}}))   # the v4.1 flash model reasons by default; low effort keeps the answer inside the token limit


def spent():
    n, usd = 0, 0.0
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            n += 1
            usd += r.get("cost_usd") or 0.0
    return n, usd


RENDER = {"on": True}


def page_text(url, cache):
    """Plain fetch first; if the text has no dated sentence at all, render the page in the real Chrome (LIMITER 1: script-built pages). Cached per URL and mode."""
    if url in cache:
        return cache[url]
    try:
        t, _n = fetch_text(url)
    except Exception:                                                        # noqa: BLE001
        t = ""
    t = "" if (t and is_block_page(t)) else (t or "")
    if RENDER["on"] and L.looks_dateless(t):
        from src.cfp_monitor.render_text import render_text
        rt, note = render_text(url)
        print(f"  render {url[:60]}: plain {len(t)} chars -> {len(rt)} chars ({note})", flush=True)
        if len(rt) > len(t):
            t = rt
    cache[url] = t
    return t


def edition_of(pin):
    m = re.match(r"(20\d\d)-", pin["canonical"])
    return m.group(1) if m else ""


def ask(model_key, event, edition, text):
    return _call(model_key, event, [{"role": "system", "content": L.SYSTEM}, {"role": "user", "content": L.user_message(event, edition, text)}])


def ask_with(system, model_key, event, text, cap=12000):
    """Same call and budget log with a different system prompt (used by experiments/finder_reader_test: the submission deadline instead of the edition facts)."""
    page = text[:cap]
    return _call(model_key, event, [{"role": "system", "content": system}, {"role": "user", "content": "EVENT: " + event + chr(10) * 2 + "PAGE TEXT:" + chr(10) + page}])


def _call(model_key, event, msgs):
    n, usd = spent()
    if n >= MAX_REQUESTS or usd >= MAX_USD:
        sys.exit(f"budget reached: {n} requests, {usd:.3f} USD")
    body, cost, secs, r = {}, None, 0, None
    for attempt, pause in enumerate((0, 8, 20, 45)):          # a rate limit (429) or a server error is a FAILED CALL, never a blank answer
        if pause:
            time.sleep(pause)
        r, secs = sp.call_model(sp.MODELS[model_key], msgs)
        body = r.json() if r.status_code == 200 else {}
        cost = (body.get("usage") or {}).get("cost")
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"model": sp.MODELS[model_key], "event": event, "seconds": secs, "cost_usd": cost, "usage": body.get("usage"), "status": r.status_code, "attempt": attempt}) + "\n")
        if r.status_code == 200 and body.get("choices"):
            break
    else:
        return None, None
    out = (body["choices"][0]["message"].get("content") or "")
    try:
        return json.loads(out), cost
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", out, re.S)
        try:
            return (json.loads(m.group(0)) if m else {}), cost
        except json.JSONDecodeError:
            return {}, cost


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["B"])
    ap.add_argument("--repeats", type=int, default=1, help="run each model this many times: temperature 0 is not deterministic at low reasoning effort")
    ap.add_argument("--no-render", action="store_true", help="plain fetch only (the 2026-10-03 baseline)")
    a = ap.parse_args()
    RENDER["on"] = not a.no_render
    cache = json.loads(PAGES.read_text(encoding="utf-8")) if PAGES.exists() else {}
    pins = load_pins()
    gold = L.gold_facts(pins)
    by_event = {}
    for g in gold:
        by_event.setdefault(g["canonical"], []).append(g)
    pin_by = {p["canonical"]: p for p in pins}
    jobs = []                                                                # (name, edition, text, [gold facts])
    for cid, facts in by_event.items():
        p = pin_by[cid]
        texts = [page_text(u, cache) for u in p.get("links", [])]
        text = "\n\n".join(t[:7000] for t in texts if t)
        jobs.append((p["event"], edition_of(p), text, facts, [len(t) for t in texts]))
    traps = {c["id"]: c for c in json.load(open(ROOT / "docs" / "qa" / "trap-cases.json", encoding="utf-8"))["cases"]}
    jobs.append(("TRAP T01 Carbon Capture Technology Expo MENA, asked 2026 edition (page shows 2027): must stay blank", "2026", traps["T01"]["fixture"], [{"field": "start_date", "gold": ""}], [len(traps["T01"]["fixture"])]))
    # ODSC East: the page header states the 2027 edition (read by Claude in a real browser 2026-10-03; NOT operator-verified, so not in the pins). The page text is fetched like the others.
    odsc = page_text("https://odsc.ai/east/", cache)
    jobs.append(("ODSC East 2027, the real page (Claude's browser read: header says May 10-12th, 2027)", "2027", odsc[:14000], [{"field": "start_date", "gold": "2027-05-10"}], [len(odsc)]))
    jobs.append(("TRAP T02 ODSC East two editions on one page, asked 2027", "2027", traps["T02"]["fixture"], [{"field": "start_date", "gold": "2027-05-10"}], [len(traps["T02"]["fixture"])]))
    jobs.append(("TRAP T02 ODSC East two editions on one page, asked 2026", "2026", traps["T02"]["fixture"], [{"field": "start_date", "gold": "2026-04-28"}], [len(traps["T02"]["fixture"])]))
    jobs.append(("TRAP T09 European CCUS 2027", "2027", traps["T09"]["fixture"], [{"field": "start_date", "gold": "2027-01-26"}], [len(traps["T09"]["fixture"])]))
    PAGES.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    results = {}
    for mk in a.models:
      for rep in range(a.repeats):
        items, total = [], 0.0
        for event, edition, text, facts, lens in jobs:
            readable = bool(text.strip())
            fields, cost = ({}, 0.0)
            failed = False
            if readable:
                fields, cost = ask(mk, event, edition, text)
                failed = fields is None
                total += cost or 0.0
                time.sleep(2)
            for f in facts:
                if failed:
                    got, why = "", "CALL FAILED (rate limit or server error after 4 tries): not scored"
                else:
                    got, why = L.accept(f["field"], (fields or {}).get(f["field"], {}), text, edition) if readable else ("", "page unreadable")
                items.append({"event": event, "field": f["field"], "gold": f["gold"], "accepted": got, "why": why, "readable": readable, "call_failed": failed, "tier": f.get("tier", "person-confirmed")})
        key = f"{mk}#{rep + 1}"
        results[key] = {"model": sp.MODELS[mk], "score": L.score(items), "cost_usd": round(total, 5), "items": items}
        s = results[key]["score"]
        print(f"\n== {sp.MODELS[mk]} run {rep + 1}: precision {s['precision']}, recall {s['recall']} ({s['found_of_gold']}), wrong {s['wrong']}, blanks kept blank {s['blank_kept_blank']} of {s['blank_gold']}, false accepts {s['false_accept']}, calls failed {s['calls_failed']}, cost ${total:.4f}", flush=True)
    # stability: a fact is STABLE if it is accepted and correct in every run of a model
    for mk in a.models:
        runs = [results[f"{mk}#{r + 1}"]["items"] for r in range(a.repeats)]
        keyed = {}
        for run in runs:
            for i in run:
                if i.get("call_failed"):
                    continue
                ok = (i["accepted"] and i["gold"] and L.same(i["field"], i["accepted"], i["gold"])) or (not i["accepted"] and not i["gold"])
                keyed.setdefault((i["event"], i["field"], i["gold"]), []).append(bool(ok) and bool(i["gold"]))
        gold_keys = [k for k in keyed if k[2]]
        always = sum(1 for k in gold_keys if all(keyed[k]))
        ever = sum(1 for k in gold_keys if any(keyed[k]))
        print(f"   {sp.MODELS[mk]}: of {len(gold_keys)} verified facts, found in EVERY run {always}, in at least one run {ever}", flush=True)
    (HERE / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    n, usd = spent()
    print(f"\ntotal so far: {n} requests, {usd:.4f} USD")


if __name__ == "__main__":
    main()
