"""Arms B, C and D of experiment T1 (2026-11-07). Blind: reads rows.json only (never key.json). Writes arm_b.jsonl / arm_c.jsonl / arm_d.jsonl and calls.jsonl beside it.

    .venv/Scripts/python.exe experiments/research_path_bakeoff/arm_bcd.py --arms B C [--limit 3] [--max-usd 1.0]
    .venv/Scripts/python.exe experiments/research_path_bakeoff/arm_bcd.py --arms D [--max-minutes 75]

B  search, fetch, extract, prove. ONE search per row for the official call page: the OpenRouter `openrouter:web_search` server tool (engine exa, 5 results,
   0.007 USD a request) on deepseek/deepseek-chat (the existing OpenRouter key; no Perplexity, DeepSeek, Brave or Exa key exists on this PC). Candidates:
   0 = the deadline page we hold (else the call page we hold), then the model's answer URLs, the url_citation annotations, and last year's URL with the
   year bumped; the top 3 are FETCHED by us (experiments/read_the_page_pass/run.page_text: plain fetch, then the real Chrome over CDP when the text has
   no dated sentence), READ one page at a time by the cheap reader (deepseek-chat, finder_reader_test.SYSTEM through read_the_page_pass.run.ask_with),
   PROVED in code (finder_reader_test.accept_deadline: the quote is on the page, states that day, month and year, uses call wording) and resolved to one
   deadline by the main-call rule (finder_reader_test.main_call.choose_main). A row with no proven quote is an honest blank.
C  OpenAI web_search with url_citation annotations. No OpenAI key exists here, so it runs through OpenRouter's `openrouter:web_search` server tool with
   engine native on openai/gpt-5-mini (OpenAI's own search, priced through at 0.01 USD a search call); the answer is the model's REPORT (deadline, URL,
   quote) and the scorer fetches the cited page itself to see whether it states the date. Recorded as 'C via OpenRouter', not the Responses API itself.
D  Codex CLI `codex exec --search` on the ChatGPT subscription (0 USD marginal): the same question, answer parsed for a date and a URL. No citation
   contract: nothing says the URL states the date until the scorer fetches it. Serial, one fresh ephemeral run per row, stops at the first Codex error.
Every provider call is one line of calls.jsonl (arm, row, provider, model, seconds, status, usd, searches, tokens). Spend caps: --max-usd per arm (B, C),
read from calls.jsonl, so a restart never spends twice. Keys come from the environment and are never printed. Nothing is written outside this folder."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (ROOT, ROOT / "experiments" / "sitemap_discovery", ROOT / "experiments" / "sentence_picking"):
    sys.path.insert(0, str(p))
# src/cfp_monitor/config.Settings reads CFP_CDP_URL when the module is IMPORTED, so the real Chrome (scripts/launch_chrome_cdp.bat, port 9222) is only used if
# this is set before any cfp_monitor import; the smoke test rendered through a headless browser for that reason (2026-11-07).
os.environ.setdefault("CFP_CDP_URL", "http://127.0.0.1:9222")

OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
# Search charges, used ONLY when the response carries no usage.cost. OpenRouter's usage.cost already includes the server tool charge: the smoke test's raw
# usage blocks show B cost 0.00808 = 0.00108 inference + 0.007 Exa, and C cost 0.02371 = 0.00371 inference + 2 x 0.01 OpenAI search (raw/*_01_server-tool.json).
EXA_USD = 0.007              # per Exa request (OpenRouter web search docs, read 2026-11-07)
OPENAI_SEARCH_USD = 0.01     # per web search call, OpenAI native through OpenRouter (model listing 'web_search': 0.01)
CALLS = HERE / "calls.jsonl"
CACHE = HERE / "pages_cache.json"
RAW = HERE / "raw"
MODEL_B_SEARCH = "deepseek/deepseek-chat"
MODEL_C = "openai/gpt-5-mini"

ASK_DEADLINE = ("Find the submission deadline for the MAIN call of this event: the call for papers, speakers, abstracts or proposals (not posters, awards, workshops, "
                "sponsors, registration or early-bird). If there are several rounds, give the next one to close after today. Use web search and read the official page.\n"
                'Answer ONLY a JSON object: {"deadline": "YYYY-MM-DD or empty", "url": "the official page that states this date", '
                '"quote": "one sentence copied verbatim from that page that states the date", "call": "what the deadline is for, in the page\'s words"}. '
                "If no official page states a deadline with its year for this edition, return an empty deadline, empty url and empty quote. Never guess a date.")
FIND_PAGE = ("Find the official web page of this event that states the deadline to submit a talk, paper, abstract or speaker proposal for the edition given "
             "(the call for papers / call for speakers page, or the event's own submission page). Use the web search tool once. "
             'Answer ONLY a JSON object: {"urls": ["the best official page first", "up to 4 more candidates"]}. '
             "Only pages on the event's own site or its submission platform; never news sites, aggregators or social media.")


# ------------------------------------------------------------------ logging and budget
def log_call(rec: dict) -> None:
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **rec}
    with open(CALLS, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def spent(arm: str) -> float:
    if not CALLS.exists():
        return 0.0
    return sum((json.loads(l).get("usd") or 0.0) for l in CALLS.read_text(encoding="utf-8").splitlines() if json.loads(l).get("arm") == arm)


def save_raw(name: str, body) -> None:
    RAW.mkdir(exist_ok=True)
    (RAW / name).write_text(json.dumps(body, ensure_ascii=False, indent=1) if not isinstance(body, str) else body, encoding="utf-8")


def parse_json(out: str) -> dict:
    try:
        return json.loads(out)
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", out or "", re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}


def canon_url(u: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", (u or "").lower()).split("#")[0].split("?")[0].rstrip("/")


def host_of(u: str) -> str:
    return urlparse(u).netloc.lower().removeprefix("www.") if u and u.startswith("http") else ""


# ------------------------------------------------------------------ OpenRouter with the web search server tool
def openrouter_search(model: str, system: str, user: str, engine: str, arm: str, tag: str, max_tokens: int = 1200, reasoning_low: bool = False) -> dict:
    """One chat completion with the `openrouter:web_search` server tool. Returns {"text", "annotations", "usage", "searches", "usd", "secs", "status", "error"}.
    Falls back to the deprecated `plugins: [{id: web}]` form if the server tool is refused for this model (recorded in the call log)."""
    import httpx
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("OPENROUTER_API_KEY missing")
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    base = {"model": model, "messages": msgs, "temperature": 0, "max_tokens": max_tokens, "usage": {"include": True}}
    if reasoning_low:
        base["reasoning"] = {"effort": "low"}
    shapes = [("server-tool", {**base, "tools": [{"type": "openrouter:web_search", "parameters": {"engine": engine, "max_results": 5}}], "max_tool_calls": 2}),
              ("plugin", {**base, "plugins": [{"id": "web", "engine": engine, "max_results": 5}]})]
    last = {"text": "", "annotations": [], "usage": {}, "searches": 0, "usd": 0.0, "secs": 0, "status": 0, "error": "", "shape": ""}
    for shape, body in shapes:
        t0 = time.time()
        try:
            r = httpx.post(OPENROUTER, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=body, timeout=150)
            secs, status, j = round(time.time() - t0, 1), r.status_code, (r.json() if r.content else {})
        except Exception as e:                                       # noqa: BLE001
            secs, status, j = round(time.time() - t0, 1), 0, {"error": {"message": f"{type(e).__name__}: {e}"}}
        save_raw(f"{arm}_{tag}_{shape}.json", j)
        usage = j.get("usage") or {}
        details = usage.get("server_tool_use_details") or {}
        searches = int(details.get("web_search_requests") or 0)
        msg = ((j.get("choices") or [{}])[0].get("message") or {})
        ok = status == 200 and bool(j.get("choices"))
        if ok and searches == 0 and (msg.get("annotations") or shape == "plugin"):
            searches = 1                                              # the plugin form reports no count: one request was made by construction
        per = EXA_USD if engine == "exa" else OPENAI_SEARCH_USD
        inference = ((usage.get("cost_details") or {}).get("upstream_inference_cost"))
        usd = float(usage["cost"]) if usage.get("cost") is not None else float(inference or 0.0) + searches * per
        err = "" if ok else str((j.get("error") or {}).get("message") or j)[:300]
        log_call({"arm": arm, "row": tag, "provider": "openrouter", "model": model, "shape": shape, "engine": engine, "seconds": secs, "status": status, "usd": round(usd, 5),
                  "usd_model": usage.get("cost"), "searches": searches, "tokens": {"in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens")}, "error": err})
        last = {"text": msg.get("content") or "", "annotations": [a.get("url_citation", {}) for a in (msg.get("annotations") or []) if a.get("type") == "url_citation"],
                "usage": usage, "searches": searches, "usd": usd, "secs": secs, "status": status, "error": err, "shape": shape}
        if ok or not (status == 400 and "tool" in err.lower()):
            break                                                     # only an "unsupported tool" 400 earns the fallback shape
    return last


# ------------------------------------------------------------------ arm B
def bump_year(u: str, edition: str) -> str:
    """Last year's URL with the year moved to the edition (2026 -> 2027, '26' after letters -> '27'). '' when nothing changes."""
    if not u or not edition.isdigit():
        return ""
    prev = str(int(edition) - 1)
    out = u.replace(prev, edition) if prev in u else re.sub(rf"(?<=[A-Za-z_-]){prev[2:]}(?=[/._-]|$)", edition[2:], u)
    return out if out != u else ""


