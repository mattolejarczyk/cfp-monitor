"""Researched rows that are NOT in the approved file yet: the PROVISIONAL rows (ACT-68; QA-REGISTER A61). Read-only; changes nothing.

    python scripts/provisional_rows.py --kind awards [--markets-dir <dir>] [--db <db>] [--on 2026-10-12] [--json out.json]

WHY. A researched award (or event) can be held out of the approved file for want of a permanent id upstream has not given yet, by the row rule, or because it is new this week
(weekend_import never loads a new event without an id). It then never reaches the customer's page, even though we hold the research: three weeks running the operator had no
deliverable Awards page. The page builder can show such a row, clearly marked Provisional, with no 'Deadline confirmed' badge and one plain sentence. This module finds those rows.

THE QUESTION, per row of the newest raw research file of a market (`Markets/<Market>_audited.csv`, as it came back from upstream: before the repairs, the gate and the row rule):
  * Does the approved file (`<Market>_audited.final.csv`) already carry it? By the permanent canonical id, through `identity.to_canonical` (never by comparing upstream ids): the
    research row's id comes from `<Market>_audited.identity.csv` (written by run_market_audit from the INPUT list), else through the seed/award lookup. Yes -> NOT provisional.
  * No permanent id yet (blank): by NAME and SUBMISSION URL, the way the customer sheets are matched (`customer_awards.name_key` / `url_key`; for conferences the name must match
    exactly, years included, because the year is the edition). A deep URL counts only when no other name uses it. Yes -> NOT provisional.
  * Otherwise -> a candidate, with the category `waiting_for_id` (blank id) or `not_loaded` (an id exists but the row is not in the approved file).
Excluded, each counted and never silent: a stub (`Audit Exception`: not researched this week), a row with no usable name, a second row for the same award, a research file older than
`max_age_days` (no research this cycle: the file is last cycle's and every row in it was either loaded or deliberately held then).

For the Awards page only (conferences are NOT wired: see QA-REGISTER A61 for what it would take) `to_page_rows` turns the candidates into delivery rows for scripts/build_review_page.py:
the status is derived (an Open or Upcoming row whose deadline has passed is Closed), the confidence is cleared (no Verified badge), and the row is tagged `_PROVISIONAL` = 1.
Pure functions plus thin readers; the database is opened `file:...?mode=ro` only."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.cfp_monitor.identity import to_canonical                          # noqa: E402

MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
LIVE_DB = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor\cfp_monitor.db")
RAW_NAME = {"awards": "Awards", "Cybersecurity": "Cybersecurity", "Utility": "Utility"}
SENTENCE = "Researched this week; our final checks are still running."
MAX_AGE_DAYS = 9
FLAG = "_PROVISIONAL"


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def tidy(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def usable_name(name: str) -> bool:
    return len(re.findall(r"[A-Za-z0-9]", name or "")) >= 3


# ============================================================================ finding the raw research
def find_raw(markets_dir: Path, market: str, on: date, max_age_days: int = MAX_AGE_DAYS) -> tuple[Path | None, str]:
    """-> (path, note). The newest raw research file of the market: Markets/<M>_audited.csv, else the newest weekend/<stamp>/<M>_audited.csv. None (with the reason) when there is none
    or when it is older than max_age_days at `on` (last cycle's file)."""
    name = f"{market}_audited.csv"
    cands = [p for p in [Path(markets_dir) / name, *sorted(Path(markets_dir).glob(f"weekend/*/{name}"))] if p.exists()]
    if not cands:
        return None, f"no raw research file {name} found under {markets_dir}"
    # the Markets copy is the one run_market_audit writes and the one the identity file sits beside; take it unless a weekend copy is NEWER
    best = max(cands, key=lambda p: p.stat().st_mtime)
    age = (on - datetime.fromtimestamp(best.stat().st_mtime).date()).days
    if age > max_age_days:
        return None, f"the newest raw research ({best}) is {age} days old at {on}: no research this cycle, nothing to show as provisional"
    return best, ""


def read_identity(raw_path: Path, markets_dir: Path, market: str) -> dict[str, str]:
    """{output EVENT_ID: permanent canonical id}, from <M>_audited.identity.csv beside the raw file or in the Markets folder. {} when there is none (the callers then fall back to the lookup)."""
    for folder in (Path(raw_path).parent, Path(markets_dir)):
        p = folder / f"{market}_audited.identity.csv"
        if p.exists():
            return {(r.get("OUTPUT_EVENT_ID") or "").strip(): (r.get("EVENT_ID_CANON") or "").strip() for r in read_csv(p)}
    return {}


def awards_lookup(db: Path | None) -> dict[str, str]:
    """upstream EVENT_ID -> our award id (award_grounding_facts.upstream_event_id), read-only. {} when the database cannot be read."""
    if not db or not Path(db).exists():
        return {}
    try:
        con = sqlite3.connect(f"file:{str(db).replace(chr(92), '/')}?mode=ro", uri=True)
        try:
            return {(u or "").strip(): e for e, u in con.execute("select event_id, upstream_event_id from award_grounding_facts") if u}
        finally:
            con.close()
    except sqlite3.Error:
        return {}


# ============================================================================ the question
def _keys(kind: str):
    if kind == "awards":
        from scripts import customer_awards as ca
        return ca.name_key, ca.url_key
    return (lambda s: re.sub(r"[^a-z0-9]+", " ", tidy(s).lower()).strip()), (lambda u: "")


def approved_index(approved: list[dict], up_to_canon: dict[str, str], kind: str) -> dict:
    """What the approved file already carries: {(canonical id, market)}, {(market, name key)}, {(market, deep url key)} and the set of raw EVENT_IDs. An EVENT_ID that is not in the lookup
    passes through to_canonical unchanged."""
    name_key, url_key = _keys(kind)
    canon, names, urls, ids = set(), set(), {}, set()
    for r in approved:
        m = (r.get("Market") or "").strip()
        eid = (r.get("EVENT_ID") or "").strip()
        ids.add(eid)
        canon.add((to_canonical(eid, up_to_canon), m))
        k = name_key(r.get("CONFERENCE") or "")
        if k:
            names.add((m, k))
        for col in ("SUBMISSION URL", "CONFERENCE URL", "CFP_SUBMISSION_URL", "MAIN_INFO_URL"):
            u = url_key(r.get(col) or "")
            if u:
                urls.setdefault((m, u), set()).add(k)
    return {"canon": canon, "names": names, "urls": {k for k, v in urls.items() if len(v) <= 1}, "ids": ids}


def candidates(raw: list[dict], identity: dict[str, str], approved: list[dict], up_to_canon: dict[str, str], kind: str = "awards") -> dict:
    """-> {'rows': [{'row', 'canon', 'category', 'name', 'market'}], 'excluded': {reason: n}}. Pure."""
    name_key, url_key = _keys(kind)
    idx = approved_index(approved, up_to_canon, kind)
    out, seen = [], set()
    excluded: dict[str, int] = {}

    def skip(why):
        excluded[why] = excluded.get(why, 0) + 1

    for r in raw:
        name, m = tidy(r.get("CONFERENCE")), (r.get("Market") or "").strip()
        eid = (r.get("EVENT_ID") or "").strip()
        if "Audit Exception" in (r.get("STATUS DETAILS") or ""):
            skip("a stub: not researched this week")
            continue
        if not usable_name(name):
            skip("no usable name")
            continue
        canon = identity.get(eid, "")
        mapped = to_canonical(eid, up_to_canon)
        if eid in idx["ids"] or (mapped, m) in idx["canon"] or (canon and (canon, m) in idx["canon"]):
            continue                                                    # the approved file already has it (by id)
        if not canon:
            # no permanent id yet: the customer-sheet way of recognising the same award
            if (m, name_key(name)) in idx["names"] and name_key(name):
                continue
            if any((m, url_key(r.get(c) or "")) in idx["urls"] for c in ("SUBMISSION URL", "CONFERENCE URL") if url_key(r.get(c) or "")):
                continue
        key = (m, canon or name_key(name))
        if key in seen:
            skip("a second row for the same award")
            continue
        seen.add(key)
        out.append({"row": r, "canon": canon, "category": "waiting_for_id" if not canon else "not_loaded", "name": name, "market": m})
    return {"rows": out, "excluded": excluded}


def derive_status(row: dict, on: date) -> dict:
    """A copy whose STATUS is never Open or Upcoming after its deadline: it becomes Closed. A blank or unreadable deadline leaves the status alone."""
    r = dict(row)
    dl = (r.get("SUBMISSION DEADLINE") or "").strip()[:10]
    try:
        passed = date.fromisoformat(dl) < on
    except ValueError:
        passed = False
    if passed and (r.get("STATUS") or "").strip() in ("Open", "Upcoming", ""):
        r["STATUS"] = "Closed"
    return r


BAD = chr(0xFFFD)                   # the replacement character: a broken apostrophe or dash in upstream's file
PLACEHOLDERS = {"nan", "none", "null", "n/a", "na", "tbd", "unknown"}
TEXT_FIELDS = ("CONFERENCE", "STATUS DETAILS", "DEADLINE_QUOTE", "ORGANIZER", "TRACK")


def clean_text(text: str) -> str:
    """A raw research cell as the page may show it: the replacement character (a broken apostrophe or dash in upstream's file) becomes an apostrophe inside a word and a hyphen elsewhere."""
    t = re.sub(r"(?<=\w)" + BAD + r"(?=\w)", "'", text or "")
    return t.replace(BAD, "-")


def to_page_rows(cands: list[dict], on: date) -> list[dict]:
    """Delivery-shaped rows for the page builder: derived status, confidence cleared, placeholder places ('nan') blanked, tagged. The research text (deadline sentence) is kept as upstream wrote it."""
    out = []
    for c in cands:
        r = derive_status(c["row"], on)
        for col in ("CITY", "STATE_PROVINCE", "COUNTRY", "FORMAT"):
            if tidy(r.get(col)).lower() in PLACEHOLDERS:
                r[col] = ""
        for col in TEXT_FIELDS:
            r[col] = clean_text(r.get(col) or "")
        r["GROUNDING_CONFIDENCE"] = ""
        r["IS_PROJECTED"] = ""
        r[FLAG] = "1"
        out.append(r)
    return out


# ============================================================================ the readers
def awards_candidates(markets_dir: Path, approved: list[dict], db: Path | None, on: date, max_age_days: int = MAX_AGE_DAYS,
                      lookup: dict[str, str] | None = None) -> tuple[dict, str, Path | None]:
    """-> (candidates(...) result, note, the raw file used). The Awards version, with the lookup (upstream id -> our award id) read from the database (read-only) unless one is given. WITHOUT a lookup
    the approved rows cannot be tied to the permanent ids, so every renamed row would look new: nothing is shown and the note says why."""
    raw_path, note = find_raw(markets_dir, "Awards", on, max_age_days)
    if raw_path is None:
        return {"rows": [], "excluded": {}}, note, None
    lookup = awards_lookup(db) if lookup is None else lookup
    if not lookup:
        return {"rows": [], "excluded": {}}, "the award id lookup could not be read (the database was unreadable or holds no upstream ids): approved rows cannot be told from new ones, so none is shown as provisional", raw_path
    raw = read_csv(raw_path)
    return candidates(raw, read_identity(raw_path, markets_dir, "Awards"), approved, lookup, "awards"), "", raw_path


def conference_candidates(markets_dir: Path, market: str, approved: list[dict], up_to_canon: dict[str, str], on: date,
                          max_age_days: int = MAX_AGE_DAYS) -> tuple[dict, str, Path | None]:
    """The same question for a conference market (NOT wired into the page): researched rows the approved `<Market>_audited.final.csv` does not carry."""
    raw_path, note = find_raw(markets_dir, market, on, max_age_days)
    if raw_path is None:
        return {"rows": [], "excluded": {}}, note, None
    return candidates(read_csv(raw_path), read_identity(raw_path, markets_dir, market), approved, up_to_canon, "conference"), "", raw_path


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kind", choices=["awards", "Cybersecurity", "Utility"], default="awards")
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--on", default=date.today().isoformat())
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    on, md = date.fromisoformat(a.on), Path(a.markets_dir)
    try:
        if a.kind == "awards":
            approved = read_csv(md / "Awards_audited.final.csv")
            res, note, raw = awards_candidates(md, approved, Path(a.db), on)
        else:
            from src.cfp_monitor import identity
            approved = read_csv(md / f"{a.kind}_audited.final.csv")
            res, note, raw = conference_candidates(md, a.kind, approved, identity.seed_map(a.db)[0], on)
    except Exception as e:                                                  # noqa: BLE001
        print(f"PROVISIONAL: UNKNOWN - {type(e).__name__}: {e}")
        return 0
    if note:
        print(f"PROVISIONAL: none - {note}")
    print(f"PROVISIONAL: {len(res['rows'])} researched row(s) not in the approved file (raw research: {raw})")
    for c in res["rows"]:
        print(f"  [{c['category']}] {c['market']}: {c['name']}")
    for why, n in res["excluded"].items():
        print(f"  excluded {n}: {why}")
    if a.json:
        Path(a.json).write_text(json.dumps({"rows": [{k: v for k, v in c.items() if k != "row"} for c in res["rows"]], "excluded": res["excluded"], "note": note}, indent=1, ensure_ascii=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
