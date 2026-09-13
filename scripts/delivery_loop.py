"""Close a delivery's hand-back loop without a person carrying messages between the two sides.

    python scripts/delivery_loop.py <delivery.csv> --market <Canonical> [--prior <previous.csv>]
        [--db <db>] [--max-rounds 2] [--max-requests 10] [--dry-run]

Each round:
    1. gate                  scripts/accept_delivery.py --json      (the one gate)
    2. mechanical repairs    scripts/mechanical_repairs.py           (contract v2.4)
    3. gate again            - stop here if ACCEPTED
    4. findings              every remaining failure, as a structured question per row
    5. upstream answers      Markets/answer_findings.py              (Gemini, grounded)
    6. verify and apply      every answer checked against the live page before it is used
Stops when the gate accepts, when a round makes no progress, at --max-rounds, or on a quota
error. Everything lands in a loop_<delivery>_<stamp>/ folder beside the delivery, ending in
SUMMARY.md.

WHAT IT NEVER DOES
  - modify the delivery it was given (it works on copies)
  - import anything (a person imports an ACCEPTED file, per the runbook)
  - apply a change to a CLAIM - a date, a status, event dates. Upstream may propose one; it is
    checked and listed for a person to approve. Only citations and links are applied here,
    which contract v2.0.1 section 3 gives to upstream outright.
  - trust an answer: a URL must resolve and be a real page, evidence must not be a homepage, and
    a quote must be the page's own text containing the deadline. Our own extraction replaces a
    quote that is not (v2.0.1 section 3 note: "upstream supplies the claim and the candidate
    page; downstream extracts and proves the quote").

WHY. 2026-09-12: seven hand-back documents carried by copy and paste, most of them this exact
shape of question. See handoff-files/Contract_v2.4_Amendment_Downstream_Mechanical_Repairs_20260912.md
and Markets/standing_rules.md for the other two steps.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import mechanical_repairs as mr                          # noqa: E402
from src.cfp_monitor import rules                                    # noqa: E402

MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
LINK_FIELDS = ("SUBMISSION URL", "CFP_SUBMISSION_URL", "VENUE_EVIDENCE_URL")
EVIDENCE = "DEADLINE_EVIDENCE_URL"
DEADLINE_CHECKS = {"2", "3", "R2", "R22"}
SNAPSHOT = ("CONFERENCE", "CONFERENCE URL", "LOCATION", "CITY", "COUNTRY", "CONFERENCE DATES",
            "START DATE", "SUBMISSION DEADLINE", "STATUS", "STATUS DETAILS", "IS_PROJECTED",
            "CFP MODEL TYPE", "OPPORTUNITY_TYPE", "SUBMISSION URL", "CFP_SUBMISSION_URL",
            "DEADLINE_EVIDENCE_URL", "DEADLINE_QUOTE", "VENUE_EVIDENCE_URL")


# ============================================================================ findings
def gate_failures(payload: dict) -> list[tuple[str, str, str]]:
    """[(check, check name, failure text)] for every failed check in accept_delivery's JSON."""
    out = []
    for results in payload.values():
        for r in results:
            if not r.get("passed"):
                out += [(str(r["check"]), r.get("name", ""), str(f)) for f in r.get("failures", [])]
    return out


def match_row(text: str, rows: list[dict]) -> Optional[dict]:
    """The gate prefixes a failure with the conference name cut to 36-48 characters. A failure
    maps to a row only when exactly one row's name produces that prefix - otherwise it is left
    for a person rather than pinned on the wrong event (2.5)."""
    hits = [r for r in rows
            if any(text.startswith((r.get("CONFERENCE") or "")[:k] + ":")
                   for k in (36, 38, 40, 44, 48)) and r.get("CONFERENCE")]
    uniq = {id(r): r for r in hits}
    return next(iter(uniq.values())) if len(uniq) == 1 else None


def classify(check: str, text: str) -> tuple[str, str]:
    """(kind, field) for one gate failure."""
    if check in DEADLINE_CHECKS:
        return "deadline_evidence", EVIDENCE
    for f in LINK_FIELDS:
        if f in text:
            return "link", f
    return "other", ""


