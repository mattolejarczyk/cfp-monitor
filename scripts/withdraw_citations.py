"""CARRY UPSTREAM'S WITHDRAWN DEADLINE CITATIONS into the approved files and the database, safely (ACT-46, failure point B3). Report-only unless --apply.

    python scripts/withdraw_citations.py --propose [--out withdrawals.csv]      # which rows qualify by our own data (a list to compare with upstream's)
    python scripts/withdraw_citations.py --file withdrawals.csv --source "upstream note 28"            # the plan: which cells change, nothing written
    python scripts/withdraw_citations.py --file withdrawals.csv --source "..." --apply [--markets-dir <dir>] [--db <db>]

WHY. Upstream withdrew the dead deadline citations of nine past editions and of OWASP USA, Argus and CES (R1: a withdrawn citation keeps the deadline, loses its page and quote). A sparse patch cannot carry
a blank (a blank means 'not part of this patch'), our own withdrawal rule refuses a passed deadline (`rules.may_withdraw_citation`: a page coming down after its deadline is not proof the citation was wrong),
and `apply_row_patch.py --withdraw` works on an undelivered file only. The citation fields are upstream's (contract section 3), so their declared withdrawal is carried here, deliberately and one row at a time.
INPUT. A CSV with the column EVENT_ID = OUR canonical id (contract 5.4: never an upstream id) and optionally `reason`. A DEADLINE_EVIDENCE_URL / DEADLINE_QUOTE column, if present, must be BLANK (it declares the
clear); any other non-blank column is refused: this tool blanks the citation and nothing else, apart from the consequence below.
WHAT IT CHANGES, per row, in the approved file (`<Market>_audited.final.csv`) and in `grounding_facts`: DEADLINE_EVIDENCE_URL and DEADLINE_QUOTE become blank; the deadline STAYS (R1); and because a deadline
without a page is a projection (R11) IS_PROJECTED becomes true and GROUNDING_CONFIDENCE `Projected (<edition>)` unless they already say so. A row whose citation page is ALIVE in `link_checks` is refused (a live page
is not a withdrawal: someone must say why); `--allow-alive` overrides, named. A row with a customer-worked status is reported by scripts/customer_context.py's rule, never touched here (these fields are not theirs).
SAFETY. Backups first (`*.pre-withdraw-<stamp>.bak.csv` beside each approved file, `cfp_monitor.pre-withdraw-<stamp>.db` made with SQLite's backup API); the approved file is read back and only the planned cells may
differ (scripts/approved_edit.py); the database update is guarded on the old URL; a ledger line per row is appended to docs/operations/withdrawn_citations.csv (what the citation WAS, so nothing is lost).
NEXT (printed): re-gate each edited approved file with the network, re-promote it, run check_invariants, then the Monday build. Reuses scripts/approved_edit.py, identity.seed_map / to_canonical."""
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.approved_edit import backup_db, read_approved, write_approved     # noqa: E402
from src.cfp_monitor.identity import seed_map, to_canonical                     # noqa: E402

LIVE_DB = Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor" / "cfp_monitor.db"
MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
LEDGER = ROOT / "docs" / "operations" / "withdrawn_citations.csv"
CITATION = ("DEADLINE_EVIDENCE_URL", "DEADLINE_QUOTE")
LEDGER_COLS = ["date", "event_id", "event", "market", "old_url", "old_quote", "source", "reason", "link_state"]


