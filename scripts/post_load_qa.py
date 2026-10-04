"""Step QA report for the Saturday LOAD: what did the load change in the database, and did it lose anything we had proven?

    python scripts/post_load_qa.py --previous-db <backup taken before the load> [--import-json <weekend_import report>]

WHY (2026-10-03). The first live load of the narrow-prompt research dropped verified evidence on three events whose deadlines were
still ahead (RSA Conference 2027, Black Hat Asia's call for summits, Nullcon), reverted a hand-corrected submission link, and wrote
and listed a start date it had introduced on ODSC East that we then wrongly cleared (the page states it; a flag asks a person to confirm, it does not prove a date wrong). Every one of those was found by hand AFTER the load. This report
runs the same comparisons automatically, right after the load and before anyone relies on it, and files them in the weekly QA folder
(runs_out/qa/<cycle Monday>/load.md and .json, the shape in src/cfp_monitor/qa_report.py). It reads; it never changes pipeline data.

WHAT IT CHECKS (a FLAG is a thing for a person to look at, never a failure of the run)
  1 Future-deadline rows. For every event whose deadline was ahead of today before OR after the load: REGRESSION flags for evidence page or
    quote lost, deadline lost, verified -> projected, submission link lost. Moves and evidence swaps are listed without a flag.
  2 Blank rates of the fields the short research question does not ask (organizer, overview, categories, coordinator email) and a venue
    word in CITY, against the pre-load database: a rise of 15 points or more is flagged.
  3 Dates on the shipped approved files: start date against the conference-dates text, and the four year checks (start_date_arbiter).
  4 Guessed start dates: a start date the load introduced or changed on a projected row that has no evidence page.
  5 The approved files are signed and fresh, so Monday's pages will publish (publish_guard).
  6 The watch-list of named rows (watchlist_check.py), as one line.
Pure functions below take plain dicts so the same rules are tested without a database."""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.cfp_monitor import qa_report                                     # noqa: E402

LIVE = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor")
MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
VENUE_WORDS = ("hyatt", "sheraton", "westin", "hilton", "marriott", "ahoy", "excel", "sands", "convention", "centre", "center", "hotel", "resort", "pullman",
               "intercontinental", "ifema", "arena", "stadium", "expo", "hall")
UNASKED = ("organizer", "overview", "categories", "coordinator_email")
COLS = ("event_id", "name", "deadline", "is_projected", "deadline_evidence_url", "deadline_quote", "submission_url", "status",
        "start_date", "city", "organizer", "overview", "categories", "coordinator_email")


def _b(v) -> str:
    return (str(v) if v is not None else "").strip()


def _d(v) -> date | None:
    try:
        return date.fromisoformat(_b(v))
    except ValueError:
        return None


def deadline_changes(old: dict, new: dict, today: date) -> tuple[list[list], list[str], list[str]]:
    """(rows, flags, past) for rows whose deadline was ahead before or after the load."""
    rows, flags, past = [], [], []
    for k, n in new.items():
        o = old.get(k)
        if o is None:
            continue
        od, nd = _d(o.get("deadline")), _d(n.get("deadline"))
        if not ((od and od >= today) or (nd and nd >= today)):
            if _b(o.get("deadline")) != _b(n.get("deadline")):
                past.append(f"{n['name'][:50]}: deadline {o.get('deadline') or '-'} -> {n.get('deadline') or '-'} (already passed)")
            continue
        name = n.get("name", k)[:50]
        reg, chg = [], []
        if _b(o.get("deadline")) and not _b(n.get("deadline")):
            reg.append("deadline LOST")
        elif _b(o.get("deadline")) != _b(n.get("deadline")):
            chg.append(f"deadline {o.get('deadline') or '-'} -> {n.get('deadline') or '-'}")
        if _b(o.get("deadline_evidence_url")) and not _b(n.get("deadline_evidence_url")):
            reg.append("evidence page LOST")
        elif _b(o.get("deadline_evidence_url")) != _b(n.get("deadline_evidence_url")):
            chg.append("evidence page changed")
        if _b(o.get("deadline_quote")) and not _b(n.get("deadline_quote")):
            reg.append("quote LOST")
        if _b(o.get("is_projected")).lower() == "false" and _b(n.get("is_projected")).lower() == "true":
            reg.append("verified -> projected")
        if _b(o.get("submission_url")) and not _b(n.get("submission_url")):
            reg.append("submission link LOST")
        elif _b(o.get("submission_url")) != _b(n.get("submission_url")):
            chg.append("submission link changed")
        if reg or chg:
            rows.append([name, o.get("deadline") or "-", n.get("deadline") or "-", "REGRESSION: " + "; ".join(reg) if reg else "changed", "; ".join(chg)])
        if reg:
            flags.append(f"{name} (deadline {n.get('deadline') or o.get('deadline')}): " + "; ".join(reg))
    return rows, flags, past


