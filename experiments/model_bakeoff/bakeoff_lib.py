"""ACT-56 model bake-off: shared logic. Roles: (1) page READER, (2) SECOND OPINION.

NEW CODE: searched TOOLING.md for "model comparison / bake-off / codex wrapper" - found nothing. Reused: experiments/read_the_page_pass (pass_lib.SYSTEM, user_message, accept, gold_facts,
score), experiments/finder_reader_test (SYSTEM, accept_deadline), scripts/pinned_rows.load_pins and scripts/answer_key (person-confirmed tier). This file only adds the provider
wrappers (OpenRouter, Codex CLI), the BLIND request builder, the usage logs and the second-opinion comparison.

INDEPENDENCE (operator rule, 2026-10-06; see RESULTS.md 'Independence'):
  * blind_messages() is the ONLY place a request is built: one system message + one user message (event, edition, page text). It takes no gold value, no earlier answer and no
    other model's output as input, and assert_blind() refuses a request whose header carries a digit other than the edition year.
  * Every call is a fresh single-turn request: openrouter_ask() posts one request with no history; codex_ask() starts a new `codex exec --ephemeral` in an EMPTY scratch directory with a
    read-only sandbox, never `resume`.
  * Scoring against the answer key (pass_lib.score / same) and the second-opinion comparison (second_opinion()) happen in code AFTER all calls, from saved answers.
Nothing here writes to the database, the pipeline or any customer file."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import hashlib
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.read_the_page_pass import pass_lib as L          # noqa: E402

OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
LOG = HERE / "llm_log.jsonl"          # every OpenRouter call: model, seconds, cost, status
CODEX_LOG = HERE / "codex_usage.jsonl"  # every Codex call: model, seconds, tokens used, exit status
MAX_USD_RUN, MAX_USD_TOTAL = 0.30, 1.00

CONFIG = HERE / "models.json"         # ONE place that defines a model: id, route, effort, price source and date. Adding a model = adding an entry; no code change.
REGISTRY = HERE / "registry.jsonl"    # append-only: one row per (call, fact). Never rewritten.
PAGE_DIR = HERE / "pages"             # saved page text (sha256-named) so any row can be replayed


def load_models(path: Path = CONFIG) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))["models"]


# ------------------------------------------------------------------ the blind request
def blind_messages(system: str, event: str, edition: str, page_text: str, cap: int = 12000) -> list[dict]:
    """The one and only request shape: system + user, nothing else. No gold, no earlier answer, no other model's output."""
    user = f"EVENT: {event}\nEDITION YEAR TO REPORT: {edition}\n\nPAGE TEXT:\n{page_text[:cap]}"
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    assert_blind(msgs, edition)
    return msgs


def assert_blind(msgs: list[dict], edition: str) -> None:
    if [m["role"] for m in msgs] != ["system", "user"]:
        raise ValueError("a request must be exactly one system and one user message")
    header = msgs[1]["content"].split("PAGE TEXT:", 1)[0]
    leak = re.findall(r"\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{2,4}", header)      # an event NAME may carry a year ('Nullcon Goa 2027'); a full date would be a leaked answer
    if leak:
        raise ValueError(f"request header carries a date: {leak}")


# ------------------------------------------------------------------ providers
def _parse(out: str) -> dict:
    try:
        return json.loads(out)
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", out or "", re.S)
        try:
            return json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            return {}


def spent_usd() -> float:
    if not LOG.exists():
        return 0.0
    return sum((json.loads(x).get("cost_usd") or 0.0) for x in LOG.read_text(encoding="utf-8").splitlines() if x.strip())


