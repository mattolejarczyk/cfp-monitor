"""SHADOW SECOND READER (ACT-61, 2026-10-06): GPT-6 Luna (effort max, Codex CLI on the operator's ChatGPT subscription) reads the same non-deadline facts as scripts/shadow_reader.py
from the same pages, and the two answers are set against each other and against the database. It changes NOTHING.

    python scripts/luna_shadow.py [--markets Cybersecurity Utility] [--token-budget 1500000] [--max-minutes 45] [--limit N] [--run-log <weekend log>]

WHAT IT DOES. For the live rows of the approved files (the same filter as shadow_reader.select_rows) it asks Luna, one fresh blind `codex exec --ephemeral` per event (bakeoff_lib.blind_messages and
codex_ask: only the event, the edition year and the page text; never another model's answer, the database value or any key), for start date, city, country, venue, organizer and format. Luna's
answers pass the PRODUCTION proof rule exactly (pass_lib.accept: the quote is literally on the page, a date states day, month and the edition's year, the merged German label rule). Then, in code:
  agree / disagree   both readers have a proven value: equal, or not
  Luna-only          Luna proved a value, the existing reader proved none
  reader-only        the existing reader proved a value, Luna proved none
The existing reader's answers are read from its newest runs_out/shadow/shadow_reader_*.json (an event it did not read has no answer: it is counted separately, never as reader-only). The database
value is looked up through identity.to_canonical (never a join on the upstream id) in grounding_facts, opened read-only (venue and format have no database column).

ORDER (a partial run is still useful): customer-linked rows first, then rows starting in the next 60 days, then the rest; inside a tier rows the existing reader answered first, then soonest start.

OUTPUT. (a) runs_out/qa/<date>/luna_shadow.md: every DISAGREEMENT (event, fact, both answers, both quotes), Luna-only and reader-only facts, Luna against the database, and the stop reason;
(b) rows appended to experiments/model_bakeoff/registry.jsonl (append-only, model_key 'luna-shadow', role 'shadow', key_value blank, plus db_value and reader_value); (c) the summary line
    LUNA SHADOW: n facts read, agree a, disagree d, Luna-only found f, reader-only found r, tokens t (budget b)
n is the number of facts Luna was asked about in the calls that finished (6 per event); a, d, f, r count the facts of events the existing reader also answered.

GUARANTEES. Never opens the database for writing, never edits an approved file, a pin or a page. Writes only the report and the registry (plus the wrapper's own Codex usage log). TOKEN BUDGET
(--token-budget, default 1,500,000, the tokens the Codex wrapper reports per call): it stops BEFORE a call that the average call so far says would pass it, and says so. --max-minutes (default 45)
and --run-log/--total-hours work as in shadow_reader. ANY Codex error (limit, auth, model, timeout, missing binary) stops the run at once, the EXACT text goes in the report and in
'LUNA SHADOW: stopped - <text>'; no retry loop; NEVER a fallback to OpenRouter. Skipped with 'LUNA SHADOW: skipped - codex not signed in' when `codex login status` says so. Always exits 0.
Public page text only; the customer sheets are used only to know WHICH events are customer-linked (their canonical ids), never their content."""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from scripts import shadow_reader as SR                                   # noqa: E402  (also puts the experiments folders on the path)
from experiments.model_bakeoff import bakeoff_lib as B                    # noqa: E402
from experiments.model_bakeoff import registry as REG                     # noqa: E402
from experiments.read_the_page_pass import pass_lib as L                  # noqa: E402
from src.cfp_monitor import identity, qa_report                           # noqa: E402

MODEL_KEY = "luna"                       # the entry in experiments/model_bakeoff/models.json (gpt-6-luna, codex, max)
REGISTRY_KEY = "luna-shadow"             # its OWN model_key in the registry: compare.py runs on 'luna' never see shadow rows
LIVE_DB = Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor" / "cfp_monitor.db"
SHADOW_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor" / "runs_out" / "shadow"
FIELDS = SR.FIELDS                       # (reader key, our column, label)
DB_COLUMN = {"start_date": "start_date", "city": "city", "country": "country", "organizer": "organizer"}      # venue and format have no database column
DEFAULT_CALL_TOKENS = 17000              # measured average of the bake-off calls (codex_usage.jsonl), used only when the wrapper could not read the token count
SOON_DAYS = 60


