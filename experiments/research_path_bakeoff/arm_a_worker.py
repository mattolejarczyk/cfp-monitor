"""Arm A of experiment T1, and experiment T2: the CURRENT grounded call (run_market_audit.audit_conference) on the experiment rows, on a COPY.

    C:\\Python313\\python.exe experiments/research_path_bakeoff/arm_a_worker.py --rows rows.json --out arm_a_serial.jsonl --delay 16 --timeout 120 --workers 1
    C:\\Python313\\python.exe experiments/research_path_bakeoff/arm_a_worker.py --rows rows.json --out arm_a_parallel.jsonl --delay 0 --timeout 60 --workers 4

Runs under the interpreter the Markets tests use (google.genai, pandas). Imports run_market_audit.py from markets_copy/ (a copy of the upstream working
area's script and its standing_rules.md, taken the day of the run), never the live file, and writes NOTHING under the Markets folder: results go beside
this script. Exactly the production call: CFP_PROMPT_MODE=narrow-first, model default, verify_citations=False (run_all.ps1 passes no --verify-citations),
one RateLimiter shared by every worker (T1: 16 s like the Saturday job; T2: 0 with 4 workers), the client's own retry layer off (attempts=1) as in main().
Per row: seconds, attempts, searches run, source hosts, error classes, the deadline, evidence URL and quote returned, token counts (from usage_metadata).
The grounding trail and health file are written like a real run (<out>.grounding.jsonl, <out>.health.json). Stops at the first HTTP 429 (quota) and says so.
The key is never read here."""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "markets_copy"))
os.environ.setdefault("CFP_PROMPT_MODE", "narrow-first")

