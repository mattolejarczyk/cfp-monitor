"""The weekly RELEASE GATE: is this week's delivery complete and safe to forward? One verdict, one email to the OPERATOR ONLY (ACT-68; QA-REGISTER A62). Reports, never blocks: exit code 0 always.

    python scripts/release_gate.py [--on 2026-10-12] [--preflight | --thursday] [--dry-run] [--work-dir D] [--weekly-dir D] [--markets-dir D] [--snapshots-dir D] [--db DB] [--qa-root D] [--no-attach]

WHY. Three weeks running the operator had no deliverable Awards page and assembled the Conference page by hand. Nothing said, in one place, whether the week's files were complete; the gaps were found by hand on Monday
morning. This reads the approved files, the customer sheets, the research queue, the database (read-only) and, when they exist, the built pages, and answers: GO, GO WITH NOTES or NO-GO, naming every row behind a note.

THREE MODES (the third, --thursday, is described at the end). TWO OF THEM: MONDAY (default): after the build and the manifest, with the two HTML pages. PRE-FLIGHT (--preflight, run on Sunday by weekend_recap.py after the Sunday sweep): the same checks from the APPROVED FILES and the newest
customer snapshots WITHOUT building pages; the checks that need a built page say 'not built yet'. In both modes the page is the approved file as the page builder would show it (awards: the awards-page rule, plus the provisional rows).

THE CHECKS, each PASS / WARN / FAIL naming the rows:
  a  pages built, fresh and healthy (publish_guard on the three approved files; the manifest; the pages parse and carry today's date)
  b  CUSTOMER COVERAGE for the four sheets (Arnica and Utility Global, conferences and awards): every customer row for an event still ahead is on the page or carries EXACTLY ONE reason from REASONS. A row that is not
     even in the research queue is a FAIL. Past events and withdrawn rows are counted, not listed as gaps.
  c  researched-but-not-on-page rows (raw research files against the approved files), named with why they were held
  d  staleness: approved rows not re-researched within refresh_policy's longest explained gap plus slack (carry_age.rows_carried_whole)
  e  provisional rows (the Awards page shows researched awards that are not approved yet, marked Provisional)
  f  customer-sheet snapshot freshness: older than 2 days WARN, older than 4 days FAIL
  g  build QA, from qa_build.compare on the rows: an Open row past its deadline FAIL, a retired label FAIL, a page more than 10 percent smaller than last week's FAIL; disputed deadlines, dead links, upstream promises not kept, rows gone since last week WARN
  h  upstream: promises overdue (docs/operations/upstream_commitments.csv) and ids owed (input rows with a blank permanent id)
VERDICT. NO-GO = any FAIL; GO WITH NOTES = a WARN and no FAIL; GO = all PASS (a check that cannot be judged is a WARN, never a silent pass). 'not built yet' (NA) does not count.

THURSDAY (--thursday, ACT-70; QA-REGISTER A65): at 18:00 the evening before Friday's 02:00 awards research and Saturday's 02:00 conference research, from files only: (t1) which patches of docs/control/patches
are in Markets run_monthly.ps1 (by STEP marker or the patch's own added line) and which are approved but NOT applied; (t2) awards on the input list with no permanent id; (t3) the user-level switches
CFP_AWARDS_NEW_EVENTS, CFP_AWARDS_AUTOADD_APPLY, CFP_AUTOADD_APPLY, CFP_REFRESH_APPLY as ON / OFF / not set with what each means for Friday and Saturday, and whether the mail settings are present (values
are never printed); (t4) the four customer sheet snapshot ages and the dry-run coverage (customer_coverage.run, customer_awards.run) so a customer row that is not in the research queue is seen BEFORE the
research. Verdict READY / READY WITH NOTES / FIX BEFORE 02:00; the email goes to CFP_RECAP_TO only; report thursday.md/.json; exit code 0 always. --qa-root redirects every file it writes.

OUTPUT. runs_out/qa/<cycle Monday>/release_gate.md + .json (pre-flight: preflight.md + .json) in the shared qa_report shape; stdout `GATE: <verdict> - <one line>`; the email (subject, plain text, HTML) is built
by build_email and sent through alerts.maybe_send_email to CFP_RECAP_TO ONLY (there is no recipient option) with both pages attached when they exist (each under 8 MB). --dry-run writes the email text beside the report and sends nothing."""
from __future__ import annotations

import argparse
import contextlib
import csv
import html as H
import io
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.cfp_monitor import qa_report                                      # noqa: E402
from src.cfp_monitor.identity import seed_map, to_canonical                # noqa: E402
from src.cfp_monitor.grounding import parse_loose_date                     # noqa: E402

MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
SNAPSHOTS = MARKETS / "customer_snapshots"
WEEKLY = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\handoff-files\weekly")
LIVE_DB = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\matts\AppData\Local")) / "CFP-Monitor" / "cfp_monitor.db"
OPS = ROOT / "docs" / "operations"
CONF_MARKETS = ("Cybersecurity", "Utility")
# the one vocabulary of reasons a customer row may be missing from the page with (nothing else is accepted; a missing row with none of these is "NOT ON THE PAGE, NO REASON")
R_PAST, R_WITHDRAWN, R_ID, R_HELD, R_PROV, R_DUP = ("past event", "withdrawn by customer", "held waiting for an id", "held by the row rule or a gate", "provisional", "duplicate listing")
R_QUEUED, R_RULED = "awaiting first research", "ruled out by the operator"
REASONS = (R_PAST, R_WITHDRAWN, R_ID, R_HELD, R_PROV, R_DUP, R_QUEUED, R_RULED)
QUIET_REASONS = (R_PAST, R_WITHDRAWN, R_DUP, R_RULED)         # counted, not a gap
SHEETS = {  # key -> (label, market, kind)
    "arnica": ("Arnica conferences", "Cybersecurity", "conference"), "utility": ("Utility Global conferences", "Utility", "conference"),
    "arnica-awards": ("Arnica awards", "Cybersecurity", "awards"), "utility-awards": ("Utility Global awards", "Utility", "awards"),
}
SNAP_WARN_DAYS, SNAP_FAIL_DAYS = 2.0, 4.0
SHRINK_FAIL = 0.10
STALE_SLACK_DAYS = 7
MAX_ATTACH_BYTES = 8_000_000
NAMES_SHOWN = 40


class Check(dict):
    """{'id','title','status' (PASS|WARN|FAIL|NA),'summary','rows'}"""

    def __init__(self, cid, title, status, summary, rows=None):
        super().__init__(id=cid, title=title, status=status, summary=summary, rows=list(rows or []))


def tidy(t) -> str:
    return re.sub(r"\s+", " ", (t or "").replace("\xa0", " ")).strip()


def ascii_text(t: str) -> str:
    from scripts.customer_awards import ascii_text as a
    return a(t)


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))



# ============================================================================ inputs
class Opts:
    def __init__(self, on: date, now: datetime | None = None, preflight: bool = False, markets_dir: Path = MARKETS, db: Path = LIVE_DB, snapshots_dir: Path = SNAPSHOTS,
                 awards_sheets_dir: Path | None = None, weekly_dir: Path = WEEKLY, work_dir: Path | None = None, qa_root: Path = qa_report.QA_ROOT,
                 commitments: Path = OPS / "upstream_commitments.csv", given_ids: Path = OPS / "given_ids.csv", ledger: Path = OPS / "customer_not_researched.csv"):
        self.on, self.now, self.preflight = on, now or datetime.now(), preflight
        self.markets_dir, self.db, self.snapshots_dir = Path(markets_dir), Path(db), Path(snapshots_dir)
        self.awards_sheets_dir = Path(awards_sheets_dir) if awards_sheets_dir else self.snapshots_dir
        self.weekly_dir = Path(weekly_dir)
        self.work_dir = Path(work_dir) if work_dir else self.weekly_dir / f"work_{on.isoformat()}"
        self.qa_root, self.commitments, self.given_ids, self.ledger = Path(qa_root), Path(commitments), Path(given_ids), Path(ledger)


def page_paths(o: Opts) -> dict:
    """{'conference': path|None, 'awards': path|None, 'published': bool}: the published folder first, else the work folder (then the pages are NOT published)."""
    if o.preflight:
        return {"conference": None, "awards": None, "published": False, "folder": None}
    names = {"conference": f"Conference Review {o.on} - Live Markets.html", "awards": f"Awards Review {o.on}.html"}
    pub = o.weekly_dir / o.on.isoformat()
    out = {"published": all((pub / n).exists() for n in names.values()), "folder": None}
    for k, n in names.items():
        for folder in (pub, o.work_dir):
            if (folder / n).exists():
                out[k] = folder / n
                out["folder"] = out["folder"] or folder
                break
        else:
            out[k] = None
    return out


def load_approved(o: Opts) -> dict:
    res: dict = {}
    for name in (*CONF_MARKETS, "Awards"):
        p = o.markets_dir / f"{name}_audited.final.csv"
        res[name] = read_csv(p) if p.exists() else None
    return res


def awards_customer_index(o: Opts):
    from scripts import customer_awards as ca
    return ca.customer_index(o.awards_sheets_dir)


