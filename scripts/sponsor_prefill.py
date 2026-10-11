"""Sponsor check, cost cut (ACT-64): put last week's settled sponsorship answer into the NEW research file BEFORE the sponsor-only pass, so the pass skips it. FAILURE-ISOLATED; exit code 0 always.

    python scripts/sponsor_prefill.py --market Cybersecurity [--apply] [--today 2026-10-17] [--markets-dir <dir>] [--db <db>] [--out-dir <dir>] [--prior <approved csv>]

WHY (docs/design/sponsor-check-cost-plan.md). The pass in Markets/run_market_audit.py (run_sponsor_only_pass) asks only rows whose SPONSOR_REQUIRED is blank or Unknown and writes a Yes/No row through for
free. But every Saturday run_monthly.ps1 archives last week's audited file and the new research starts with BLANK sponsor cells, so every row is asked again (2026-10-10: about 235 requests, about 44 USD,
104 of 219 repeated an answer held from last week). scripts/sponsor_carry.py puts the old answer back AFTER the fact (kept as it is). This script does it BEFORE, for rows that qualify. The pass is not changed.

A row is CARRIED (SPONSOR_REQUIRED, SPONSOR_URL, SPONSOR_COST copied from last week's row; SPONSOR_QUOTE is left to sponsor_carry's rule 4 in the import, which fills a blank quote when the answer is the same) only when ALL hold:
  1. the same permanent id (identity.to_canonical on both sides; this week's id from <Market>_audited.identity.csv, never by name and never a direct join on upstream ids) and the same non-blank EDITION;
  2. last week's SPONSOR_REQUIRED is Yes or No (Unknown and blank are never carried);
  3. for a Yes: last week's SPONSOR_URL is present and is not RECORDED DEAD in `link_checks` (opened mode=ro). A blank URL or a recorded-dead link means ask again. A URL with NO record
     (the weekly sweep does not cover sponsor_url yet) is carried, and the 8-week rotation is the safety net; `--missing-link-asks` (constant MISSING_LINK_ASKS) makes it ask instead;
  4. the row is not due for the re-check. SETTLED rows: due when stable_hash(canonical id) % 8 equals this week's number % 8 (about 1/8 of rows each week, each row once in 8 weeks, none twice in a window;
     scripts/refresh_plan.stable_hash), or when carry_ledger.json says the sponsorship unit was last confirmed 8 weeks ago or more (a safety net on top of the rotation). UNKNOWN rows follow the same
     idea with 2 buckets (half each week). A first-time event (no prior row) is always asked.
Where last week's row comes from: <Market>_audited.final.csv (the approved file) first, then the newest archived <Market>_audited*.csv under archive/<month>, so an event that never shipped keeps its answer.
Any doubt (two prior rows disagreeing, two new rows for one id, an unreadable cell, no id) means carry NOTHING for that row. Any exception means carry nothing at all: print `SPONSOR-PREFILL: UNKNOWN - <why>`, exit 0.

KNOWN LIMIT, stated plainly: the unchanged pass treats every blank or Unknown cell as pending, so an Unknown row cannot be SKIPPED by anything this script writes. The 2-week Unknown rotation is computed and
reported (reason `unknown_deferred`) but those rows are still asked until run_market_audit.py learns to honour it (a change that is the reviewer's, not made here). Settled rows are skipped as designed.

DEFAULT IS A DRY RUN: only the report is written (runs_out/qa/<date>/sponsor_prefill_<market>.csv and .md). `--apply` writes the cells into <Market>_audited.csv through scripts/approved_edit.write_approved:
timestamped backup first, then a read-back proving that ONLY the three sponsor cells of carried rows changed. A second apply finds nothing left to carry and changes nothing (no backup written)."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.approved_edit import read_approved, write_approved   # noqa: E402
from scripts.carry_age import load_ledger                         # noqa: E402
from scripts.refresh_plan import stable_hash                      # noqa: E402
from src.cfp_monitor import identity, qa_report                   # noqa: E402

MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
LIVE_DB = Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor" / "cfp_monitor.db"
CELLS = ("SPONSOR_REQUIRED", "SPONSOR_URL", "SPONSOR_COST")
MISSING_LINK_ASKS = False     # reviewer 2026-10-11: a Yes whose link has NO link_checks record is carried (the sweep does not cover sponsor_url yet); True = ask again (the strict rule, one switch away)
SETTLED_WEEKS = 8            # operator decision 2026-10-11
UNKNOWN_WEEKS = 2
REPORT_COLS = ["market", "row", "canonical", "conference", "edition", "decision", "reason", "link", "prior_source", "prior_answer", "detail"]
REASONS = ("carried", "new_event", "unknown_ask", "unknown_deferred", "due_recheck", "link_dead", "link_missing", "edition_changed", "doubt")


def cell(row: dict, col: str) -> str:
    return (row.get(col) or "").strip()


def week_number(d: date) -> int:
    """Monday-based week count: constant from Monday to Sunday, so a Saturday 02:00 run that crosses midnight stays in one week."""
    return (d.toordinal() - 1) // 7


def settled_due(canon: str, today: date, ledger: dict) -> tuple[bool, str]:
    if stable_hash(canon) % SETTLED_WEEKS == week_number(today) % SETTLED_WEEKS:
        return True, f"rotation slot {stable_hash(canon) % SETTLED_WEEKS} of {SETTLED_WEEKS} falls this week"
    conf = (((ledger.get(canon) or {}).get("units") or {}).get("sponsorship") or {}).get("confirmed", "")
    try:
        age = (today - date.fromisoformat(conf[:10])).days
    except ValueError:
        return False, ""
    if age >= SETTLED_WEEKS * 7:
        return True, f"carry ledger: sponsorship last confirmed {conf}, {age // 7} weeks ago"
    return False, ""


def unknown_asked_now(canon: str, today: date) -> bool:
    return stable_hash(canon) % UNKNOWN_WEEKS == week_number(today) % UNKNOWN_WEEKS


def url_keys(u: str) -> set[str]:
    u = (u or "").strip()
    return {u, u.rstrip("/")} if u else set()


def link_state(url: str, states: dict[str, str]) -> str:
    """'alive' | 'dead' | 'missing'. Only an explicit alive counts as alive; two spellings of one URL that disagree are a doubt (reported as missing)."""
    seen = {states[k] for k in url_keys(url) if k in states}
    if not seen:
        return "missing"
    if seen == {"alive"}:
        return "alive"
    return "dead" if "dead" in seen and "alive" not in seen else "missing"


def read_link_states(db: Path) -> dict[str, str]:
    con = sqlite3.connect(f"file:{str(db).replace(chr(92), '/')}?mode=ro", uri=True)
    try:
        out: dict[str, str] = {}
        for url, state in con.execute("select url, state from link_checks where url is not null"):
            out[(url or "").strip()] = (state or "").strip().lower()
        return out
    finally:
        con.close()


def read_identity(path: Path) -> dict[str, str]:
    if not Path(path).exists():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return {(r.get("OUTPUT_EVENT_ID") or "").strip(): (r.get("EVENT_ID_CANON") or "").strip() for r in csv.DictReader(fh)}


def archived_candidates(markets_dir: Path, market: str) -> list[Path]:
    """The archived audited files of a market, newest first. Only <Market>_audited.csv and <Market>_audited.<stamp>.csv: never identity, progress, backup, grounding or tmp files."""
    pat = re.compile(rf"^{re.escape(market)}_audited(\.\d{{8}}-\d{{6}})?\.csv$")
    files = [p for p in (Path(markets_dir) / "archive").glob("*/*.csv") if pat.match(p.name)]
    return sorted(files, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)


def load_priors(markets_dir: Path, market: str, up_to_canon: dict[str, str], approved: Path | None = None,
                archived: Path | None = None) -> tuple[dict[str, list[tuple[dict, str]]], list[str]]:
    """{canonical: [(row, source label), ...]} from the approved file and then the newest archived file, plus notes on where it looked. The first source holding the event wins."""
    notes: list[str] = []
    sources: list[tuple[Path, str, dict[str, str]]] = []
    appr = approved or Path(markets_dir) / f"{market}_audited.final.csv"
    if appr.exists():
        sources.append((appr, "approved " + appr.name, up_to_canon))
    else:
        notes.append(f"approved file {appr} not found")
    arch = archived
    if arch is None:
        cands = archived_candidates(markets_dir, market)
        arch = cands[0] if cands else None
    if arch is not None:
        sources.append((arch, f"archive {arch.parent.name}/{arch.name}", {**up_to_canon, **read_identity(arch.parent / f"{market}_audited.identity.csv")}))
    else:
        notes.append("no archived audited file found")
    out: dict[str, list[tuple[dict, str]]] = {}
    for path, label, lookup in sources:
        _cols, rows, _b, _c = read_approved(path)
        here: dict[str, list[tuple[dict, str]]] = {}
        for r in rows:
            canon = identity.to_canonical(r.get("EVENT_ID", ""), lookup)
            if canon:
                here.setdefault(canon, []).append((r, label))
        for canon, lst in here.items():
            out.setdefault(canon, lst)                      # the first source that holds the event wins
        notes.append(f"{label}: {len(rows)} rows")
    return out, notes


def plan(rows: list[dict], canons: list[str], priors: dict[str, list[tuple[dict, str]]], states: dict[str, str], ledger: dict, today: date,
         missing_link_asks: bool = MISSING_LINK_ASKS) -> list[dict]:
    """One decision per row of the new file. Pure. decision is carry | ask | skip."""
    count: dict[str, int] = {}
    for c in canons:
        if c:
            count[c] = count.get(c, 0) + 1
    out = []
    for i, (row, canon) in enumerate(zip(rows, canons)):
        d = {"market": row.get("Market", ""), "row": i, "canonical": canon, "conference": cell(row, "CONFERENCE"), "edition": cell(row, "EDITION"),
             "decision": "ask", "reason": "", "link": "", "prior_source": "", "prior_answer": "", "detail": "", "values": None}
        out.append(d)
        cur = cell(row, "SPONSOR_REQUIRED").lower()
        if cell(row, "DUP_OF"):
            d.update(decision="skip", reason="duplicate_row", detail="DUP_OF is set: the pass never asks it")
            continue
        if cur in ("yes", "no"):
            d.update(decision="skip", reason="already_answered", detail=f"this file already holds {cell(row, 'SPONSOR_REQUIRED')}: never touched")
            continue
        if not canon:
            d.update(reason="doubt", detail="no permanent id for this row")
            continue
        if count.get(canon, 0) > 1:
            d.update(reason="doubt", detail="more than one row in this file for the same permanent id")
            continue
        pri = priors.get(canon)
        if not pri:
            d.update(reason="new_event", detail="no row for this event in the approved file or the archive")
            continue
        prow, src = pri[0]
        d["prior_source"] = src
        if len({tuple(cell(r, c) for c in CELLS + ("EDITION",)) for r, _ in pri}) > 1:
            d.update(reason="doubt", detail="more than one prior row for this id and they differ")
            continue
        prior = cell(prow, "SPONSOR_REQUIRED")
        d["prior_answer"] = prior
        if prior.lower() not in ("yes", "no"):
            if unknown_asked_now(canon, today):
                d.update(reason="unknown_ask", detail="prior answer Unknown or blank; its 2-week slot falls this week")
            else:
                d.update(reason="unknown_deferred", detail="prior answer Unknown or blank; its 2-week slot does not fall this week, but the unchanged pass asks any blank anyway")
            continue
        if not cell(row, "EDITION") or cell(row, "EDITION") != cell(prow, "EDITION"):
            d.update(reason="edition_changed", detail=f"edition {cell(prow, 'EDITION') or '(blank)'} -> {cell(row, 'EDITION') or '(blank)'}")
            continue
        if prior.lower() == "yes":
            url = cell(prow, "SPONSOR_URL")
            if not url:
                d.update(reason="link_missing", detail="a Yes with a blank sponsor link")
                continue
            st = link_state(url, states)
            if st == "dead":
                d.update(reason="link_dead", detail=f"sponsor link is recorded dead in link_checks: {url}")
                continue
            if st == "missing" and missing_link_asks:
                d.update(reason="link_missing", detail=f"sponsor link has no (clear) link_checks record and the strict rule is on: {url}")
                continue
            if st == "missing":
                d["link"] = "not_recorded"
        due, why = settled_due(canon, today, ledger)
        if due:
            d.update(reason="due_recheck", detail=why)
            continue
        d.update(decision="carry", reason="carried",
                 detail=("settled Yes, same edition, link not recorded in link_checks (carried; the 8-week rotation is the safety net)" if d.get("link") == "not_recorded"
                         else "settled Yes, same edition, link alive") if prior.lower() == "yes" else "settled No, same edition",
                 values={c: cell(prow, c) for c in CELLS})
        d["values"]["SPONSOR_REQUIRED"] = prior
    return out


def summarize(decisions: list[dict]) -> tuple[str, dict]:
    n = {k: 0 for k in REASONS}
    n["skip"] = 0
    n["carried_link_not_recorded"] = 0
    for d in decisions:
        if d["decision"] == "skip":
            n["skip"] += 1
        else:
            n[d["reason"]] += 1
            if d["reason"] == "carried" and d.get("link") == "not_recorded":
                n["carried_link_not_recorded"] += 1
    ask = len(decisions) - n["skip"] - n["carried"]
    unknown = n["unknown_ask"] + n["unknown_deferred"]
    other = n["doubt"]
    line = (f"SPONSOR-PREFILL: {n['carried']} carried, {ask} to ask ({n['new_event']} new, {unknown} unknown, {n['due_recheck']} due for re-check, "
            f"{n['link_dead'] + n['link_missing'] + n['edition_changed']} link dead/edition changed)")
    if other:
        line += f"; {other} asked for lack of certainty"
    if n["carried_link_not_recorded"]:
        line += f"; {n['carried_link_not_recorded']} of the carried have no link_checks record (link not recorded, carried)"
    if n["skip"]:
        line += f"; {n['skip']} already answered or duplicate (left as they are)"
    return line, n


def apply_values(path: Path, decisions: list[dict]) -> tuple[Path | None, int]:
    """Write the carried cells into the audited file: backup, read-back proof that exactly those cells changed. Returns (backup or None when nothing to change, cells changed)."""
    cols, before, bom, crlf = read_approved(path)
    missing = [c for c in CELLS if c not in cols]
    if missing:
        raise ValueError(f"{path.name} has no column(s) {missing}")
    after = [dict(r) for r in before]
    expect: set[tuple[int, str]] = set()
    for d in decisions:
        if d["decision"] != "carry":
            continue
        for c, v in d["values"].items():
            if cell(after[d["row"]], c) != v.strip():
                after[d["row"]][c] = v
                expect.add((d["row"], c))
    if not expect:
        return None, 0
    return write_approved(path, cols, before, after, bom, crlf, "sponsor-prefill", expect_cells=expect), len(expect)


def write_report(decisions: list[dict], market: str, out_dir: Path, line: str, counts: dict, meta: list[str]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cp = out_dir / f"sponsor_prefill_{market}.csv"
    with open(cp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=REPORT_COLS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows([{**d, "market": market} for d in decisions])
    mp = out_dir / f"sponsor_prefill_{market}.md"
    lines = [f"# Sponsor prefill - {market}", "", f"`{line}`", "", *[f"- {m}" for m in meta], "", "| reason | rows |", "|---|---|"]
    lines += [f"| {k if k != 'carried_link_not_recorded' else 'of which carried with link not recorded'} | {v} |" for k, v in counts.items() if v]
    for title, keys in (("Carried (not asked)", ("carried",)), ("Asked: why", tuple(k for k in REASONS if k != "carried"))):
        lines += ["", f"## {title}", ""]
        for d in decisions:
            if d["decision"] != "skip" and d["reason"] in keys:
                lines.append(f"- {d['conference'][:70]} [{d['canonical']}] {d['reason']}: {d['detail']}")
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return cp, mp


def run(market: str, markets_dir: Path, db: Path, today: date, out_dir: Path, apply: bool, prior: Path | None = None, ledger_path: Path | None = None,
        audited: Path | None = None, missing_link_asks: bool = MISSING_LINK_ASKS) -> str:
    audited = audited or Path(markets_dir) / f"{market}_audited.csv"
    if not audited.exists():
        raise FileNotFoundError(f"{audited} not found")
    cols, rows, _b, _c = read_approved(audited)
    if not all(c in cols for c in CELLS):
        raise ValueError(f"{audited.name} is missing a sponsor column")
    up_to_canon, roots = identity.seed_map(str(db))
    if not up_to_canon:
        raise RuntimeError(f"the EVENT_ID seed map is empty (looked in {[str(r) for r in roots]})")
    ident = read_identity(Path(markets_dir) / f"{market}_audited.identity.csv")
    canons = [ident.get((r.get("EVENT_ID") or "").strip(), "") or identity.to_canonical(r.get("EVENT_ID", ""), up_to_canon) for r in rows]
    priors, notes = load_priors(Path(markets_dir), market, up_to_canon, approved=prior)
    states = read_link_states(db)
    ledger = load_ledger(ledger_path or (Path(db).parent / "carry_ledger.json"))
    decisions = plan(rows, canons, priors, states, ledger, today, missing_link_asks)
    line, counts = summarize(decisions)
    meta = [f"date {today.isoformat()}, week number {week_number(today)} (settled slot {week_number(today) % SETTLED_WEEKS} of {SETTLED_WEEKS}, unknown slot {week_number(today) % UNKNOWN_WEEKS} of {UNKNOWN_WEEKS})",
            f"new file: {audited.name}, {len(rows)} rows", *notes, f"link_checks rows read: {len(states)}", f"carry ledger entries: {len(ledger)}",
            "mode: APPLY" if apply else "mode: DRY RUN (the audited file is not touched)"]
    if apply:
        bak, n = apply_values(audited, decisions)
        meta.append(f"applied: {n} cells changed, backup {bak.name if bak else '(none: nothing to change)'}")
    cp, mp = write_report(decisions, market, out_dir, line, counts, meta)
    return line + f"\nSPONSOR-PREFILL REPORT: {cp} ; {mp}"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--market", required=True)
    ap.add_argument("--apply", action="store_true", help="write the carried cells into <Market>_audited.csv (default: dry run, report only)")
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--out-dir", default="", help="default runs_out/qa/<today>")
    ap.add_argument("--prior", default="", help="the approved file to use as last week's answers (default <Market>_audited.final.csv)")
    ap.add_argument("--missing-link-asks", action="store_true", default=MISSING_LINK_ASKS,
                    help="strict: a Yes whose sponsor link has no link_checks record is asked again (default off: only a RECORDED dead link or a blank link asks)")
    ap.add_argument("--ledger", default="", help="carry_ledger.json (default beside the db)")
    a = ap.parse_args()
    try:
        today = date.fromisoformat(a.today)
        print(run(a.market, Path(a.markets_dir), Path(a.db), today, Path(a.out_dir) if a.out_dir else qa_report.QA_ROOT / a.today, a.apply,
                  Path(a.prior) if a.prior else None, Path(a.ledger) if a.ledger else None,
                  missing_link_asks=a.missing_link_asks))
    except BaseException as e:                              # nothing here may stop the Saturday job; carrying nothing is today's behaviour
        if isinstance(e, KeyboardInterrupt):
            raise
        print(f"SPONSOR-PREFILL: UNKNOWN - {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
