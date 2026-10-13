"""The weekly RELEASE GATE: is this week's delivery complete and safe to forward? One verdict, one email to the OPERATOR ONLY (ACT-68; QA-REGISTER A62). Reports, never blocks: exit code 0 always.

    python scripts/release_gate.py [--on 2026-10-12] [--preflight] [--dry-run] [--work-dir D] [--weekly-dir D] [--markets-dir D] [--snapshots-dir D] [--db DB] [--qa-root D] [--no-attach]

WHY. Three weeks running the operator had no deliverable Awards page and assembled the Conference page by hand. Nothing said, in one place, whether the week's files were complete; the gaps were found by hand on Monday
morning. This reads the approved files, the customer sheets, the research queue, the database (read-only) and, when they exist, the built pages, and answers: GO, GO WITH NOTES or NO-GO, naming every row behind a note.

TWO MODES. MONDAY (default): after the build and the manifest, with the two HTML pages. PRE-FLIGHT (--preflight, run on Sunday by weekend_recap.py after the Sunday sweep): the same checks from the APPROVED FILES and the newest
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
    if view["conference"] is None and all(approved.get(m) is not None for m in CONF_MARKETS):
        with contextlib.redirect_stdout(quiet):
            view["conference"] = brp.build([*approved["Cybersecurity"], *approved["Utility"]], o.on.isoformat())
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


def coverage_conferences(o: Opts, approved: dict, lookup: dict) -> dict:
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
    for c in view.get("prov_hidden", []):
        items.append(f"Awards, {c['market']}: {c['name']} - researched, left off the page on purpose (not an award and no customer sheet lists it)")
    for market, res in conf_cands.items():
        for c in res["rows"]:
            low = tidy(c["name"]).lower()
            if any(len(b) >= 8 and (low.startswith(b) or b.startswith(low[:len(b)])) for b in named_in_b):
                continue                                                         # already named, with the customer who lists it, under (b)
            why = held_reason(c["name"], c["canon"], lookup)
            tag = "no permanent id yet" if c["category"] == "waiting_for_id" else (why or "researched but not in the approved file")
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
    if view.get("awards") is None:
        return Check("e", "Provisional rows", "NA", "not judged (no awards rows)")
    note = [x for x in view.get("prov_notes", []) if x]
    return Check("e", "Provisional rows on the Awards page", "WARN" if names else "PASS",
                 f"{len(names)} Provisional award(s) on the page: researched, not approved yet" if names else "no provisional rows" + (f" ({note[0]})" if note else ""), [f"WARN {n}" for n in names])


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
    return Check("f", "Customer sheet snapshots are fresh", st, "all four snapshots are under 2 days old" if st == "PASS" else "a customer sheet snapshot is old: the page may miss what the customer changed", rows)


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
    cov_conf = safely_cov(lambda: coverage_conferences(o, approved, lookup))
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
              "provisional": len([r for r in (view.get("awards") or []) if r.get("prov")])}
    return {"checks": checks, "verdict": verdict, "counts": counts, "coverage": {"conference": cov_conf, "awards": cov_awards}, "coverage_lines": cov_lines, "pages": pages,
            "preflight": o.preflight, "on": o.on.isoformat()}


def safely_cov(fn):
    try:
        return fn()
    except Exception as e:                                                      # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


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
    subj, text, html_ = build_email(rep)
    return bool(mailer(subj, text, html=html_, to_env="CFP_RECAP_TO", attachments=attachments_for(rep) or None))


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--on", default=date.today().isoformat())
    ap.add_argument("--now", default="", help="the moment to age the snapshots against (default: now); for rehearsals")
    ap.add_argument("--preflight", action="store_true", help="Sunday pre-flight: judge the approved files and the newest snapshots, build no pages")
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