def openrouter_ask(model_id: str, msgs: list[dict], tag: str, max_tokens: int = 3000, run_usd: list | None = None, effort: str = "low") -> dict:
    """One fresh single-turn call. Returns {parsed, raw, cost, seconds, status, error}. A 429 or server error is a FAILED CALL (parsed None), never a blank answer."""
    import httpx
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY missing")                       # never printed
    body = {"model": model_id, "messages": msgs, "temperature": 0, "max_tokens": max_tokens, "usage": {"include": True},
            "reasoning": {"effort": effort}}                                  # default low = the setting the baseline runner uses (run.py SP_EXTRA)
    last = {"parsed": None, "raw": "", "cost": 0.0, "seconds": 0.0, "status": None, "error": "no attempt"}
    for attempt, pause in enumerate((0, 8, 20)):
        if spent_usd() >= MAX_USD_TOTAL or (run_usd is not None and run_usd[0] >= MAX_USD_RUN):
            last["error"] = "budget cap reached"
            return last
        if pause:
            time.sleep(pause)
        if attempt == 1 and "response_format" not in body:
            body["response_format"] = {"type": "json_object"}
        t0 = time.time()
        try:
            r = httpx.post(OPENROUTER, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=body, timeout=120)
        except Exception as e:                                                # noqa: BLE001
            last = {"parsed": None, "raw": "", "cost": 0.0, "seconds": round(time.time() - t0, 1), "status": None, "error": f"exception {type(e).__name__}"}
            continue
        secs = round(time.time() - t0, 1)
        j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        cost = (j.get("usage") or {}).get("cost") or 0.0
        if run_usd is not None:
            run_usd[0] += cost
        rec = {"ts": date.today().isoformat(), "model": model_id, "tag": tag, "seconds": secs, "cost_usd": cost, "usage": j.get("usage"), "status": r.status_code, "attempt": attempt}
        if r.status_code != 200:
            rec["error"] = str(j.get("error", ""))[:300]
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        if r.status_code == 200 and j.get("choices"):
            raw = j["choices"][0]["message"].get("content") or ""
            u = j.get("usage") or {}
            return {"parsed": _parse(raw), "raw": raw, "cost": cost, "seconds": secs, "status": 200, "error": "", "tokens_in": u.get("prompt_tokens"), "tokens_out": u.get("completion_tokens")}
        last = {"parsed": None, "raw": "", "cost": cost, "seconds": secs, "status": r.status_code, "error": rec.get("error", "")}
        if r.status_code in (400, 401, 402, 403, 404):                        # not a transient failure: stop, record the text
            if r.status_code == 400 and attempt == 0:
                body.pop("reasoning", None)                                    # a model that rejects the reasoning option: retry once without it, and say so in the log
                rec2 = dict(rec, note="retried without reasoning option")
                with open(LOG, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec2) + "\n")
                continue
            break
    return last


class CodexError(RuntimeError):
    """Carries the EXACT text Codex printed. The operator requires it verbatim."""


def codex_ask(model: str, msgs: list[dict], tag: str, effort: str = "max", timeout: int = 600) -> dict:
    """One fresh `codex exec` (never resumed, --ephemeral) in an empty scratch directory, read-only sandbox, prompt on stdin. Raises CodexError with the exact output on any failure:
    the caller must STOP, not retry in a loop."""
    prompt = (msgs[0]["content"] + "\n\n" + msgs[1]["content"] +
              "\n\nAnswer with the JSON object only. Do not run any commands or read any files; use only the page text above.")
    with tempfile.TemporaryDirectory(prefix="codex_blind_") as scratch:
        out_file = Path(scratch) / "last.txt"
        cmd = ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "-C", scratch, "-m", model,
               "-c", f"model_reasoning_effort={effort}", "-o", str(out_file), "-"]
        t0 = time.time()
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, shell=(os.name == "nt"))
        secs = round(time.time() - t0, 1)
        combined = (p.stdout or "") + "\n" + (p.stderr or "")
        tokens = None
        m = re.search(r"tokens used\D{0,20}([\d,]+)", combined, re.I)
        if m:
            tokens = int(m.group(1).replace(",", ""))
        last = out_file.read_text(encoding="utf-8", errors="replace") if out_file.exists() else ""
        rec = {"ts": date.today().isoformat(), "model": model, "effort": effort, "tag": tag, "seconds": secs, "tokens_used": tokens, "returncode": p.returncode}
        if p.returncode != 0 or not last.strip():
            rec["error"] = combined.strip()[-1500:]
            with open(CODEX_LOG, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
            raise CodexError(combined.strip()[-3000:] or f"codex exited {p.returncode} with no output")
        with open(CODEX_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    return {"parsed": _parse(last), "raw": last, "cost": 0.0, "seconds": secs, "status": 200, "error": "", "tokens": tokens}


def ask(model_key: str, msgs: list[dict], tag: str, run_usd: list | None = None) -> dict:
    cfg = load_models()[model_key]
    if cfg["route"] == "openrouter":
        return openrouter_ask(cfg["id"], msgs, tag, run_usd=run_usd, effort=cfg.get("effort", "low"))
    return codex_ask(cfg["id"], msgs, tag, effort=cfg.get("effort", "max"))


# ------------------------------------------------------------------ jobs and scoring
def edition_of(canonical: str) -> str:
    m = re.match(r"(20\d\d)-", canonical)
    return m.group(1) if m else ""


def score_item(job: dict, field: str, gold: str, answer: dict | None) -> dict:
    """Code decides: the same acceptance rules as the production reader. answer None = the call failed (not scored)."""
    if answer is None:
        return {"event": job["event"], "field": field, "gold": gold, "accepted": "", "why": "CALL FAILED", "call_failed": True, "tier": "person-confirmed"}
    if job["kind"] == "deadline":
        from experiments.finder_reader_test.run import accept_deadline
        got, why = accept_deadline(answer.get("deadline", {}), job["text"], date.today().isoformat())
    else:
        got, why = L.accept(field, answer.get(field, {}), job["text"], job["edition"])
    return {"event": job["event"], "field": field, "gold": gold, "accepted": got, "why": why, "call_failed": False, "tier": "person-confirmed"}


def person_confirmed_events() -> set[str]:
    from scripts.answer_key import reader_key
    return {r["canonical"] for r in reader_key() if r.get("canonical")}