SEARCH_USD = 0.014                      # Google Search grounding, 14 USD per 1,000 (docs/design/inspection-2026-11-07.md)
TOKEN_USD = {"in": 0.50 / 1e6, "out": 3.00 / 1e6}   # ASSUMED list price of gemini-3-flash-preview per token; reported separately, flagged in RESULT.md


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--delay", type=float, default=16.0)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    import run_market_audit as M                                    # the COPY (sys.path above); reads markets_copy/standing_rules.md at import
    from google import genai
    from google.genai import types
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY missing from the environment")
    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=int(a.timeout * 1000), retry_options=types.HttpRetryOptions(attempts=1)))
    data = json.loads(Path(a.rows).read_text(encoding="utf-8"))
    today, rows = data["today"], data["rows"][: a.limit or None]
    limiter = M.RateLimiter(a.delay)
    usage_lock, usage = threading.Lock(), {}                         # per conference label: token counts of every attempt, captured around the API call
    orig = client.models.generate_content

    def counting_generate(*args, **kw):
        r = orig(*args, **kw)
        um = getattr(r, "usage_metadata", None)
        if um is not None:
            with usage_lock:
                usage.setdefault(threading.get_ident(), []).append({"in": getattr(um, "prompt_token_count", 0) or 0, "out": getattr(um, "candidates_token_count", 0) or 0,
                                                                     "thinking": getattr(um, "thoughts_token_count", 0) or 0, "tool": getattr(um, "tool_use_prompt_token_count", 0) or 0})
        return r
    client.models.generate_content = counting_generate
    out_path = Path(a.out)
    stop = {"why": ""}
    print(f"ARM A: {len(rows)} rows, delay {a.delay}s, timeout {a.timeout}s, workers {a.workers}, prompt mode {M.prompt_mode()}, model {M.DEFAULT_MODEL}", flush=True)
    t_run = time.time()

    def one(row):
        if stop["why"]:
            return {"canonical": row["canonical"], "event": row["event"], "skipped": stop["why"]}
        label = M.cell(row["input_row"], "CONFERENCE") or "row"
        before = len(M.GROUNDING_TRAIL.attempts)
        with usage_lock:
            usage[threading.get_ident()] = []
        t0 = time.time()
        err = ""
        try:
            rec = M.audit_conference(client, dict(row["input_row"]), today, limiter=limiter, verify_citations=False)
        except M.QuotaExhausted as e:
            stop["why"] = f"quota (429) at row {row['n']} {row['event']}: {str(e)[:200]}"
            rec, err = {}, str(e)
        except Exception as e:                                       # noqa: BLE001  the experiment records a failure, it does not die on one
            rec, err = {}, f"{type(e).__name__}: {e}"
        secs = round(time.time() - t0, 1)
        attempts = [x for x in M.GROUNDING_TRAIL.attempts[before:] if x.get("row") == label]
        with usage_lock:
            toks = usage.get(threading.get_ident(), [])
        if any(x.get("error_class") == "http_429_quota" for x in attempts) and not stop["why"]:
            stop["why"] = f"first HTTP 429 at row {row['n']} {row['event']}"
        n_search = sum(x.get("n_queries", 0) for x in attempts)
        hosts = sorted({M.host_of(s.get("title", "")) or M.host_of(s.get("uri", "")) for x in attempts for s in x.get("sources", [])} - {"", "vertexaisearch.cloud.google.com"})
        tin, tout = sum(t["in"] + t["tool"] for t in toks), sum(t["out"] + t["thinking"] for t in toks)
        res = {"canonical": row["canonical"], "event": row["event"], "market": row["market"], "secs": secs, "attempts": len(attempts),
               "errors": [x["error_class"] for x in attempts if x.get("error_class")], "searched": any(x.get("searched") for x in attempts),
               "searches": n_search, "source_hosts": hosts, "deadline": str(rec.get("SUBMISSION DEADLINE") or "")[:10], "evidence_url": str(rec.get("DEADLINE_EVIDENCE_URL") or ""),
               "quote": str(rec.get("DEADLINE_QUOTE") or ""), "status": str(rec.get("STATUS") or ""), "is_projected": rec.get("IS_PROJECTED", ""), "confidence": rec.get("GROUNDING_CONFIDENCE", ""),
               "stub": "[Audit Exception]" in str(rec.get("STATUS DETAILS", "")), "error": err, "tokens_in": tin, "tokens_out": tout,
               "usd_search": round(n_search * SEARCH_USD, 4), "usd_tokens_est": round(tin * TOKEN_USD["in"] + tout * TOKEN_USD["out"], 5),
               "cfp_url": rec.get("CFP_SUBMISSION_URL", ""), "started_at": round(t0 - t_run, 1)}
        print(f"  [{row['n']:>2}] {secs:6.1f}s attempts {len(attempts)} searches {n_search:>2} deadline {res['deadline'] or '-':10} {row['event'][:50]}"
              + (f"  ERR {err[:60]}" if err else ""), flush=True)
        return res

    results = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(one, r) for r in rows]
        for f in as_completed(futs):
            results.append(f.result())
    results.sort(key=lambda r: next(r2["n"] for r2 in rows if r2["canonical"] == r["canonical"]))
    wall = round(time.time() - t_run, 1)
    with open(out_path, "w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    trail = M.GROUNDING_TRAIL.write(str(out_path))
    verdict, reasons = M.CALL_HEALTH.verdict()
    health = M.GROUNDING_TRAIL.write_health(str(out_path), verdict, reasons)
    done = [r for r in results if not r.get("skipped")]
    n_att = sum(r["attempts"] for r in done)
    n504 = sum(r["errors"].count("http_504") for r in done)
    n429 = sum(r["errors"].count("http_429_quota") for r in done)
    summary = {"rows": len(rows), "done": len(done), "skipped": len(results) - len(done), "wall_secs": wall, "workers": a.workers, "delay": a.delay, "timeout": a.timeout,
               "attempts": n_att, "http_504": n504, "http_429": n429, "timeouts": sum(r["errors"].count("timeout") for r in done),
               "searches": sum(r["searches"] for r in done), "usd_search": round(sum(r["usd_search"] for r in done), 3),
               "usd_tokens_est": round(sum(r["usd_tokens_est"] for r in done), 3), "stubs": sum(1 for r in done if r["stub"]), "stop": stop["why"],
               "health": M.CALL_HEALTH.banner(), "trail": M.GROUNDING_TRAIL.banner_line(), "finished": datetime.now().isoformat(timespec="seconds")}
    Path(str(out_path) + ".summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"\n{summary['health']}\n{summary['trail']}")
    print(f"ARM A DONE: {len(done)} of {len(rows)} rows in {wall:.0f}s wall ({a.workers} worker(s)); attempts {n_att}, 504s {n504}, 429s {n429}; "
          f"searches {summary['searches']} = {summary['usd_search']:.3f} USD at 14 USD per 1,000, tokens about {summary['usd_tokens_est']:.3f} USD; "
          f"{'STOPPED: ' + stop['why'] if stop['why'] else 'no quota stop'} -> {out_path}, {trail}, {health}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
