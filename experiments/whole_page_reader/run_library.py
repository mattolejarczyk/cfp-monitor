"""Run the frozen whole-page reader (reader.py: prompt v2b, the gate, the tolerant parser) over the OFFLINE PAGE LIBRARY. Advisory output only.

   python run_library.py --run [--limit N]     one request per usable page, 4 in parallel, resumable; hard caps below
   python run_library.py --summarize           gate every answer in code and write library_results.json

Reads saved text from page_library/page_library.db (scripts/page_library.py): no browser, no network except OpenRouter. Pages longer than 16,000 characters are read
from their first 16,000 (flagged `truncated`). Nothing is written to the conference database, the deliveries or the customer sheets.
Approved 2026-10-01: all usable pages; hard cap 0.60 USD and 420 requests.
"""
import json, os, sqlite3, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import reader as R                                                      # noqa: E402  (frozen prompt v2b, gate, tolerant parser, model call)

LIB = ROOT / "page_library" / "page_library.db"
LOG = HERE / "llm_log_library.jsonl"
OUT = HERE / "library_results.json"
MAX_REQUESTS, MAX_USD = 420, 0.60
WORKERS = 4
TODAY = date(2026, 10, 1)
_lock = threading.Lock()


def usable_pages():
    db = sqlite3.connect(f"file:{LIB.as_posix()}?mode=ro", uri=True)
    rows = db.execute("select url, host, text from pages where chars >= 300 and coalesce(soft404,'')='' and blocked=0 and coalesce(error,'')='' order by host, url").fetchall()
    db.close()
    return rows


def logged():
    done, n, usd = set(), 0, 0.0
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            n += 1; usd += r.get("cost_usd") or 0.0
            if r.get("content"):
                done.add(r["url"])
    return done, n, usd


def one(row, state):
    url, host, text = row
    with _lock:
        if state["n"] >= MAX_REQUESTS or state["usd"] >= MAX_USD:
            state["stopped"] = True
            return
        state["n"] += 1
    msgs = [{"role": "system", "content": R.SYSTEM}, {"role": "user", "content": "URL: " + url + "\n\nPAGE TEXT:\n" + text[:R.PAGE_CAP]}]
    err, content, cost = "", None, 0.0
    try:
        r, secs = R.sp.call_model(R.MODEL, msgs)
        j = r.json()
        content = j["choices"][0]["message"]["content"]
        cost = (j.get("usage") or {}).get("cost") or 0.0
    except Exception as e:                                              # noqa: BLE001
        secs, err = 0, f"{type(e).__name__}: {str(e)[:120]}"
    with _lock:
        state["usd"] += cost
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"url": url, "host": host, "secs": secs, "cost_usd": cost, "content": content, "error": err, "truncated": len(text) > R.PAGE_CAP, "prompt": R.PROMPT_VERSION}) + "\n")
        state["done"] += 1
        if state["done"] % 20 == 0:
            print(f"{state['done']} done  ${state['usd']:.4f}  {time.strftime('%H:%M:%S')}", flush=True)


def run(limit=None):
    done, n, usd = logged()
    todo = [r for r in usable_pages() if r[0] not in done]
    if limit:
        todo = todo[:limit]
    print(f"{len(todo)} pages to read; already read {len(done)}; spent so far {n} requests ${usd:.4f}", flush=True)
    state = {"n": n, "usd": usd, "done": 0, "stopped": False}
    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(lambda r: one(r, state), todo))
    print(f"FINISHED: {state['done']} requests this run; total ${state['usd']:.4f}{'; STOPPED AT CAP' if state['stopped'] else ''}", flush=True)


def summarize():
    pages = {u: (h, t) for u, h, t in usable_pages()}
    latest = {}
    for line in LOG.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("content"):
            latest[r["url"]] = r
    res, unparse, labels, malformed = {}, 0, {}, 0
    for url, r in latest.items():
        items = R.parse_items(r["content"], tolerant=True)
        if items is None:
            unparse += 1; continue
        host, text = pages[url]
        bad = sum(1 for d in items if not isinstance(d, dict))      # the model sometimes returns a bare string instead of an object
        malformed += bad
        items = [d for d in items if isinstance(d, dict)]
        acc = []
        for d in items:
            labels[d.get("label")] = labels.get(d.get("label"), 0) + 1
            ok, why = R.gate(text, d)
            if ok:
                acc.append({"date": d["closing_date"], "round": d.get("round", ""), "quote": d["unit_text"][:140], "heading": (d.get("heading") or "")[:60]})
        res[url] = {"host": host, "n_items": len(items), "accepted": acc, "truncated": r.get("truncated", False)}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    n, usd = logged()[1:]
    acc_pages = {u: v for u, v in res.items() if v["accepted"]}
    allacc = [(v["host"], a, u) for u, v in acc_pages.items() for a in v["accepted"]]
    future = [x for x in allacc if x[1]["date"] >= TODAY.isoformat()]
    print(f"pages read {len(latest)} (unparseable even tolerant: {unparse}); requests {n}; spent ${usd:.4f}")
    print(f"pages with at least one accepted submission deadline: {len(acc_pages)}; accepted dates: {len(allacc)}; on {len({x[0] for x in allacc})} sites")
    print(f"accepted dates still ahead of {TODAY}: {len(future)} on {len({x[0] for x in future})} sites")
    print("model labels:", dict(sorted(labels.items(), key=lambda x: -x[1])))
    print("truncated pages:", sum(1 for v in res.values() if v["truncated"]), "| malformed items skipped:", malformed)


if __name__ == "__main__":
    a = sys.argv
    if "--run" in a:
        run(int(a[a.index("--limit") + 1]) if "--limit" in a else None)
    if "--summarize" in a:
        summarize()
