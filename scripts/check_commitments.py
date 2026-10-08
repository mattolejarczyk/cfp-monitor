"""Did upstream do what it said it would? A ledger of concrete promises, checked against the data (ACT-58). READ-ONLY, always exits 0.

    python scripts/check_commitments.py                          # against the PUBLISHED files Markets/<Market>_audited.final.csv (what the customer pages are built from)
    python scripts/check_commitments.py --file delivery.csv      # against ANY delivery CSV, today (an upstream row they send now can be checked now)
    python scripts/check_commitments.py --today 2026-10-11 --out-dir <dir>

WHY. Across notes 33 to 38 (2026-10-06) upstream answered 'we will do X in Saturday's research' several times and nothing proved it was done. Each promise is one line of `docs/operations/upstream_commitments.csv`: which event
(OUR canonical id, or `*` for every row), which column, what it must be, and the date it is due. This reads the rows and says per promise: KEPT, NOT KEPT (due date reached and the value is wrong: it names what was found),
NOT YET (before the due date, or the event's row is not in the file yet), per the ops:
    equals        the cell equals the expected text (case and spacing ignored)
    blank         the cell is empty
    contains      the cell contains the text (case ignored)
    not_contains  the cell does NOT contain the text (for `*`: no row in the file may)
    absent        the event is NOT in the file (a promise to drop or keep out a row)
A row is paired to an event by its canonical id (`identity.to_canonical` on the file's EVENT_ID; never by joining on an upstream id). Output: one summary line `COMMITMENTS: <k> kept, <n> NOT kept, <y> not yet`,
a line per NOT KEPT, and a report `<out-dir>/commitments.md/.json` (default %LOCALAPPDATA%\\CFP-Monitor\\runs_out\\qa\\<date>\\). Nothing is written to the data; a bad ledger line is reported, not fatal.

LEDGER HYGIENE (ACT-58). Every ledger line is linted first, so a malformed promise cannot be silently skipped: it needs an id, a due date (YYYY-MM-DD), a known op, a market, a column this script knows (the 45 delivery
fields), an expected value where the op needs one, and an event id that resolves (`identity.to_canonical` leaves it unchanged, i.e. it is OUR canonical id, and it is one we hold: a seed sheet or the checked file).
A line with a problem is reported as BAD LEDGER LINE with the reasons, whatever the data says. `--lint` prints only that.

DRAFT NOTE TO UPSTREAM. When any promise is NOT KEPT a draft note is written next to the report, `NOTE-TO-UPSTREAM-DRAFT-commitments.md`: one numbered item per unmet promise (event, field, what was found,
what was promised). It is a FILE for the operator to read, number and send. Code never sends it."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.cfp_monitor.identity import market_canonical_ids, seed_map, to_canonical      # noqa: E402

LEDGER = ROOT / "docs" / "operations" / "upstream_commitments.csv"
MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
LIVE_DB = Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor" / "cfp_monitor.db"
OPS = ("equals", "blank", "contains", "not_contains", "absent")
NEEDS_VALUE = ("equals", "contains", "not_contains")
MARKET_NAMES = ("Cybersecurity", "Utility")
DRAFT_NAME = "NOTE-TO-UPSTREAM-DRAFT-commitments.md"
# The 45 fields of a delivery row (the header of Markets/<Market>_audited.final.csv on 2026-10-08). A ledger column must be one of these.
KNOWN_COLUMNS = tuple(c.strip() for c in (
    "EVENT_ID,CONFERENCE,CONFERENCE URL,LOCATION,CONFERENCE DATES,LATEST UPDATE,SUBMISSION DEADLINE,SUBMISSION DATE VERIFIED,PRIORITY,STATUS,STATUS DETAILS,CFP MODEL TYPE,SUBMISSION URL,COORDINATOR EMAIL,"
    "OVERVIEW,CATEGORIES,NOTES,TRACK,GROUNDING_CONFIDENCE,EDITION,START DATE,Market,CITY,STATE_PROVINCE,COUNTRY,MAIN_INFO_URL,CFP_SUBMISSION_URL,DEADLINE_EVIDENCE_URL,VENUE_EVIDENCE_URL,DEADLINE_QUOTE,IS_PROJECTED,"
    "SOURCE_AS_OF,GATED_STATUS,ISSUES,OPPORTUNITY_TYPE,FORMAT,LIFECYCLE_EVIDENCE_URL,LIFECYCLE_QUOTE,ORGANIZER,SPONSOR_REQUIRED,SPONSOR_URL,SPONSOR_COST,SPONSOR_QUOTE,SUBMISSION_OPENS,ANNOUNCEMENT_DATE").split(","))
OP_WORDS = {"equals": "the value {exp!r}", "blank": "the cell left blank", "contains": "a value containing {exp!r}",
            "not_contains": "no value containing {exp!r}", "absent": "the row not in the file"}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def read_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def judge(c: dict, rows_by_canon: dict[str, dict], all_rows: list[dict], today: str, have_file: bool) -> tuple[str, str]:
    """(KEPT | NOT KEPT | NOT YET | BAD LEDGER LINE, detail)."""
    op, col, exp, ev = c["op"].strip(), c["column"].strip(), c["expected"], c["event_id"].strip()
    if op not in OPS:
        return "BAD LEDGER LINE", f"unknown op {op!r}"
    due = (c.get("due") or "").strip()
    pending = bool(due) and today < due
    if not have_file:
        return "NOT YET", "no file to check"
    if ev == "*":
        if op != "not_contains":
            return "BAD LEDGER LINE", "'*' is only for not_contains"
        hits = [r.get("CONFERENCE", "")[:40] for r in all_rows if norm(exp) in norm(r.get(col, ""))]
        if not hits:
            return "KEPT", "no row contains it"
        return ("NOT YET", f"{len(hits)} row(s) still contain {exp!r} (due {due})") if pending else ("NOT KEPT", f"{len(hits)} row(s) contain {exp!r}: {', '.join(hits[:3])}")
    row = rows_by_canon.get(ev)
    if op == "absent":
        if row is None:
            return "KEPT", "not in the file"
        return ("NOT YET", f"still in the file (due {due})") if pending else ("NOT KEPT", "the row is in the file")
    if row is None:
        return "NOT YET", "the event's row is not in the file yet"
    if col not in row:
        return "BAD LEDGER LINE", f"no column {col!r}"
    val = row.get(col, "")
    ok = {"equals": norm(val) == norm(exp), "blank": not (val or "").strip(), "contains": norm(exp) in norm(val), "not_contains": norm(exp) not in norm(val)}[op]
    if ok:
        return "KEPT", f"{col} = {val!r}"
    return ("NOT YET", f"{col} is {val!r}, due {due}") if pending else ("NOT KEPT", f"{col} is {val!r}, expected {op} {exp!r}")


def lint_ledger(rows: list[dict], up_to_canon: dict[str, str], known_ids: set[str]) -> dict[str, list[str]]:
    """ledger line id -> the reasons it is malformed (lines with no problem are absent). `known_ids` empty means no id source was visible,
    in which case the id-resolution check is skipped rather than condemning every line."""
    out: dict[str, list[str]] = {}
    seen: set[str] = set()
    for n, c in enumerate(rows, start=2):                                      # n = the line number in the file
        key = (c.get("id") or "").strip() or f"line {n}"
        bad: list[str] = []
        if not (c.get("id") or "").strip():
            bad.append("no id")
        elif key in seen:
            bad.append("duplicate id")
        seen.add(key)
        due = (c.get("due") or "").strip()
        try:
            date.fromisoformat(due)
        except ValueError:
            bad.append(f"due date {due!r} is not YYYY-MM-DD" if due else "no due date")
        op, col, ev = (c.get("op") or "").strip(), (c.get("column") or "").strip(), (c.get("event_id") or "").strip()
        if op not in OPS:
            bad.append(f"unknown op {op!r}")
        if (c.get("market") or "").strip() not in MARKET_NAMES:
            bad.append(f"market {(c.get('market') or '').strip()!r} is not one of {', '.join(MARKET_NAMES)}")
        if col not in KNOWN_COLUMNS:
            bad.append(f"column {col!r} is not a delivery field")
        if op in NEEDS_VALUE and not (c.get("expected") or "").strip():
            bad.append(f"op {op} needs an expected value")
        if ev == "*":
            if op != "not_contains":
                bad.append("'*' is only for not_contains")
        elif not ev:
            bad.append("no event id")
        else:
            canon = to_canonical(ev, up_to_canon)
            if canon != ev:
                bad.append(f"event id is upstream's, ours is {canon!r}")
            elif known_ids and ev not in known_ids:
                bad.append("event id is not one we hold (not on a seed sheet or in the checked file)")
        if bad:
            out[key] = bad
    return out


def run(ledger: Path, files: dict[str, Path], db: Path, today: str, strict_ids: bool = False) -> list[dict]:
    up_to_canon, _ = seed_map(str(db)) if Path(db).exists() else ({}, [])
    loaded: dict[str, tuple[list[dict], dict[str, dict]]] = {}
    for market, p in files.items():
        if Path(p).exists():
            rows = read_rows(Path(p))
            loaded[market] = (rows, {to_canonical((r.get("EVENT_ID") or "").strip(), up_to_canon): r for r in rows})
    known: set[str] = set()
    try:
        known = market_canonical_ids(str(db)) if (strict_ids and Path(db).exists()) else set()   # strict only: promises are usually about rows not yet delivered, so "not one we hold" is noise by default
    except Exception:                                                        # no seed sheets visible: the id check is skipped, not failed
        known = set()
    if known:                                                                # only trust the id check when a real id source was seen
        for _, by in loaded.values():
            known |= set(by)
    ledger_rows = read_rows(ledger)
    problems = lint_ledger(ledger_rows, up_to_canon, known)
    out = []
    for n, c in enumerate(ledger_rows, start=2):
        market = c["market"].strip()
        if "*" in files:
            rows, by = loaded.get("*", ([], {}))
            have = "*" in loaded
        else:
            rows, by = loaded.get(market, ([], {}))
            have = market in loaded
        state, detail = judge(c, by, rows, today, have)
        bad = problems.get((c.get("id") or "").strip() or f"line {n}")
        if bad and state != "BAD LEDGER LINE":                              # a malformed promise is never reported as kept, not kept or not yet
            state, detail = "BAD LEDGER LINE", "; ".join(bad)
        out.append({"id": c["id"], "event_id": c["event_id"], "what": c["what"], "note": c["note"], "due": c["due"], "state": state, "detail": detail,
                    "promised_on": c.get("promised_on", ""), "column": c.get("column", ""), "op": c.get("op", ""), "expected": c.get("expected", "")})
    return out


def draft_note(res: list[dict], today: str) -> str:
    """A plain-ASCII draft note to upstream naming every NOT KEPT promise: event, field, what was found, what was promised. '' when none."""
    broken = [r for r in res if r["state"] == "NOT KEPT"]
    if not broken:
        return ""
    lines = ["DRAFT - written by scripts/check_commitments.py for the operator to read, number and send. Nothing has been sent.", "",
             f"Note NN - promises not yet kept. Checked on our side on {today} (our promise checker against the published files).", "",
             f"{len(broken)} of the corrections you agreed to are not in the data. For each: the event (our id), the field, what we found, and what you said you would do.", ""]
    for i, r in enumerate(broken, start=1):
        want = OP_WORDS.get(r["op"], r["op"]).format(exp=r["expected"])
        ev = "every row" if r["event_id"] == "*" else r["event_id"]
        on = f" on {r['promised_on']}" if r["promised_on"] else ""
        lines += [f"{i}. {ev}, field {r['column']}.", f"   Promised{on} (your answer to note {r['note']}, due {r['due']}): {r['what']}.",
                  f"   Expected: {want}.", f"   Found: {r['detail']}.", ""]
    lines += ["Please send each corrected row in full (all 45 fields, under our id) so we can check it the same day.", "",
              "What would help most: the rows above, before Saturday."]
    return "\n".join(lines).encode("ascii", "replace").decode("ascii") + "\n"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger", default=str(LEDGER))
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--file", help="check a delivery CSV instead of the published files")
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--out-dir")
    ap.add_argument("--lint", action="store_true", help="print only the ledger-hygiene problems")
    ap.add_argument("--strict-ids", action="store_true", help="also flag ids we do not hold (noisy: promises are about rows not yet delivered)")
    a = ap.parse_args()
    try:
        files = {"*": Path(a.file)} if a.file else {m: Path(a.markets_dir) / f"{m}_audited.final.csv" for m in ("Cybersecurity", "Utility")}
        res = run(Path(a.ledger), files, Path(a.db), a.today, strict_ids=a.strict_ids)
    except Exception as e:                                   # a checker must never stop the job
        print(f"COMMITMENTS: UNKNOWN - {type(e).__name__}: {e}")
        return 0
    if a.lint:
        bad = [r for r in res if r["state"] == "BAD LEDGER LINE"]
        print(f"LEDGER: {len(bad)} malformed line(s) of {len(res)}")
        for r in bad:
            print(f"LEDGER BAD: {r['id']} - {r['detail']}")
        return 0
    n = {s: sum(1 for r in res if r["state"] == s) for s in ("KEPT", "NOT KEPT", "NOT YET", "BAD LEDGER LINE")}
    print(f"COMMITMENTS: {n['KEPT']} kept, {n['NOT KEPT']} NOT kept, {n['NOT YET']} not yet" + (f", {n['BAD LEDGER LINE']} bad ledger line(s)" if n["BAD LEDGER LINE"] else "") + f" (of {len(res)}, as of {a.today})")
    for r in res:
        if r["state"] in ("NOT KEPT", "BAD LEDGER LINE"):
            print(f"COMMITMENT {r['state']}: {r['id']} (note {r['note']}) {r['what']} - {r['detail']}")
    out_dir = Path(a.out_dir) if a.out_dir else Path(os.environ.get("LOCALAPPDATA", ".")) / "CFP-Monitor" / "runs_out" / "qa" / a.today
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "commitments.json").write_text(json.dumps({"today": a.today, "summary": n, "results": res}, indent=1, ensure_ascii=False), encoding="utf-8")
        lines = [f"# Upstream commitments - {a.today}", "", f"{n['KEPT']} kept, {n['NOT KEPT']} NOT kept, {n['NOT YET']} not yet, of {len(res)}", "", "| id | note | state | what | detail |", "|---|---|---|---|---|"]
        lines += [f"| {r['id']} | {r['note']} | {r['state']} | {r['what']} | {r['detail']} |" for r in res]
        (out_dir / "commitments.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        note = draft_note(res, a.today)
        if note:
            (out_dir / DRAFT_NAME).write_text(note, encoding="utf-8")
            print(f"COMMITMENTS: draft note to upstream written for the operator to send (never sent by code): {out_dir / DRAFT_NAME}")
    except OSError as e:
        print(f"COMMITMENTS: report not written ({e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