def build_findings(rows: list[dict], payload: dict, declined: list, withdrawn: list,
                   delivery: str, market: str, today: date) -> tuple[dict, list[str]]:
    """Findings JSON for answer_findings.py, and the failures no row could be matched to."""
    by_name: dict[str, dict] = {}
    unmatched: list[str] = []

    def add(row, kind, fld, detail, blocking):
        item = by_name.setdefault(row["CONFERENCE"], {
            "conference": row["CONFERENCE"], "blocking": False,
            "row": {k: row.get(k, "") for k in SNAPSHOT if k in row}, "problems": []})
        if any(p["kind"] == kind and p["field"] == fld for p in item["problems"]):
            return
        item["problems"].append({"kind": kind, "field": fld, "detail": detail})
        item["blocking"] |= blocking

    for check, name, text in gate_failures(payload):
        row = match_row(text, rows)
        if row is None:
            unmatched.append(f"[{check}] {name}: {text}")
            continue
        kind, fld = classify(check, text)
        add(row, kind, fld, f"gate check {check} ({name}): {text}", True)

    names = {r["CONFERENCE"]: r for r in rows if r.get("CONFERENCE")}
    for d in declined:
        row = names.get(d.conference)
        if row is None:
            continue
        if d.cls == "A":
            add(row, "deadline_evidence", EVIDENCE, f"quote could not be re-copied: {d.why}", True)
        elif d.cls in ("B", "D") and d.field in LINK_FIELDS + (EVIDENCE,):
            kind = "deadline_evidence" if d.field == EVIDENCE else "link"
            add(row, kind, d.field, d.why, True)
        else:
            add(row, "other", d.field, d.why, False)
    # A dead link we withdrew leaves the customer without one. Not blocking, but worth a question.
    for rep in withdrawn:
        row = names.get(rep.conference)
        if row is not None and rep.field in LINK_FIELDS and rep.before:
            add(row, "link", rep.field, f"{rep.before} was dead and has been withdrawn - is there "
                                        f"a live page for this field?", False)

    items = sorted(by_name.values(), key=lambda i: (not i["blocking"], i["conference"]))
    return ({"delivery": delivery, "market": market, "today": today.isoformat(), "rows": items},
            unmatched)


# ============================================================================ apply answers
@dataclass
class Applied:
    conference: str
    field: str
    before: str
    after: str
    why: str


@dataclass
class ForPerson:
    conference: str
    what: str
    detail: str


@dataclass
class ApplyResult:
    applied: list[Applied] = field(default_factory=list)
    for_person: list[ForPerson] = field(default_factory=list)


def _resolves(code) -> bool:
    return bool(code) and (200 <= code < 400 or code == 403)


def _page_ok(url: str, code, *, evidence: bool) -> Optional[str]:
    """Why this URL cannot be used, or None."""
    from src.cfp_monitor.verify import is_homepage
    ok, why = rules.citation_source_admissible(url)
    if not ok:
        return why
    ok, why = rules.url_is_a_page(url)
    if not ok:
        return why
    if evidence and is_homepage(url):
        return "a homepage cannot evidence a deadline (R3)"
    if not _resolves(code):
        return f"does not resolve (HTTP {code})"
    return None


