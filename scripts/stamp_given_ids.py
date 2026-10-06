"""Stamp the permanent ids UPSTREAM GAVE US onto the blank-id rows of our research input lists (ACT-51). Report-only unless --apply.

    python scripts/stamp_given_ids.py --ids-csv ids.csv [--markets-dir <dir>] [--db <db>] [--pick "<id>=<CONFERENCE of the surviving row>"] [--apply]

INPUT. A CSV with columns `sheet` (Cybersecurity or Utility), `id` (upstream's EVENT_ID), `start` (their stated start, ISO, may be blank) and `url` (their main site); an optional `conference` column holds the exact name of OUR row when several of our rows share one address. Identity is upstream's (contract 5.4): we never mint
an id, and we never join on one: a row of ours is paired with their id by the event's own URL, nothing else.

WHAT IT DOES. For each id, finds OUR input rows of that market that have a BLANK EVENT_ID_CANON and the same URL (scheme, 'www.', a trailing slash and a '?...' tracking suffix ignored) and stamps the id on the row.
It does NOT stamp, and says why, when: the id is already an id in our database (the event is already held: the id is not new); the id is already stamped on another input row; no blank row of ours has that URL; two
or more blank rows share the URL (a duplicate listing: name the survivor with --pick '<id>=<CONFERENCE>' and the other rows get DUP_OF=<id> where the list has that column); or their stated start differs from
our row's (reported; the id is still stamped, the date is the research's to settle). It also lists any id whose words closely resemble an id we ALREADY hold for the same year (a likely second id for one event:
tell upstream which one we hold, never rewrite theirs).

SAFETY. Only the EVENT_ID_CANON (and DUP_OF) cells change: scripts/approved_edit.write_approved writes a timestamped backup first, writes .tmp, reads back and proves that exactly the expected cells changed and
nothing else, then replaces. Report by default."""
from __future__ import annotations

import argparse
import csv
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.approved_edit import read_approved, write_approved      # noqa: E402

MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
LIVE_DB = Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor" / "cfp_monitor.db"
LEDGER = ROOT / "docs" / "operations" / "given_ids.csv"     # read by stamp_input_ids.py: an id listed here is KNOWN before its event is in the database


def norm_url(u: str) -> str:
    u = re.sub(r"^https?://(www\.)?", "", (u or "").strip().lower())
    u = u.split("#")[0]
    if "?" in u and "eventkey" not in u:
        u = u.split("?")[0]
    return u.rstrip("/")


def iso_of(text: str) -> str:
    for f in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime((text or "").strip(), f).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return ""


def words(slug: str) -> set[str]:
    return set(re.sub(r"-speaking$", "", slug).split("-")[1:-1])


def plan(ids: list[dict], inputs: dict[str, list[dict]], have: set[str], picks: dict[str, str], allow_held: bool = False) -> dict:
    """{'stamp': [(market, row index, id)], 'dup': [(market, row index, id)], 'notes': [(id, what)], 'resemble': [(id, held id)]}."""
    out = {"stamp": [], "dup": [], "notes": [], "resemble": []}
    taken = {(r.get("EVENT_ID_CANON") or "").strip() for rows in inputs.values() for r in rows} - {""}
    seen: set[str] = set()
    for u in ids:
        i, market = u["id"].strip(), u["sheet"].strip()
        if i in seen:
            out["notes"].append((i, "listed twice in the ids file"))
            continue
        seen.add(i)
        if i in have and not allow_held:
            out["notes"].append((i, "already an id in our database: the event is held, not new (--allow-held stamps it on a blank input row)"))
            continue
        if i in taken:
            out["notes"].append((i, "already stamped on an input row"))
            continue
        rows = inputs.get(market, [])
        cand = [k for k, r in enumerate(rows) if not (r.get("EVENT_ID_CANON") or "").strip() and not (r.get("DUP_OF") or "").strip() and norm_url(r["CONFERENCE URL"]) == norm_url(u["url"])]
        for h in have:
            hw, uw = words(h), words(i)
            if h[:4] == i[:4] and len(uw) >= 3 and len(uw & hw) / len(uw) >= 0.85:
                out["resemble"].append((i, h))
        want_name = (u.get("conference") or "").strip().lower()      # optional column: the exact name of OUR row, to tell apart rows that share one address
        if want_name:
            cand = [k for k in cand if rows[k]["CONFERENCE"].strip().lower() == want_name]
        if not cand:
            out["notes"].append((i, "no blank-id row of ours has this URL" + (" and this name" if want_name else "")))
            continue
        if len(cand) > 1:
            want = picks.get(i)
            hit = [k for k in cand if want and rows[k]["CONFERENCE"].strip().lower() == want.strip().lower()]
            if not hit:
                out["notes"].append((i, f"{len(cand)} blank rows share this URL ({', '.join(rows[k]['CONFERENCE'] for k in cand)}): name the survivor with --pick"))
                continue
            out["stamp"].append((market, hit[0], i))
            for k in cand:
                if k != hit[0]:
                    out["dup"].append((market, k, i))
            continue
        k = cand[0]
        out["stamp"].append((market, k, i))
        a, b = iso_of(u.get("start", "")), iso_of(rows[k].get("START DATE", ""))
        if a and b and a != b:
            out["notes"].append((i, f"STAMPED, but their start {a} differs from ours {b}: the research settles the date"))
    return out