# ------------------------------------------------------------------ pure logic
def priority_key(row: dict, canonical: str, customer: set[str], today: str, answered: set[str]) -> tuple:
    """0 customer-linked, 1 starts within SOON_DAYS, 2 the rest; then rows the existing reader answered, then soonest start."""
    start = (row.get("START DATE") or "")[:10]
    horizon = (date.fromisoformat(today) + timedelta(days=SOON_DAYS)).isoformat()
    tier = 0 if canonical in customer else (1 if start and today <= start <= horizon else 2)
    return (tier, 0 if row.get("EVENT_ID", "") in answered else 1, start or "9999", row.get("CONFERENCE", ""))


def pick_rows(rows: list[dict], today: str, customer: set[str], up_to_canon: dict[str, str], answered: set[str], limit: int = 0) -> list[dict]:
    live = SR.select_rows(rows, today, 10 ** 9)
    out = []
    for r in live:
        canon = identity.to_canonical((r.get("EVENT_ID") or "").strip(), up_to_canon)
        out.append(dict(r, _canon=canon, _tier=priority_key(r, canon, customer, today, answered)[0]))
    out.sort(key=lambda r: priority_key(r, r["_canon"], customer, today, answered))
    return out[:limit] if limit else out


def fact_relation(key: str, luna: str, reader: str, luna_quote: str = "", reader_quote: str = "") -> str:
    """agree | disagree | luna-only | reader-only | none. A text field is still agree when one reader's value is written inside the other's own quote (the page states both)."""
    if not luna and not reader:
        return "none"
    if not reader:
        return "luna-only"
    if not luna:
        return "reader-only"
    if L.same(key, luna, reader):
        return "agree"
    if key != "start_date" and (SR._squash(reader) in SR._squash(luna_quote) or SR._squash(luna) in SR._squash(reader_quote)):
        return "agree"
    return "disagree"


def judge_event(row: dict, parsed: dict | None, text: str, reader_rec: dict | None, db_fact: dict | None) -> dict:
    """One event: per field Luna's PROVEN value (pass_lib.accept), the existing reader's, the database's and the relations. parsed None = the call produced no answer."""
    edition = SR.edition_of(row)
    rec = {"event": row.get("CONFERENCE", ""), "id": row.get("EVENT_ID", ""), "canonical": row.get("_canon", ""), "market": row.get("_market", ""), "edition": edition,
           "tier": row.get("_tier"), "reader_answered": reader_rec is not None, "fields": {}}
    for key, _col, _label in FIELDS:
        item = (parsed or {}).get(key) or {}
        got, why = L.accept(key, item, text, edition) if text.strip() else ("", "page unreadable")
        quote = item.get("quote", "") if got else ""
        rf = ((reader_rec or {}).get("fields") or {}).get(key) or {}
        rval, rquote = rf.get("reader", "") or "", rf.get("quote", "") or ""
        dbv = str((db_fact or {}).get(DB_COLUMN[key]) or "").strip() if key in DB_COLUMN else ""
        rec["fields"][key] = {"luna": got, "luna_quote": quote, "luna_why": why, "reader": rval, "reader_quote": rquote, "reader_url": rf.get("url", ""),
                              "db": dbv, "db_known": key in DB_COLUMN,
                              "vs_reader": fact_relation(key, got, rval, quote, rquote) if reader_rec is not None else "no-reader-answer",
                              "vs_db": (SR.compare_field(key, dbv, got, quote) if key in DB_COLUMN else "n/a")}
    return rec


def tally(recs: list[dict]) -> dict:
    t = {"read": 6 * len(recs), "agree": 0, "disagree": 0, "luna-only": 0, "reader-only": 0, "no_reader_events": sum(1 for r in recs if not r["reader_answered"])}
    t["read"] = len(FIELDS) * len(recs)
    for r in recs:
        for f in r["fields"].values():
            if f["vs_reader"] in ("agree", "disagree", "luna-only", "reader-only"):
                t[f["vs_reader"]] += 1
    return t


def summary_line(t: dict, tokens: int, budget: int, stop: str = "") -> str:
    line = (f"LUNA SHADOW: {t['read']} facts read, agree {t['agree']}, disagree {t['disagree']}, Luna-only found {t['luna-only']}, reader-only found {t['reader-only']}, "
            f"tokens {tokens} (budget {budget})")
    if t["no_reader_events"]:
        line += f"; {t['no_reader_events']} event(s) had no answer from the existing reader"
    if stop:
        line += f"; stopped: {stop}"
    return line


def one_line(text: str, cap: int = 600) -> str:
    return " ".join((text or "").split())[:cap]


