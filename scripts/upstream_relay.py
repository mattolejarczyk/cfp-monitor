"""A logged, scoped, cost-capped direct line to upstream (the Gemini research partner) - replaces copy and paste of notes (ACT-69).

    python scripts/upstream_relay.py ping
    python scripts/upstream_relay.py models
    python scripts/upstream_relay.py send --note FILE --kind id_request|fact_confirmation|question|troubleshoot
                                          [--provenance customer_awards-request|release-gate] [--operator-approved] [--dry-run]
    python scripts/upstream_relay.py journal verify

WHAT IT IS. Text in, text out, through the Gemini REST API (generateContent). NO Google Search, NO grounding, NO code execution, NO tools: the request body has no "tools" key.
The system prompt is a BRIEFING PACK built from repo files (the contract, upstream_commitments.csv, given_ids.csv, the last three notes to upstream) so a stateless API behaves as the
research partner under the contract. Not wired to any scheduled task: manual use only.

THE KEY IS A SECRET. It is read from the environment variable CFP_RELAY_GEMINI_KEY, falling back to the Windows USER environment (winreg; a process started before the variable was set does
not see it). It travels ONLY in the x-goog-api-key header, never in a URL. Its value is never printed, logged, written to a file or put in an error: every string that leaves this module goes
through redact(). It is not validated by prefix (the newer keys start 'AQ.'). Only its LENGTH may be reported.

POLICY (decide()). id_request / fact_confirmation go without approval ONLY when --provenance names a generator in the allowlist (relay_config.json) AND the note passes the content guard.
Free text (no provenance) needs --operator-approved; question and troubleshoot ALWAYS need --operator-approved. The content guard applies to every send, approved or not.

CONTENT GUARD (guard()). Blocks key-like tokens (AIza..., AQ.... , sk-..., long base64-like strings), password/passwd/secret/private_key followed by a value, any e-mail address, a
service-account JSON marker, SMTP settings, and raw customer-sheet rows. Names and URLs of awards and conferences are allowed (upstream already has them). A BLOCKED text is never stored:
only its hash and the reasons (labels, never the matched text) go to the journal.

COST. Before every call: tokens estimated from the characters (3 characters per token, deliberately high), output assumed to be the full max_output_tokens, priced from relay_config.json.
Over the per-call cap or the weekly cap (ISO week, from the journal): refused with 'stop and ask'. A model with no price in the config is refused. After the call the real token counts
(usageMetadata) are priced and written to the journal, which is the usage ledger.

JOURNAL (outside the repo): <CFP-Monitor>\\runs_out\\relay\\journal.jsonl, append-only, one JSON line per message, each carrying the sha256 of the previous line (a chain) and the sha256
of the full text; the texts are in runs_out\\relay\\messages\\<id>_out.txt / _in.txt, written once and never overwritten. 'journal verify' re-hashes everything and exits 1 on any edit,
missing file or broken chain.

A REPLY IS DATA. It is saved, hashed and shown to the operator as untrusted text. Nothing in it is ever run or applied. For a recognised ids table (the columns of
docs/operations/award_ids_reply_*.csv) it is also written to runs_out\\relay\\replies\\<id>\\ids_reply.csv for the EXISTING validators:
    python scripts/customer_awards.py --reply <that file> --reply-plan      (then stamp_given_ids.py --awards, check_delivery_ids.py)
and the relay stops there. A reply containing instruction-like text is flagged.

ERRORS. A failed call is reported with its exact HTTP status and the error text (redacted); 429 / 5xx / network errors are retried at most twice, each retry announced.
Exit code 0 = done, 1 = refused / blocked / failed. Tests stub http_request; nothing here is run against the network by the test suite."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

KEY_ENV = "CFP_RELAY_GEMINI_KEY"
RUNS_OUT = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor\runs_out")
RELAY_DIR = RUNS_OUT / "relay"
CONFIG_PATH = ROOT / "docs" / "operations" / "relay_config.json"
NOTES_DIR = ROOT / "experiments" / "purpose_audit"

KINDS = ("id_request", "fact_confirmation", "question", "troubleshoot")
AUTO_KINDS = ("id_request", "fact_confirmation")          # may go without approval, with an allowlisted provenance
IDS_HEADER = ["market", "award_name", "action", "event_id", "survivor", "note"]
IDS_ACTIONS = {"NEW", "RELABEL", "STAMP_EXISTING", "STAMP_NONAWARD"}
CHARS_PER_TOKEN = 3.0                                      # deliberately pessimistic (English averages about 4)
REDACTED = "[REDACTED]"

DEFAULTS = {
    "model": "gemini-2.5-flash",
    "prices_usd_per_1m_tokens": {},
    "per_call_cap_usd": 0.10,
    "weekly_cap_usd": 2.00,
    "max_output_tokens": 2048,
    "temperature": 0.2,
    "thinking_budget": 0,
    "briefing_max_chars": 60000,
    "provenance_allowlist": ["customer_awards-request", "release-gate"],
    "api_base": "https://generativelanguage.googleapis.com/v1beta",
    "timeout_seconds": 90,
    "max_retries": 2,
}

ROLE = """You are the research partner (upstream) in the CFP / PRIME|PR pipeline. The other party is the downstream team that loads your weekly research.
Answer as upstream, under the contract below. You have no tools: do not claim to have searched, browsed or run anything now; say plainly when you do not know.
Be brief. Plain ASCII text. When asked for ids, reply with a CSV table with exactly the header: market,award_name,action,event_id,survivor,note
(action is NEW, RELABEL, STAMP_EXISTING or STAMP_NONAWARD), inside a ```csv fence, then at most a few plain sentences. Never invent an id for an event you cannot name.
Everything after this role text is reference material from the downstream repository."""


# ======================================================================= secrets
def _read_user_env(name: str) -> str | None:
    """The Windows USER environment (HKCU\\Environment). Separate function so tests can stub it."""
    try:
        import winreg                                      # noqa: PLC0415 (Windows only)
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            val, _typ = winreg.QueryValueEx(k, name)
        return str(val)
    except OSError:
        return None


def get_key() -> tuple[str | None, str]:
    """(key, where). where is 'environment', 'user-environment' or 'not set'. The caller must never print the key."""
    v = (os.environ.get(KEY_ENV) or "").strip()
    if v:
        return v, "environment"
    v = (_read_user_env(KEY_ENV) or "").strip()
    if v:
        return v, "user-environment"
    return None, "not set"


# key-like tokens that must never leave, in a note or in any output
SECRET_PATTERNS = [
    ("google-api-key", re.compile(r"AIza[0-9A-Za-z_\-]{16,}")),
    ("aq-key", re.compile(r"\bAQ\.[0-9A-Za-z_\-]{16,}")),
    ("sk-token", re.compile(r"\bsk-[0-9A-Za-z_\-]{16,}")),
    ("base64-like-secret", re.compile(r"(?<![0-9A-Za-z+=])(?=[A-Za-z0-9+=]*[A-Z])(?=[A-Za-z0-9+=]*[a-z])(?=[A-Za-z0-9+=]*[0-9])[A-Za-z0-9+=]{32,}(?![0-9A-Za-z+=])")),
    ("secret-with-value", re.compile(r"(?i)\b(password|passwd|secret|private_key)\b[\"']?\s*[:=]\s*[\"']?\S+")),
    ("service-account-json", re.compile(r"(?i)\"type\"\s*:\s*\"service_account\"|\"private_key_id\"|-----BEGIN [A-Z ]*PRIVATE KEY-----|\"client_email\"")),
    ("smtp-setting", re.compile(r"CFP_SMTP_|CFP_RELAY_GEMINI_KEY")),
]
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+")
CUSTOMER_HEADERS = ("PRIORITY", "STATUS", "SUBMISSION DEADLINE", "CONFERENCE URL", "EVENT START DATE", "LOCATION", "CONFERENCE")
PRIORITY_VALUES = {"p1", "p2", "p3", "1", "2", "3", "high", "medium", "low", "critical"}
STATUS_VALUES = {"accepted", "declined", "pending", "submitted", "open", "closed", "won", "lost", "applied", "considering", "in progress", "not started", "rejected", "no"}


def say(text: str) -> None:
    """Every line this tool prints goes through here, so the key cannot reach the console."""
    print(redact(text))


def redact(text: str, key: str | None = None) -> str:
    """Remove the key (if known) and anything key-shaped from a string that is about to leave this module."""
    if not isinstance(text, str):
        text = str(text)
    if key is None:
        key = get_key()[0]
    if key and len(key) >= 8:
        text = text.replace(key, REDACTED)
    for _label, rx in SECRET_PATTERNS[:3]:
        text = rx.sub(REDACTED, text)
    return text


def _split_fields(line: str) -> list[str]:
    for d in ("\t", "|", ";", ","):
        if line.count(d) >= 5:
            return [f.strip() for f in line.split(d)]
    return []


def _customer_row_lines(text: str) -> int:
    n = 0
    for line in text.splitlines():
        f = _split_fields(line)
        if len(f) <= 5:
            continue
        up = line.upper()
        if sum(1 for h in CUSTOMER_HEADERS if h in up) >= 3 and "PRIORITY" in up and "STATUS" in up:
            n += 1                                           # the sheet's header row
            continue
        low = [x.strip().strip('"').lower() for x in f]
        if any(x in PRIORITY_VALUES for x in low) and any(x in STATUS_VALUES for x in low) and len(f) >= 7:
            n += 1                                           # a data row: a priority and a status among 7+ columns
    return n


def guard(text: str, secrets_only: bool = False) -> list[str]:
    """Labels of every reason this text must not leave (never the matched text itself). Empty list = clean."""
    hits = []
    for label, rx in SECRET_PATTERNS:
        if rx.search(text):
            hits.append(label)
    k = get_key()[0]
    if k and len(k) >= 8 and k in text:
        hits.append("the-relay-key-itself")
    if secrets_only:
        return hits
    if EMAIL_RE.search(text):
        hits.append("email-address")
    if _customer_row_lines(text):
        hits.append("customer-sheet-rows")
    return hits


INSTRUCTION_RE = re.compile(r"(?i)(ignore (all |any )?(previous|prior|above)|disregard|you (must|should) (now )?(run|execute|delete|apply|send)|"
                            r"\b(run|execute) (the following|this|these)|```\s*(powershell|bash|sh|cmd|python)\b|\bcurl\b|\brm -|\bdel /|Remove-Item|\bsudo\b)")