def apply_answers(rows: list[dict], answers: dict, today: date,
                  fetch: Callable[[str], tuple[Optional[int], str]],
                  browser_dead: Callable[[list[str]], set[str]]) -> ApplyResult:
    """Verify each answer against the live page and apply what survives, in memory."""
    from src.cfp_monitor.verify import find_date
    res = ApplyResult()
    names = {r["CONFERENCE"]: r for r in rows if r.get("CONFERENCE")}

    def put(row, fld, value, why):
        if row.get(fld, "") != value:
            res.applied.append(Applied(row["CONFERENCE"], fld, row.get(fld, ""), value, why))
            row[fld] = value

    for block in answers.get("rows", []):
        name = block.get("conference", "")
        row = names.get(name)
        for issue in block.get("issues", []):
            res.for_person.append(ForPerson(name, "upstream answer incomplete", issue))
        if row is None:
            res.for_person.append(ForPerson(name, "answer names a row not in the delivery", ""))
            continue
        for a in block.get("answers", []):
            disp, fld, url = a["disposition"], a.get("field", ""), a.get("url", "")

            if disp == "propose_change":
                code, text = fetch(url) if url.startswith("http") else (None, "")
                proof = ("quote found verbatim on the page"
                         if a.get("quote") and text
                         and mr._norm_quote(a["quote"]) in mr._norm_quote(text)
                         else "quote NOT confirmed on the page")
                res.for_person.append(ForPerson(
                    name, "upstream proposes changing the claim - approve or reject",
                    f"changes {a.get('changes')} | {url} (HTTP {code}; {proof}) | "
                    f"quote: {a.get('quote')!r} | {a.get('explanation')}"))
                continue

            if disp == "replace" and fld in LINK_FIELDS:
                code, _ = fetch(url)
                bad = _page_ok(url, code, evidence=fld == "VENUE_EVIDENCE_URL")
                if bad:
                    res.for_person.append(ForPerson(name, f"rejected replacement for {fld}",
                                                    f"{url}: {bad}"))
                    continue
                old = row.get(fld, "")
                targets = [fld] + ([f for f in ("SUBMISSION URL", "CFP_SUBMISSION_URL")
                                    if f != fld and old and row.get(f, "") == old])
                for t in targets:
                    put(row, t, url, f"upstream replacement, verified live (HTTP {code})")
                continue

            if disp == "replace" and fld == EVIDENCE:
                code, text = fetch(url)
                bad = _page_ok(url, code, evidence=True)
                d = rules.parse_date(row.get("SUBMISSION DEADLINE"))
                if not bad and not text:
                    bad = "page could not be read"
                if not bad and not d:
                    bad = "the row has no deadline to evidence - that is a claim change"
                if not bad and not find_date(text, d):
                    bad = f"the page does not state the row's deadline {d.isoformat()}"
                if bad:
                    res.for_person.append(ForPerson(name, "rejected deadline evidence",
                                                    f"{url}: {bad}"))
                    continue
                quote, how = a.get("quote", ""), "upstream's quote, verbatim on the page"
                if not (quote and mr._norm_quote(quote) in mr._norm_quote(text)
                        and mr._occurrences(quote, d)):
                    quote, why = mr.find_quote_span(text, name, d)
                    how = "quote extracted by us - upstream's was not the page's own text"
                    if quote is None:
                        res.for_person.append(ForPerson(
                            name, "deadline is on the page but no unambiguous quote",
                            f"{url}: {why}"))
                        continue
                put(row, EVIDENCE, url, f"upstream evidence, verified (HTTP {code})")
                put(row, "DEADLINE_QUOTE", quote, how)
                if row.get("IS_PROJECTED", "").lower() == "true" and not rules.deadline_has_passed(row, today):
                    put(row, "IS_PROJECTED", "false", "R2: a future deadline now backed by a live citation")
                    put(row, "GROUNDING_CONFIDENCE",
                        rules.bound_confidence(row.get("GROUNDING_CONFIDENCE", ""), False), "R11")
                continue

            if disp == "none_public" and fld == EVIDENCE:
                if not row.get(EVIDENCE) and row.get("IS_PROJECTED", "").lower() == "true":
                    continue
                if mr.withdrawal_would_break_prose(row):
                    res.for_person.append(ForPerson(
                        name, "no public page states the deadline, but withdrawing breaks check 4",
                        f"STATUS DETAILS asserts an active call: {row.get('STATUS DETAILS')!r}"))
                    continue
                for wf, wv in rules.withdrawal_changes(row, fetched=True, today=today).items():
                    put(row, wf, wv, f"R1 withdrawal - upstream: no public page states it. "
                                     f"{a.get('explanation', '')}")
                continue

            if disp == "none_public" and fld in LINK_FIELDS:
                cur = row.get(fld, "")
                if cur and fetch(cur)[0] in rules.DISPROVING_STATUS and cur in browser_dead([cur]):
                    put(row, fld, "", "withdrawn - dead, and upstream: no public page")
                continue

            res.for_person.append(ForPerson(name, "answer not usable",
                                            f"{disp} on {fld!r}: {a.get('explanation', '')}"))
    return res