def arm_b_row(row: dict, today: str, ctx, cache: dict) -> dict:
    from experiments.finder_reader_test import run as F
    from experiments.finder_reader_test.main_call import choose_main
    held = row["held"]
    t0 = time.time()
    user = f"EVENT: {row['event']}\nEDITION YEAR: {row['edition']}\nEVENT SITE: {', '.join(row['hosts']) or 'unknown'}"
    s = openrouter_search(MODEL_B_SEARCH, FIND_PAGE, user, "exa", "B", f"{row['n']:02d}")
    answer = parse_json(s["text"])
    from_answer = [u for u in (answer.get("urls") or []) if isinstance(u, str) and u.startswith("http")]
    from_ann = [a.get("url", "") for a in s["annotations"] if a.get("url", "").startswith("http")]
    own = set(row["hosts"])
    ordered = []
    for u, src in ([(held["evidence"] or held["cfp"], "held")] + [(u, "answer") for u in from_answer] + [(u, "annotation") for u in from_ann]
                   + [(bump_year(held["evidence"], row["edition"]), "bump"), (bump_year(held["cfp"], row["edition"]), "bump")]):
        if u and canon_url(u) not in {canon_url(x) for x, _ in ordered}:
            ordered.append((u, src))
    # own-site candidates before foreign ones, held first, otherwise the order above
    ordered = [c for c in ordered if c[1] == "held"] + [c for c in ordered if c[1] != "held" and (host_of(c[0]) in own or not own)] + [c for c in ordered if c[1] != "held" and own and host_of(c[0]) not in own]
    top = ordered[:3]
    pages, cands = [], []
    for u, src in top:
        text = ctx.page_text(u, cache)
        got, why, what, quote, cost = "", "page unreadable", "", "", None
        if text.strip():
            fields, cost = ctx.R.ask_with(F.SYSTEM, "C", row["event"], text)
            log_call({"arm": "B", "row": f"{row['n']:02d}", "provider": "openrouter", "model": "deepseek/deepseek-chat (reader)", "seconds": None, "status": 200 if fields is not None else 0,
                      "usd": round(cost or 0.0, 6), "searches": 0, "url": u})
            fields = fields or {}
            got, why = F.accept_deadline(fields.get("deadline", {}), text, today)
            what, quote = str(fields.get("what", "")), str((fields.get("deadline") or {}).get("quote", ""))
        pages.append({"url": u, "source": src, "chars": len(text), "accepted": got, "why": why, "what": what, "quote": quote if got else ""})
        if got:
            cands.append({"value": got, "url": u, "what": what, "quote": quote, "home": False})
    pick = choose_main(cands, today)
    pu = next((p for p in pages if p["accepted"] == pick["pick"]), {}) if pick["pick"] else {}
    return {"canonical": row["canonical"], "event": row["event"], "market": row["market"], "deadline": pick["pick"], "url": pu.get("url", ""), "quote": pu.get("quote", ""),
            "why": pick["why"], "other_calls": pick["other_calls"], "candidates": [{"url": u, "source": src} for u, src in ordered[:8]], "fetched": pages,
            "search": {"shape": s["shape"], "status": s["status"], "error": s["error"], "answer_urls": from_answer, "annotation_urls": from_ann, "searches": s["searches"], "usd": round(s["usd"], 5)},
            "usd": round(s["usd"] + sum((p.get("cost") or 0) for p in []), 5), "secs": round(time.time() - t0, 1)}


