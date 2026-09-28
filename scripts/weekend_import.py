"""Saturday research -> database -> promoted delivery, with no person in the loop.

    python scripts/weekend_import.py [--markets Cybersecurity Utility] [--research-exit N]
        [--sandbox <dir>] [--report <json>]

WHY (2026-09-27). Saturday's research wrote its results to Markets\\<Market>_audited.csv and
stopped. Everything after that - gate, repair, import, verify, reconcile, promote - was a set of
documented commands a person ran by hand (runbook sections 1-4b). When nobody ran them, Sunday's
verification checked LAST week's database and Monday's page published LAST week's file, or went
DEGRADED because the publish guard refused a stale one. The research was a week behind by
construction. This script is those same commands, in the runbook's order, run unattended.

THE ROW-BY-ROW RULE (agreed with the operator 2026-09-27)
The gate still judges a WHOLE file and still has the only say (one gate). What changes is which
rows go into the file it judges:
  - a row that passes ships as this week's research
  - a row that fails is replaced by LAST week's accepted version of the same event (matched
    through identity.to_canonical - contract 5.4, never a direct EVENT_ID comparison)
  - a row that fails with no accepted prior version, or whose prior version also fails now, is
    held back from this week's file. Its database record is untouched and it is declared in
    held_rows.txt (contract 2.1: a label, never a deletion)
The file that results must be ACCEPTED by the gate like any other before anything is imported.
Every substitution and hold is listed in the report, so nothing is decided silently.

WHAT A FAILURE DOES
  - research failed (non-zero exit, a market's output missing, short, or stale): nothing is
    imported and nothing is promoted. The database stays exactly as it was.
  - a market cannot reach ACCEPTED, or a gate failure cannot be tied to a row: that market is
    skipped; the other market still proceeds.
  - the import leaves the database unreconciled (check_invariants): the database, the seed
    sheets and held_rows.txt are restored from the backup taken at the start, and nothing is
    promoted. Nothing half-imported survives.

--sandbox <dir> copies the database and the seed sheets into <dir> and does everything there,
promoting into <dir> too - a full rehearsal that cannot touch the live data.

Every tool here already existed and is called as a subprocess, exactly as the runbook runs it:
mechanical_repairs.py, accept_delivery.py, import_grounding.py, verify_grounding.py,
fix_edition.py, check_invariants.py, promote_delivery.py. The only new logic is the row rule.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.cfp_monitor.identity import (SEED_FILES, assert_mapped, seed_map,   # noqa: E402
                                      to_canonical)

PY = sys.executable
MARKETS_DIR = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
LIVE = Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor"

# market -> (seed file name in market_sheets, upstream label for verify_grounding, canonical).
# Seed file names come from identity.SEED_FILES: the seed format has one owner.
MARKETS = {m: (SEED_FILES[m], m, m) for m in ("Cybersecurity", "Utility")}
# AWARDS (Friday 02:00, operator 2026-09-28) run the same rule through their own importer and
# tables (import_awards.py -> award_grounding_facts). No seed sheet: award_grounding_facts keeps
# upstream's id beside ours (upstream_event_id), and that column is the crossing.
MARKETS["Awards"] = (None, "Awards", "Awards")
AWARDS = "Awards"
# The gate truncates CONFERENCE to 40 characters (38 in two checks) at the front of a failure.
NAME_PREFIX = 38
MAX_ROUNDS = 3
MAX_OUTPUT_AGE_H = 30


# ============================================================================ csv helpers
def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        return list(rd.fieldnames or []), list(rd)


def write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def run(cmd: list[str], cwd: Path, log: list[str], timeout: int = 7200) -> int:
    t0 = time.time()
    try:
        p = subprocess.run([str(c) for c in cmd], cwd=str(cwd), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        rc, out = p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        rc, out = 124, f"TIMEOUT after {time.time() - t0:.0f}s"
    shown = [Path(str(cmd[1])).name] + [str(c) for c in cmd[2:]]
    log.append(f"$ {' '.join(shown)}  -> exit {rc} ({time.time() - t0:.0f}s)")
    log.append(out.rstrip())
    return rc


# ============================================================================ the gate
def gate(csv_path: Path, cwd: Path, log: list[str], network: bool = True,
         db: Path | None = None, market: str | None = None) -> tuple[str, list[tuple[str, str]], Path]:
    """Run THE gate. Returns (verdict, [(check, failure text)], json path).

    ACCEPTED means every check passed and none was skipped - accept_delivery's own rule.
    """
    js = csv_path.with_name(csv_path.stem + (".gate.json" if network else ".gate-db.json"))
    cmd = [PY, ROOT / "scripts" / "accept_delivery.py", csv_path, "--json", js]
    if not network:
        cmd.append("--no-network")
    if db and market:
        cmd += ["--db", db, "--market", market]
    run(cmd, cwd, log)
    if not js.exists():
        return "NO-RESULT", [("?", "the gate wrote no result file")], js
    payload = json.loads(js.read_text(encoding="utf-8"))
    fails, skipped = [], False
    for results in payload.values():
        for r in results:
            if r.get("passed"):
                continue
            for f in r.get("failures", []):
                if str(f).startswith("SKIPPED"):
                    skipped = True
                else:
                    fails.append((str(r.get("check")), str(f)))
    if fails:
        return "REJECTED", fails, js
    return ("ACCEPTED" if not skipped else "ACCEPTED-NO-NETWORK"), [], js


# ============================================================================ the row rule
def rows_for_failure(text: str, rows: list[dict]) -> list[int]:
    """Which rows a gate failure names. The gate writes CONFERENCE[:40] (or [:38]) first.

    Deliberately greedy: rows that share a 38-character prefix (three Gartner Security & Risk
    Management Summits do) are ALL taken, because holding a passing row costs one row of
    freshness while shipping a failing one costs the whole file.
    """
    hits = []
    for i, r in enumerate(rows):
        name = (r.get("CONFERENCE") or "").strip()
        if name and text.startswith(name[:NAME_PREFIX]):
            hits.append(i)
    return hits


def map_failures(fails: list[tuple[str, str]], rows: list[dict]) -> tuple[dict[int, list[str]], list[str]]:
    """{row index: [reasons]} and the failures that name no row (which stop the market)."""
    by_row: dict[int, list[str]] = {}
    unmapped: list[str] = []
    for check, text in fails:
        idx = rows_for_failure(text, rows)
        if not idx:
            unmapped.append(f"[{check}] {text}")
        for i in idx:
            by_row.setdefault(i, []).append(f"[{check}] {text}")
    return by_row, unmapped


def apply_row_rule(rows: list[dict], sources: list[str], bad: dict[int, list[str]],
                   prior_by_canon: dict[str, dict], up_to_canon: dict[str, str],
                   decisions: list[dict]) -> tuple[list[dict], list[str]]:
    """Replace each failing row with last week's accepted version, or hold it back.

    `sources[i]` is "new" (this week's research) or "prior" (already substituted). A prior row
    that fails too is held back rather than substituted again - there is nothing older to use.
    """
    out_rows, out_src = [], []
    for i, (r, src) in enumerate(zip(rows, sources)):
        if i not in bad:
            out_rows.append(r)
            out_src.append(src)
            continue
        canon = to_canonical(r.get("EVENT_ID", ""), up_to_canon)
        prior = prior_by_canon.get(canon)
        entry = {"conference": r.get("CONFERENCE", ""), "canonical": canon, "reasons": bad[i]}
        if src == "new" and prior is not None:
            out_rows.append(prior)
            out_src.append("prior")
            decisions.append({**entry, "action": "kept-last-week"})
        else:
            # A held row is removed from this week's FILE only. Its database row stays, and
            # it is declared in held_rows.txt before reconciliation.
            if src == "prior":
                decisions[:] = [d for d in decisions
                                if not (d["canonical"] == canon
                                        and d["action"] in ("kept-last-week", "carried-over"))]
            decisions.append({**entry, "action": "held-back",
                              "why_no_prior": "last week's version fails now too" if src == "prior"
                              else "no accepted version from last week"})
    return out_rows, out_src


# ============================================================================ per market
def check_research(market: str, markets_dir: Path, research_exit: int | None) -> str | None:
    """Why this market's research cannot be used, or None if it can."""
    if research_exit not in (None, 0):
        return f"the research run exited {research_exit} (3 = out of quota, 4 = search collapsed)"
    out = markets_dir / f"{market}_audited.csv"
    inp = markets_dir / f"{market}_input.csv"
    if not out.exists():
        return f"no research output at {out.name}"
    age_h = (time.time() - out.stat().st_mtime) / 3600
    if age_h > MAX_OUTPUT_AGE_H:
        return f"{out.name} is {age_h:.0f}h old - this weekend's research did not write it"
    if inp.exists():
        # rows labelled DUP_OF are skipped by the audit on purpose (one award listed twice), so
        # they are not "missing" - the awards list carries 14
        n_in = sum(1 for r in read_csv(inp)[1] if not (r.get("DUP_OF") or "").strip())
        n_out = len(read_csv(out)[1])
        if n_out < n_in:
            return f"{out.name} holds {n_out} rows for {n_in} input rows - the run stopped short"
    return None


def resolve_market(market: str, markets_dir: Path, work: Path, db: Path,
                   up_to_canon: dict[str, str], log: list[str],
                   ledger: Path | None = None) -> dict:
    """Repair, gate, apply the row rule until the gate ACCEPTS. Touches no database."""
    res: dict = {"market": market, "status": "FAILED", "decisions": []}
    src = markets_dir / f"{market}_audited.csv"
    prior_path = markets_dir / f"{market}_audited.final.csv"
    if market == AWARDS:
        # Before the first Friday run the awards page was built from the newest dated research
        # output, never promoted; that file is last week's accepted version for the row rule.
        from scripts.stamp_input_ids import published_awards
        prior_path = published_awards(markets_dir) or prior_path
        up_to_canon = award_lookup(db)
    res["input"] = str(markets_dir / f"{market}_input.csv")
    cols, new_rows = read_csv(src)
    res["rows"] = len(new_rows)
    res["stubs"] = sum(1 for r in new_rows if "Audit Exception" in (r.get("STATUS DETAILS") or ""))

    # 1. mechanical repairs (contract v2.4), on a copy. It never changes a claim.
    stage = work / f"{market}_audited.csv"
    shutil.copy2(src, stage)
    rep_cmd = [PY, ROOT / "scripts" / "mechanical_repairs.py", stage, "--apply", "--no-gate"]
    if prior_path.exists():
        rep_cmd += ["--prior", prior_path]
    if ledger:
        rep_cmd += ["--ledger", ledger]
    run(rep_cmd, work, log)
    repaired = stage.with_name(stage.stem + ".repaired.csv")
    base = repaired if repaired.exists() else stage
    cols, rows = read_csv(base)
    res["repairs_log"] = str(stage.with_name(stage.stem + ".repairs.md"))

    prior_by_canon: dict[str, dict] = {}
    if prior_path.exists():
        pcols, prows = read_csv(prior_path)
        for r in prows:
            prior_by_canon.setdefault(to_canonical(r.get("EVENT_ID", ""), up_to_canon), r)

    # IDENTITY IS CARRIED, NOT REBUILT (2026-09-27). Each researched row lands on the permanent
    # id of the input event it answers. A row with no such id - or a stub, which holds only the
    # input list's older data - is treated as failing from the start, so the row rule gives it
    # last week's version or holds it back. Nothing is ever loaded under an id derived from a
    # name the model may have changed.
    identity = load_identity(markets_dir, market, read_csv(src)[1])
    known = award_ids(db) if market == AWARDS else db_ids(db)
    canon_of: dict[str, str] = {}
    pre_bad: dict[int, list[str]] = {}
    seen_canon: set[str] = set()
    for i, r in enumerate(rows):
        c = identity.get((r.get("EVENT_ID") or "").strip(), "")
        if "Audit Exception" in (r.get("STATUS DETAILS") or ""):
            pre_bad[i] = ["not researched this week (every search attempt failed)"]
        elif not c or c not in known:
            pre_bad[i] = ["no permanent id - cannot tell for certain which event this is, so it "
                          "is not loaded (a rename would otherwise create a duplicate)"]
        elif c in seen_canon:
            pre_bad[i] = [f"a second row for the same event ({c})"]
        if c:
            canon_of[(r.get("EVENT_ID") or "").strip()] = c
            seen_canon.add(c)
    # the row rule looks prior versions up by canonical id; give it the carried ids
    lookup = {**up_to_canon, **canon_of}
    sources = ["new"] * len(rows)
    if pre_bad:
        rows, sources = apply_row_rule(rows, sources, pre_bad, prior_by_canon, lookup,
                                       res["decisions"])
    # Last week's events that no row of this week's research covers stay on the page as they were.
    claimed = {to_canonical(r.get("EVENT_ID", ""), lookup) for r in rows}
    # One EVENT_ID per market in a file (gate R8c). A carried-over row whose id another row
    # already holds would make the whole file unacceptable, so it is held back and listed.
    taken = {((r.get("Market") or "").strip(), (r.get("EVENT_ID") or "").strip()) for r in rows}
    for c, pr in prior_by_canon.items():
        slot = ((pr.get("Market") or "").strip(), (pr.get("EVENT_ID") or "").strip())
        if c not in claimed and slot in taken:
            res["decisions"].append({"conference": pr.get("CONFERENCE", ""), "canonical": c,
                                     "reasons": ["another row in this week's file already uses its id"],
                                     "action": "held-back", "why_no_prior": "id collision"})
            continue
        if c not in claimed:
            taken.add(slot)
            rows.append(pr)
            sources.append("prior")
            res["decisions"].append({"conference": pr.get("CONFERENCE", ""), "canonical": c,
                                     "reasons": ["not covered by this week's research"],
                                     "action": "carried-over"})

    # 2. gate -> row rule -> gate, until ACCEPTED
    cand = work / f"{market}_audited.candidate.csv"
    for rnd in range(1, MAX_ROUNDS + 1):
        write_csv(cand, cols, rows)
        verdict, fails, js = gate(cand, work, log, network=True)
        log.append(f"[{market}] round {rnd}: {verdict}, {len(fails)} failure(s)")
        if verdict == "ACCEPTED":
            ids_csv = work / f"{market}_ids.csv"
            write_ids(ids_csv, rows, lookup)
            res["ids_csv"] = str(ids_csv)
            res["carried_over"] = sum(1 for d in res["decisions"] if d["action"] == "carried-over")
            res.update(status="ACCEPTED", candidate=str(cand), accept_json=str(js),
                       shipped=len(rows),
                       from_this_week=sum(1 for s in sources if s == "new"),
                       from_last_week=sum(1 for s in sources if s == "prior"),
                       rounds=rnd)
            res["held_back"] = sum(1 for d in res["decisions"] if d["action"] == "held-back")
            return res
        if verdict != "REJECTED":
            res["why"] = f"the gate did not run to completion ({verdict})"
            return res
        bad, unmapped = map_failures(fails, rows)
        if unmapped:
            res["why"] = ("the gate rejected the file for something not tied to one row, so the "
                          "row rule cannot fix it: " + "; ".join(unmapped[:3]))
            return res
        rows, sources = apply_row_rule(rows, sources, bad, prior_by_canon, lookup,
                                       res["decisions"])
    res["why"] = f"still not ACCEPTED after {MAX_ROUNDS} rounds"
    return res


def load_identity(markets_dir: Path, market: str, out_rows: list[dict]) -> dict[str, str]:
    """{output EVENT_ID: permanent canonical id} for this week's research.

    Read from <Market>_audited.identity.csv, which run_market_audit writes row by row. Research
    written before that file existed is linked through the progress ledger instead: the ledger
    records the INPUT name of each output row, in the same order, and the input list carries
    EVENT_ID_CANON (stamp_input_ids.py). Either way the id comes from the input, never the name.
    """
    ident = markets_dir / f"{market}_audited.identity.csv"
    if ident.exists():
        return {r["OUTPUT_EVENT_ID"].strip(): (r.get("EVENT_ID_CANON") or "").strip()
                for r in read_csv(ident)[1]}
    ledger = markets_dir / f"{market}_audited.progress.txt"
    inp = markets_dir / f"{market}_input.csv"
    if not (ledger.exists() and inp.exists()):
        return {}
    names = [l.strip() for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
    if len(names) != len(out_rows):
        return {}          # the pairing is only exact when the two line up one-to-one
    # ...and only when the ORDER still holds. A file patched after the run (rows added,
    # re-cut, reordered - the 2026-09-05 awards file was) keeps the same length with every pair
    # shifted, and a positional pairing then hands awards each other's ids (found in the first
    # awards rehearsal, 2026-09-28). Research renames some rows but keeps most names, so fewer
    # than half matching exactly means the order is gone: trust nothing, guess nothing.
    same = sum(1 for o, n in zip(out_rows, names) if (o.get("CONFERENCE") or "").strip() == n)
    if same * 2 < len(names):
        return {}
    by_name = {r["CONFERENCE"].strip(): (r.get("EVENT_ID_CANON") or "").strip()
               for r in read_csv(inp)[1]}
    return {(o.get("EVENT_ID") or "").strip(): by_name.get(n, "") for o, n in zip(out_rows, names)}


def write_ids(path: Path, rows: list[dict], lookup: dict[str, str]) -> None:
    """The EVENT_ID -> canonical map import_grounding --ids lands every row on."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["EVENT_ID", "EVENT_ID_CANON"])
        for r in rows:
            e = (r.get("EVENT_ID") or "").strip()
            w.writerow([e, to_canonical(e, lookup)])


# ============================================================================ database phase
def backup(paths: list[Path], stamp: str) -> dict[Path, Path]:
    saved = {}
    for p in paths:
        if p.exists():
            b = p.with_name(f"{p.name}.pre-weekend-{stamp}")
            shutil.copy2(p, b)
            saved[p] = b
    return saved


def restore(saved: dict[Path, Path]) -> None:
    for p, b in saved.items():
        shutil.copy2(b, p)


def db_ids(db: Path) -> set[str]:
    import sqlite3
    con = sqlite3.connect(str(db))
    try:
        return {r[0] for r in con.execute("select event_id from grounding_facts")}
    finally:
        con.close()


def award_ids(db: Path) -> set[str]:
    import sqlite3
    con = sqlite3.connect(str(db))
    try:
        return {r[0] for r in con.execute("select event_id from award_grounding_facts")}
    finally:
        con.close()


def award_lookup(db: Path) -> dict[str, str]:
    """upstream EVENT_ID -> our award id, from the column import_awards keeps for this (5.4)."""
    import sqlite3
    con = sqlite3.connect(str(db))
    try:
        return {(u or "").strip(): e for e, u in
                con.execute("select event_id, upstream_event_id from award_grounding_facts") if u}
    finally:
        con.close()


def declare_held(held_file: Path, entries: list[tuple[str, str]]) -> int:
    """Append `<event_id>  # <reason>` lines for ids not already declared."""
    have = set()
    if held_file.exists():
        for line in held_file.read_text(encoding="utf-8").splitlines():
            s = line.split("#", 1)[0].strip()
            if s:
                have.add(s)
    new = [(i, why) for i, why in entries if i and i not in have]
    if new:
        with open(held_file, "a", encoding="utf-8") as fh:
            for i, why in new:
                fh.write(f"{i}  # AUTO {datetime.now():%Y-%m-%d} weekend_import - {why}\n")
    return len(new)


def invariant_failures(out: str) -> dict[str, list[str]]:
    fails: dict[str, list[str]] = {}
    check = None
    for line in out.splitlines():
        m = re.match(r"^\s*\[FAIL\]\s+(\S+)", line)
        if m:
            check = m.group(1)
            fails.setdefault(check, [])
            continue
        if re.match(r"^\s*\[(ok|warn|skip)", line) or line.startswith("RESULT:"):
            check = None
            continue
        m = re.match(r"^\s{4,}- (\S+)", line)
        if check and m:
            fails[check].append(m.group(1))
    return fails


def load_markets(resolved: list[dict], db: Path, data_root: Path, log: list[str]) -> str | None:
    """Import, verify, re-gate with the database, reconcile. None on success, else why."""
    for res in resolved:
        m = res["market"]
        seed_name, label, canon = MARKETS[m]
        cand = Path(res["candidate"])
        if m == AWARDS:
            # import_awards re-reads the gate's own JSON and refuses anything not ACCEPTED, and
            # lands each row on its carried id. Awards have no verify_grounding / fix_edition /
            # conference-criteria pass; Monday re-checks their deadlines and links
            # (check_award_deadlines, link_check_awards), and invariants 10-15 reconcile them.
            rc = run([PY, ROOT / "scripts" / "import_awards.py", cand, "--db", db,
                      "--gate-json", res["accept_json"], "--seed", res["input"],
                      "--ids", res["ids_csv"], "--source-list",
                      f"weekly-awards-{datetime.now():%Y%m%d}", "--apply"], data_root, log)
            if rc != 0:
                return f"{m}: import_awards exited {rc}"
            continue
        rc = run([PY, ROOT / "scripts" / "import_grounding.py", cand,
                  "--out", f"market_sheets/{seed_name}", "--seed", db,
                  "--ids", res["ids_csv"]], data_root, log)
        if rc != 0:
            return f"{m}: import_grounding exited {rc}"
        # verify BETWEEN import and reconcile: skipping it leaves every new row with no verify
        # state, which check 4 reports (runbook, 2026-09-20).
        rc = run([PY, ROOT / "scripts" / "verify_grounding.py", "--db", db, "--market", label,
                  "--seed-csv", f"market_sheets/{seed_name}", "--layers", "012", "--apply"],
                 data_root, log)
        if rc != 0:
            return f"{m}: verify_grounding exited {rc}"
        # key_year is frozen by fix_edition; a new row without it fails invariant 7.
        rc = run([PY, ROOT / "scripts" / "fix_edition.py", "--db", db, "--delivery", cand,
                  "--apply"], data_root, log)
        if rc != 0:
            return f"{m}: fix_edition exited {rc}"
        verdict, fails, _ = gate(cand, data_root, log, network=False, db=db, market=canon)
        if verdict not in ("ACCEPTED", "ACCEPTED-NO-NETWORK"):
            return (f"{m}: the gate with the database loaded said {verdict}: "
                    + "; ".join(f"[{c}] {t}" for c, t in fails[:3]))

    held = data_root / "market_sheets" / "held_rows.txt"
    in_db = db_ids(db)
    up_to_canon, _ = seed_map(str(db))
    entries = []
    for res in resolved:
        for d in res["decisions"]:
            if d["action"] == "held-back" and d["canonical"] in in_db:
                entries.append((d["canonical"], f"held back from this week's file by the row "
                                f"rule: {'; '.join(d['reasons'])[:200]}"))
    n = declare_held(held, entries)
    if n:
        log.append(f"declared {n} held-back row(s) in held_rows.txt")

    seed_dir = data_root / "market_sheets"
    awards_cand = [r["candidate"] for r in resolved if r["market"] == AWARDS]
    awards_seed = [r["input"] for r in resolved if r["market"] == AWARDS]
    for attempt in (1, 2):
        out: list[str] = []
        inv = [PY, ROOT / "scripts" / "check_invariants.py", "--db", db, "--seed-dir", seed_dir]
        if awards_cand:
            # checks 14-15, the awards half; --awards-seed so its DUP_OF exclusions are known
            inv += ["--awards-delivery", awards_cand[0], "--awards-seed", awards_seed[0]]
        rc = run(inv, data_root, out)
        log.extend(out)
        if rc == 0:
            return None
        fails = invariant_failures("\n".join(out))
        # A row the database holds and this week's delivery does not - an event upstream renamed
        # or dropped - is contract 2.1's case exactly: label it, never delete it. Only check 2,
        # and only once; anything else is a real reconciliation failure.
        if attempt == 1 and set(fails) == {"2"} and fails["2"]:
            declare_held(held, [(i, "in the database, absent from this weekend's delivery "
                                    "(renamed or dropped upstream) - review") for i in fails["2"]])
            log.append(f"declared {len(fails['2'])} undeclared extra row(s); re-checking")
            continue
        return "the database did not reconcile after import: failed checks " + ", ".join(sorted(fails))
    return "the database did not reconcile after import"


# ============================================================================ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--markets", nargs="+", default=list(MARKETS))
    ap.add_argument("--research-exit", type=int, help="run_monthly's research exit code")
    ap.add_argument("--markets-dir", default=str(MARKETS_DIR))
    ap.add_argument("--live", default=str(LIVE), help="the live build (database + market_sheets)")
    ap.add_argument("--sandbox", help="rehearse on copies in this directory; touches nothing live")
    ap.add_argument("--report", help="write the result JSON here (default: <work>/weekend_import.json)")
    args = ap.parse_args()

    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
    markets_dir = Path(args.markets_dir)
    live = Path(args.live)
    if args.sandbox:
        data_root = Path(args.sandbox)
        data_root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(live / "cfp_monitor.db", data_root / "cfp_monitor.db")
        # the whole folder: a rehearsal must see exactly what the live load would
        shutil.copytree(live / "market_sheets", data_root / "market_sheets", dirs_exist_ok=True)
        final_dir = data_root
        # The repair ledger refuses a repeat repair in a later cycle; a rehearsal must not
        # record repairs that never shipped.
        repo_ledger = ROOT / "market_sheets" / "repair_ledger.txt"
        ledger = data_root / "market_sheets" / "repair_ledger.txt"
        if repo_ledger.exists():
            shutil.copy2(repo_ledger, ledger)
    else:
        ledger = None
        data_root = live
        final_dir = markets_dir
    db = data_root / "cfp_monitor.db"
    work = markets_dir / "weekend" / stamp if not args.sandbox else data_root / "work"
    work.mkdir(parents=True, exist_ok=True)
    log: list[str] = [f"weekend_import {stamp} - {'SANDBOX ' + str(data_root) if args.sandbox else 'LIVE'}"]
    report = {"stamp": stamp, "mode": "sandbox" if args.sandbox else "live",
              "markets": [], "database": "unchanged", "status": "FAILED"}
    report_path = Path(args.report) if args.report else work / "weekend_import.json"

    def finish(status: str, why: str = "") -> int:
        report["status"], report["why"] = status, why
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        (work / "weekend_import.log").write_text("\n".join(log), encoding="utf-8")
        print(f"WEEKEND IMPORT: {status}{' - ' + why if why else ''}")
        for m in report["markets"]:
            print(f"  {m['market']}: {m['status']}"
                  + (f" - {m.get('shipped')} rows shipped ({m.get('from_this_week')} this week, "
                     f"{m.get('from_last_week')} kept from last week, {m.get('held_back')} held back)"
                     if m["status"] in ("ACCEPTED", "PROMOTED") else f" - {m.get('why', '')}"))
        print(f"  report: {report_path}")
        return 0 if status in ("DONE", "PARTIAL") else 1

    up_to_canon, roots = seed_map(str(db))
    assert_mapped(up_to_canon, roots, minimum=50)

    resolved = []
    for m in args.markets:
        if m not in MARKETS:
            report["markets"].append({"market": m, "status": "SKIPPED",
                                      "why": "no customer page for this market"})
            continue
        why = check_research(m, markets_dir, args.research_exit)
        if why:
            report["markets"].append({"market": m, "status": "FAILED", "why": why})
            continue
        res = resolve_market(m, markets_dir, work, db, up_to_canon, log, ledger)
        report["markets"].append(res)
        if res["status"] == "ACCEPTED":
            resolved.append(res)

    if not resolved:
        return finish("FAILED", "no market reached an accepted file - the database was not touched")

    saved = backup([db, data_root / "market_sheets" / "held_rows.txt"]
                   + [data_root / "market_sheets" / MARKETS[r["market"]][0] for r in resolved
                      if MARKETS[r["market"]][0]], stamp)
    report["backup"] = str(saved.get(db, ""))
    why = load_markets(resolved, db, data_root, log)
    if why:
        restore(saved)
        for r in resolved:
            r["status"], r["why"] = "FAILED", "import rolled back: " + why
        return finish("FAILED", f"{why} - database restored from the backup, nothing promoted")
    report["database"] = "updated"

    for r in resolved:
        m = r["market"]
        rc = run([PY, ROOT / "scripts" / "promote_delivery.py", "--delivery", r["candidate"],
                  "--accept-json", r["accept_json"], "--market", m,
                  "--final", final_dir / f"{m}_audited.final.csv"], data_root, log)
        r["status"] = "PROMOTED" if rc == 0 else "ACCEPTED"
        if rc != 0:
            r["why"] = f"promote_delivery exited {rc}"

    ok = all(m["status"] == "PROMOTED" for m in report["markets"] if m["status"] != "SKIPPED")
    return finish("DONE" if ok else "PARTIAL")


if __name__ == "__main__":
    raise SystemExit(main())
