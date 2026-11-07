"""Post-hoc check for RESULT.md (2026-11-07): is arm B's gap the FINDER or the READER? For every keyed row where B returned no date, take the page URL
another arm (A, C or D) cited, as already fetched and cached by score.py (pages_cache.json; no new fetch), run B's own reader and code proof on it
(read_the_page_pass.run.ask_with + finder_reader_test.accept_deadline) and see whether a proven date comes out and equals the key. About 1 cent.
Writes what_if_finder.json and prints one line per row. The key is read here only to pick the rows and to score afterwards; the reader never sees it."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (ROOT, ROOT / "experiments" / "sitemap_discovery", ROOT / "experiments" / "sentence_picking"):
    sys.path.insert(0, str(p))
os.environ.setdefault("CFP_CDP_URL", "http://127.0.0.1:9222")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from experiments.finder_reader_test import run as F
    from experiments.read_the_page_pass import run as R
    R.LOG, R.MAX_REQUESTS, R.MAX_USD = HERE / "reader_llm_log.jsonl", 3000, 1.0
    data = json.loads((HERE / "rows.json").read_text(encoding="utf-8"))
    today, rows = data["today"], data["rows"]
    key = json.loads((HERE / "key.json").read_text(encoding="utf-8"))
    cache = json.loads((HERE / "pages_cache.json").read_text(encoding="utf-8"))
    arms = {}
    for a, f, u in (("A", "arm_a_serial.jsonl", "evidence_url"), ("B", "arm_b.jsonl", "url"), ("C", "arm_c.jsonl", "url"), ("D", "arm_d.jsonl", "url")):
        arms[a] = {json.loads(l)["canonical"]: (json.loads(l).get("deadline") or "", json.loads(l).get(u) or "") for l in (HERE / f).read_text(encoding="utf-8").splitlines()}
    out, proven, right = [], 0, 0
    for row in rows:
        c = row["canonical"]
        k = key[c]["key"]
        if not k or arms["B"][c][0]:
            continue
        urls = []
        for a in ("D", "C", "A"):
            dl, u = arms[a][c]
            if dl and u.startswith("http") and u not in urls and cache.get(u, "").strip():
                urls.append(u)
        rec = {"n": row["n"], "event": row["event"], "key": k, "tried": []}
        for u in urls[:2]:
            text = cache[u]
            fields, cost = R.ask_with(F.SYSTEM, "C", row["event"], text)
            got, why = F.accept_deadline((fields or {}).get("deadline", {}), text, today)
            rec["tried"].append({"url": u, "chars": len(text), "accepted": got, "why": why, "usd": cost})
            if got:
                break
        got = next((t["accepted"] for t in rec["tried"] if t["accepted"]), "")
        rec["proven"] = got
        rec["equals_key"] = bool(got) and got == k
        proven += bool(got)
        right += rec["equals_key"]
        out.append(rec)
        print(f"  [{row['n']:>2}] key {k} -> {'proven ' + got + (' = key' if rec['equals_key'] else ' != key') if got else 'no proven date'} on {len(urls[:2])} page(s) {row['event'][:45]}")
    (HERE / "what_if_finder.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"WHAT-IF: {len(out)} keyed rows where B was blank; with the other arms' pages handed to B's reader: proven {proven}, equal to the key {right}; "
          f"rows with no other arm's page {sum(1 for r in out if not r['tried'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