def report_md(recs: list[dict], t: dict, meta: dict, summary: str) -> str:
    L_ = [f"# Luna shadow {meta['stamp']} (changes nothing)", "", f"**{summary}**", "",
          f"{len(recs)} event(s) read by GPT-6 Luna (max) of {meta['selected']} selected; {meta['minutes']:.0f} minutes. Existing reader answers from: {meta['reader_file'] or 'none found'}.", ""]
    if meta["error"]:
        L_ += ["## The run stopped on a Codex error (exact text, no retry, no other model used)", "", "```", meta["error"], "```", ""]
    elif meta["stopped"]:
        L_ += [f"## Stopped: {meta['stopped']}", ""]
    dis = [(r, k, f) for r in recs for k, f in r["fields"].items() if f["vs_reader"] == "disagree"]
    L_ += [f"## Disagreements between Luna and the existing reader ({len(dis)})", "", "Both values have a quote that is literally on the page, so one of them read the wrong thing, or the page states two things: a person looks. Not an accuracy figure.", ""]
    for r, k, f in dis:
        L_ += [f"- **{r['event']}** ({r['market']}, edition {r['edition']}) {k}: Luna **{f['luna']}**, existing reader **{f['reader']}**, database {f['db'] or ('(blank)' if f['db_known'] else '(no column)')}",
               f"  - Luna quote: \"{f['luna_quote'][:240]}\"", f"  - reader quote: \"{f['reader_quote'][:240]}\" {f['reader_url']}"]
    if not dis:
        L_ += ["None."]
    for kind, title in (("luna-only", "Luna found, the existing reader did not"), ("reader-only", "The existing reader found, Luna did not")):
        items = [(r, k, f) for r in recs for k, f in r["fields"].items() if f["vs_reader"] == kind]
        L_ += ["", f"## {title} ({len(items)})", ""]
        for r, k, f in items:
            val, q = (f["luna"], f["luna_quote"]) if kind == "luna-only" else (f["reader"], f["reader_quote"])
            L_.append(f"- **{r['event']}** {k}: {val} (database {f['db'] or ('(blank)' if f['db_known'] else '(no column)')}) \"{q[:200]}\"")
    ddb = [(r, k, f) for r in recs for k, f in r["fields"].items() if f["vs_db"] == "differs"]
    L_ += ["", f"## Luna differs from what the database holds ({len(ddb)})", ""]
    for r, k, f in ddb:
        L_.append(f"- **{r['event']}** {k}: Luna **{f['luna']}**, database **{f['db']}**, existing reader {f['reader'] or '(none)'}; \"{f['luna_quote'][:200]}\"")
    if not ddb:
        L_ += ["None."]
    L_ += ["", "Definitions: n facts read = facts asked of Luna in finished calls (6 per event). agree / disagree / Luna-only / reader-only count only events the existing reader also answered "
           "(an event it did not read is listed in the summary line, not scored). Nothing here changed the database, an approved file, a pin or a page."]
    return "\n".join(L_)