def record_given(ledger: Path, stamped: list[tuple[str, str]], source: str, today: str) -> int:
    """Append (id, market) pairs to the ledger (no duplicates); returns how many were new. stamp_input_ids.py keeps a stamped id found here: without it a stamp on a
    brand-new event (not yet in the database) is cleared by the Saturday stamping step."""
    ledger = Path(ledger)
    have = set()
    if ledger.exists():
        with open(ledger, encoding="utf-8-sig", newline="") as fh:
            have = {(r["event_id"], r["market"]) for r in csv.DictReader(fh)}
    new = [(i, m) for i, m in stamped if (i, m) not in have]
    fresh = not ledger.exists()
    with open(ledger, "a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        if fresh:
            w.writerow(["event_id", "market", "given_on", "source"])
        for i, m in new:
            w.writerow([i, m, today, source])
    return len(new)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ids-csv", required=True)
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--pick", action="append", default=[], help="'<id>=<CONFERENCE of the surviving row>' when two blank rows share a URL")
    ap.add_argument("--source", default="upstream reply", help="who gave the ids (recorded in the ledger)")
    ap.add_argument("--ledger", default=str(LEDGER))
    ap.add_argument("--allow-held", action="store_true", help="stamp an id that is already in the database (a held event whose input row has no id)")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    with open(a.ids_csv, encoding="utf-8-sig", newline="") as fh:
        ids = list(csv.DictReader(fh))
    picks = dict(p.split("=", 1) for p in a.pick)
    files, inputs = {}, {}
    for m in ("Cybersecurity", "Utility"):
        p = Path(a.markets_dir) / f"{m}_input.csv"
        files[m] = (p, *read_approved(p))
        inputs[m] = files[m][2]
    con = sqlite3.connect(f"file:{a.db.replace(chr(92), '/')}?mode=ro", uri=True)
    have = {r[0] for r in con.execute("select event_id from grounding_facts")}
    con.close()
    pl = plan(ids, inputs, have, picks, a.allow_held)
    print(f"{len(ids)} ids given: {len(pl['stamp'])} to stamp, {len(pl['dup'])} duplicate row(s) to mark DUP_OF, {len(pl['notes'])} note(s)")
    for market, k, i in pl["stamp"]:
        print(f"  STAMP {market[:5]:5s} {inputs[market][k]['CONFERENCE'][:50]:50s} <- {i}")
    for market, k, i in pl["dup"]:
        print(f"  DUP_OF {market[:5]:5s} {inputs[market][k]['CONFERENCE'][:50]:50s} -> {i}")
    for i, what in pl["notes"]:
        print(f"  NOTE  {i[:62]:62s} {what}")
    for i, h in pl["resemble"]:
        print(f"  RESEMBLES an id we hold: theirs {i}  ours {h}  (tell upstream which we hold; do not rewrite theirs)")
    if not a.apply:
        print("\nreport only; add --apply to write (backups first)")
        return 0
    for market, (p, cols, rows, bom, crlf) in files.items():
        after = [dict(r) for r in rows]
        cells = set()
        for m, k, i in pl["stamp"]:
            if m == market:
                after[k]["EVENT_ID_CANON"] = i
                cells.add((k, "EVENT_ID_CANON"))
        for m, k, i in pl["dup"]:
            if m == market and "DUP_OF" in cols:
                after[k]["DUP_OF"] = i
                cells.add((k, "DUP_OF"))
        if cells:
            bak = write_approved(p, cols, rows, after, bom, crlf, "stampids", expect_cells=cells)
            print(f"{p.name}: {len(cells)} cell(s) written; proved only those cells changed; backup {bak.name}")

    n = record_given(Path(a.ledger), [(i, m) for m, _, i in pl["stamp"]], a.source, datetime.now().strftime("%Y-%m-%d"))
    print(f"ledger {a.ledger}: {n} new id(s) recorded (stamp_input_ids.py keeps them)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
