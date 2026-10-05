"""RETIRE a duplicate event row that upstream ruled on, by declaration: kept, declared, never deleted (ACT-47, failure point D4). Report-only unless --apply.

    python scripts/retire_duplicates.py                           # the plan for docs/operations/retired_duplicates.txt, nothing written
    python scripts/retire_duplicates.py --check-pages             # also read each evidence page and prove the quoted sentence is on it (network, read-only)
    python scripts/retire_duplicates.py --apply [--markets-dir <dir>] [--db <db>] [--held-rows <file>] [--allow-survivor-missing]

WHY. Two database rows for one event put the customer's status on one row and the page on the other (all four pairs of 2026-10-05 had the customer link on a different row from the published one in at least
one pair), and every report of the pair stays open. `merge_duplicate_events.py` deletes; the 2026-10-05 rule is that a row is KEPT and DECLARED (contract 2.1, `market_sheets/held_rows.txt`), and that a ruling
without a page is a claim: each pair carries the page and the verbatim sentence that shows it is one event (R15).
THE LEDGER (docs/operations/retired_duplicates.txt), one decision per line:
    YYYY-MM-DD | survivor event_id | retired event_id | who ruled | evidence page URL | verbatim sentence on that page | why
WHAT --apply DOES, per line, in this order:
  1 REFUSES unless both ids exist in the database, and unless the SURVIVOR is already on the published page (its row is in the approved file) when the retired row is: removing the only listing of an event would
    drop it from the customer page. `--allow-survivor-missing` overrides, named (the Saturday load that brings the survivor onto the page should come first).
  2 removes the RETIRED row from the approved file `<Market>_audited.final.csv` if it is there (backup first; read back: exactly that row gone, every other row identical, order kept) so the customer page shows one row;
  3 declares the retired id in held_rows.txt with the reason, the page and the date (idempotent), so check_invariants.py counts it as a decision and not an accident.
  It NEVER touches the database (the row is kept) and never touches client_conferences (a customer link is not ours to move: it is reported, with the survivor, so a person decides).
find_duplicate_events.py reads the same ledger and reports a retired pair as DECIDED, not outstanding.
NEXT (printed): re-gate the edited approved file with the network, re-promote it, check_invariants.py --db, build the Monday pages. Reuses scripts/approved_edit.py, identity.seed_map / to_canonical, verify.fetch_text."""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.approved_edit import read_approved, write_approved     # noqa: E402
from src.cfp_monitor.identity import seed_map, to_canonical          # noqa: E402

LIVE_DB = Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor" / "cfp_monitor.db"
MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
LEDGER = ROOT / "docs" / "operations" / "retired_duplicates.txt"
FIELDS = ("date", "survivor", "retired", "who", "page", "quote", "why")


def load_retirements(path: Path = LEDGER) -> list[dict]:
    """The ledger's decisions. A malformed line raises: a decision nobody can read is not a decision."""
    out = []
    if not Path(path).exists():
        return out
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = [p.strip() for p in s.split("|")]
        if len(parts) != 7:
            raise ValueError(f"{path}:{n}: expected 7 fields ({' | '.join(FIELDS)}), got {len(parts)}")
        d = dict(zip(FIELDS, parts))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d["date"]) or not d["survivor"] or not d["retired"] or d["survivor"] == d["retired"]:
            raise ValueError(f"{path}:{n}: needs a date, and two DIFFERENT event ids")
        if not d["page"].startswith("http") or len(d["quote"]) < 15:
            raise ValueError(f"{path}:{n}: a ruling without a page and a sentence is a claim (R15): give the evidence page and the verbatim sentence")
        out.append(d)
    return out


def held_line(d: dict) -> str:
    return (f"{d['retired']}  # RETIRED {d['date']} - duplicate of {d['survivor']} (R15, ruled by {d['who']}); evidence {d['page']}: \"{d['quote'][:160]}\"."
            f" {d['why']} Kept, never deleted; it must never be promoted.")


def declared(held_file: Path) -> set[str]:
    if not Path(held_file).exists():
        return set()
    return {ln.split("#")[0].strip() for ln in Path(held_file).read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.lstrip().startswith("#") and ln.split("#")[0].strip()}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip().lower()


def quote_on_page(page: str, quote: str) -> bool:
    return norm(quote) in norm(page)


