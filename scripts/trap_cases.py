"""Run the TRAP CASES (docs/qa/trap-cases.json): the events and pages that have already fooled us, as data.

    python scripts/trap_cases.py                       # check the code we already run against every case it can check offline
    python scripts/trap_cases.py --method pkg.mod:fn   # score a method: fn(case) -> {"answer": "<what it says>"} or None

WHY (2026-10-03). Every new way of getting data (a shorter prompt, a cheap model reading a page, a second model) has to be tried on the same hard cases before it is
trusted, or each experiment re-discovers the same traps. The cases are written down once, with the page text we saw, the wrong answer and the right one.

RESULT PER CASE: PASS (every offline check holds) | GAP (our code does not catch this yet: recorded, not hidden) | HUMAN (needs a person or a model to answer) | FAIL (a check
that should hold does not: a regression in our code, or in the method under test).
A case can mix them; the worst applies (FAIL > GAP > HUMAN > PASS). Offline checks use only pure functions already in the repo; nothing here fetches a page."""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CASES = ROOT / "docs" / "qa" / "trap-cases.json"
TODAY = date(2026, 10, 3)          # the day the cases were read; year checks are evaluated as of then


def load_cases(path: Path = CASES) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["cases"]


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def run_check(case: dict, chk: dict) -> tuple[str, str]:
    """(verdict, detail) for one offline check."""
    t = chk["type"]
    if t == "human":
        return "HUMAN", chk["note"]
    if t == "arbiter_proves":
        from scripts.start_date_arbiter import proven
        got = proven([("fixture", case["fixture"])], _d(chk["date"]))[0]
        return ("PASS" if got == chk["expect"] else "FAIL"), f"page proves {chk['date']}: {got} (expected {chk['expect']})"
    if t == "find_date":
        from src.cfp_monitor.verify import find_date
        got = find_date(case["fixture"], _d(chk["date"]))
        return ("PASS" if got == chk["expect"] else "FAIL"), f"find_date {chk['date']}: {got} (expected {chk['expect']})"
    if t == "block_page":
        from src.cfp_monitor.verify import is_block_page
        got = is_block_page(case["fixture"])
        return ("PASS" if got == chk["expect"] else "FAIL"), f"is_block_page: {got} (expected {chk['expect']})"
    if t == "first_date":
        from scripts.start_date_arbiter import first_date
        got = first_date(chk["text"])
        got = got.isoformat() if got else None
        return ("PASS" if got == chk["expect"] else "FAIL"), f"first_date: {got} (expected {chk['expect']})"
    if t == "year_check":
        from scripts.start_date_arbiter import year_checks
        fails = year_checks(chk["row"], TODAY)
        ok = any(f.startswith(chk["expect_fail"]) for f in fails)
        return ("PASS" if ok else "FAIL"), f"year checks fired: {[f[:2] for f in fails]} (expected {chk['expect_fail']})"
    if t == "guessed_start_flag":
        from scripts.post_load_qa import guessed_dates
        got = bool(guessed_dates({"k": {"name": "n", **chk["old"]}}, {"k": {"name": "n", **chk["new"]}}))
        return ("PASS" if got == chk["expect_flag"] else "FAIL"), f"load QA flags the introduced start date: {got} (expected {chk['expect_flag']})"
    if t == "event_named_on_page":
        got = chk["event"].lower() in case["fixture"].lower()
        return ("PASS" if got == chk["expect"] else "FAIL"), f"event named on the page: {got} (expected {chk['expect']})"
    if chk.get("gap"):
        # A check for something our code cannot do yet. If someone builds it, this stops being a gap and must be turned into a real check.
        probe = {"earliest_deadline": ("src.cfp_monitor.verify", "earliest_deadline"),
                 "aggregator_citation_flag": ("scripts.accept_delivery", "is_aggregator_url")}.get(t)
        if probe:
            try:
                getattr(importlib.import_module(probe[0]), probe[1])
                return "FAIL", f"{t}: {probe[1]} now exists; replace this gap with a real check"
            except (ImportError, AttributeError):
                pass
        return "GAP", f"{t}: our code does not do this yet"
    return "FAIL", f"unknown check type {t!r}"


ORDER = {"PASS": 0, "HUMAN": 1, "GAP": 2, "FAIL": 3}


def run_all(cases: list[dict]) -> list[dict]:
    out = []
    for c in cases:
        res = [run_check(c, k) for k in c["checks"]]
        worst = max((v for v, _ in res), key=ORDER.get)
        out.append({"id": c["id"], "name": c["name"], "result": worst, "details": res})
    return out


def score_method(cases: list[dict], fn) -> list[dict]:
    """A method is scored on the cases it can answer: its answer must contain the right value and not the wrong one."""
    out = []
    for c in cases:
        ans = fn(c)
        if ans is None:
            out.append({"id": c["id"], "name": c["name"], "result": "SKIP", "details": []})
            continue
        a = str(ans.get("answer", "")).lower()
        right_tokens = [x for x in (c["right"].split(" ")[0],) if x]
        ok = bool(a) and all(tok.lower().strip(",;.") in a for tok in right_tokens) and c["wrong"].split(" ")[0].lower() not in a
        out.append({"id": c["id"], "name": c["name"], "result": "PASS" if ok else "FAIL", "details": [("", f"answered {a[:80]!r}")]})
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--method", help="module:function to score on the cases")
    ap.add_argument("--cases", default=str(CASES))
    a = ap.parse_args()
    cases = load_cases(Path(a.cases))
    if a.method:
        mod, fn = a.method.split(":")
        res = score_method(cases, getattr(importlib.import_module(mod), fn))
    else:
        res = run_all(cases)
    for r in res:
        print(f"{r['id']}  {r['result']:5s} {r['name']}")
        for v, d in r["details"]:
            if v in ("FAIL", "GAP", "HUMAN") or a.method:
                print(f"        [{v}] {d}")
    n = {k: sum(1 for r in res if r["result"] == k) for k in ("PASS", "GAP", "HUMAN", "FAIL", "SKIP")}
    print(f"\n{len(res)} cases: " + ", ".join(f"{v} {k}" for k, v in n.items() if v))
    return 1 if n["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