def looks_like_instructions(text: str) -> bool:
    return bool(INSTRUCTION_RE.search(text))


# ======================================================================= config
def load_config(path: Path | None = None) -> dict:
    p = Path(path or CONFIG_PATH)
    cfg = dict(DEFAULTS)
    if p.exists():
        cfg.update(json.loads(p.read_text(encoding="utf-8")))
    return cfg


def save_model(model: str, path: Path | None = None) -> None:
    """Rewrite only the 'model' value (keeps the comments and everything else as written)."""
    p = Path(path or CONFIG_PATH)
    raw = p.read_text(encoding="utf-8")
    new, n = re.subn(r'("model"\s*:\s*)"[^"]*"', lambda m: f'{m.group(1)}"{model}"', raw, count=1)
    if n != 1:
        raise RuntimeError("relay_config.json has no \"model\" entry to update")
    p.write_text(new, encoding="utf-8")


# ======================================================================= HTTP
def http_request(method: str, url: str, headers: dict, body: bytes | None, timeout: float) -> tuple[int, str]:
    """(status, text). A non-2xx answer is RETURNED, not raised; a network failure raises OSError. Tests replace this function."""
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:                  # noqa: S310 (fixed https endpoint from the config)
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        raise OSError(str(e.reason)) from None


def sleep(seconds: float) -> None:
    time.sleep(seconds)