def plan_one(d: dict, db_rows: dict[str, dict], approved: dict[str, tuple[str, int]], links: dict[str, tuple[int, str]], held: set[str], allow_missing: bool) -> dict:
    """{'problems': [...], 'remove_from': (market, index) or None, 'declare': bool, 'notes': [...]} for one ledger line."""
    out = {"problems": [], "remove_from": None, "declare": d["retired"] not in held, "notes": []}
    for role in ("survivor", "retired"):
        if d[role] not in db_rows:
            out["problems"].append(f"{role} {d[role]} is not in the database")
    if out["problems"]:
        return out
    if d["retired"] in approved:
        if d["survivor"] not in approved and not allow_missing:
            out["problems"].append(f"the retired row is on the published page but the SURVIVOR {d['survivor']} is not: removing the retired row would drop the event from the customer page "
                                   f"(let a load bring the survivor onto the page first, or --allow-survivor-missing)")
        else:
            out["remove_from"] = approved[d["retired"]]
    sv, rt = links.get(d["survivor"], (0, "")), links.get(d["retired"], (0, ""))
    if rt[0]:
        out["notes"].append(f"a customer row ({rt[1] or 'no status'}) is linked to the RETIRED row: its status will not show on the page row; repoint it to the survivor (a person decides, the link is not moved here)")
    if sv[0] and rt[0]:
        out["notes"].append("customer rows are linked to BOTH rows")
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger", default=str(LEDGER))
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--held-rows", help="default: market_sheets/held_rows.txt beside the database")
    ap.add_argument("--check-pages", action="store_true", help="read each evidence page (network, read-only) and prove the quoted sentence is on it")
    ap.add_argument("--allow-survivor-missing", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    held_path = Path(a.held_rows) if a.held_rows else Path(a.db).parent / "market_sheets" / "held_rows.txt"
    decisions = load_retirements(Path(a.ledger))
    if not decisions:
        print("no decisions in the ledger")
        return 0
    up_to_canon, _roots = seed_map(a.db)
    files, approved = {}, {}
    for m in ("Cybersecurity", "Utility"):
        p = Path(a.markets_dir) / f"{m}_audited.final.csv"
        cols, rows, bom, crlf = read_approved(p)
        files[m] = (p, cols, rows, bom, crlf)
        for i, r in enumerate(rows):
            approved.setdefault(to_canonical(r["EVENT_ID"], up_to_canon), (m, i))
    con = sqlite3.connect(f"file:{a.db.replace(chr(92), '/')}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    db_rows = {r["event_id"]: dict(r) for r in con.execute("select event_id, name, url, status, edition, start_date from grounding_facts")}
    links = {}
    for r in con.execute("select event_id, count(*), group_concat(coalesce(status,''), '/') from client_conferences where event_id is not null and event_id != '' group by event_id"):
        links[r[0]] = (r[1], r[2])
    con.close()
    held = declared(held_path)
    bad = 0
    plans = []
    for d in decisions:
        pl = plan_one(d, db_rows, approved, links, held, a.allow_survivor_missing)
        if a.check_pages and not any("not in the database" in p for p in pl["problems"]):          # the page is checked even for a blocked decision: the proof and the block are separate questions
            from src.cfp_monitor.verify import fetch_text
            try:
                text, _n = fetch_text(d["page"])
            except Exception as e:                                                      # noqa: BLE001
                text = ""
                pl["problems"].append(f"the evidence page could not be read: {type(e).__name__}")
            if text and not quote_on_page(text, d["quote"]):
                pl["problems"].append("the quoted sentence is NOT on the evidence page")
            elif text:
                pl["notes"].append("the quoted sentence is on the evidence page (read now)")
        same_site = urlparse(db_rows.get(d["survivor"], {}).get("url") or "").netloc.removeprefix("www.") == urlparse(db_rows.get(d["retired"], {}).get("url") or "").netloc.removeprefix("www.")
        if not same_site:
            pl["notes"].append("the two rows do NOT share a host: read the evidence carefully")
        plans.append((d, pl))
        bad += bool(pl["problems"])
        print(f"{d['date']}  survivor {d['survivor']}\n            retired  {d['retired']}  [{db_rows.get(d['retired'], {}).get('name', '?')[:48]}]")
        print(f"            evidence {d['page']}")
        print(f"            on the published page now: survivor {'yes' if d['survivor'] in approved else 'no'}, retired {'yes' if d['retired'] in approved else 'no'}")
        for p in pl["problems"]:
            print(f"            BLOCKED: {p}")
        if not pl["problems"]:
            print(f"            plan: {'remove from ' + pl['remove_from'][0] + ' approved file; ' if pl['remove_from'] else 'not on the published page; '}{'declare in held_rows.txt' if pl['declare'] else 'already declared'}")
        for n in pl["notes"]:
            print(f"            note: {n}")
    print(f"\n{len(decisions)} decision(s), {bad} blocked")
    if not a.apply:
        print("report only; add --apply to write (backups first)")
        return 1 if bad else 0
    if bad:
        print("nothing written: fix or override the blocked decision(s) first")
        return 1
    removals = {}
    for d, pl in plans:
        if pl["remove_from"]:
            removals.setdefault(pl["remove_from"][0], set()).add(pl["remove_from"][1])
    edited = []
    for m, idx in removals.items():
        p, cols, rows, bom, crlf = files[m]
        after = [r for i, r in enumerate(rows) if i not in idx]
        bak = write_approved(p, cols, rows, after, bom, crlf, "retire", expect_removed=set(idx))
        edited.append(p.name)
        print(f"{p.name}: {len(idx)} row(s) removed ({len(rows)} -> {len(after)}); proved every other row identical; backup {bak.name}")
    new = [held_line(d) for d, pl in plans if pl["declare"]]
    if new:
        held_path.parent.mkdir(parents=True, exist_ok=True)
        with open(held_path, "a", encoding="utf-8", newline="") as fh:
            fh.write("\n# --- RETIRED duplicates (ACT-47, scripts/retire_duplicates.py): kept, declared, never deleted ---\n" + "\n".join(new) + "\n")
        print(f"held_rows.txt: {len(new)} declaration(s) appended -> {held_path}")
    # READ BACK from disk: the page must now hold at most one row per event, and never the retired one.
    after_ids = set()
    for m in ("Cybersecurity", "Utility"):
        _c, rows_now, _b, _l = read_approved(files[m][0])
        after_ids |= {to_canonical(r["EVENT_ID"], up_to_canon) for r in rows_now}
    for d, pl in plans:
        n = (d["survivor"] in after_ids) + (d["retired"] in after_ids)
        print(f"read back: {d['survivor']}: {n} row(s) of this event on the published page" + ("" if n == 1 else "  <<< WARNING: " + ("the event is not on the page" if n == 0 else "the duplicate is still on the page")))
        if d["retired"] in after_ids:
            print("a retired row is still on the page: stop")
            return 1
    if edited:
        print("\nNEXT (required): re-gate with the network and re-promote " + ", ".join(edited) + " (market-runbook 7.5), run check_invariants.py --db, then build the Monday pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
