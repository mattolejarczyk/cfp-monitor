"""ACT-56 run registry: an APPEND-ONLY log, one row per (call, fact tested). Never rewritten, never deleted.

Row fields: run_id, ts, model_key, model_id, route, effort, role, job, event, edition, fact, prompt_sha, page_sha (the page text is saved under pages/<page_sha>.txt so any row can be
replayed), raw_response (FULL), parsed, quote, quote_verbatim_on_page, accepted (what the production acceptance rule let through), accept_why, key_value, verdict
(correct | correct-blank | missed | wrong-accepted | call-failed), tokens_in, tokens_out, tokens_total (Codex reports one total), cost_usd, latency_s, error.

Scoring happens HERE, in code, AFTER the call: the key value is never part of any request (bakeoff_lib.blind_messages takes no key value)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from experiments.model_bakeoff import bakeoff_lib as B
from experiments.read_the_page_pass import pass_lib as L

REGISTRY = B.HERE / "registry.jsonl"
PAGE_DIR = B.HERE / "pages"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save_page(text: str, page_dir: Path | None = None) -> str:
    d = page_dir or PAGE_DIR
    h = sha(text)[:16]
    d.mkdir(exist_ok=True)
    f = d / f"{h}.txt"
    if not f.exists():
        f.write_text(text, encoding="utf-8")
    return h


def verdict(item: dict) -> str:
    """correct = accepted and equals the key; correct-blank = key blank and nothing accepted; missed = nothing accepted for a fact the key has; wrong-accepted = accepted and differs
    from the key, or accepted where the key is blank; call-failed = no usable answer (not scored)."""
    if item.get("call_failed"):
        return "call-failed"
    if not item["gold"]:
        return "wrong-accepted" if item["accepted"] else "correct-blank"
    if not item["accepted"]:
        return "missed"
    return "correct" if L.same(item["field"], item["accepted"], item["gold"]) else "wrong-accepted"


def append_rows(model_key: str, run_id: str, job: dict, msgs: list[dict], result: dict, registry: Path | None = None, page_dir: Path | None = None, role: str = "reader") -> list[dict]:
    cfg = B.load_models()[model_key]
    ok = result.get("status") == 200 and result.get("parsed") is not None
    page_hash = save_page(job["text"], page_dir)
    prompt_hash = sha(msgs[0]["content"] + "\n" + msgs[1]["content"])[:16]
    rows = []
    for f in job["facts"]:
        it = B.score_item(job, f["field"], f["gold"], result["parsed"] if ok else None)
        pf = (result["parsed"] or {}).get("deadline" if job["kind"] == "deadline" else f["field"], {}) if ok else {}
        quote = pf.get("quote", "") if isinstance(pf, dict) else ""
        rows.append({"run_id": run_id, "ts": datetime.now().isoformat(timespec="seconds"), "model_key": model_key, "model_id": cfg["id"], "route": cfg["route"],
                     "effort": cfg.get("effort", ""), "role": role, "job": job["id"], "event": job["event"], "edition": job["edition"], "fact": f["field"],
                     "prompt_sha": prompt_hash, "page_sha": page_hash, "raw_response": result.get("raw", ""), "parsed": pf if ok else None, "quote": quote,
                     "quote_verbatim_on_page": bool(quote) and L.norm(quote) in L.norm(job["text"]), "accepted": it["accepted"], "accept_why": it["why"],
                     "key_value": f["gold"], "verdict": verdict(it), "tokens_in": result.get("tokens_in"), "tokens_out": result.get("tokens_out"),
                     "tokens_total": result.get("tokens"), "cost_usd": result.get("cost"), "latency_s": result.get("seconds"), "error": result.get("error", "")})
    with open(registry or REGISTRY, "a", encoding="utf-8") as fh:        # append only
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return rows


def read(registry: Path | None = None) -> list[dict]:
    p = registry or REGISTRY
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []
