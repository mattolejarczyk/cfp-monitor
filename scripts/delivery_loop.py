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
from src.cfp_monitor.run_health import HEALTH                        # noqa: E402

MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
LINK_FIELDS = ("SUBMISSION URL", "CFP_SUBMISSION_URL", "VENUE_EVIDENCE_URL")
CRAWLABLE_FIELDS = ("SUBMISSION URL", "CFP_SUBMISSION_URL")
EVIDENCE = "DEADLINE_EVIDENCE_URL"
DEADLINE_CHECKS = {"2", "3", "R2", "R22"}
SNAPSHOT = ("CONFERENCE", "CONFERENCE URL", "LOCATION", "CITY", "COUNTRY", "CONFERENCE DATES",
            "START DATE", "SUBMISSION DEADLINE", "STATUS", "STATUS DETAILS", "IS_PROJECTED",
            "CFP MODEL TYPE", "OPPORTUNITY_TYPE", "SUBMISSION URL", "CFP_SUBMISSION_URL",
            "DEADLINE_EVIDENCE_URL", "DEADLINE_QUOTE", "VENUE_EVIDENCE_URL", "MAIN_INFO_URL")


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

    def add(row, kind, fld, detail, blocking, dead_url=""):
        item = by_name.setdefault(row["CONFERENCE"], {
            "conference": row["CONFERENCE"], "blocking": False,
            "row": {k: row.get(k, "") for k in SNAPSHOT if k in row}, "problems": []})
        if any(p["kind"] == kind and p["field"] == fld for p in item["problems"]):
            return
        item["problems"].append({"kind": kind, "field": fld, "detail": detail,
                                 "dead_url": dead_url or (row.get(fld, "") if kind == "link" else "")})
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
        if row is None or mr.is_fine_link(d):
            continue                       # a link checked and found alive is not a question
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
                                        f"a live page for this field?", False, dead_url=rep.before)

    # Order is what a --max-requests cap spends first. Blocking rows, then rows whose answers
    # can be applied, then rows asking only "other" questions - those can only ever end up on
    # a person's list, so they are the last thing worth paying for.
    items = sorted(by_name.values(),
                   key=lambda i: (not i["blocking"],
                                  all(p["kind"] == "other" for p in i["problems"]),
                                  i["conference"]))
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
                dead = url.startswith("http") and url in browser_dead([url])
                quoted = bool(a.get("quote") and text
                              and mr._norm_quote(a["quote"]) in mr._norm_quote(text))
                # The VERDICT LEADS. On 2026-09-13 a proposal whose page was a browser 404 and whose
                # quote was not on it reached this list with the failure cut off by the summary's
                # column width - a person skimming would have seen only the proposed values.
                if dead or not quoted:
                    verdict = "EVIDENCE FAILS: " + "; ".join(
                        ([f"page is not-found in a real browser (plain HTTP {code})"] if dead else [])
                        + ([] if quoted else ["quote is not on the page"])) + " - reject"
                    what = "upstream proposed a change its own evidence does not support"
                else:
                    verdict = f"evidence checks out: page loads (HTTP {code}), quote found verbatim"
                    what = "upstream proposes changing the claim - approve or reject"
                res.for_person.append(ForPerson(
                    name, what, f"{verdict} | changes {a.get('changes')} | {url} | "
                                f"quote: {a.get('quote')!r} | {a.get('explanation')}"))
                continue

            if disp == "replace" and fld in LINK_FIELDS:
                code, _ = fetch(url)
                bad = _page_ok(url, code, evidence=fld == "VENUE_EVIDENCE_URL")
                # A 403 is "exists but blocks scripts" for a CITATION (R3), but it hides soft 404s:
                # on 2026-09-13 upstream's replacement for SecureWorld East answered 403 to a plain
                # fetch and was, in a browser, "Page not found". A link a customer clicks is
                # checked in a real browser before it replaces anything.
                if not bad and url in browser_dead([url]):
                    bad = "a real browser shows a not-found page (plain fetch said HTTP %s)" % code
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
                if not bad and url in browser_dead([url]):
                    bad = "a real browser shows a not-found page"
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
                if cur and fetch(cur)[0] in rules.NEEDS_BROWSER_STATUS and cur in browser_dead([cur]):
                    put(row, fld, "", "withdrawn - dead, and upstream: no public page")
                continue

            res.for_person.append(ForPerson(name, "answer not usable",
                                            f"{disp} on {fld!r}: {a.get('explanation', '')}"))
    return res