def build_view(o: Opts, approved: dict, pages: dict) -> dict:
    """The rows each page shows: {'conference': [page row dicts] | None, 'awards': ..., 'source': {'conference': 'page'|'approved'}, 'prov': [provisional candidates shown], 'prov_notes': [...]}.
    A BUILT page is read back (qa_build.page_data: exactly what is sent); otherwise the approved file is run through the page builder's own rules."""
    import qa_build
    from scripts import build_review_page as brp
    from scripts import provisional_rows as pr
    view: dict = {"source": {}, "conference": None, "awards": None, "prov": [], "prov_notes": [], "prov_excluded": {}}
    for kind in ("conference", "awards"):
        p = pages.get(kind)
        if p:
            view[kind] = qa_build.page_data(p)
            view["source"][kind] = "page"
    quiet = io.StringIO()
    view["conf_prov_rows"], view["conf_prov_report"], view["conf_prov_notes"] = [], [], []
    if all(approved.get(m) is not None for m in CONF_MARKETS):
        u2c = seed_map(str(o.db))[0] if o.db.exists() else {}
        for m in CONF_MARKETS:
            try:
                got, rep, msg = pr.conference_page_rows(o.markets_dir, m, approved[m], u2c, o.on, data_root=o.db.parent) if u2c else ([], [], "the event-id map could not be read")
            except Exception as e:                                          # noqa: BLE001
                got, rep, msg = [], [], f"{type(e).__name__}: {e}"
            view["conf_prov_rows"] += got
            view["conf_prov_report"] += rep
            if msg:
                view["conf_prov_notes"].append(f"{m}: {msg}")
        if view["conference"] is None:
            with contextlib.redirect_stdout(quiet):
                view["conference"] = brp.build([*approved["Cybersecurity"], *approved["Utility"], *view["conf_prov_rows"]], o.on.isoformat())
            view["source"]["conference"] = "approved"
    cust = None
    if approved.get("Awards") is not None:
        cust = awards_customer_index(o)
        res, note, raw = pr.awards_candidates(o.markets_dir, approved["Awards"], o.db, o.on)
        view["prov_notes"].append(note)
        view["prov_excluded"] = res["excluded"]
        rows = pr.to_page_rows(res["rows"], o.on)
        shown_rows, _dropped = brp.awards_only(rows, cust)
        shown_names = {tidy(r.get("CONFERENCE")) for r in shown_rows}
        view["prov"] = [c for c in res["rows"] if c["name"] in shown_names]
        view["prov_hidden"] = [c for c in res["rows"] if c["name"] not in shown_names]
        view["raw_awards"] = raw
        if view["awards"] is not None:                              # a BUILT page is the truth about what was shown
            on_page = {tidy(r.get("n")) for r in view["awards"] if r.get("prov")}
            view["prov_not_on_page"] = [c for c in view["prov"] if pr.clean_text(c["name"]) not in on_page and c["name"] not in on_page]
            view["prov"] = [c for c in view["prov"] if c not in view["prov_not_on_page"]]
        if view["awards"] is None:
            kept, _ = brp.awards_only(approved["Awards"], cust)
            with contextlib.redirect_stdout(quiet):
                view["awards"] = brp.build(kept + shown_rows, o.on.isoformat())
            view["source"]["awards"] = "approved"
    return view


# ============================================================================ held reasons
def gate_reasons_from_log(text: str) -> list[tuple[str, str]]:
    """[(name as the log prints it, 'gate: <check title>: <detail>')] from a weekend_import.log: the '  [FAIL] n  title (k)' blocks and the lines '           - name: detail' under them."""
    out, title = [], ""
    for ln in text.splitlines():
        m = re.match(r"\s*\[FAIL\]\s+\S+\s+(.*?)\s*(?:\(\d+\))?\s*$", ln)
        if m:
            title = m.group(1)
            continue
        m = re.match(r"\s{6,}-\s+(.{3,60}?):\s+(.+)$", ln)
        if m and title:
            out.append((m.group(1).strip(), f"the gate failed '{title}': {m.group(2).strip()[:110]}"))
        elif ln.strip() and not ln.startswith(" "):
            title = ""
    return out


def held_lookup(o: Opts) -> dict:
    """What the newest Friday/Saturday import log and market_sheets/held_rows.txt say about held rows: {'log': [(name, reason)], 'held_rows': {canonical id: reason}}. Missing files give empty maps."""
    logs: list[tuple[str, str]] = []
    folders = sorted(p for p in (o.markets_dir / "weekend").glob("*") if p.is_dir())[-4:] if (o.markets_dir / "weekend").is_dir() else []
    for f in folders:
        lp = f / "weekend_import.log"
        if lp.exists():
            txt = lp.read_text(encoding="utf-8", errors="replace")
            logs += gate_reasons_from_log(txt)
            for m in re.finditer(r"NEW EVENT HELD \(not loaded\): (.{3,70}?) - (.+)", txt):
                logs.append((m.group(1).strip(), m.group(2).strip()[:140]))
    held_rows: dict[str, str] = {}
    hp = o.db.parent / "market_sheets" / "held_rows.txt"
    if hp.exists():
        for ln in hp.read_text(encoding="utf-8", errors="replace").splitlines():
            if "#" in ln:
                k, why = ln.split("#", 1)
                if k.strip():
                    held_rows[k.strip()] = re.sub(r"^AUTO \S+ weekend_import - ", "", why.strip())[:140]
    return {"log": logs, "held_rows": held_rows}


def held_reason(name: str, canon: str, lookup: dict) -> str:
    """The most specific reason the files give for why this researched row is not approved; '' when they give none."""
    if canon and canon in lookup["held_rows"]:
        return lookup["held_rows"][canon]
    low = tidy(name).lower()
    for n, why in reversed(lookup["log"]):
        n = tidy(n).lower()
        if n and (low.startswith(n[:38]) or n.startswith(low[:38])):
            return why
    return ""


# ============================================================================ (b) coverage
def past_by_dates(item: dict, today: date) -> bool:
    """An award is a PAST event when every date the customer's row states (event date, dates inside the deadline text) is before today, and it states at least one."""
    ds = []
    for field in ("event_date", "deadline"):
        txt = item.get(field) or ""
        for m in re.finditer(r"\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{1,2}-\d{1,2}", txt):
            d = parse_loose_date(m.group(0))
            if d:
                ds.append(d)
    return bool(ds) and max(ds) < today


def researched_inputs(o: Opts, market_file: str) -> set[str]:
    """Lower-cased INPUT names the newest research of this list answered (not a stub): from <name>_audited.identity.csv + the raw file."""
    from scripts import provisional_rows as pr
    raw_path, _ = pr.find_raw(o.markets_dir, market_file, o.on, max_age_days=60)
    ident = o.markets_dir / f"{market_file}_audited.identity.csv"
    if raw_path is None or not ident.exists():
        return set()
    stub = {tidy(r.get("EVENT_ID")) for r in read_csv(raw_path) if "Audit Exception" in (r.get("STATUS DETAILS") or "")}
    return {tidy(r.get("INPUT_CONFERENCE")).lower() for r in read_csv(ident) if tidy(r.get("OUTPUT_EVENT_ID")) not in stub}


def page_index(rows: list[dict]) -> dict:
    from scripts import customer_awards as ca
    idx: dict = {}
    for r in rows:
        m = r.get("m") or ""
        d = idx.setdefault(m, {"names": {}, "urls": {}})
        k = ca.name_key(r.get("n") or "")
        if k:
            d["names"].setdefault(k, r)
        for u in (r.get("sub"), r.get("url")):
            if ca.url_key(u or ""):
                d["urls"].setdefault(ca.url_key(u), []).append(r)
    return idx