# ------------------------------------------------------------------ world access (all injectable in tests)
def codex_status() -> tuple[bool, str]:
    """(signed in, the text). Never raises."""
    try:
        p = subprocess.run(["codex", "login", "status"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, shell=(os.name == "nt"))
    except Exception as e:                                                  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    txt = ((p.stdout or "") + " " + (p.stderr or "")).strip()
    return (p.returncode == 0 and "logged in" in txt.lower() and "not logged in" not in txt.lower()), txt


def ro_connect(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{str(db).replace(chr(92), '/')}?mode=ro", uri=True)


def load_db_context(db: Path) -> tuple[dict, dict, set]:
    """(up_to_canon, grounding facts by canonical event_id, canonical ids of customer-linked events). Read-only. Raises on a missing database."""
    up_to_canon, _roots = identity.seed_map(str(db))
    con = ro_connect(db)
    con.row_factory = sqlite3.Row
    try:
        facts = {r["event_id"]: dict(r) for r in con.execute("select event_id, name, start_date, city, country, organizer from grounding_facts")}
        try:
            cust = {identity.to_canonical((r[0] or "").strip(), up_to_canon) for r in con.execute("select event_id from client_conferences where event_id is not null and event_id != ''")}
        except sqlite3.Error:
            cust = set()
    finally:
        con.close()
    return up_to_canon, facts, cust


def load_reader_answers(shadow_dir: Path, today: str, explicit: str = "") -> tuple[dict, str]:
    """{upstream EVENT_ID: record} from the newest shadow_reader_*.json written within 3 days (or the explicit file)."""
    f = Path(explicit) if explicit else None
    if f is None and shadow_dir.exists():
        cands = [p for p in shadow_dir.glob("shadow_reader_*.json") if time.time() - p.stat().st_mtime < 3 * 86400]
        f = max(cands, key=lambda p: p.stat().st_mtime) if cands else None
    if not f or not f.exists():
        return {}, ""
    try:
        return {e["id"]: e for e in json.loads(f.read_text(encoding="utf-8")).get("events", [])}, str(f)
    except (OSError, ValueError, KeyError):
        return {}, ""


def fetch_pages(row: dict, cache: dict) -> list[tuple[str, str]]:
    """The existing reader's own page path: the page library first, then its plain fetch (+ Chrome render when dateless). Not a new fetcher."""
    import answer_key_prefill as P
    from experiments.read_the_page_pass import run as R
    return [(u, P.lib_text(u) or R.page_text(u, cache) or "") for u in row["_urls"]]


def registry_rows(run_id: str, row: dict, rec: dict, parsed_raw: dict, msgs: list[dict], text: str, page_dir: Path | None) -> list[dict]:
    cfg = B.load_models()[MODEL_KEY]
    page_hash = REG.save_page(text, page_dir)
    prompt_hash = REG.sha(msgs[0]["content"] + "\n" + msgs[1]["content"])[:16]
    out = []
    for key, f in rec["fields"].items():
        out.append({"run_id": run_id, "ts": datetime.now().isoformat(timespec="seconds"), "model_key": REGISTRY_KEY, "model_id": cfg["id"], "route": cfg["route"], "effort": cfg.get("effort", ""),
                    "role": "shadow", "job": f"shadow::{rec['event'][:40]}::{rec['canonical']}", "event": rec["event"], "edition": rec["edition"], "fact": key,
                    "prompt_sha": prompt_hash, "page_sha": page_hash, "raw_response": parsed_raw.get("raw", ""), "parsed": (parsed_raw.get("parsed") or {}).get(key),
                    "quote": f["luna_quote"], "quote_verbatim_on_page": bool(f["luna_quote"]) and L.norm(f["luna_quote"]) in L.norm(text), "accepted": f["luna"], "accept_why": f["luna_why"],
                    "key_value": "", "verdict": f"shadow-{f['vs_reader']}", "db_value": f["db"], "reader_value": f["reader"], "reader_quote": f["reader_quote"], "vs_db": f["vs_db"],
                    "tokens_in": None, "tokens_out": None, "tokens_total": parsed_raw.get("tokens"), "cost_usd": 0.0, "latency_s": parsed_raw.get("seconds"), "error": ""})
    return out


def append_registry(rows: list[dict], registry: Path) -> None:
    with open(registry, "a", encoding="utf-8") as fh:                       # append only
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------ the run
def run(a, status=codex_status, ask=None, pages=fetch_pages) -> int:
    """Prints the summary line and returns 0. `status`, `ask` and `pages` are replaced in tests."""
    budget = a.token_budget
    ok, txt = status()
    if not ok:
        print("LUNA SHADOW: skipped - codex not signed in")
        return 0
    up_to_canon, facts, customer = load_db_context(Path(a.db))
    rows = []
    for m in a.markets:
        fin = Path(a.markets_dir) / f"{m}_audited.final.csv"
        if fin.exists():
            import csv
            with open(fin, encoding="utf-8-sig", newline="") as fh:
                rows += [dict(r, _market=m) for r in csv.DictReader(fh)]
    answers, reader_file = load_reader_answers(Path(a.reader_dir), a.today, a.reader_json)
    events = pick_rows(rows, a.today, customer, up_to_canon, set(answers), a.limit)
    print(f"luna shadow: {len(events)} live events in priority order from {len(rows)} approved rows; existing-reader answers: {reader_file or 'none'}", flush=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = f"lunashadow-{a.today}-{stamp}"
    cfg = B.load_models()[MODEL_KEY]
    ask = ask or (lambda msgs, tag, timeout: B.codex_ask(cfg["id"], msgs, tag, effort=cfg.get("effort", "max"), timeout=timeout))
    registry, page_dir = Path(a.registry), (Path(a.registry).parent / "pages")
    recs, tokens, calls, stopped, error, t0, cache = [], 0, 0, "", "", time.time(), {}
    for ev in events:
        used_min = (time.time() - t0) / 60
        if used_min > a.max_minutes:
            stopped = f"the {a.max_minutes:g}-minute limit"
            break
        avg = tokens // calls if calls else 0
        if tokens >= budget or (calls and tokens + avg > budget):
            stopped = f"token budget reached ({tokens} used of {budget})"
            break
        try:
            pgs = pages(ev, cache)
            text = "\n\n".join(t[:SR.PAGE_CHARS] for _u, t in pgs if t)
            if not text.strip():
                print(f"  skipped {ev['CONFERENCE'][:50]}: no readable page", flush=True)
                continue
            msgs = B.blind_messages(L.SYSTEM, ev["CONFERENCE"], SR.edition_of(ev) or a.today[:4], text)
            res = ask(msgs, f"{run_id}:{ev['CONFERENCE'][:40]}", int(max(60, min(600, (a.max_minutes - used_min) * 60))))
        except Exception as e:                                              # noqa: BLE001  ANY failure of the model route stops the run: exact text, no retry, no other model
            error = str(e).strip() or f"{type(e).__name__}"
            if not isinstance(e, B.CodexError):
                error = f"{type(e).__name__}: {error}"
            break
        calls += 1
        tokens += int(res.get("tokens") or DEFAULT_CALL_TOKENS)
        try:
            rec = judge_event(ev, res.get("parsed") or {}, text, answers.get(ev.get("EVENT_ID", "")), facts.get(ev["_canon"]))
            recs.append(rec)
            append_registry(registry_rows(run_id, ev, rec, res, msgs, text, page_dir), registry)
        except Exception as e:                                              # noqa: BLE001  a bookkeeping fault must not hide the tokens already spent
            error = f"internal error while recording {ev['CONFERENCE'][:40]}: {type(e).__name__}: {e}"
            break
        marks = " ".join(f"{k[:4]}={rec['fields'][k]['vs_reader'][:5]}" for k, _c, _l in FIELDS)
        print(f"  [{len(recs)}/{len(events)}] {ev['CONFERENCE'][:44]:44} {marks}", flush=True)
    t = tally(recs)
    meta = {"stamp": stamp, "selected": len(events), "stopped": stopped, "error": error, "minutes": (time.time() - t0) / 60, "reader_file": reader_file}
    if error:
        summary = f"LUNA SHADOW: stopped - {one_line(error)}"
    else:
        summary = summary_line(t, tokens, budget, stopped)
    out_dir = Path(a.out_dir) if a.out_dir else qa_report.QA_ROOT / a.today
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "luna_shadow.md").write_text(report_md(recs, t, meta, summary if not error else summary + "\n\n" + summary_line(t, tokens, budget, "error")), encoding="utf-8")
    print(summary)
    if error:
        print(summary_line(t, tokens, budget, "error").replace("LUNA SHADOW:", "LUNA SHADOW PARTIAL:", 1))
    print(f"luna shadow report: {out_dir / 'luna_shadow.md'}")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--markets", nargs="+", default=["Cybersecurity", "Utility"])
    ap.add_argument("--markets-dir", default=str(SR.MARKETS_DIR))
    ap.add_argument("--db", default=str(LIVE_DB), help="read-only; use a COPY for a rehearsal")
    ap.add_argument("--token-budget", type=int, default=1500000, help="subscription tokens per run (as reported by the Codex wrapper); stop when reached")
    ap.add_argument("--max-minutes", type=float, default=45)
    ap.add_argument("--limit", type=int, default=0, help="only the first N events in priority order (rehearsal)")
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--reader-dir", default=str(SHADOW_DIR), help="where the existing reader's shadow_reader_*.json files are")
    ap.add_argument("--reader-json", default="", help="a specific existing-reader result file")
    ap.add_argument("--registry", default=str(REG.REGISTRY), help="append-only registry (use a scratch file for a rehearsal)")
    ap.add_argument("--out-dir", default="", help="default runs_out/qa/<today>")
    ap.add_argument("--run-log", help="the weekend job's log: its creation time is the job's start, used with --total-hours")
    ap.add_argument("--total-hours", type=float, default=4.6)
    a = ap.parse_args()
    try:
        if a.run_log and Path(a.run_log).exists():
            left = a.total_hours * 60 - (time.time() - os.path.getctime(a.run_log)) / 60
            if left < 12:
                print(f"LUNA SHADOW: skipped - only {left:.0f} minutes left inside the job's time budget")
                return 0
            a.max_minutes = min(a.max_minutes, left - 8)
        return run(a)
    except BaseException as e:                                              # noqa: BLE001  the weekend job must never fail because of this script
        print(f"LUNA SHADOW: stopped - {one_line(f'{type(e).__name__}: {e}')}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