# ------------------------------------------------------------------ arm C
def arm_c_row(row: dict, today: str) -> dict:
    t0 = time.time()
    user = f"EVENT: {row['event']}\nEDITION YEAR: {row['edition']}\nEVENT SITE: {', '.join(row['hosts']) or 'unknown'}\nTODAY: {today}"
    s = openrouter_search(MODEL_C, ASK_DEADLINE, user, "native", "C", f"{row['n']:02d}", max_tokens=2500, reasoning_low=True)
    ans = parse_json(s["text"])
    dl = str(ans.get("deadline") or "").strip()[:10]
    return {"canonical": row["canonical"], "event": row["event"], "market": row["market"], "deadline": dl if re.fullmatch(r"\d{4}-\d{2}-\d{2}", dl) else "",
            "deadline_raw": str(ans.get("deadline") or ""), "url": str(ans.get("url") or ""), "quote": str(ans.get("quote") or ""), "call": str(ans.get("call") or ""),
            "annotation_urls": [a.get("url", "") for a in s["annotations"]], "searches": s["searches"], "usd": round(s["usd"], 5), "secs": round(time.time() - t0, 1),
            "status": s["status"], "error": s["error"], "shape": s["shape"], "text": s["text"][:1500]}


# ------------------------------------------------------------------ arm D
class CodexStop(RuntimeError):
    pass