def coverage_awards(o: Opts, rows_page: list[dict], approved_awards, lookup: dict) -> dict:
    """{sheet: stats} for the two awards sheets, or {'error': why}."""
    from scripts import customer_awards as ca
    inp_path = o.markets_dir / "Awards_input.csv"
    if not inp_path.exists():
        return {"error": f"the awards input list was not found ({inp_path})"}
    sheets = {}
    for client in ca.CLIENTS:
        p = ca.newest_sheet(o.awards_sheets_dir, client)
        if p is None:
            return {"error": f"no snapshot of the {client} sheet in {o.awards_sheets_dir}"}
        sheets[client] = ca.sheet_rows(p, client)
    inp = read_csv(inp_path)
    res = ca.check(sheets, inp, ca.load_ledger(o.ledger))
    verdict = {}
    for key in ("in_queue", "wrong_market", "excluded", "not_in_queue"):
        for it in res[key]:
            verdict[(it["client"], it["sheet_row"])] = (key, it)
    researched = researched_inputs(o, "Awards")
    in_by_name = {tidy(r.get("CONFERENCE")).lower(): r for r in inp}
    pidx = page_index(rows_page)
    out: dict = {}
    for client, rows in sheets.items():
        label, market, _k = SHEETS[client]
        use: dict[str, set[str]] = {}
        for r in rows:
            u = ca.url_key(r["url"])
            if u:
                use.setdefault(u, set()).add(ca.name_key(r["name"]))
        st = {"label": label, "market": market, "total": len(rows), "past": 0, "withdrawn": 0, "on_page": 0, "provisional": 0, "missing": [], "not_in_queue": [], "reasons": {}}
        for r in rows:
            key, it = verdict[(client, r["sheet_row"])]
            hit = None
            d = pidx.get(market, {"names": {}, "urls": {}})
            k, u = ca.name_key(r["name"]), ca.url_key(r["url"])
            if k and k in d["names"]:
                hit = d["names"][k]
            elif u and len(use.get(u, set())) <= 1:
                cands = d["urls"].get(u, [])
                if len({ca.name_key(c.get("n") or "") for c in cands}) == 1:
                    hit = cands[0]
            if hit is not None:
                st["on_page"] += 1
                if hit.get("prov"):
                    st["provisional"] += 1
                    st["reasons"][R_PROV] = st["reasons"].get(R_PROV, 0) + 1
                    st["missing"].append({"name": r["name"], "reason": R_PROV, "detail": "shown on the page as Provisional", "row": r["sheet_row"], "on_page": True})
                continue
            if past_by_dates(r, o.on):
                st["past"] += 1
                st["reasons"][R_PAST] = st["reasons"].get(R_PAST, 0) + 1
                st["missing"].append({"name": r["name"], "reason": R_PAST, "detail": "every date the customer's row states is before today", "row": r["sheet_row"], "on_page": False})
                continue
            reason, detail = None, ""
            if key == "excluded":
                if "ledger" in it["why"]:
                    reason, detail = R_RULED, it["why"]
                else:
                    reason, detail = R_DUP, it["why"]
            elif key == "not_in_queue":
                st["not_in_queue"].append({"name": r["name"], "row": r["sheet_row"], "detail": "no row on the awards input list has its name or its submission URL"})
                continue
            elif key == "wrong_market":
                reason, detail = R_QUEUED, f"on the input list only under the other market ({it['why']}); its sibling row is added at the next Friday step"
            else:
                irow = in_by_name.get(tidy(it["input_row"]).lower())
                canon = tidy((irow or {}).get("EVENT_ID_CANON"))
                was_researched = tidy(it["input_row"]).lower() in researched
                why = held_reason(it["input_row"], canon, lookup)
                if not was_researched:
                    reason, detail = R_QUEUED, "on the research queue, not researched yet"
                elif not canon:
                    reason, detail = R_ID, "researched this week; no permanent id yet, so it cannot be loaded"
                else:
                    reason, detail = R_HELD, why or "researched, but not in the approved file (new award: first load off or capped, or the row rule held it)"
            st["reasons"][reason] = st["reasons"].get(reason, 0) + 1
            st["missing"].append({"name": r["name"], "reason": reason, "detail": detail, "row": r["sheet_row"], "on_page": False})
        out[client] = st
    return out