class RelayError(Exception):
    """Carries a message that is already redacted."""


def call_api(method: str, path: str, cfg: dict, key: str, payload: dict | None = None) -> dict:
    """One Gemini REST call with the key in the header only. Retries 429 / 5xx / network errors at most cfg.max_retries times, each announced."""
    url = cfg["api_base"].rstrip("/") + "/" + path.lstrip("/")
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    attempts = 1 + int(cfg["max_retries"])
    last = ""
    for n in range(1, attempts + 1):
        try:
            status, text = http_request(method, url, headers, body, float(cfg["timeout_seconds"]))
        except OSError as e:
            status, text = 0, f"network error: {e}"
        if 200 <= status < 300:
            try:
                return json.loads(text)
            except ValueError:
                raise RelayError(f"HTTP {status} but the body is not JSON: {redact(text, key)[:300]}") from None
        last = f"HTTP {status}: {redact(text, key).strip()[:600]}" if status else redact(text, key)
        if (status == 429 or status >= 500 or status == 0) and n < attempts:
            wait = 2 ** n
            say(f"retry {n} of {attempts - 1} in {wait}s after {last[:120]}")
            sleep(wait)
            continue
        break
    raise RelayError(last)


# ======================================================================= prices and cost
def est_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN) + 1


def price_of(cfg: dict) -> tuple[float, float]:
    p = (cfg.get("prices_usd_per_1m_tokens") or {}).get(cfg["model"])
    if not p:
        raise RelayError(f"no price for model {cfg['model']!r} in relay_config.json: the operator adds it from https://ai.google.dev/gemini-api/docs/pricing; stop and ask")
    return float(p["input"]), float(p["output"])