# ============================================================================ links by crawl
def crawl_answers(findings: dict, hunt: Callable[[list[dict]], list[dict]]) -> dict:
    """Answer LINK questions by crawling the conference's own site, not by asking a model.

    WHY NOT GEMINI. 2026-09-13: 17 grounded Gemini calls across three pilots returned two link
    answers, both plausible and both 404 in a real browser. A diagnostic call showed grounding
    did run - 8 searches - but its sources are recorded per DOMAIN and it supported only the
    dates; the URL paths were composed, not read. Asking a model to REPORT where a page lives
    produces guesses. scripts/find_replacement_links.py crawls the site and takes a link it
    actually found, and apply_answers() still browser-checks it before use.

    Returns the same shape as Markets/answer_findings.py, so apply_answers() is unchanged.
    Deadline-evidence and "other" questions are not a crawl's to answer; they are listed for
    the Saturday re-research or a person.
    """
    out = {"delivery": findings.get("delivery"), "market": findings.get("market"),
           "today": findings.get("today"), "via": "crawl (find_replacement_links.hunt)",
           "rows": [], "not_asked": []}
    jobs, where = [], []                    # one crawl per (row, dead url)
    for item in findings.get("rows", []):
        row = item.get("row", {})
        by_url: dict[str, list[int]] = {}
        for n, p in enumerate(item.get("problems", []), 1):
            # A crawl finds SUBMISSION pages (find_replacement_links hunts res.submission_url).
            # Using its answer for VENUE_EVIDENCE_URL applied an events listing as St. Louis's
            # venue evidence on 2026-09-13. Other link fields need research, not this crawl.
            if p.get("kind") != "link" or p.get("field") not in CRAWLABLE_FIELDS:
                out["not_asked"].append(f"{item['conference']} - problem {n} ({p.get('kind')} "
                                        f"{p.get('field') or ''}) - needs research, not a crawl")
                continue
            by_url.setdefault(p.get("dead_url") or "", []).append(n)
        for dead, probs in by_url.items():
            jobs.append({"event_id": item["conference"], "name": item["conference"],
                         "submission_url": dead or row.get("CONFERENCE URL", ""),
                         "url": row.get("CONFERENCE URL", ""),
                         "main_info_url": row.get("MAIN_INFO_URL", "")})
            where.append((item, probs))
    if not jobs:
        return out
    results = hunt(jobs)
    blocks: dict[str, dict] = {}
    for (item, probs), rec in zip(where, results):
        block = blocks.setdefault(item["conference"], {"conference": item["conference"],
                                                       "answers": [], "issues": []})
        url, verdict = rec.get("PROPOSED URL", ""), rec.get("VERDICT", "")
        for n in probs:
            fld = item["problems"][n - 1].get("field", "")
            if url and verdict == "CONFIDENT":
                block["answers"].append({
                    "problem": n, "kind": "link", "field": fld, "disposition": "replace",
                    "url": url, "quote": "", "changes": {},
                    "explanation": f"found by crawling {rec.get('START URL', '')}: "
                                   f"{rec.get('FOUND VIA', '')} ({rec.get('WHY', '')})"})
            elif url:
                block["issues"].append(f"problem {n}: crawl found a candidate that needs review - "
                                       f"{url} ({rec.get('WHY', '')})")
            elif rec.get("OUTCOME") == "Could not read the site":
                block["issues"].append(f"problem {n}: NOT CHECKED - the crawl could not read the "
                                       f"site ({rec.get('NOTE', '')}); retry, this is not a finding")
            else:
                block["issues"].append(f"problem {n}: crawl found no live page - "
                                       f"{rec.get('NOTE') or rec.get('OUTCOME') or 'nothing found'}; "
                                       f"call state: {rec.get('CFP STATE') or 'undetermined'} "
                                       f"(pages read: {rec.get('PAGES READ') or 'unknown'})")
    out["rows"] = list(blocks.values())
    return out