def blank_rates(old: dict, new: dict, threshold: float = 0.15) -> tuple[list[list], list[str]]:
    rows, flags = [], []
    n_old, n_new = max(len(old), 1), max(len(new), 1)
    for c in UNASKED:
        bo = sum(1 for r in old.values() if not _b(r.get(c)))
        bn = sum(1 for r in new.values() if not _b(r.get(c)))
        rows.append([c, f"{bo} of {len(old)}", f"{bn} of {len(new)}"])
        if bn / n_new - bo / n_old >= threshold:
            flags.append(f"{c} is blank on {bn} of {len(new)} rows after the load (was {bo} of {len(old)}): the research left a field out and nothing carried it")
    vo = sum(1 for r in old.values() if any(w in _b(r.get("city")).lower() for w in VENUE_WORDS))
    vn = sum(1 for r in new.values() if any(w in _b(r.get("city")).lower() for w in VENUE_WORDS))
    rows.append(["CITY holds a venue word", f"{vo}", f"{vn}"])
    if vn - vo >= max(3, int(0.05 * n_new)):
        flags.append(f"CITY holds a venue word on {vn} rows after the load (was {vo})")
    return rows, flags


def date_checks(market: str, rows: list[dict], today: date) -> tuple[list, list[str]]:
    from scripts.start_date_arbiter import first_date, year_checks
    agree = dis = blank = 0
    flags, bad = [], []
    for r in rows:
        a, b = _b(r.get("START DATE")), first_date(r.get("CONFERENCE DATES", ""))
        if not a or not b:
            blank += 1
        elif a == b.isoformat():
            agree += 1
        else:
            dis += 1
            bad.append(r.get("CONFERENCE", "")[:40])
        yf = year_checks(r, today)
        if yf:
            flags.append(f"{market}: {r.get('CONFERENCE', '')[:44]}: " + "; ".join(yf))
    if dis:
        flags.append(f"{market}: start date and conference-dates text disagree on {dis} shipped row(s): " + ", ".join(bad[:6]))
    return [market, len(rows), agree, dis, blank], flags


def guessed_dates(old: dict, new: dict, pinned: set | None = None) -> list[str]:
    """A start date INTRODUCED OR CHANGED by this load on a projected row with no evidence page (the ODSC East case: the load set 2027-05-10 and
    'Upcoming'; the date was in fact right, which is why this is a list for a person to confirm). Existing start dates on such rows
    are normal (they come from the event's own site) and are not flagged."""
    out = []
    for k, r in new.items():
        if pinned and k in pinned:
            continue                                  # a person verified this fact on the event's own page (pinned_rows.json): nothing to confirm
        if _b((old.get(k) or {}).get("start_date")) == _b(r.get("start_date")):
            continue
        if _b(r.get("start_date")) and _b(r.get("is_projected")).lower() == "true" and not _b(r.get("deadline_evidence_url")):
            out.append(f"{_b(r.get('name'))[:50]}: the load set start date {r.get('start_date')} (was {_b((old.get(k) or {}).get('start_date')) or 'blank'}) on a projected row with no evidence page: confirm a page states this edition")
    return out


