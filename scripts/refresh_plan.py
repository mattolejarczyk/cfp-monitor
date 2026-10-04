"""Which awards are worth researching THIS week? Mark the dormant ones so the research skips them (2026-10-04).

    python scripts/refresh_plan.py --market Awards [--apply] [--today YYYY-MM-DD] [--max-skip-fraction 0.7]

WHY. 76 of 129 awards are Closed with nothing ahead, and the Friday job researches every row at about 6 cents a call, so about half of the weekly spend asks questions whose answer cannot have
changed (a closed award's next cycle is announced months later). The conference side learned the same: a short question, asked only where something can have changed, is cheaper and is what grounded.
This is the 'refresh scheduler' idea (designed 10-01, never built), for awards first.

THE RULE. An award is RESEARCHED this week if ANY of these holds; otherwise it is marked REFRESH_SKIP with the reason, and the audit skips it exactly as it skips a DUP_OF row. Its last accepted
row stays on the page: the weekend import carries any row the research did not cover ("carried-over"), so nothing disappears.
  new         no database record, or no permanent id on the input row (never skip what we do not know)
  live        STATUS is not Closed (Open, Upcoming, Needs Verification, blank)
  date-ahead  a stored deadline or opening date is still ahead (a stale STATUS must not hide it)
  opening     the next cycle is expected to open within 60 days (last opening date + whole years; if none, last deadline - 60 days + whole years)
  rotation    last researched 21+ days ago AND (ISO week + a stable hash of the award id) mod 4 = 0: every Closed award is looked at about once every four weeks, a quarter of them each week
  stale       last researched 56+ days ago or never stamped: the rotation can never be allowed to starve a row
SAFETY. If the plan would skip more than --max-skip-fraction of the rows (default 0.7) it skips NOTHING and says why (something is off with the data, not with the awards). It never skips a row it
cannot place in the database. --apply rewrites the REFRESH_SKIP column of <market>_input.csv (every run recomputes it; the previous file is kept once per day as <market>_input.pre-refresh.csv).
Reads the live database read-only. Without --apply it only prints the plan and the estimated saving."""
from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
LIVE_DB = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor\cfp_monitor.db")
COLUMN = "REFRESH_SKIP"
OPENING_WINDOW_DAYS, ROTATION_MIN_AGE, STALE_DAYS, ROTATION_WEEKS = 60, 21, 56, 4
CENTS_PER_CALL = 6.1          # measured on the conference narrow question (2026-09-30); awards not yet measured


def stable_hash(s: str) -> int:
    return int(hashlib.sha1((s or "").encode("utf-8")).hexdigest()[:8], 16)


def _d(v) -> date | None:
    try:
        return date.fromisoformat((v or "").strip()[:10])
    except ValueError:
        return None