CODEX_MODEL = ["gpt-6-luna"]   # the Codex model the model bake-off ran on this ChatGPT account (experiments/model_bakeoff/models.json); the config default gpt-6.1-sol is refused ("not supported when using Codex with a ChatGPT account")


def codex_search(prompt: str, tag: str, timeout: int = 300, effort: str = "low") -> dict:
    """One fresh `codex exec --search` (ephemeral, read-only sandbox, empty scratch dir), prompt on stdin. Mirrors experiments/model_bakeoff/bakeoff_lib.codex_ask plus --search."""
    with tempfile.TemporaryDirectory(prefix="codex_search_") as scratch:
        out_file = Path(scratch) / "last.txt"
        # `--search` is a top-level codex flag ("Enable live web search ... the native Responses web_search tool"), not an exec option (codex-cli 0.155.1)
        cmd = ["codex", "--search", "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "-C", scratch, "-m", CODEX_MODEL[0], "-c", f"model_reasoning_effort={effort}", "-o", str(out_file), "-"]
        t0 = time.time()
        try:
            p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, shell=(os.name == "nt"))
        except subprocess.TimeoutExpired:
            log_call({"arm": "D", "row": tag, "provider": "codex", "model": CODEX_MODEL[0], "seconds": timeout, "status": 0, "usd": 0.0, "searches": None, "error": "timeout"})
            return {"text": "", "secs": timeout, "tokens": None, "error": "timeout", "stdout": ""}
        secs = round(time.time() - t0, 1)
        combined = (p.stdout or "") + "\n" + (p.stderr or "")
        m = re.search(r"tokens used\D{0,20}([\d,]+)", combined, re.I)
        tokens = int(m.group(1).replace(",", "")) if m else None
        last = out_file.read_text(encoding="utf-8", errors="replace") if out_file.exists() else ""
        err = "" if (p.returncode == 0 and last.strip()) else combined.strip()[-1500:]
        log_call({"arm": "D", "row": tag, "provider": "codex", "model": CODEX_MODEL[0], "seconds": secs, "status": p.returncode, "usd": 0.0, "searches": None, "tokens": tokens, "error": err[-300:]})
        save_raw(f"D_{tag}_console.txt", combined)
        if err:
            raise CodexStop(err)
        return {"text": last, "secs": secs, "tokens": tokens, "error": "", "stdout": combined[-2000:]}