def read_db(path: Path, table: str = "grounding_facts") -> dict:
    """The rows of `table` (grounding_facts for conferences, award_grounding_facts for awards: the two kinds never mix)."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    have = {r[1] for r in con.execute(f"pragma table_info({table})")}
    cols = [c for c in COLS if c in have]
    out = {r["event_id"]: dict(r) for r in con.execute(f"select {','.join(cols)} from {table}")}
    con.close()
    return out


def read_csv_rows(path: Path) -> list[dict]:
    import csv
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def build(old: dict, new: dict, finals: dict[str, list[dict]], signed: dict[str, tuple[bool, str]], watch: str, today: date, steps: dict | None = None, pinned: set | None = None,
          kind: str = "conference", skipped: list | None = None) -> dict:
    awards = kind == "award"
    rep = qa_report.new_report("load_awards" if awards else "load", today)
    rows, flags, past = deadline_changes(old, new, today)
    rep["sections"].append({"title": "Rows with a deadline still ahead: what the load changed",
                            "note": "REGRESSION = something we had proven was lost. A move or an evidence swap is listed without a flag.",
                            "columns": ["Event", "Deadline before", "Deadline now", "Result", "Other changes"], "rows": rows, "flags": flags})
    rep["flags"] += flags
    rep["past"] = past
    brows, bflags = blank_rates(old, new)
    rep["sections"].append({"title": "Fields the short research question does not ask", "columns": ["Field", "Blank before", "Blank after"], "rows": brows, "flags": bflags})
    rep["flags"] += bflags
    if not awards:                                    # awards have no event start date: nothing here applies to them
        drows, dflags = [], []
        for m, rs in finals.items():
            r, f = date_checks(m, rs, today)
            drows.append(r)
            dflags += f
        rep["sections"].append({"title": "Dates on the shipped approved files", "columns": ["Market", "Rows", "Start agrees with dates text", "Disagrees", "One side blank"],
                                "rows": drows, "flags": dflags})
        rep["flags"] += dflags
        g = guessed_dates(old, new, pinned)
        rep["sections"].append({"title": "Start dates with no page behind the edition", "columns": ["Row"], "rows": [[x] for x in g], "flags": g})
        rep["flags"] += g
    if skipped is not None:
        from collections import Counter
        why = Counter(s.split(":")[0] for s in skipped)
        rep["sections"].append({"title": "Awards the refresh policy did not research this week (kept as they were)",
                                "note": "Closed awards whose next cycle is not near are researched about once every four weeks, in rotation (scripts/refresh_plan.py). They are not a failure and not counted as stale.",
                                "columns": ["Reason", "Awards"], "rows": [[k, v] for k, v in why.most_common()], "flags": []})
    if steps:
        from scripts.failure_steps import STEPS, line
        stp_rows = [[m, v["researched"], v["shipped_fresh"], *[v["counts"][s] for s in STEPS]] for m, v in steps.items()]
        rep["sections"].append({"title": "Why rows did not ship this week's research, by step (FIND / PROVE / READ / IDENTITY)",
                                "note": "FIND = the cited page is a 404 or the search failed; PROVE = the page exists but the quote is not on it; READ = the claim is wrong or inconsistent (a year check, active-call wording on a projected row); "
                                        "IDENTITY = no permanent id or a duplicate id (not a tool); FORMAT = file shape; COVERAGE = last week's event not in this week's research (not a failure). A row is counted under the first step that failed it.",
                                "columns": ["Market", "Rows researched", "Shipped fresh", *STEPS], "rows": stp_rows, "flags": []})
        hist_rows = []
        for m, v in steps.items():
            for h in v["history"]:
                hist_rows.append([m, h.get("stamp", "")[:8], *[h["counts"].get(s, 0) for s in STEPS]])
        rep["sections"].append({"title": "The same counts for the last loads (the trend that tells us which step to improve)", "columns": ["Market", "Load", *STEPS], "rows": hist_rows, "flags": []})
        for m, v in steps.items():
            for r in v["rises"]:
                rep["flags"].append(f"{m}: more rows failed a step than last load: {r}")
        rep["step_summary"] = "; ".join(f"{m}: {line(v['counts'])}" for m, v in steps.items())
    srows = [[m, "yes" if ok else "NO", why] for m, (ok, why) in signed.items()]
    sflags = [f"{m}: Monday's page will NOT publish - {why}" for m, (ok, why) in signed.items() if not ok]
    rep["sections"].append({"title": "Approved files signed and fresh (Monday's pages publish)", "columns": ["Market", "Will publish", "Reason"], "rows": srows, "flags": sflags})
    rep["flags"] += sflags
    if not awards:
        rep["sections"].append({"title": "Watch-list of named rows", "note": watch or "not run", "columns": [], "rows": [], "flags": []})
        if watch and "ALL OK" not in watch:
            rep["flags"].append("watch-list: " + watch)
    return qa_report.finish(rep, "the load lost nothing we had proven" + ("" if awards else "; every shipped date and year is consistent"))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--previous-db", help="the backup taken before the load (default: the backup named in --import-json)")
    ap.add_argument("--import-json")
    ap.add_argument("--db", default=str(LIVE / "cfp_monitor.db"))
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--markets", nargs="+", default=["Cybersecurity", "Utility"])
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--out", default=str(qa_report.QA_ROOT))
    ap.add_argument("--strict", action="store_true", help="exit 1 when anything is flagged")
    a = ap.parse_args()
    today = datetime.strptime(a.today, "%Y-%m-%d").date()
    prev = a.previous_db
    if not prev and a.import_json and Path(a.import_json).exists():
        prev = json.loads(Path(a.import_json).read_text(encoding="utf-8")).get("backup")
    if not prev or not Path(prev).exists():
        print("post_load_qa: no pre-load backup to compare with (give --previous-db)", file=sys.stderr)
        return 2
    awards = a.markets == ["Awards"]                  # the Friday awards load: its own table, its own report (load_awards), no dates or watch-list
    table = "award_grounding_facts" if awards else "grounding_facts"
    old, new = read_db(Path(prev), table), read_db(Path(a.db), table)
    mdir = Path(a.markets_dir)
    finals = {m: read_csv_rows(mdir / f"{m}_audited.final.csv") for m in a.markets if (mdir / f"{m}_audited.final.csv").exists()}
    from src.cfp_monitor.publish_guard import check_publish_fresh
    signed = {m: check_publish_fresh(mdir / f"{m}_audited.final.csv", today) for m in a.markets if (mdir / f"{m}_audited.final.csv").exists() or not awards}
    try:
        if awards:
            raise RuntimeError("not applicable to awards")
        w = subprocess.run([sys.executable, str(ROOT / "scripts" / "watchlist_check.py"), "--previous-db", str(prev)], capture_output=True, text=True,
                           encoding="utf-8", timeout=300).stdout
        watch = next((ln.strip("* ").strip() for ln in w.splitlines() if "ALL OK" in ln or "need a look" in ln), "")
    except Exception as e:                                                  # noqa: BLE001
        watch = "" if awards else f"watch-list did not run: {e}"
    steps = None
    if a.import_json and Path(a.import_json).exists():
        from scripts import failure_steps as fs
        imp = json.loads(Path(a.import_json).read_text(encoding="utf-8"))
        hist_path = Path(a.out) / "step_failures.jsonl"
        steps = {}
        for mk in imp.get("markets", []):
            if mk.get("market") not in a.markets:
                continue
            summ = fs.summarize(mk.get("decisions", []))
            cnt = fs.counts(summ)
            fs.append_history(hist_path, {"stamp": imp.get("stamp", ""), "market": mk["market"], "counts": cnt, "researched": mk.get("rows"), "shipped_fresh": mk.get("from_this_week")})
            hist = fs.load_history(hist_path, mk["market"], 5)
            prior = hist[-2]["counts"] if len(hist) >= 2 else None
            steps[mk["market"]] = {"counts": cnt, "researched": mk.get("rows"), "shipped_fresh": mk.get("from_this_week"), "history": hist, "rises": fs.rises(cnt, prior)}
    from scripts.pinned_rows import load_pins
    skipped = None
    if awards:
        from scripts.refresh_plan import skipped_reasons
        skipped = skipped_reasons(mdir / "Awards_input.csv")
    rep = build(old, new, finals, signed, watch, today, steps, {p['canonical'] for p in load_pins()}, "award" if awards else "conference", skipped)
    d = qa_report.write(rep, qa_report.to_markdown(rep, "Friday awards load - what changed and what was lost" if awards else "Saturday load - what changed and what was lost"), Path(a.out))
    print(f"{rep['status']}: {rep['summary']}  ->  {d / ('load_awards.md' if awards else 'load.md')}")
    for f in rep["flags"]:
        print("  FLAG:", f)
    return 1 if (a.strict and rep["flags"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