def _plus_years(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:                                  # 29 February
        return d.replace(year=d.year + n, day=28)


def expected_open(rec: dict, today: date) -> date | None:
    """When the NEXT cycle should open: the last opening date (or, without one, the last deadline minus 60 days) moved forward by whole years to the first one not already well past."""
    base = _d(rec.get("submission_opens"))
    if base is None:
        dl = _d(rec.get("deadline"))
        base = dl - timedelta(days=60) if dl else None
    if base is None:
        return None
    n = 0
    while _plus_years(base, n) < today - timedelta(days=30) and n < 5:
        n += 1
    return _plus_years(base, n)


def due(rec: dict | None, award_id: str, today: date) -> tuple[bool, str]:
    """(research it?, reason). `rec` is the award's database row (dict) or None."""
    if not award_id or rec is None:
        return True, "new"
    status = (rec.get("status") or "").strip().lower()
    if status != "closed":
        return True, "live"
    ahead = [d for d in (_d(rec.get("deadline")), _d(rec.get("submission_opens"))) if d and d >= today]
    if ahead:
        return True, "date-ahead"
    eo = expected_open(rec, today)
    if eo is not None and (eo - today).days <= OPENING_WINDOW_DAYS:
        return True, "opening"
    seen = _d(rec.get("source_as_of"))
    age = (today - seen).days if seen else 10**6
    if age >= STALE_DAYS:
        return True, "stale"
    iso_week = today.isocalendar()[1]
    if age >= ROTATION_MIN_AGE and (iso_week + stable_hash(award_id)) % ROTATION_WEEKS == 0:
        return True, "rotation"
    return False, f"dormant (closed, next cycle not near, researched {age} days ago)"


def plan(rows: list[dict], db_rows: dict, today: date, max_skip_fraction: float = 0.7) -> dict:
    """{'skip': {row_index: reason}, 'why': Counter-like dict of reasons for researched rows, 'fuse': text or ''}. Rows labelled DUP_OF are left to the audit's own rule."""
    skip, why = {}, {}
    candidates = [i for i, r in enumerate(rows) if not (r.get("DUP_OF") or "").strip()]
    for i in candidates:
        r = rows[i]
        aid = (r.get("EVENT_ID_CANON") or "").strip()
        go, reason = due(db_rows.get(aid), aid, today)
        if go:
            why[reason] = why.get(reason, 0) + 1
        else:
            skip[i] = reason
    fuse = ""
    if candidates and len(skip) / len(candidates) > max_skip_fraction:
        fuse = f"would skip {len(skip)} of {len(candidates)} rows (over {int(max_skip_fraction * 100)}%): skipping nothing, something is off with the data"
        skip = {}
    return {"skip": skip, "researched": why, "fuse": fuse, "rows": len(candidates)}


def read_db_rows(db: Path, market: str) -> dict:
    table = "award_grounding_facts" if market == "Awards" else "grounding_facts"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return {r["event_id"]: dict(r) for r in con.execute(f"select * from {table}")}
    finally:
        con.close()


def skipped_reasons(input_path: Path) -> list[str]:
    """['dormant (closed, ...): <award>', ...] for the rows an earlier --apply marked; [] when there is no file or no mark."""
    p = Path(input_path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return [f"{r.get(COLUMN)}: {(r.get('CONFERENCE') or '')[:50]}" for r in csv.DictReader(fh) if (r.get(COLUMN) or "").strip()]


def apply_marks(input_path: Path, skip: dict) -> int:
    """Rewrite the REFRESH_SKIP column (cleared first, so a stale mark never survives). Keeps a once-a-day backup. Returns rows marked."""
    p = Path(input_path)
    with open(p, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        cols, rows = list(rd.fieldnames or []), list(rd)
    bak = p.with_name(p.stem + ".pre-refresh.csv")
    if not bak.exists() or date.fromtimestamp(bak.stat().st_mtime) < date.today():
        shutil.copy2(p, bak)
    if COLUMN not in cols:
        cols.append(COLUMN)
    for i, r in enumerate(rows):
        r[COLUMN] = skip.get(i, "")
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)
    return len(skip)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--market", default="Awards", choices=["Awards"])
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--max-skip-fraction", type=float, default=0.7)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    inp = Path(a.markets_dir) / f"{a.market}_input.csv"
    if not inp.exists():
        print(f"refresh_plan: no input file {inp} (nothing marked)")
        return 0
    try:
        with open(inp, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        pl = plan(rows, read_db_rows(Path(a.db), a.market), date.fromisoformat(a.today), a.max_skip_fraction)
    except Exception as e:                                           # noqa: BLE001  a planning fault must never cost the research window
        print(f"refresh_plan FAILED ({type(e).__name__}: {e}): nothing marked, every award will be researched")
        return 0
    n, k = pl["rows"], len(pl["skip"])
    print(f"refresh_plan {a.market} {a.today}: {n} awards, research {n - k}, skip {k} ({100 * k // max(n, 1)}%); researched because: "
          + ", ".join(f"{r} {c}" for r, c in sorted(pl["researched"].items(), key=lambda x: -x[1])))
    if pl["fuse"]:
        print("  FUSE:", pl["fuse"])
    print(f"  estimated saving this run: about {k * CENTS_PER_CALL / 100:.2f} USD ({k} calls at {CENTS_PER_CALL} cents, the conference figure)")
    if a.apply:
        print(f"  marked {apply_marks(inp, pl['skip'])} row(s) in {inp.name} (column {COLUMN}); backup {inp.stem}.pre-refresh.csv")
    else:
        print("  report only: nothing written (add --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