def _live_hunt(jobs: list[dict]) -> list[dict]:
    import asyncio
    from scripts.find_replacement_links import hunt
    from src.cfp_monitor.config import Settings
    return asyncio.run(hunt(jobs, Settings()))


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
    # A gate that REJECTS writes its JSON; a gate that CRASHES does not. Without this, a crash
    # read as "rejected with no failures" and the loop built zero findings from it.
    if not payload:
        HEALTH.fail("gate_run", "gate_crashed", f"exit {code}, no JSON - see {log.name}")
    else:
        HEALTH.ok("gate_run")
    return code == 0, payload


def main() -> int:
    ap = argparse.ArgumentParser(description="Close a delivery's hand-back loop.")
    ap.add_argument("delivery")
    ap.add_argument("--market", required=True, help="canonical market, e.g. Cybersecurity")
    ap.add_argument("--prior", help="previous version of the delivery (repair class B)")
    ap.add_argument("--db", default=r"C:\Users\matts\AppData\Local\CFP-Monitor\cfp_monitor.db")
    ap.add_argument("--max-rounds", type=int, default=2)
    ap.add_argument("--max-requests", type=int, default=10,
                    help="hard cap on Gemini calls per round, retries included")
    ap.add_argument("--attempts", type=int, default=2, help="Gemini calls per row at most")
    ap.add_argument("--model", help="Gemini model for the upstream step (default: the audit's)")
    ap.add_argument("--links-via", choices=("crawl", "gemini"), default="crawl",
                    help="how link questions are answered. crawl (default) uses "
                         "find_replacement_links on the conference's own site and spends no Gemini "
                         "quota; gemini asks every question through Markets/answer_findings.py")
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
        if a.links_via == "crawl":
            if a.dry_run:
                n_links = sum(1 for i in findings["rows"] for p in i["problems"] if p["kind"] == "link")
                summary.append(f"- DRY RUN: {n_links} link question(s) would be crawled; nothing run")
                break
            answers = crawl_answers(findings, _live_hunt)
            answers_path.write_text(json.dumps(answers, indent=2, ensure_ascii=False), encoding="utf-8")
            code = 0
        else:
            answers = None
        if answers is None:
            cmd = ["py", str(Path(a.markets_dir) / "answer_findings.py"), "--findings", str(fpath),
                   "--max-requests", str(a.max_requests), "--attempts", str(a.attempts)]
            if a.model:
                cmd += ["--model", a.model]
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
            if isinstance(answers.get("health"), dict):
                HEALTH.merge(answers["health"])
        summary.append(f"- link questions answered via: {a.links_via}")
        for n in answers.get("not_asked", []):
            for_person.append(ForPerson(n, "not asked - over the request cap" if a.links_via == "gemini"
                                        else "not a link question - Saturday research or a person", ""))
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
    # HEALTH GOES FIRST. A degraded run's other sections describe what it could not see, so the
    # reader must meet the verdict before the results.
    status, _reasons = HEALTH.verdict()
    summary[2:2] = [f"    HEALTH:  {status}", ""] + HEALTH.report_lines() + [""]
    (work / "SUMMARY.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    (work / "health.json").write_text(json.dumps({"status": status, **HEALTH.to_dict()}, indent=2),
                                      encoding="utf-8")
    print("\n".join(summary))
    print(f"\n{HEALTH.banner()}")
    print(f"all artifacts: {work}")
    # Exit codes: 0 accepted, 1 not accepted, 2 DEGRADED - checked first, because an accepted
    # verdict from a run that could not see is not an acceptance anyone should act on.
    if status == "DEGRADED":
        return 2
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(main())