def arm_d_row(row: dict, today: str) -> dict:
    prompt = (ASK_DEADLINE + "\n\n" + f"EVENT: {row['event']}\nEDITION YEAR: {row['edition']}\nEVENT SITE: {', '.join(row['hosts']) or 'unknown'}\nTODAY: {today}"
              + "\n\nDo not run commands or read files; use web search only. Answer with the JSON object only.")
    r = codex_search(prompt, f"{row['n']:02d}")
    ans = parse_json(r["text"])
    dl = str(ans.get("deadline") or "").strip()[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dl):
        m = re.search(r"\b(20\d\d-\d\d-\d\d)\b", r["text"])
        dl = m.group(1) if m else ""
    url = str(ans.get("url") or "")
    if not url.startswith("http"):
        m = re.search(r"https?://[^\s\"'<>)]+", r["text"])
        url = m.group(0) if m else ""
    return {"canonical": row["canonical"], "event": row["event"], "market": row["market"], "deadline": dl, "url": url, "quote": str(ans.get("quote") or ""),
            "call": str(ans.get("call") or ""), "parsed_json": bool(ans), "tokens": r["tokens"], "usd": 0.0, "secs": r["secs"], "error": r["error"], "text": r["text"][:1500]}


# ------------------------------------------------------------------ main
def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="+", default=["B", "C"])
    ap.add_argument("--rows", default=str(HERE / "rows.json"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-usd", type=float, default=1.0, help="per arm, read from calls.jsonl")
    ap.add_argument("--max-minutes", type=float, default=90)
    ap.add_argument("--codex-model", default=CODEX_MODEL[0])
    a = ap.parse_args()
    CODEX_MODEL[0] = a.codex_model
    data = json.loads(Path(a.rows).read_text(encoding="utf-8"))
    today, rows = data["today"], data["rows"][: a.limit or None]
    for arm in a.arms:
        out = HERE / f"arm_{arm.lower()}.jsonl"
        done = {json.loads(l)["canonical"] for l in out.read_text(encoding="utf-8").splitlines()} if out.exists() else set()
        todo = [r for r in rows if r["canonical"] not in done]
        print(f"ARM {arm}: {len(todo)} rows to do ({len(done)} already in {out.name}); spent so far {spent(arm):.3f} USD, cap {a.max_usd}", flush=True)
        ctx, cache = None, {}
        if arm == "B":
            from types import SimpleNamespace
            from experiments.read_the_page_pass import run as R
            R.LOG, R.MAX_REQUESTS, R.MAX_USD = HERE / "reader_llm_log.jsonl", 2000, a.max_usd     # the reader's own log and cap, never the experiments' shared log
            cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
            ctx = SimpleNamespace(R=R, page_text=R.page_text)
        t_run, stop, attempted = time.time(), "", 0
        for row in todo:
            if (time.time() - t_run) / 60 > a.max_minutes:
                stop = f"stopped at {a.max_minutes} minutes"
                break
            if arm in ("B", "C") and spent(arm) >= a.max_usd:
                stop = f"stopped at the {a.max_usd} USD cap"
                break
            attempted += 1
            try:
                if arm == "B":
                    res = arm_b_row(row, today, ctx, cache)
                    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                elif arm == "C":
                    res = arm_c_row(row, today)
                else:
                    res = arm_d_row(row, today)
            except CodexStop as e:
                stop = f"Codex error at row {row['n']} (exact text follows, not retried):\n{e}"
                break
            except SystemExit as e:
                stop = f"reader budget guard: {e}"
                break
            except Exception as e:                                   # noqa: BLE001  one bad row never ends the arm
                res = {"canonical": row["canonical"], "event": row["event"], "market": row["market"], "deadline": "", "url": "", "quote": "", "error": f"{type(e).__name__}: {e}", "usd": 0.0, "secs": 0}
            with open(out, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(res, ensure_ascii=False) + "\n")
            print(f"  [{row['n']:>2}] {arm} {res.get('secs', 0):6.1f}s {res.get('usd', 0):.4f} USD deadline {res.get('deadline') or '-':10} {row['event'][:46]:46} {str(res.get('url', ''))[:60]}"
                  + (f"  ERR {str(res.get('error'))[:50]}" if res.get("error") else ""), flush=True)
        print(f"ARM {arm} DONE: {attempted} of {len(todo)} attempted, {(time.time() - t_run) / 60:.1f} min, spent {spent(arm):.3f} USD{'; ' + stop if stop else ''}", flush=True)
        if arm == "B":
            try:
                import asyncio
                from src.cfp_monitor import fetch as _f
                asyncio.run(_f.close_fallback_browser())
            except Exception:                                        # noqa: BLE001
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