def read_declaration(path: Path) -> list[dict]:
    """The rows of a withdrawal file; refuses a row that carries anything else than an id, a reason and blank citation cells."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        cols, rows = list(rd.fieldnames or []), list(rd)
    if "EVENT_ID" not in cols:
        raise SystemExit("the withdrawal file needs an EVENT_ID column holding OUR canonical id")
    extra = [c for c in cols if c not in ("EVENT_ID", "reason", "event") + CITATION]
    if extra:
        raise SystemExit(f"columns {extra} are not allowed: this tool blanks a citation and nothing else")
    for r in rows:
        for c in CITATION:
            if (r.get(c) or "").strip():
                raise SystemExit(f"{r['EVENT_ID']}: {c} is not blank in the withdrawal file (a withdrawal declares a CLEAR; it carries no new citation)")
    return rows


def link_state(con: sqlite3.Connection, url: str) -> str:
    if not url:
        return "none"
    r = con.execute("select state from link_checks where url=?", (url,)).fetchone()
    return r[0] if r else "unchecked"


def plan_row(row: dict, db_row: dict | None, state: str, allow_alive: bool) -> dict:
    """What would change for one row: {'file': {col: new}, 'db': {col: new}, 'skip': reason or ''}."""
    out = {"file": {}, "db": {}, "skip": ""}
    if row is None and db_row is None:
        out["skip"] = "no row with this id in an approved file or the database"
        return out
    has_file = row is not None and ((row.get("DEADLINE_EVIDENCE_URL") or "").strip() or (row.get("DEADLINE_QUOTE") or "").strip())
    has_db = db_row is not None and ((db_row.get("deadline_evidence_url") or "").strip() or (db_row.get("deadline_quote") or "").strip())
    if not has_file and not has_db:
        out["skip"] = "already clear in both"
        return out
    if state == "alive" and not allow_alive:
        out["skip"] = "the citation page is ALIVE in link_checks: a live page is not a withdrawal (--allow-alive to override, named)"
        return out
    if row is not None:
        for c in CITATION:
            if (row.get(c) or "") != "":
                out["file"][c] = ""
        if has_file and (row.get("IS_PROJECTED") or "").strip().lower() != "true":
            out["file"]["IS_PROJECTED"] = "true"
        ed = (row.get("EDITION") or "").strip()
        proj = f"Projected ({ed})" if ed else "Projected"
        if has_file and (row.get("GROUNDING_CONFIDENCE") or "") != proj and (row.get("IS_PROJECTED") or "").strip().lower() != "true":
            out["file"]["GROUNDING_CONFIDENCE"] = proj
    if db_row is not None and has_db:
        out["db"] = {"deadline_evidence_url": "", "deadline_quote": ""}
        if (db_row.get("is_projected") or "").strip().lower() != "true":
            out["db"]["is_projected"] = "true"
    return out


def propose(approved: dict[str, tuple[str, dict]], con: sqlite3.Connection, today: str) -> list[dict]:
    """Rows of the approved files whose deadline citation is DEAD in link_checks and whose call is over (the deadline has passed, or the event has started): the class upstream withdrew.
    A LIST TO COMPARE with upstream's own declaration, never to apply unread: a row can qualify by our rule and not be on upstream's list."""
    out = []
    for cid, (market, r) in approved.items():
        url = (r.get("DEADLINE_EVIDENCE_URL") or "").strip()
        start, dl = (r.get("START DATE") or "").strip(), (r.get("SUBMISSION DEADLINE") or "").strip()
        over = (dl and dl < today) or (start and start < today)
        if url and link_state(con, url) == "dead" and over:
            out.append({"EVENT_ID": cid, "event": r["CONFERENCE"], "reason": f"citation page dead in link_checks; deadline {dl or '-'}, start {start or '-'}"})
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", help="withdrawal CSV: EVENT_ID (OUR id), optional reason; citation cells blank")
    ap.add_argument("--propose", action="store_true", help="list the rows that qualify by our own data (dead citation, event over) as a withdrawal CSV")
    ap.add_argument("--out", help="with --propose: write the list here")
    ap.add_argument("--source", default="", help="who declared the withdrawal (recorded in the ledger), e.g. 'upstream note 28'")
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--ledger", default=str(LEDGER))
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--allow-alive", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    up_to_canon, _roots = seed_map(a.db)
    files, approved = {}, {}
    for m in ("Cybersecurity", "Utility"):
        p = Path(a.markets_dir) / f"{m}_audited.final.csv"
        cols, rows, bom, crlf = read_approved(p)
        files[m] = (p, cols, rows, bom, crlf)
        for i, r in enumerate(rows):
            approved.setdefault(to_canonical(r["EVENT_ID"], up_to_canon), (m, r, i)[:2])
    con = sqlite3.connect(f"file:{a.db.replace(chr(92), '/')}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    if a.propose:
        rows = propose(approved, con, a.today)
        print(f"{len(rows)} row(s) qualify: a dead citation page and a call that is over (deadline passed or event started); compare with upstream's own list before applying")
        for r in rows:
            print(f"  {r['EVENT_ID']:62s} {r['event'][:44]}")
        if a.out:
            with open(a.out, "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=["EVENT_ID", "event", "reason"])
                w.writeheader()
                w.writerows(rows)
            print(f"written {a.out}")
        return 0
    if not a.file:
        ap.error("give --file or --propose")
    decl = read_declaration(Path(a.file))
    plans = []
    for d in decl:
        cid = d["EVENT_ID"].strip()
        hit = approved.get(cid)
        db_row = con.execute("select * from grounding_facts where event_id=?", (cid,)).fetchone()
        db_row = dict(db_row) if db_row else None
        url = ((hit[1].get("DEADLINE_EVIDENCE_URL") if hit else "") or (db_row or {}).get("deadline_evidence_url") or "").strip()
        st = link_state(con, url)
        pl = plan_row(hit[1] if hit else None, db_row, st, a.allow_alive)
        plans.append((d, cid, hit, db_row, url, st, pl))
    n_file = n_db = skipped = 0
    for d, cid, hit, db_row, url, st, pl in plans:
        name = (hit[1]["CONFERENCE"] if hit else (db_row or {}).get("name", "")) or d.get("event", "")
        if pl["skip"]:
            skipped += 1
            print(f"  SKIP   {cid:62s} {pl['skip']}")
        else:
            n_file += bool(pl["file"])
            n_db += bool(pl["db"])
            print(f"  CLEAR  {cid:62s} {name[:34]:34s} link {st:9s} file {sorted(pl['file'])} db {sorted(pl['db'])}")
    print(f"\n{len(plans)} declared: {len(plans) - skipped} to clear ({n_file} in an approved file, {n_db} in the database), {skipped} skipped")
    if not a.apply:
        print("report only; add --apply to write (backups first)")
        return 0

    # ---- apply: approved files, then the database, then the ledger ------------------------------------------------------------------------
    edited = []
    for m, (p, cols, rows, bom, crlf) in files.items():
        after = [dict(r) for r in rows]
        cells = set()
        for d, cid, hit, db_row, url, st, pl in plans:
            if pl["skip"] or not pl["file"] or not hit or hit[0] != m:
                continue
            idx = next(i for i, r in enumerate(rows) if r is hit[1])
            for c, v in pl["file"].items():
                after[idx][c] = v
                if rows[idx][c] != v:
                    cells.add((idx, c))
        if cells:
            bak = write_approved(p, cols, rows, after, bom, crlf, "withdraw", expect_cells=cells)
            edited.append(p.name)
            print(f"{p.name}: {len(cells)} cell(s) written on {len({i for i, _ in cells})} row(s); proved only those cells changed; backup {bak.name}")
    con.close()
    todo = [(cid, pl["db"], url) for d, cid, hit, db_row, url, st, pl in plans if not pl["skip"] and pl["db"]]
    if todo:
        bak = backup_db(Path(a.db), "withdraw")
        db = sqlite3.connect(a.db)
        n = 0
        for cid, upd, url in todo:
            cur = db.execute(f"update grounding_facts set {','.join(k + '=?' for k in upd)} where event_id=? and coalesce(deadline_evidence_url,'')=?", (*upd.values(), cid, url))
            n += cur.rowcount
        db.commit()
        db.close()
        print(f"database: {n} row(s) updated (guarded on the old URL); backup {bak.name}")
    new = not Path(a.ledger).exists()
    with open(a.ledger, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LEDGER_COLS)
        if new:
            w.writeheader()
        for d, cid, hit, db_row, url, st, pl in plans:
            if pl["skip"]:
                continue
            w.writerow({"date": a.today, "event_id": cid, "event": (hit[1]["CONFERENCE"] if hit else (db_row or {}).get("name", "")), "market": hit[0] if hit else "",
                        "old_url": url, "old_quote": ((hit[1].get("DEADLINE_QUOTE") if hit else "") or (db_row or {}).get("deadline_quote") or "")[:300], "source": a.source,
                        "reason": d.get("reason", ""), "link_state": st})
    print(f"ledger: {a.ledger}")
    if edited:
        print("\nNEXT (required): re-gate with the network and re-promote " + ", ".join(edited) + " (market-runbook 7.5), run check_invariants.py --db, then build the Monday pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