def coverage_conferences(o: Opts, approved: dict, lookup: dict, prov: dict | None = None) -> dict:
    """{sheet: stats} for the two conference sheets (client_conferences, opened read-only), or {'error': why}. Reuses customer_coverage.check twice: against the APPROVED files (is it on the page?) and against the research input lists (is it queued?)."""
    import sqlite3
    import customer_coverage as cc
    if not o.db.exists():
        return {"error": f"the database was not found ({o.db})"}
    u2c, _roots = seed_map(str(o.db))
    con = sqlite3.connect(f"file:{str(o.db).replace(chr(92), '/')}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute("select * from client_conferences")]
    finally:
        con.close()
    if not rows:
        return {"error": "client_conferences is empty"}
    today = o.on.isoformat()
    as_inputs = {m: [{**r, "EVENT_ID_CANON": to_canonical(tidy(r.get("EVENT_ID")), u2c)} for r in (approved.get(m) or [])] for m in CONF_MARKETS}
    queue_inputs = {}
    for m in CONF_MARKETS:
        p = o.markets_dir / f"{m}_input.csv"
        if not p.exists():
            return {"error": f"input list not found ({p})"}
        queue_inputs[m] = read_csv(p)
    on_page = cc.check(rows, as_inputs, u2c, [], today)
    queued = cc.check(rows, queue_inputs, u2c, cc.load_ledger(o.ledger), today)
    qverdict = {}
    for key in ("in_queue", "excluded", "not_in_queue"):
        for it in queued[key]:
            qverdict[(it["client"], it["name"], it["url"])] = (key, it)
    researched = {m: researched_inputs(o, m) for m in CONF_MARKETS}
    out: dict = {}
    for client, sheet in (("arnica", "arnica"), ("utility-global", "utility")):
        label, market, _k = SHEETS[sheet]
        mine = [r for r in rows if r["client_key"] == client]
        st = {"label": label, "market": market, "total": len(mine), "past": 0, "withdrawn": 0, "on_page": 0, "provisional": 0, "missing": [], "not_in_queue": [], "reasons": {}}
        for it in on_page["in_queue"]:
            if it["client"] == client:
                st["on_page"] += 1
        for it in on_page["excluded"]:
            if it["client"] != client:
                continue
            for lead, reason in (("event is over", R_PAST), ("the customer removed", R_WITHDRAWN)):
                if it["why"].startswith(lead):
                    st["past" if reason == R_PAST else "withdrawn"] += 1
                    st["reasons"][reason] = st["reasons"].get(reason, 0) + 1
                    st["missing"].append({"name": it["name"], "reason": reason, "detail": it["why"], "start": it["start"], "on_page": False})
        for it in on_page["not_in_queue"]:
            if it["client"] != client:
                continue
            qk, qi = qverdict.get((it["client"], it["name"], it["url"]), ("not_in_queue", it))
            name = it["name"]
            shown = (prov or {}).get(market, {})
            pk = next((k for k in (tidy(qi.get("input_row") or "").lower(), tidy(name).lower()) if k in shown), None) if qk == "in_queue" else None
            hit = shown[pk] if pk is not None else None
            if hit is not None:                                              # researched, held out of the approved file, and shown on the page as Provisional (ACT-70)
                st["on_page"] += 1
                st["provisional"] += 1
                st["reasons"][R_PROV] = st["reasons"].get(R_PROV, 0) + 1
                st["missing"].append({"name": name, "reason": R_PROV, "detail": "shown on the page as Provisional" + (f" (left blank: {hit})" if hit else ""), "start": it["start"], "on_page": True})
                continue
            irow = next((r for r in queue_inputs[market] if tidy(r.get("CONFERENCE")) == tidy(qi.get("input_row"))), None) if qk == "in_queue" else None
            if qk == "not_in_queue":
                st["not_in_queue"].append({"name": name, "detail": f"customer start {it['start'] or 'unknown'}; no input row has its event id or its URL"})
                continue
            if qk == "excluded":
                reason, detail = (R_RULED if qi["why"].startswith("operator") else R_DUP), qi["why"]
            else:
                canon = tidy((irow or {}).get("EVENT_ID_CANON"))
                was = tidy(qi.get("input_row")).lower() in researched[market]
                why = held_reason(qi.get("input_row") or name, canon, lookup) or held_reason(name, canon, lookup)
                if not was:
                    reason, detail = R_QUEUED, "on the research queue, not researched yet"
                elif not canon:
                    reason, detail = R_ID, "researched this week; no permanent id yet, so it cannot be loaded"
                else:
                    reason, detail = R_HELD, why or "researched, but not in the approved file"
            st["reasons"][reason] = st["reasons"].get(reason, 0) + 1
            st["missing"].append({"name": name, "reason": reason, "detail": detail, "start": it["start"], "on_page": False})
        out[sheet] = st
    return out


def check_coverage(o: Opts, view: dict, approved: dict, lookup: dict, cov_conf, cov_awards) -> Check:
    rows, fails, warns, lines = [], [], [], []
    for title, cov in (("conferences", cov_conf), ("awards", cov_awards)):
        if "error" in cov:
            warns.append(f"customer {title}: could not be judged - {cov['error']}")
    for cov in (cov_conf, cov_awards):
        if "error" in cov:
            continue
        for sheet, st in cov.items():
            ahead = st["total"] - st["past"] - st["withdrawn"]
            absent = [m for m in st["missing"] if not m["on_page"]]
            lines.append(f"{st['label']}: {st['on_page']} of {ahead} rows still ahead are on the page"
                         + (f" ({st['provisional']} of them Provisional)" if st["provisional"] else "")
                         + f"; {len([m for m in absent if m['reason'] not in QUIET_REASONS])} missing with a reason to look at; {len(st['not_in_queue'])} NOT in the research queue; "
                         f"{st['past']} past events, {st['withdrawn']} withdrawn, {len([m for m in absent if m['reason'] in (R_DUP, R_RULED)])} duplicate or ruled out (not counted). Not on the page in all: {len(absent)} of {st['total']}")
            for n in st["not_in_queue"]:
                fails.append(f"{st['label']}: {n['name']} - NOT in the research queue ({n['detail']})")
            for m in st["missing"]:
                assert m["reason"] in REASONS, m["reason"]
                if not m["on_page"] and m["reason"] not in QUIET_REASONS:
                    warns.append(f"{st['label']}: {m['name']} - {m['reason']}: {m['detail']}")
    status = "FAIL" if fails else "WARN" if warns else "PASS"
    return Check("b", "Customer coverage: every row still ahead is on the page, or has one named reason", status,
                 ((f"{len(fails)} customer row(s) are not even in the research queue; " if fails else "") + f"{len(warns)} row(s) missing from the page with a reason to look at") if (fails or warns) else "every customer row ahead is on the page",
                 [*[f"FAIL {x}" for x in fails], *[f"WARN {x}" for x in warns], *[f"INFO {x}" for x in lines]]), lines


# ============================================================================ the other checks
def check_pages(o: Opts, pages: dict, approved: dict) -> Check:
    from src.cfp_monitor.publish_guard import check_publish_fresh
    rows, bad = [], []
    for name in (*CONF_MARKETS, "Awards"):
        p = o.markets_dir / f"{name}_audited.final.csv"
        ok, why = check_publish_fresh(p, today=o.on)
        rows.append(f"{'ok' if ok else 'STALE'} {name}: {why}")
        if not ok:
            bad.append(f"{name} approved file: {why}")
    if o.preflight:
        st = "FAIL" if bad else "PASS"
        return Check("a", "Pages built, fresh and healthy", "FAIL" if bad else "PASS",
                     ("approved files NOT fresh (the Monday build would publish old research); " if bad else "approved files fresh and accepted; ") + "pages not built yet (pre-flight)", rows)
    import qa_build
    for kind, label in (("conference", "Conference page"), ("awards", "Awards page")):
        p = pages.get(kind)
        if not p:
            bad.append(f"{label}: not found for {o.on} (looked in {o.weekly_dir / o.on.isoformat()} and {o.work_dir})")
            continue
        try:
            n = len(qa_build.page_data(p))
            size = Path(p).stat().st_size
            d = qa_build.page_date(p)
            rows.append(f"{label}: {Path(p).name}, {n} rows, {size // 1024} KB")
            if size < 20_000 or n == 0:
                bad.append(f"{label}: {Path(p).name} is too small or empty ({size} bytes, {n} rows)")
            if d != o.on:
                bad.append(f"{label}: {Path(p).name} is dated {d}, not {o.on} (an old page)")
        except Exception as e:                                                  # noqa: BLE001
            bad.append(f"{label}: {Path(p).name} cannot be read back ({type(e).__name__}: {e})")
    if not pages.get("published"):
        bad.append(f"the pages are NOT published ({o.weekly_dir / o.on.isoformat()} is missing one): the build was DEGRADED or has not finished; they must not be sent")
    man = o.work_dir / "MANIFEST.md"
    if man.exists():
        m = re.search(r"HEALTH:\s*(\w+)", man.read_text(encoding="utf-8", errors="replace"))
        rows.append(f"MANIFEST: HEALTH {m.group(1) if m else 'not stated'}")
        if not m or m.group(1) != "HEALTHY":
            bad.append(f"the build manifest says HEALTH {m.group(1) if m else 'not stated'}")
    else:
        bad.append(f"no MANIFEST.md in {o.work_dir}")
    return Check("a", "Pages built, fresh and healthy", "FAIL" if bad else "PASS", ("; ".join(bad[:3]) if bad else "both pages built today, published, build healthy, approved files fresh"),
                 [*[f"FAIL {b}" for b in bad], *[f"INFO {r}" for r in rows]])


def check_researched_not_on_page(o: Opts, view: dict, approved: dict, lookup: dict, conf_cands: dict, named_in_b: set | None = None) -> Check:
    items = []
    named_in_b = named_in_b or set()
    shown_conf = {tidy(e["name"]): ", ".join(e["blanked"]) for e in view.get("conf_prov_report", [])}
    for c in view.get("prov_hidden", []):
        items.append(f"Awards, {c['market']}: {c['name']} - researched, left off the page on purpose (not an award and no customer sheet lists it)")
    for market, res in conf_cands.items():
        for c in res["rows"]:
            low = tidy(c["name"]).lower()
            if tidy(c["name"]) not in shown_conf and any(len(b) >= 8 and (low.startswith(b) or b.startswith(low[:len(b)])) for b in named_in_b):
                continue                                                         # already named, with the customer who lists it, under (b)
            why = held_reason(c["name"], c["canon"], lookup)
            tag = "no permanent id yet" if c["category"] == "waiting_for_id" else (why or "researched but not in the approved file")
            if tidy(c["name"]) in shown_conf:
                items.append(f"Conferences, {market}: {c['name']} - shown on the Conference page as Provisional (left blank: {shown_conf[tidy(c['name'])] or 'nothing'})")
                continue
            items.append(f"Conferences, {market}: {c['name']} - {tag}")
    for c in view.get("prov_not_on_page", []):
        items.append(f"Awards, {c['market']}: {c['name']} - should be shown as Provisional but the built page does not carry it (was the page built without --provisional-dir?)")
    for c in view.get("prov", []):
        items.append(f"Awards, {c['market']}: {c['name']} - shown on the Awards page as Provisional")
    if not items:
        return Check("c", "Researched rows that are not on the page", "PASS", "every researched row is in the approved file" + (" or already named under (b)" if named_in_b else ""))
    n_off = len([i for i in items if "as Provisional" not in i])
    return Check("c", "Researched rows that are not on the page", "WARN" if n_off else "PASS",
                 f"{n_off} more researched row(s) are on neither page; {len(items) - n_off} are shown as Provisional" if n_off else f"{len(items)} researched row(s) shown as Provisional only", [f"WARN {i}" if "as Provisional" not in i else f"INFO {i}" for i in items])


def check_staleness(o: Opts, approved: dict) -> Check:
    from carry_age import rows_carried_whole
    import refresh_plan
    try:
        limit = refresh_plan.max_explained_days() + STALE_SLACK_DAYS
    except Exception:                                                           # noqa: BLE001
        limit = 67 + STALE_SLACK_DAYS
    old, info = [], []
    for name in (*CONF_MARKETS, "Awards"):
        rows = approved.get(name)
        if rows is None:
            continue
        for r in rows_carried_whole(rows, o.on, limit):
            old.append(f"{name}: {r['name']} - last researched {r['source_as_of']} ({r['days']} days)")
        if name == "Awards":
            n35 = len(rows_carried_whole(rows, o.on, 35))
            info.append(f"INFO Awards: {n35} of {len(rows)} rows were last researched more than 35 days ago (carried; the limit above is the conference policy's)")
    return Check("d", f"Staleness: rows not researched in {limit} days", "WARN" if old else "PASS",
                 f"{len(old)} approved row(s) not researched in more than {limit} days" if old else f"no approved row is older than {limit} days", [*[f"WARN {x}" for x in old], *info])


def check_provisional(o: Opts, view: dict) -> Check:
    names = [f"{r.get('n')} ({r.get('m')})" for r in (view.get("awards") or []) if r.get("prov")]
    conf = [f"{r.get('n')} ({r.get('m')})" for r in (view.get("conference") or []) if r.get("prov")]
    if view.get("awards") is None and view.get("conference") is None:
        return Check("e", "Provisional rows", "NA", "not judged (no rows)")
    note = [x for x in view.get("prov_notes", []) if x]
    blanks = {e["name"]: e for e in view.get("conf_prov_report", [])}
    rows = [f"WARN Awards: {n}" for n in names]
    for r in (view.get("conference") or []):
        if r.get("prov"):
            e = blanks.get(r.get("n"))
            rows.append(f"WARN Conferences: {r.get('n')} ({r.get('m')})" + (f" - left blank: {', '.join(e['blanked']) or 'nothing'}" if e else ""))
    parts = []
    if names:
        parts.append(f"{len(names)} Provisional award(s)")
    if conf:
        parts.append(f"{len(conf)} Provisional conference(s) with the failing field left blank")
    return Check("e", "Provisional rows on the pages", "WARN" if (names or conf) else "PASS",
                 (" and ".join(parts) + " on the pages: researched, not approved yet") if parts else "no provisional rows" + (f" ({note[0]})" if note else ""), rows)


def snapshot_age_days(path: Path, now: datetime) -> float:
    m = re.search(r"_(\d{8})-(\d{6})\.csv$", Path(path).name)
    when = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S") if m else datetime.fromtimestamp(Path(path).stat().st_mtime)
    return max(0.0, (now - when).total_seconds() / 86400)


def check_snapshots(o: Opts) -> Check:
    from scripts import customer_awards as ca
    rows, st = [], "PASS"
    for key, (label, _market, kind) in SHEETS.items():
        base = o.awards_sheets_dir if kind == "awards" else o.snapshots_dir
        p = ca.newest_sheet(base, key)
        if p is None:
            rows.append(f"FAIL {label}: no snapshot in {base}")
            st = "FAIL"
            continue
        age = snapshot_age_days(p, o.now)
        lvl = "FAIL" if age > SNAP_FAIL_DAYS else "WARN" if age > SNAP_WARN_DAYS else "PASS"
        st = "FAIL" if lvl == "FAIL" else ("WARN" if lvl == "WARN" and st != "FAIL" else st)
        rows.append(f"{lvl if lvl != 'PASS' else 'INFO'} {label}: {Path(p).name}, {age:.1f} days old")
    ages = [float(m.group(1)) for r in rows for m in [re.search(r", ([\d.]+) days old", r)] if m]
    n_old = sum(1 for a in ages if a > SNAP_WARN_DAYS)
    missing = sum(1 for r in rows if r.startswith("FAIL") and "no snapshot" in r)
    summary = ("all four snapshots are under 2 days old" if st == "PASS" else
               f"{n_old + missing} of the four customer sheet snapshots {'is' if n_old + missing == 1 else 'are'} older than 2 days or missing"
               + (f" (the oldest is {max(ages):.1f} days)" if ages else "") + ": the page may miss what the customer changed")
    return Check("f", "Customer sheet snapshots (age)", st, summary, rows)


def previous_rows(o: Opts, kind: str):
    import qa_build
    earlier = [p for p in qa_build.published_pages(kind, o.weekly_dir) if (qa_build.page_date(p) or date.max) < o.on]
    return (qa_build.page_data(earlier[-1]), earlier[-1]) if earlier else (None, None)


def check_build_qa(o: Opts, view: dict, commitments) -> Check:
    import qa_build
    fails, warns, info = [], [], []
    cust = awards_customer_index(o)
    for kind, label in (("conference", "Conference page"), ("awards", "Awards page")):
        cur = view.get(kind)
        if cur is None:
            warns.append(f"{label}: no rows to judge")
            continue
        prev, prev_path = previous_rows(o, kind)
        res = qa_build.compare(cur, prev, o.on, kind, cust)
        for f in res["flags"]:
            low = f.lower()
            if "shows open with a deadline" in low or "retired" in low:
                fails.append(f)
            elif "disputes" in low or "dead" in low or "gone" in low or "moved earlier" in low or "lost its deadline" in low:
                warns.append(f)
            else:
                warns.append(f)
        if prev is not None and len(prev) and len(cur) < len(prev) * (1 - SHRINK_FAIL):
            fails.append(f"{label}: {len(cur)} rows against {len(prev)} on {prev_path.name}: more than {int(SHRINK_FAIL * 100)} percent fewer than last week")
        info.append(f"INFO {label}: {len(cur)} rows" + (f" (last week {len(prev)})" if prev is not None else " (no earlier page to compare with)") + f"; source: {view['source'].get(kind, '?')}")
        if view["source"].get(kind) == "approved":
            info.append(f"INFO {label}: dead links and disputed deadlines are judged on the built page: not built yet")
    if commitments is None:
        warns.append("upstream promises: the checker could not run")
    else:
        bad = [r for r in commitments if r["state"] == "NOT KEPT"]
        if bad:
            warns.append(f"{len(bad)} upstream promise(s) NOT KEPT (each is named under h)")
    status = "FAIL" if fails else "WARN" if warns else "PASS"
    return Check("g", "Build QA: what the pages would show", status, f"{len(fails)} blocking, {len(warns)} to look at" if (fails or warns) else "nothing on the pages needs a look",
                 [*[f"FAIL {x}" for x in fails], *[f"WARN {x}" for x in warns], *info])


def ids_owed(o: Opts) -> list[str]:
    out = []
    for name in ("Awards", *CONF_MARKETS):
        p = o.markets_dir / f"{name}_input.csv"
        if not p.exists():
            continue
        for r in read_csv(p):
            if not tidy(r.get("EVENT_ID_CANON")) and not tidy(r.get("DUP_OF")):
                out.append(f"{name}: {tidy(r.get('CONFERENCE'))}")
    return out


def check_upstream(o: Opts, commitments) -> Check:
    rows, warns = [], []
    if commitments is None:
        warns.append("the promise checker could not run")
    else:
        due = [r for r in commitments if r["state"] in ("NOT KEPT", "BAD LEDGER LINE")]
        for r in due:
            warns.append(f"promise overdue: {r['id']} (note {r['note']}, due {r['due']}): {r['what']} - {r['detail']}")
        rows.append(f"INFO {sum(r['state'] == 'KEPT' for r in commitments)} promise(s) kept, {len(due)} overdue or malformed, {sum(r['state'] == 'NOT YET' for r in commitments)} not yet due")
    owed = ids_owed(o)
    for x in owed:
        warns.append(f"id owed by upstream: {x}")
    given = 0
    if o.given_ids.exists():
        given = len(read_csv(o.given_ids))
    rows.append(f"INFO {given} permanent ids are recorded as given by upstream (docs/operations/given_ids.csv)")
    return Check("h", "Upstream: promises overdue and ids owed", "WARN" if warns else "PASS",
                 f"{len([w for w in warns if w.startswith('promise')])} promise(s) overdue, {len(owed)} id(s) owed" if warns else "nothing overdue, no ids owed", [*[f"WARN {w}" for w in warns], *rows])


def verdict_of(checks: list[Check]) -> str:
    st = {c["status"] for c in checks}
    return "NO-GO" if "FAIL" in st else "GO WITH NOTES" if "WARN" in st else "GO"


# ============================================================================ run
def commitments_for(o: Opts):
    try:
        import check_commitments as cc
        files = {m: o.markets_dir / f"{m}_audited.final.csv" for m in cc.MARKET_NAMES}
        return cc.run(o.commitments, files, o.db, o.on.isoformat())
    except Exception:                                                           # noqa: BLE001
        return None


def safely(cid: str, title: str, fn):
    try:
        return fn()
    except Exception as e:                                                      # noqa: BLE001
        return Check(cid, title, "WARN", f"could not be judged: {type(e).__name__}: {e}")


def evaluate(o: Opts) -> dict:
    """Run every check. Returns the report dict (checks, verdict, coverage, counts). Never raises for a check fault: that check becomes a WARN."""
    from scripts import provisional_rows as pr
    approved = load_approved(o)
    pages = page_paths(o)
    missing = [n for n, r in approved.items() if r is None]
    view = build_view(o, approved, pages) if not missing else {"source": {}, "conference": None, "awards": None, "prov": [], "prov_notes": [], "prov_excluded": {}}
    lookup = held_lookup(o)
    commitments = commitments_for(o)
    conf_cands = {}
    for m in CONF_MARKETS:
        if approved.get(m) is not None:
            try:
                u2c = seed_map(str(o.db))[0] if o.db.exists() else {}
                res, _note, _raw = pr.conference_candidates(o.markets_dir, m, approved[m], u2c, o.on)
                conf_cands[m] = res
            except Exception:                                                   # noqa: BLE001
                conf_cands[m] = {"rows": [], "excluded": {}}
    prov_shown: dict = {}
    for e in view.get("conf_prov_report", []):
        prov_shown.setdefault(e["market"], {})[tidy(e["name"]).lower()] = ", ".join(e["blanked"])
    cov_conf = safely_cov(lambda: coverage_conferences(o, approved, lookup, prov_shown))
    cov_awards = safely_cov(lambda: coverage_awards(o, view.get("awards") or [], approved.get("Awards"), lookup))
    checks: list[Check] = []
    cov_lines: list[str] = []
    checks.append(safely("a", "Pages built, fresh and healthy", lambda: check_pages(o, pages, approved)))
    try:
        cb, cov_lines = check_coverage(o, view, approved, lookup, cov_conf, cov_awards)
        checks.append(cb)
    except Exception as e:                                                      # noqa: BLE001
        checks.append(Check("b", "Customer coverage", "WARN", f"could not be judged: {type(e).__name__}: {e}"))
    named_b = {tidy(m["name"]).lower() for cov in (cov_conf, cov_awards) if "error" not in cov for st in cov.values() for m in st["missing"] if not m["on_page"]}
    checks.append(safely("c", "Researched rows that are not on the page", lambda: check_researched_not_on_page(o, view, approved, lookup, conf_cands, named_b)))
    checks.append(safely("d", "Staleness", lambda: check_staleness(o, approved)))
    checks.append(safely("e", "Provisional rows", lambda: check_provisional(o, view)))
    checks.append(safely("f", "Customer sheet snapshots", lambda: check_snapshots(o)))
    checks.append(safely("g", "Build QA", lambda: check_build_qa(o, view, commitments)))
    checks.append(safely("h", "Upstream", lambda: check_upstream(o, commitments)))
    if missing:
        checks.insert(0, Check("a0", "Approved files present", "FAIL", f"approved file(s) missing: {', '.join(missing)}"))
    verdict = verdict_of(checks)
    counts = {"conference": len(view["conference"]) if view.get("conference") is not None else None,
              "awards": len(view["awards"]) if view.get("awards") is not None else None,
              "provisional": len([r for r in (view.get("awards") or []) if r.get("prov")]),
              "provisional_conference": len([r for r in (view.get("conference") or []) if r.get("prov")])}
    return {"checks": checks, "verdict": verdict, "counts": counts, "coverage": {"conference": cov_conf, "awards": cov_awards}, "coverage_lines": cov_lines, "pages": pages,
            "preflight": o.preflight, "on": o.on.isoformat()}


def safely_cov(fn):
    try:
        return fn()
    except Exception as e:                                                      # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


# ============================================================================ the Thursday pre-flight (ACT-70)
PATCHES = ROOT / "docs" / "control" / "patches"
THURSDAY_VERDICT = {"GO": "READY", "GO WITH NOTES": "READY WITH NOTES", "NO-GO": "FIX BEFORE 02:00"}
MARKERS = ("0", "0a0", "0a1", "0a1b", "0a", "0a2", "0b")        # the STEP markers of Markets\run_monthly.ps1 the Friday/Saturday chain is built from (more are learnt from the patches)
THU_SNAP_WARN_DAYS, THU_SNAP_FAIL_DAYS = 7.0, 10.0              # the weekly intake runs Saturday 02:00, so on Thursday evening a snapshot is normally 5.7 days old
SWITCHES = (
    ("CFP_AWARDS_NEW_EVENTS", "Friday", "a NEW award that upstream has given an id loads on Friday", "a new award is researched but NOT loaded (the Awards page shows it as Provisional)"),
    ("CFP_AWARDS_AUTOADD_APPLY", "Friday", "Friday ADDS customer awards that are missing from the research queue", "Friday only REPORTS the customer awards that are missing from the research queue; they are not researched"),
    ("CFP_AUTOADD_APPLY", "Saturday", "Saturday ADDS customer conferences that are missing from the research queue", "Saturday only REPORTS the customer conferences that are missing from the research queue; they are not researched"),
    ("CFP_REFRESH_APPLY", "Saturday", "Saturday skips researching closed events the refresh policy covers (last week's row is carried)", "Saturday researches every row, as before the refresh policy"),
)
MAIL_VARS = ("CFP_RECAP_TO", "CFP_SMTP_HOST", "CFP_SMTP_PORT", "CFP_SMTP_USER", "CFP_SMTP_PASS")


def env_value(name: str, env: dict | None = None) -> str:
    """The value a scheduled task started now would see: the USER-level variable, then the machine-level, then this process's. `env` (tests) replaces all three. Never printed by callers."""
    if env is not None:
        return env.get(name, "") or ""
    try:
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, "Environment"), (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    v, _t = winreg.QueryValueEx(k, name)
                    if v:
                        return str(v)
            except OSError:
                continue
    except ImportError:
        pass
    return os.environ.get(name, "") or ""


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()


def patch_signature(patch_text: str) -> dict:
    """What identifies a patch in the live script: its STEP marker when the added text carries one, else its longest added code line (comments and blanks do not count)."""
    target, added = "", []
    for ln in patch_text.splitlines():
        if ln.startswith("+++ "):
            target = re.sub(r"^b/", "", ln[4:].strip())
        elif ln.startswith("+") and not ln.startswith("+++"):
            added.append(ln[1:])
    for ln in added:
        m = re.search(r"STEP\s+(\w+):", ln)
        if m:
            return {"kind": "marker", "marker": m.group(1), "target": Path(target).name}
    code = [a for a in added if a.strip() and not a.strip().startswith("#")]
    line = max(code, key=lambda a: len(_norm(a)), default="")
    return {"kind": "line", "line": _norm(line), "target": Path(target).name}


def patches_status(markets_dir: Path, patches_dir: Path = PATCHES) -> dict:
    """{'script', 'readable', 'markers': {marker: present}, 'patches': [{'name', 'applied': True|False|None, 'how'}]}. Reads Markets run_monthly.ps1 (and run_overnight.ps1 for its patch) and
    docs/control/patches; changes nothing."""
    texts: dict = {}
    for name in ("run_monthly.ps1", "run_overnight.ps1"):
        try:
            texts[name] = (Path(markets_dir) / name).read_text(encoding="utf-8", errors="replace")
        except OSError:
            texts[name] = None
    live = texts["run_monthly.ps1"]
    out: dict = {"script": str(Path(markets_dir) / "run_monthly.ps1"), "readable": live is not None, "markers": {}, "patches": []}
    sigs = []
    for pf in sorted(Path(patches_dir).glob("ACT-*.patch")):
        try:
            sigs.append((pf.name, patch_signature(pf.read_text(encoding="utf-8", errors="replace"))))
        except OSError:
            continue
    learnt = [x["marker"] for _n, x in sigs if x["kind"] == "marker"]
    for m in dict.fromkeys([*MARKERS, *learnt]):
        out["markers"][m] = bool(live and re.search(r"STEP\s+" + re.escape(m) + r":", live))
    for name, sig in sigs:
        text = texts.get(sig["target"])
        if text is None:
            out["patches"].append({"name": name, "applied": None, "how": f"{sig['target'] or 'its target script'} could not be read"})
        elif sig["kind"] == "marker":
            out["patches"].append({"name": name, "applied": bool(re.search(r"STEP\s+" + re.escape(sig["marker"]) + r":", text)), "how": f"STEP {sig['marker']}"})
        else:
            out["patches"].append({"name": name, "applied": bool(sig["line"]) and _norm(sig["line"]) in _norm(text), "how": "its added step line"})
    return out


def thursday_awards_waiting(o: Opts) -> list[str]:
    return [x for x in ids_owed(o) if x.startswith("Awards:")]


def newest_request_draft(qa_root: Path) -> Path | None:
    cands = sorted(Path(qa_root).glob("*/request_to_upstream_awards_*.md"), key=lambda p: p.stat().st_mtime) if Path(qa_root).is_dir() else []
    return cands[-1] if cands else None


def thursday_checks(o: Opts, env: dict | None = None, patches_dir: Path = PATCHES) -> tuple[list, dict]:
    """The four Thursday checks and the facts behind them (for the report and the tests)."""
    facts: dict = {}
    checks: list = []

    def c1():
        ps = patches_status(o.markets_dir, patches_dir)
        facts["patches"] = ps
        if not ps["readable"]:
            return Check("t1", "Patches applied to the weekend script", "FAIL", f"{ps['script']} could not be read: nothing can be said about which steps will run")
        miss = [p for p in ps["patches"] if p["applied"] is False]
        unk = [p for p in ps["patches"] if p["applied"] is None]
        rows = [f"WARN {p['name']}: patch in the repo; its text is NOT in the live script ({p['how']} is not there): not applied, or applied in different words - if not applied that step will not run" for p in miss]
        rows += [f"WARN {p['name']}: {p['how']}" for p in unk]
        rows += [f"INFO {p['name']}: applied ({p['how']})" for p in ps["patches"] if p["applied"]]
        rows += [f"INFO STEP {m}: {'present' if ok else 'ABSENT'} in the live script" for m, ok in ps["markers"].items()]
        n_ok = sum(1 for p in ps["patches"] if p["applied"])
        return Check("t1", "Patches applied to the weekend script", "WARN" if (miss or unk) else "PASS",
                     f"{n_ok} of {len(ps['patches'])} patches are in the live script; {len(miss)} approved but not applied" if (miss or unk) else f"all {len(ps['patches'])} patches are in the live script", rows)
    checks.append(safely("t1", "Patches applied to the weekend script", c1))

    def c2():
        waiting = thursday_awards_waiting(o)
        facts["awards_waiting"] = waiting
        draft = newest_request_draft(o.qa_root)
        facts["request_draft"] = str(draft) if draft else ""
        rows = [f"WARN {w} (researched on Friday, but it cannot load until upstream gives it an id)" for w in waiting]
        rows.append(f"INFO draft request to upstream for ids: {draft}" if draft else "INFO no draft request to upstream for award ids was found under the QA folder")
        summary = (f"{len(waiting)} award(s) on the input list have no permanent id yet" + ("; send the draft request before Friday 02:00" if draft else "")) if waiting else "no award on the input list is waiting for an id"
        return Check("t2", "Awards waiting for a permanent id", "WARN" if waiting else "PASS", summary, rows)
    checks.append(safely("t2", "Awards waiting for a permanent id", c2))

    def c3():
        rows, state = [], {}
        for name, day, on_text, off_text in SWITCHES:
            v = env_value(name, env)
            st = "ON" if v == "1" else ("OFF" if v else "not set")
            state[name] = st
            rows.append(f"INFO {name} is {st} - {day}: " + (on_text if st == "ON" else off_text))
        mail = {n: bool(env_value(n, env)) for n in MAIL_VARS}
        facts["switches"], facts["mail"] = state, mail
        absent = [n for n, ok in mail.items() if not ok]
        rows.append("INFO email: " + ", ".join(f"{n} {'set' if ok else 'NOT SET'}" for n, ok in mail.items()))
        if absent:
            rows.insert(0, f"WARN email cannot reach you from a scheduled task: {', '.join(absent)} not set at user or machine level (the recap and the gate email would not arrive)")
        return Check("t3", "Switches and the mailer", "WARN" if absent else "PASS",
                     (f"{len(absent)} mail setting(s) missing" if absent else "the mail settings are present") + "; " + ", ".join(f"{n.replace('CFP_', '')} {s}" for n, s in state.items()), rows)
    checks.append(safely("t3", "Switches and the mailer", c3))

    def c4():
        from scripts import customer_awards as ca
        import customer_coverage as cc
        rows, fails, warns, ages = [], [], [], {}
        for key, (label, _m, kind) in SHEETS.items():
            base = o.awards_sheets_dir if kind == "awards" else o.snapshots_dir
            p = ca.newest_sheet(base, key)
            if p is None:
                fails.append(f"{label}: no snapshot in {base}")
                continue
            age = snapshot_age_days(p, o.now)
            ages[key] = round(age, 1)
            note = ("Friday's awards run reads this snapshot as it is (the intake runs on Saturday 02:00)" if kind == "awards" else "Saturday's intake takes a fresh one before the research")
            if age > THU_SNAP_FAIL_DAYS:
                fails.append(f"{label}: {Path(p).name}, {age:.1f} days old: the weekly intake has not run for over a week")
            elif age > THU_SNAP_WARN_DAYS:
                warns.append(f"{label}: {Path(p).name}, {age:.1f} days old: the weekly intake missed a week")
            else:
                rows.append(f"INFO {label}: {Path(p).name}, {age:.1f} days old - {note}")
        facts["snapshot_ages"] = ages
        conf_nq: list = []
        res, degraded, why = cc.run(o.db, o.markets_dir, o.ledger, o.on.isoformat())
        if res is None:
            warns.append(f"customer conferences: could not be judged - {why}")
            facts["conference_coverage"] = {"error": why}
        else:
            lines = cc.summary_lines(res)
            conf_nq = [x["name"] for x in res["not_in_queue"]]
            facts["conference_coverage"] = {"in_queue": len(res["in_queue"]), "not_in_queue": len(conf_nq), "lines": lines, "degraded": degraded}
            rows += [f"INFO {x}" for x in lines]
        lines_a, _rc = ca.run(o.on.isoformat(), o.awards_sheets_dir, o.markets_dir, o.ledger, Path(o.qa_root) / o.on.isoformat() / "thursday_awards", ca.CAP_PER_MARKET, False)
        facts["awards_coverage_lines"] = lines_a
        rows += [f"INFO {x}" for x in lines_a]
        m = re.search(r"AWARDS COVERAGE: (\d+) of (\d+) customer awards are on the research input list; (\d+) are NOT", " ".join(lines_a))
        aw_nq = int(m.group(3)) if m else 0
        facts["awards_not_in_queue"] = aw_nq
        sw = facts.get("switches", {})
        if conf_nq:
            names = "; ".join(conf_nq[:6]) + ("; and more" if len(conf_nq) > 6 else "")
            if sw.get("CFP_AUTOADD_APPLY") == "ON":
                rows.insert(0, f"INFO {len(conf_nq)} customer conference(s) are not in the research queue; CFP_AUTOADD_APPLY is ON, so Saturday adds them: {names}")
            else:
                fails.insert(0, f"{len(conf_nq)} customer conference(s) are NOT in the research queue and CFP_AUTOADD_APPLY is {sw.get('CFP_AUTOADD_APPLY', 'not set')}, so Saturday will NOT research them: {names}")
        if aw_nq:
            if sw.get("CFP_AWARDS_AUTOADD_APPLY") == "ON":
                rows.insert(0, f"INFO {aw_nq} customer award(s) are not in the research queue; CFP_AWARDS_AUTOADD_APPLY is ON, so Friday adds them")
            else:
                fails.insert(0, f"{aw_nq} customer award(s) are NOT in the research queue and CFP_AWARDS_AUTOADD_APPLY is {sw.get('CFP_AWARDS_AUTOADD_APPLY', 'not set')}, so Friday will NOT research them")
        status = "FAIL" if fails else "WARN" if warns else "PASS"
        body = [*[f"FAIL {x}" for x in fails], *[f"WARN {x}" for x in warns], *rows]
        return Check("t4", "Customer sheets: snapshot ages and coverage of the research queue", status,
                     f"{len(fails)} problem(s) to fix before 02:00" if fails else f"{len(warns)} note(s)" if warns else "every customer row ahead is in the research queue (or will be added)", body)
    checks.append(safely("t4", "Customer sheets", c4))
    return checks, facts


def evaluate_thursday(o: Opts, env: dict | None = None, patches_dir: Path = PATCHES) -> dict:
    checks, facts = thursday_checks(o, env, patches_dir)
    gv = verdict_of(checks)
    return {"checks": checks, "facts": facts, "verdict": THURSDAY_VERDICT[gv], "gate_verdict": gv, "preflight": True, "thursday": True, "on": o.on.isoformat(),
            "counts": {}, "coverage": {}, "coverage_lines": [], "pages": {}}


def thursday_lines(rep: dict) -> list[str]:
    c = {x["id"]: x for x in rep["checks"]}
    f = rep["facts"]
    L = ["This is the Thursday pre-flight for Friday 02:00 (awards research) and Saturday 02:00 (conference research). It only reads files; nothing was changed and nothing went to a customer."]
    L.append("Patches: " + c["t1"]["summary"] + ".")
    L.append("Awards waiting for ids: " + c["t2"]["summary"] + ".")
    sw = f.get("switches", {})
    if sw:
        L.append("Switches: " + "; ".join(f"{n.replace('CFP_', '')} {s}" for n, s in sw.items()) + " (what each means is listed below).")
    L.append("Mail: " + ("all settings present." if c["t3"]["status"] == "PASS" else c["t3"]["summary"].split(";")[0] + "."))
    L.append("Customer sheets: " + c["t4"]["summary"] + ".")
    L.append({"READY": "Nothing stands in the way of Friday's and Saturday's research.", "READY WITH NOTES": "Friday and Saturday can run; the notes below say what will not happen unless you act first.",
              "FIX BEFORE 02:00": "Fix the FAIL items below before Friday 02:00: the weekly outcome would be incomplete otherwise."}[rep["verdict"]])
    return L


def thursday_email(rep: dict) -> tuple[str, str, str]:
    subj = f"CFP Thursday pre-flight: {rep['verdict']}"
    lines = thursday_lines(rep)
    T = [f"VERDICT: {rep['verdict']}  (Thursday pre-flight for {rep['on']})", ""] + [f"- {ascii_text(x)}" for x in lines]
    for title, items in named_rows(rep):
        T += ["", title.upper()] + [f"  - {x}" for x in items[:NAMES_SHOWN]]
    infos = [(ck["title"], [r[5:] for r in ck["rows"] if r.startswith("INFO")]) for ck in rep["checks"]]
    for title, items in infos:
        if items:
            T += ["", f"DETAIL: {title}".upper()] + [f"  - {ascii_text(x)}" for x in items[:NAMES_SHOWN]]
    T += ["", "This email goes to the operator only. Nothing is sent to a customer by this check."]
    colour = {"READY": "#136c3c", "READY WITH NOTES": "#9a6200", "FIX BEFORE 02:00": "#c0392b"}[rep["verdict"]]
    h = [f"<h2 style='color:{colour}'>{H.escape(rep['verdict'])}</h2>", "<ul>" + "".join(f"<li>{H.escape(ascii_text(x))}</li>" for x in lines) + "</ul>"]
    for title, items in named_rows(rep):
        h.append(f"<h3>{H.escape(title)}</h3><ul>" + "".join(f"<li>{H.escape(x)}</li>" for x in items[:NAMES_SHOWN]) + "</ul>")
    for title, items in infos:
        if items:
            h.append(f"<h3>{H.escape(title)} - detail</h3><ul>" + "".join(f"<li>{H.escape(ascii_text(x))}</li>" for x in items[:NAMES_SHOWN]) + "</ul>")
    return subj, "\n".join(T) + "\n", "<html><body style='font-family:Segoe UI,Arial,sans-serif;font-size:14px'>" + "".join(h) + "<p><i>This email goes to the operator only.</i></p></body></html>"


def thursday_markdown(rep: dict) -> str:
    L = [f"# Thursday pre-flight for {rep['on']}", "", f"**{rep['verdict']}**", ""] + [f"- {x}" for x in thursday_lines(rep)]
    for ck in rep["checks"]:
        L += ["", f"## ({ck['id']}) {ck['title']} - {ck['status']}", "", ck["summary"], ""] + [f"- {r}" for r in ck["rows"]]
    return ascii_text("\n".join(L)) + "\n"


def write_thursday_report(rep: dict, o: Opts) -> Path:
    r = qa_report.new_report("thursday", o.on)
    r.update(status="PASS" if rep["verdict"] == "READY" else "FLAG", summary=rep["verdict"], verdict=rep["verdict"], mode="thursday", checks=[dict(c) for c in rep["checks"]], facts=rep["facts"])
    r["flags"] = [f"{c['id']}: {c['summary']}" for c in rep["checks"] if c["status"] in ("WARN", "FAIL")]
    subj, text, _h = thursday_email(rep)
    r["email"] = {"subject": subj, "text": text}
    return qa_report.write(r, thursday_markdown(rep), o.qa_root)


# ============================================================================ the report and the email
def plain_lines(rep: dict) -> list[str]:
    """5 to 10 plain lines: what is in, what is missing and why, what needs a decision."""
    c = {x["id"]: x for x in rep["checks"]}
    n = rep["counts"]
    pre = rep["preflight"]
    L = []
    if pre:
        L.append(f"This is the Sunday pre-flight: the approved files and the customer sheets as they stand now, pages not built yet. Monday's build would show about {n['conference'] if n['conference'] is not None else '?'} conferences and {n['awards'] if n['awards'] is not None else '?'} awards.")
    else:
        L.append(f"The pages are {'built and published' if c.get('a', {}).get('status') == 'PASS' else 'NOT ready to send'}: {n['conference'] if n['conference'] is not None else '?'} conferences and {n['awards'] if n['awards'] is not None else '?'} awards"
                 + (f" ({n['provisional']} of the awards {'is' if n['provisional'] == 1 else 'are'} Provisional)." if n["provisional"] else "."))
    if n.get("provisional_conference"):
        L.append(f"{n['provisional_conference']} conference row(s) are shown as Provisional: researched, held by a check, with the failing field left blank (named below).")
    if c["a"]["status"] == "FAIL":
        L.append("Stop first: " + c["a"]["summary"] + ".")
    for sheet, label in (("conference", "conferences"), ("awards", "awards")):
        cov = rep["coverage"][sheet]
        if "error" in cov:
            L.append(f"Customer {label}: could not be judged ({cov['error']}).")
            continue
        parts = []
        for key, st in cov.items():
            ahead = st["total"] - st["past"] - (st["withdrawn"] if SHEETS[key][2] == "conference" else 0)
            parts.append(f"{st['label'].split(' ')[0]} {st['on_page']} of {ahead}")
        gaps = sum(len([m for m in st["missing"] if not m["on_page"] and m["reason"] not in QUIET_REASONS]) for st in cov.values())
        nq = sum(len(st["not_in_queue"]) for st in cov.values())
        L.append(f"Customer {label} still ahead that are on the page: {', '.join(parts)}. {gaps} are missing with a named reason" + (f" and {nq} are not even in the research queue (a decision: add them)." if nq else "."))
    if c.get("c", {}).get("status") == "WARN":
        L.append(c["c"]["summary"].replace("1 are", "1 is") + " (listed below).")
    if c.get("e", {}).get("status") == "WARN":
        L.append(c["e"]["summary"] + ".")
    for cid in ("g", "f", "d", "h"):
        x = c.get(cid)
        if x and x["status"] in ("WARN", "FAIL"):
            L.append(f"{x['title']}: {x['summary']}.")
    if pre:
        L.append({"GO": "Nothing stands in the way of Monday's build.", "GO WITH NOTES": "Monday's build can go ahead; the notes below say what is missing and why, so there is time to act before 07:00.",
                  "NO-GO": "Monday's build would not be safe to forward: deal with the FAIL items below before 07:00 Monday."}[rep["verdict"]])
    else:
        L.append({"GO": "Nothing stands in the way: forward the pages.", "GO WITH NOTES": "The pages can be forwarded; the notes below say what is missing and why.",
                  "NO-GO": "Do not forward the pages until the FAIL items below are dealt with."}[rep["verdict"]])
    return L[:10]


def named_rows(rep: dict) -> list[tuple[str, list[str]]]:
    out = []
    for ck in rep["checks"]:
        items = [r for r in ck["rows"] if not r.startswith("INFO")]
        if items:
            out.append((f"({ck['id']}) {ck['title']} - {ck['status']}", [ascii_text(re.sub(r'^(FAIL|WARN) ', lambda m: m.group(1) + ': ', i)) for i in items]))
    return out


def build_email(rep: dict) -> tuple[str, str, str]:
    """-> (subject, plain text, html)."""
    n = rep["counts"]
    word = "pre-flight" if rep["preflight"] else "pages"
    subj = f"CFP weekly {word}: {rep['verdict']} - Conferences {n['conference'] if n['conference'] is not None else '?'}, Awards {n['awards'] if n['awards'] is not None else '?'}"
    lines = plain_lines(rep)
    T = [f"VERDICT: {rep['verdict']}  ({'Sunday pre-flight' if rep['preflight'] else 'Monday build'} for {rep['on']})", ""]
    T += [f"- {ascii_text(x)}" for x in lines] + ["", "CUSTOMER COVERAGE (rows still ahead that are on the page)"]
    T += [f"  {ascii_text(x)}" for x in rep["coverage_lines"]] or ["  (not judged)"]
    for title, items in named_rows(rep):
        T += ["", title.upper()] + [f"  - {x}" for x in items[:NAMES_SHOWN]] + ([f"  ... and {len(items) - NAMES_SHOWN} more (all of them are in release_gate.md)"] if len(items) > NAMES_SHOWN else [])
    T += ["", "This email goes to the operator only. Nothing is sent to a customer by this check."]
    text = "\n".join(T) + "\n"
    colour = {"GO": "#136c3c", "GO WITH NOTES": "#9a6200", "NO-GO": "#c0392b"}[rep["verdict"]]
    h = [f"<h2 style='color:{colour}'>{H.escape(rep['verdict'])}</h2>", "<ul>" + "".join(f"<li>{H.escape(ascii_text(x))}</li>" for x in lines) + "</ul>",
         "<h3>Customer coverage</h3><ul>" + "".join(f"<li>{H.escape(ascii_text(x))}</li>" for x in rep["coverage_lines"]) + "</ul>"]
    for title, items in named_rows(rep):
        h.append(f"<h3>{H.escape(title)}</h3><ul>" + "".join(f"<li>{H.escape(x)}</li>" for x in items[:NAMES_SHOWN]) + "</ul>")
    return subj, text, "<html><body style='font-family:Segoe UI,Arial,sans-serif;font-size:14px'>" + "".join(h) + "<p><i>This email goes to the operator only.</i></p></body></html>"


def to_markdown(rep: dict) -> str:
    L = [f"# Release gate - {'Sunday pre-flight' if rep['preflight'] else 'Monday build'} for {rep['on']}", "", f"**{rep['verdict']}**", ""]
    L += [f"- {x}" for x in plain_lines(rep)] + ["", "## Customer coverage", ""] + [f"- {x}" for x in rep["coverage_lines"]]
    for ck in rep["checks"]:
        L += ["", f"## ({ck['id']}) {ck['title']} - {ck['status']}", "", ck["summary"], ""] + [f"- {r}" for r in ck["rows"]]
    return ascii_text("\n".join(L)) + "\n"


def write_report(rep: dict, o: Opts) -> Path:
    """Shared qa_report shape: runs_out/qa/<cycle>/release_gate.(md|json), or preflight.* for the Sunday run."""
    step = "preflight" if o.preflight else "release_gate"
    r = qa_report.new_report(step, o.on)
    r.update(status="PASS" if rep["verdict"] == "GO" else "FLAG", summary=rep["verdict"], verdict=rep["verdict"], mode="preflight" if o.preflight else "monday", counts=rep["counts"],
             checks=[dict(c) for c in rep["checks"]], coverage=rep["coverage"], coverage_lines=rep["coverage_lines"])
    r["flags"] = [f"{c['id']}: {c['summary']}" for c in rep["checks"] if c["status"] in ("WARN", "FAIL")]
    subj, text, _h = build_email(rep)
    r["email"] = {"subject": subj, "text": text}
    return qa_report.write(r, to_markdown(rep), o.qa_root)


def attachments_for(rep: dict) -> list[Path]:
    """Both pages when they exist and are under MAX_ATTACH_BYTES each (a copy named 'DO NOT SEND' is not made: an unpublished page is attached under its own name and the subject says NO-GO)."""
    out = []
    for kind in ("conference", "awards"):
        p = rep["pages"].get(kind)
        if p and Path(p).exists() and Path(p).stat().st_size <= MAX_ATTACH_BYTES:
            out.append(Path(p))
    return out


def send(rep: dict, mailer=None) -> bool:
    """Send to the operator ONLY. `mailer(subject, body, html=, to_env=, attachments=)` defaults to alerts.maybe_send_email; tests pass a stub. The recipient is the env var CFP_RECAP_TO: there is no way to name another."""
    if mailer is None:
        from src.cfp_monitor.alerts import maybe_send_email as mailer
    subj, text, html_ = thursday_email(rep) if rep.get("thursday") else build_email(rep)
    return bool(mailer(subj, text, html=html_, to_env="CFP_RECAP_TO", attachments=attachments_for(rep) or None))


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--on", default=date.today().isoformat())
    ap.add_argument("--now", default="", help="the moment to age the snapshots against (default: now); for rehearsals")
    ap.add_argument("--preflight", action="store_true", help="Sunday pre-flight: judge the approved files and the newest snapshots, build no pages")
    ap.add_argument("--thursday", action="store_true", help="Thursday 18:00 pre-flight for Friday's and Saturday's research (ACT-70): patches applied, awards waiting for ids, switches, customer sheet ages and coverage; READY / READY WITH NOTES / FIX BEFORE 02:00")
    ap.add_argument("--dry-run", action="store_true", help="write the report and the email text, send nothing")
    ap.add_argument("--no-attach", action="store_true")
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--snapshots-dir", default=str(SNAPSHOTS))
    ap.add_argument("--awards-sheets-dir", default="", help="a folder of <client>.csv copies of the two awards sheets (rehearsal)")
    ap.add_argument("--weekly-dir", default=str(WEEKLY))
    ap.add_argument("--work-dir", default="")
    ap.add_argument("--qa-root", default=str(qa_report.QA_ROOT))
    a = ap.parse_args(argv)
    try:
        o = Opts(date.fromisoformat(a.on), datetime.fromisoformat(a.now) if a.now else None, a.preflight, Path(a.markets_dir), Path(a.db), Path(a.snapshots_dir),
                 Path(a.awards_sheets_dir) if a.awards_sheets_dir else None, Path(a.weekly_dir), Path(a.work_dir) if a.work_dir else None, Path(a.qa_root))
        if a.thursday:
            rep = evaluate_thursday(o)
            folder = write_thursday_report(rep, o)
            subj, text, html_ = thursday_email(rep)
            print(f"GATE: {rep['verdict']} - {subj}")
            print(f"report: {folder}")
            if a.dry_run:
                (folder / "thursday_email.txt").write_text(f"Subject: {subj}"+chr(10)+"To: CFP_RECAP_TO (operator only)"+chr(10)+chr(10)+text, encoding="utf-8")
                (folder / "thursday_email.html").write_text(html_, encoding="utf-8")
                print(f"(dry run - email text written to {folder / 'thursday_email.txt'}, not sent)")
            else:
                try:
                    print("email sent to the operator" if send(rep) else "email NOT sent - CFP_RECAP_TO or CFP_SMTP_* not set")
                except Exception as e:                                          # noqa: BLE001
                    print(f"email NOT sent - {type(e).__name__}: {e}")
            return 0
        rep = evaluate(o)
        folder = write_report(rep, o)
        subj, text, html_ = build_email(rep)
        if a.no_attach:
            rep["pages"] = {}
        print(f"GATE: {rep['verdict']} - {subj}")
        print(f"report: {folder}")
        if a.dry_run:
            step = "preflight" if o.preflight else "release_gate"
            (folder / f"{step}_email.txt").write_text(f"Subject: {subj}\nTo: CFP_RECAP_TO (operator only)\nAttachments: {[p.name for p in attachments_for(rep)]}\n\n{text}", encoding="utf-8")
            (folder / f"{step}_email.html").write_text(html_, encoding="utf-8")
            print(f"(dry run - email text written to {folder / (step + '_email.txt')}, not sent)")
        else:
            try:
                print("email sent to the operator" if send(rep) else "email NOT sent - CFP_RECAP_TO or CFP_SMTP_* not set")
            except Exception as e:                                              # noqa: BLE001
                print(f"email NOT sent - {type(e).__name__}: {e}")
    except Exception as e:                                                      # noqa: BLE001
        print(f"GATE: UNKNOWN - {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