# ============================================================================ driver
def _read(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        return rd.fieldnames, list(rd)


def _write(path: Path, cols: list[str], rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)


def _gate(csv_path: Path, out_json: Path, db: str, market: str) -> tuple[bool, dict]:
    cmd = [sys.executable, str(ROOT / "scripts" / "accept_delivery.py"), str(csv_path),
           "--json", str(out_json)]
    if db:
        cmd += ["--db", db, "--market", market]
    log = out_json.with_suffix(".txt")
    with open(log, "w", encoding="utf-8") as fh:
        code = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT,
                              env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}).returncode
    payload = json.loads(out_json.read_text(encoding="utf-8")) if out_json.exists() else {}
    return code == 0, payload


def main() -> int:
    ap = argparse.ArgumentParser(description="Close a delivery's hand-back loop.")
    ap.add_argument("delivery")
    ap.add_argument("--market", required=True, help="canonical market, e.g. Cybersecurity")
    ap.add_argument("--prior", help="previous version of the delivery (repair class B)")
    ap.add_argument("--db", default=r"C:\Users\matts\AppData\Local\CFP-Monitor\cfp_monitor.db")
    ap.add_argument("--max-rounds", type=int, default=2)
    ap.add_argument("--max-requests", type=int, default=10, help="Gemini requests per round")
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--dry-run", action="store_true",
                    help="gate, repair and build findings, show the prompts; no Gemini calls")
    ap.add_argument("--ledger", default=str(mr.LEDGER))
    a = ap.parse_args()

    today = date.today()
    src = Path(a.delivery).resolve()
    work = src.parent / f"loop_{src.stem}_{datetime.now():%Y%m%d-%H%M%S}"
    work.mkdir()
    cols, rows = _read(src)
    prior = _read(Path(a.prior))[1] if a.prior else None
    ledger = Path(a.ledger)
    ledger_lines = ledger.read_text(encoding="utf-8").splitlines() if ledger.exists() else []

    summary = [f"# Delivery loop - {src.name}", "", f"    STARTED: {datetime.now():%Y-%m-%d %H:%M}",
               f"    MARKET:  {a.market}", ""]
    for_person: list[ForPerson] = []
    accepted, previous_findings, current = False, None, work / "round0_input.csv"
    shutil.copy2(src, current)

    for rnd in range(1, a.max_rounds + 1):
        tag = f"round{rnd}"
        ok, payload = _gate(current, work / f"{tag}_gate.json", a.db, a.market)
        summary.append(f"## Round {rnd}\n\n- gate on arrival: {'ACCEPTED' if ok else 'rejected'}")
        if ok:
            accepted = True
            break

        rep = mr.run(rows, prior if rnd == 1 else None, today, mr._live_fetch,
                     mr._live_browser_dead, ledger_lines)
        repaired = work / f"{tag}.repaired.csv"
        _write(repaired, cols, rows)
        mr.write_report(work / f"{tag}.repairs.md", src, rep, today)
        if rep.repairs and not a.dry_run:
            with open(ledger, "a", encoding="utf-8") as fh:
                for r in rep.repairs:
                    fh.write("\t".join([today.isoformat(), r.market, r.conference, r.field, r.cls,
                                        r.before.replace("\t", " ")[:200],
                                        r.after.replace("\t", " ")[:200], src.name]) + "\n")
        summary.append(f"- mechanical repairs: {len(rep.repairs)} made, {len(rep.declined)} declined "
                       f"(`{tag}.repairs.md`)")
        current = repaired
        ok, payload = _gate(current, work / f"{tag}_gate_repaired.json", a.db, a.market)
        summary.append(f"- gate after repairs: {'ACCEPTED' if ok else 'rejected'}")
        if ok:
            accepted = True
            break

        withdrawn = [r for r in rep.repairs if r.cls == "D"]
        findings, unmatched = build_findings(rows, payload, rep.declined, withdrawn,
                                             src.name, a.market, today)
        for u in unmatched:
            for_person.append(ForPerson("(delivery)", "gate failure not tied to one row", u))
        fpath = work / f"{tag}_findings.json"
        fpath.write_text(json.dumps(findings, indent=2, ensure_ascii=False), encoding="utf-8")
        signature = json.dumps([(i["conference"], i["problems"]) for i in findings["rows"]])
        summary.append(f"- findings for upstream: {len(findings['rows'])} row(s) "
                       f"(`{fpath.name}`)")
        if not findings["rows"]:
            break
        if signature == previous_findings:
            summary.append("- **no progress since the last round - stopping**")
            break
        previous_findings = signature

        answers_path = work / f"{tag}_answers.json"
        cmd = ["py", str(Path(a.markets_dir) / "answer_findings.py"), "--findings", str(fpath),
               "--max-requests", str(a.max_requests)]
        cmd += ["--dry-run"] if a.dry_run else ["--out", str(answers_path)]
        with open(work / f"{tag}_answers.log", "w", encoding="utf-8") as fh:
            code = subprocess.run(cmd, cwd=a.markets_dir, stdout=fh, stderr=subprocess.STDOUT,
                                  env={**__import__("os").environ,
                                       "PYTHONIOENCODING": "utf-8"}).returncode
        if a.dry_run:
            summary.append(f"- DRY RUN: prompts in `{tag}_answers.log`; nothing sent to Gemini")
            break
        if code != 0 or not answers_path.exists():
            why = "out of quota" if code == 3 else f"exit {code}"
            summary.append(f"- **upstream step stopped ({why}) - see `{tag}_answers.log`**")
            break

        answers = json.loads(answers_path.read_text(encoding="utf-8"))
        for n in answers.get("not_asked", []):
            for_person.append(ForPerson(n, "not asked - over the request cap", ""))
        applied = apply_answers(rows, answers, today, mr._live_fetch, mr._live_browser_dead)
        for_person += applied.for_person
        current = work / f"{tag}.answered.csv"
        _write(current, cols, rows)
        lines = [f"# Upstream answers applied - round {rnd}", "", "| Row | Field | Before | After | Why |",
                 "|---|---|---|---|---|"]
        cell = lambda s: (s or "(blank)").replace("|", "/").replace("\n", " ")[:120]  # noqa: E731
        lines += [f"| {cell(x.conference)} | {x.field} | {cell(x.before)} | {cell(x.after)} | {cell(x.why)} |"
                  for x in applied.applied]
        (work / f"{tag}_applied.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        summary.append(f"- upstream answers applied: {len(applied.applied)} field change(s); "
                       f"{len(applied.for_person)} item(s) for a person (`{tag}_applied.md`)")
        if not applied.applied:
            summary.append("- **nothing usable came back - stopping**")
            break
    else:
        ok, payload = _gate(current, work / "final_gate.json", a.db, a.market)
        accepted = ok
        summary.append(f"\n## Final gate after round {a.max_rounds}: {'ACCEPTED' if ok else 'rejected'}")

    final = work / "FINAL.csv"
    shutil.copy2(current, final)
    summary += ["", "## Result", "",
                f"**{'ACCEPTED' if accepted else 'NOT ACCEPTED'}** - `{final}`", ""]
    if accepted and not a.dry_run:
        summary += ["Import it (runbook section 2), then reconcile:", "", "```",
                    f'.venv\\Scripts\\python.exe scripts\\import_grounding.py "{final}" --out '
                    f'"<live market_sheets>\\<market>_seed.csv" --seed "{a.db}"',
                    f'.venv\\Scripts\\python.exe scripts\\check_invariants.py --db "{a.db}"', "```", ""]
    if for_person:
        summary += ["## Needs a person", "", "| Row | What | Detail |", "|---|---|---|"]
        summary += [f"| {p.conference} | {p.what} | {p.detail.replace('|', '/')[:400]} |"
                    for p in for_person]
    (work / "SUMMARY.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("\n".join(summary))
    print(f"\nall artifacts: {work}")
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(main())