def cost_usd(tokens_in: int, tokens_out: int, cfg: dict) -> float:
    pi, po = price_of(cfg)
    return (tokens_in * pi + tokens_out * po) / 1_000_000


def estimate(system: str, user: str, cfg: dict) -> dict:
    t_in = est_tokens(system) + est_tokens(user)
    t_out = int(cfg["max_output_tokens"]) + int(cfg.get("thinking_budget") or 0)
    return {"tokens_in": t_in, "tokens_out": t_out, "cost_usd": round(cost_usd(t_in, t_out, cfg), 6)}


# ======================================================================= journal
def journal_path() -> Path:
    return RELAY_DIR / "journal.jsonl"


def messages_dir() -> Path:
    return RELAY_DIR / "messages"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_journal() -> list[dict]:
    p = journal_path()
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def append_journal(entry: dict) -> dict:
    """Append one line, chained to the previous line's hash. Never rewrites the file."""
    p = journal_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    prev = ""
    if p.exists():
        lines = [x for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
        if lines:
            prev = sha(lines[-1])
    entry = dict(entry, prev=prev)
    with open(p, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def store_message(call_id: str, suffix: str, text: str) -> str:
    """Write once (exclusive create): a stored text is never overwritten. Returns the file name relative to messages/."""
    d = messages_dir()
    d.mkdir(parents=True, exist_ok=True)
    name = f"{call_id}_{suffix}.txt"
    with open(d / name, "x", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return name


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def week_of(ts: str) -> str:
    y, w, _ = datetime.fromisoformat(ts).isocalendar()
    return f"{y}-W{w:02d}"


def week_spend(now: datetime | None = None) -> float:
    wk = week_of((now or now_utc()).isoformat())
    return round(sum(float(e.get("cost_usd") or 0) for e in read_journal() if e.get("direction") == "in" and week_of(e["utc"]) == wk), 6)


def verify_journal() -> tuple[bool, list[str]]:
    """Re-hash the chain and every stored text. (ok, problems)."""
    problems = []
    p = journal_path()
    if not p.exists():
        return True, ["(no journal yet: nothing to verify)"]
    lines = [x for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    prev = ""
    referenced = set()
    for n, line in enumerate(lines, 1):
        try:
            e = json.loads(line)
        except ValueError:
            problems.append(f"line {n}: not valid JSON")
            prev = sha(line)
            continue
        if e.get("prev") != prev:
            problems.append(f"line {n} ({e.get('id')}): the chain is broken - an earlier line was edited, removed or inserted")
        prev = sha(line)
        f = e.get("file")
        if f:
            referenced.add(f)
            fp = messages_dir() / f
            if not fp.exists():
                problems.append(f"line {n} ({e.get('id')}): stored text {f} is missing")
            elif sha(fp.read_bytes().decode("utf-8")) != e.get("sha256"):
                problems.append(f"line {n} ({e.get('id')}): stored text {f} no longer matches its recorded sha256 (edited)")
    if messages_dir().exists():
        for fp in sorted(messages_dir().iterdir()):
            if fp.name not in referenced:
                problems.append(f"{fp.name}: a stored text with no journal line")
    return (not problems), problems


# ======================================================================= briefing pack
def _tail(text: str, n: int) -> str:
    return text if len(text) <= n else "[...earlier part omitted...]\n" + text[-n:]


def _head(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "\n[...rest omitted...]"


def _note_number(p: Path) -> int:
    m = re.search(r"NOTE-TO-UPSTREAM-(\d+)", p.name)
    return int(m.group(1)) if m else -1


def build_briefing(cfg: dict, root: Path | None = None, notes_dir: Path | None = None) -> str:
    """The system prompt: role + contract + commitments + given ids + the last three notes, capped to briefing_max_chars. Pure reading of repo files."""
    root = Path(root or ROOT)
    cap = int(cfg["briefing_max_chars"])

    def read(rel: str) -> str:
        p = root / rel
        return p.read_text(encoding="utf-8", errors="replace") if p.exists() else f"(missing: {rel})"

    nd = Path(notes_dir or (root / "experiments" / "purpose_audit"))
    notes = sorted(nd.glob("NOTE-TO-UPSTREAM-*.md"), key=_note_number)[-3:] if nd.exists() else []
    budget = max(cap - len(ROLE) - 400, 1000)
    parts = [("THE CONTRACT (pipeline-contract.md)", _head(read("docs/operations/pipeline-contract.md"), int(budget * 0.45))),
             ("PROMISES UPSTREAM HAS MADE (upstream_commitments.csv)", _head(read("docs/operations/upstream_commitments.csv"), int(budget * 0.10))),
             ("IDS UPSTREAM HAS GIVEN US (given_ids.csv, newest last)", _tail(read("docs/operations/given_ids.csv"), int(budget * 0.10)))]
    each = int(budget * 0.35 / max(len(notes), 1))
    for n in notes:
        parts.append((f"EARLIER NOTE {n.name}", _head(n.read_text(encoding="utf-8", errors="replace"), each)))
    out = [ROLE]
    for title, body in parts:
        out.append(f"\n\n===== {title} =====\n{body}")
    return _head("".join(out), cap)


# ======================================================================= reply handling
def parse_ids_reply(text: str) -> list[dict] | None:
    """Rows of a recognised ids table (header exactly IDS_HEADER, actions known), else None. Pure parsing: nothing is applied."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if [c.strip().lower() for c in ln.split(",")] == IDS_HEADER:
            start = i
            break
    if start is None:
        return None
    block = []
    for ln in lines[start:]:
        if not ln.strip() or ln.strip().startswith("```"):
            break
        block.append(ln)
    rows = list(csv.DictReader(io.StringIO("\n".join(block)), fieldnames=IDS_HEADER))[1:]
    rows = [{k: (v or "").strip() for k, v in r.items() if k in IDS_HEADER} for r in rows]
    if not rows or any(r["action"] not in IDS_ACTIONS or not r["award_name"] or not r["market"] for r in rows):
        return None
    return rows


def write_ids_reply(call_id: str, rows: list[dict]) -> Path:
    d = RELAY_DIR / "replies" / call_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / "ids_reply.csv"
    with open(p, "x", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=IDS_HEADER, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return p


def ascii_fold(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


# ======================================================================= the exchange
def new_id() -> str:
    return f"{now_utc():%Y%m%dT%H%M%SZ}-{secrets.token_hex(2)}"


def decide(kind: str, provenance: str, approved: bool, cfg: dict) -> tuple[bool, str]:
    """(allowed, reason). The content guard is separate and applies to every send."""
    if kind in AUTO_KINDS:
        if provenance and provenance in cfg["provenance_allowlist"]:
            return True, f"kind {kind} with allowlisted provenance {provenance}"
        if approved:
            return True, f"kind {kind} approved by the operator (provenance {provenance or 'none'})"
        return False, (f"kind {kind} without an allowlisted --provenance ({', '.join(cfg['provenance_allowlist'])}) is free text: it needs --operator-approved")
    if approved:
        return True, f"kind {kind} approved by the operator"
    return False, f"kind {kind} always needs --operator-approved"


def _generate(cfg: dict, key: str, system: str | None, user: str) -> dict:
    gen = {"temperature": float(cfg["temperature"]), "maxOutputTokens": int(cfg["max_output_tokens"]), "responseMimeType": "text/plain"}
    if cfg.get("thinking_budget") is not None:
        gen["thinkingConfig"] = {"thinkingBudget": int(cfg["thinking_budget"])}
    body = {"contents": [{"role": "user", "parts": [{"text": user}]}], "generationConfig": gen}      # no "tools": no search, no grounding, no code execution
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    return call_api("POST", f"models/{cfg['model']}:generateContent", cfg, key, body)


def reply_text(resp: dict) -> str:
    cands = resp.get("candidates") or []
    if not cands:
        fb = resp.get("promptFeedback") or {}
        raise RelayError(f"the API returned no candidate (promptFeedback: {json.dumps(fb)[:300]})")
    parts = (cands[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts if isinstance(p, dict))


def exchange(kind: str, user: str, system: str | None, provenance: str, cfg: dict, dry_run: bool, out=say) -> int:
    """Guard (done by the caller) -> cost check -> journal out -> call -> journal in. Returns the exit code."""
    cid = new_id()
    key, where = get_key()
    est = estimate(system or "", user, cfg)
    base = {"id": cid, "utc": now_utc().isoformat(), "kind": kind, "provenance": provenance or "", "model": cfg["model"]}
    spent = week_spend()
    refuse = None
    if est["cost_usd"] > float(cfg["per_call_cap_usd"]):
        refuse = f"estimated {est['cost_usd']:.4f} USD is over the per-call cap {float(cfg['per_call_cap_usd']):.2f} USD"
    elif spent + est["cost_usd"] > float(cfg["weekly_cap_usd"]):
        refuse = f"this week's relay spend {spent:.4f} USD plus the estimate {est['cost_usd']:.4f} USD is over the weekly cap {float(cfg['weekly_cap_usd']):.2f} USD"
    out(f"estimate: ~{est['tokens_in']} tokens in, up to {est['tokens_out']} out, up to {est['cost_usd']:.4f} USD (week so far {spent:.4f} of {float(cfg['weekly_cap_usd']):.2f} USD)")
    if refuse:
        append_journal(dict(base, direction="out", sha256=sha(user), chars=len(user), tokens_in=est["tokens_in"], est_cost_usd=est["cost_usd"], decision="blocked", reason="cost cap: " + refuse))
        out(f"REFUSED - {refuse}. Stop and ask the operator.")
        return 1
    if dry_run:
        name = store_message(cid, "dryrun", f"[DRY RUN - not sent]\nmodel: {cfg['model']}\nkind: {kind}\nprovenance: {provenance or '-'}\n\n"
                                            f"--- SYSTEM PROMPT ({len(system or '')} chars) ---\n{system or '(none)'}\n\n--- MESSAGE ---\n{user}\n")
        full = (messages_dir() / name).read_text(encoding="utf-8")
        append_journal(dict(base, direction="out", sha256=sha(full), chars=len(full), file=name, tokens_in=est["tokens_in"], est_cost_usd=est["cost_usd"], decision="dry-run", reason="no network call"))
        out(f"DRY RUN: nothing sent. Would-be message written to {messages_dir() / name}")
        return 0
    if not key:
        append_journal(dict(base, direction="out", sha256=sha(user), chars=len(user), decision="blocked", reason=f"key {KEY_ENV} is not set (environment or user environment)"))
        out(f"REFUSED - {KEY_ENV} is not set in the environment or the Windows user environment.")
        return 1
    name = store_message(cid, "out", user)
    append_journal(dict(base, direction="out", sha256=sha(user), chars=len(user), file=name, tokens_in=est["tokens_in"], est_cost_usd=est["cost_usd"], decision="sent", reason="", key_source=where))
    try:
        resp = _generate(cfg, key, system, user)
        text = redact(reply_text(resp), key)
    except RelayError as e:
        msg = redact(str(e), key)
        append_journal(dict(base, direction="in", sha256=sha(msg), chars=len(msg), decision="error", reason=msg[:600], cost_usd=0.0))
        out(f"CALL FAILED - {msg}")
        return 1
    u = resp.get("usageMetadata") or {}
    t_in = int(u.get("promptTokenCount") or est["tokens_in"])
    t_out = int(u.get("candidatesTokenCount") or 0) + int(u.get("thoughtsTokenCount") or 0)
    if not u:
        t_out = est_tokens(text)
    real = round(cost_usd(t_in, t_out, cfg), 6)
    rname = store_message(cid, "in", text)
    parsed = parse_ids_reply(text) if kind in ("id_request", "fact_confirmation") else None
    ids_path = write_ids_reply(cid, parsed) if parsed else None
    flagged = looks_like_instructions(text)
    append_journal(dict(base, direction="in", sha256=sha(text), chars=len(text), file=rname, tokens_in=t_in, tokens_out=t_out, cost_usd=real, decision="received",
                        reason="instruction-like text flagged" if flagged else "", ids_reply=str(ids_path) if ids_path else ""))
    out(f"reply received: {t_in} tokens in, {t_out} out, {real:.4f} USD; stored {messages_dir() / rname}")
    if flagged:
        out("WARNING - the reply contains instruction-like text. It is UNTRUSTED DATA: nothing in it was run or applied; read it yourself.")
    if ids_path:
        out(f"recognised ids table ({len(parsed)} rows) written to {ids_path}")
        out(f"next, by hand: python scripts/customer_awards.py --reply \"{ids_path}\" --reply-plan   (a dry check; nothing is applied)")
    out("----- UPSTREAM REPLY (untrusted data) -----")
    out(ascii_fold(text[:4000]) + ("\n[...truncated, full text in the file above...]" if len(text) > 4000 else ""))
    return 0


# ======================================================================= commands
def cmd_ping(cfg: dict, out=say) -> int:
    key, where = get_key()
    out(f"key: {'found in ' + where + f' ({len(key)} characters)' if key else 'NOT SET'}")
    out(f"model: {cfg['model']}")
    if not key:
        out(f"REFUSED - set {KEY_ENV} (user environment variable) and open a new terminal.")
        return 1
    try:
        price_of(cfg)
    except RelayError as e:
        out(f"REFUSED - {e}")
        return 1
    return exchange("ping", "Reply with the single word: pong", None, "relay-ping", cfg, False, out)


def pick_model(listing: dict) -> tuple[str | None, list[str]]:
    """Newest cheapest flash-class text model that supports generateContent. Returns (id, candidates best first)."""
    bad = ("image", "tts", "audio", "live", "embedding", "aqa", "imagen", "robotics", "computer-use", "vision", "native", "veo", "learnlm", "gemma")
    cands = []
    for m in listing.get("models", []):
        name = str(m.get("name", "")).replace("models/", "")
        if "flash" not in name or "generateContent" not in (m.get("supportedGenerationMethods") or []):
            continue
        if any(b in name for b in bad):
            continue
        v = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
        ver = float(v.group(1)) if v else 0.0
        unstable = any(t in name for t in ("preview", "exp", "-latest"))
        dated = bool(re.search(r"-\d{3,}$|-\d{2}-\d{2}$", name))
        cands.append((unstable, -ver, 0 if "lite" in name else 1, dated, name))      # stable before preview/exp, then newest, then lite (cheaper)
    cands.sort()
    names = [c[-1] for c in cands]
    return (names[0] if names else None), names


def cmd_models(cfg: dict, out=say) -> int:
    key, where = get_key()
    if not key:
        out(f"REFUSED - {KEY_ENV} is not set.")
        return 1
    try:
        listing = call_api("GET", "models?pageSize=200", cfg, key)
    except RelayError as e:
        out(f"CALL FAILED - {redact(str(e), key)}")
        return 1
    best, names = pick_model(listing)
    out(f"{len(names)} usable flash-class text model(s): " + ", ".join(names[:12]))
    if not best:
        out("no usable model found; relay_config.json unchanged")
        return 1
    if best != cfg["model"]:
        save_model(best)
        out(f"model set to {best} in relay_config.json (was {cfg['model']})")
    else:
        out(f"model {best} already set")
    cfg = load_config()
    if best not in (cfg.get("prices_usd_per_1m_tokens") or {}):
        out(f"NOTE - relay_config.json has no price for {best}: send and ping will refuse until the operator adds it (prices at https://ai.google.dev/gemini-api/docs/pricing)")
    return 0


def cmd_send(a, cfg: dict, out=say) -> int:
    note = Path(a.note)
    if not note.exists():
        out(f"REFUSED - note file not found: {note}")
        return 1
    user = note.read_text(encoding="utf-8", errors="replace")
    h = sha(user)
    cid_base = {"id": new_id(), "utc": now_utc().isoformat(), "kind": a.kind, "provenance": a.provenance or "", "model": cfg["model"], "direction": "out", "sha256": h, "chars": len(user)}
    ok, why = decide(a.kind, a.provenance or "", a.operator_approved, cfg)
    if not ok:
        append_journal(dict(cid_base, decision="blocked", reason="policy: " + why))
        out(f"REFUSED - {why}.")
        return 1
    hits = guard(user)
    if hits:
        append_journal(dict(cid_base, decision="blocked", reason="content guard: " + ", ".join(hits)))
        out(f"BLOCKED by the content guard: {', '.join(hits)}. The text was not stored or sent. Edit the note (operator approval does not override the guard).")
        return 1
    system = build_briefing(cfg)
    bhits = guard(system, secrets_only=True)
    if bhits:
        append_journal(dict(cid_base, decision="blocked", reason="content guard on the briefing pack: " + ", ".join(bhits)))
        out(f"BLOCKED - the briefing pack built from repo files trips the content guard ({', '.join(bhits)}). Nothing sent.")
        return 1
    out(f"policy: {why}; content guard: clean; briefing pack {len(system)} chars (sha256 {sha(system)[:12]})")
    try:
        price_of(cfg)
    except RelayError as e:
        append_journal(dict(cid_base, decision="blocked", reason=str(e)[:300]))
        out(f"REFUSED - {e}")
        return 1
    return exchange(a.kind, user, system, a.provenance or "", cfg, a.dry_run, out)


def cmd_journal_verify(out=say) -> int:
    ok, problems = verify_journal()
    n = len(read_journal()) if journal_path().exists() else 0
    for p in problems:
        out(("PROBLEM - " if not ok else "") + p)
    out(f"JOURNAL VERIFY: {'OK' if ok else 'FAILED'} - {n} line(s) checked")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Logged, scoped, cost-capped relay to upstream (Gemini). See the module docstring.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping", help="tiny prompt: proves the line; prints model, tokens, estimated cost")
    sub.add_parser("models", help="list usable models and store the newest cheapest flash text model in relay_config.json")
    s = sub.add_parser("send", help="send a note file to upstream")
    s.add_argument("--note", required=True)
    s.add_argument("--kind", required=True, choices=KINDS)
    s.add_argument("--provenance", default="", help="the generator that wrote the note (allowlist in relay_config.json); empty = free text")
    s.add_argument("--operator-approved", action="store_true", help="the operator has read this exact note and approves sending it")
    s.add_argument("--dry-run", action="store_true", help="everything except the network call; writes the would-be message and the estimate")
    j = sub.add_parser("journal", help="journal commands")
    j.add_argument("action", choices=["verify"])
    a = ap.parse_args(argv)
    cfg = load_config()
    if a.cmd == "ping":
        return cmd_ping(cfg)
    if a.cmd == "models":
        return cmd_models(cfg)
    if a.cmd == "send":
        return cmd_send(a, cfg)
    return cmd_journal_verify()


if __name__ == "__main__":
    sys.exit(main())
