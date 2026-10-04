"""Numbers for the CFP Status Board that can be computed from the database alone.

    python scripts/board_metrics.py [--db <live db>] [--previous-db <backup>] [--examples N] [--update-status]

WHY (2026-10-02). The board's "agreement with customer-verified dates" (20 of 40 on 2026-10-01) was computed once, by
hand, and could not be reproduced: the query was not kept. A headline number that nobody can re-run is a rumour. This
script is that query, with its definition written down, so the board can refresh the number the same way every time.

DEFINITION - customer agreement
  Population: rows in `client_conferences` where the customer's team marked the date `Verified`
              (submission_date_verified = 'Verified', case-insensitive), the customer has a date, and the customer has NOT
              withdrawn the row (withdrawn_by_customer = 0: a row they no longer track is not a promise to them).
  Our side:   the stored `deadline` of the same canonical event_id, in `grounding_facts` or `award_grounding_facts`.
  Unmatched:  rows whose customer line has no counterpart in our database are NOT in the population above; they are reported
              as the coverage gap (2026-10-02: 41 of 75, mostly older or out-of-scope events).
  Classes:    agree      the two dates are the same day
              blank      the customer has a date and ours is blank (we have nothing to offer)
              differ     both have a date and they are different days
              unreadable the customer's date cell is not a date we can read (reported, never counted as agree or differ)
  Not cleaned for editions or passed rows: a customer date of 2026-07-15 against our 2027 edition counts as `differ`.
  That is a rough reading on purpose; it is what the customer would feel on opening the sheet beside the page.

LIVE vs ALL (2026-10-02, operator questioned 28% and 50% as too low). A deadline that has already passed cannot be judged by
whether its page still carries the date: pages move on to the next edition (the purpose audit itself said 15 of 16 "absent" and 11 of 12
"unreadable" rows were already-passed deadlines, "not errors"), and the customer's dated row can still point at the previous edition. So both
headlines are reported for LIVE rows (the date a customer would act on is still ahead) with the all-rows figure kept beside it as the rough one.
  customer agreement, live: the customer's date OR ours is on or after --today.
  provable, live:  our stored deadline is on or after --today, for events on the Cybersecurity or Utility seed sheets (the market lists the
                   pipeline uses; `conference_markets` misses events added since the last crawl).
                   verified   our verifier found the date on the cited page and a citation exists
                   withdrawn  no citation (withdrawn by agreement, projected): honestly unproven, not wrong
                   unreadable the verifier could not read the cited page (HTTP 403, script-built page): unproven, a browser read would settle it
                   notfound   the page was read and the date is not on it
                   contradicted  the page was read and states a different date
COMPLETE % and ACCURATE % (2026-10-03; replace the weighted six-component overall index, which was retired the same day). See split_scores:
  complete  expected fields filled (a pinned honest blank counts) averaged with coverage; call fields excused while the event is >90 days off and no call is open
  accurate  proven / (proven + contradicted) over stated facts; unproven shown beside it, never wrong; a contradiction is never excused
Process health (freshness of the last run, share of research calls that grounded) is shown beside them as drivers, never scored.
--update-status rewrites `headline.customer`, `headline.provable` and `quality` in docs/design/status.json (levels, row counts, notes) and nothing else.
Read-only otherwise. The 2026-10-01 figure (40 rows) also counted rows the customer had withdrawn; excluding them gives the
34 this script reports for the same database.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))                      # `src.cfp_monitor` imports when run as a script
LIVE_DB = Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor" / "cfp_monitor.db"
STATUS_JSON = ROOT / "docs" / "design" / "status.json"
MARKETS_DIR = Path("C:/Users/matts/Desktop/Nicolia-PR-Prime/Markets")
CLASSES = ("agree", "blank", "differ", "unreadable")


def parse_their_date(s: str) -> str | None:
    """The customer's sheet writes MM/DD/YYYY; ISO is accepted too. Anything else is unreadable, not guessed."""
    s = (s or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


TABLE_OF = {"conference": "grounding_facts", "award": "award_grounding_facts"}


def _our_deadlines(con: sqlite3.Connection, kind: str = "conference") -> dict[str, str]:
    """Our stored deadline per canonical event_id, from the table for `kind` only (conference and award rows never mix)."""
    ours: dict[str, str] = {}
    for table in (TABLE_OF[kind],):
        try:
            for eid, dl in con.execute(f"select event_id, deadline from {table}"):
                ours[eid] = (dl or "").strip()
        except sqlite3.OperationalError:
            continue
    return ours


def _far(d: str | None, today: str, days: int = 90) -> bool:
    """`d` is more than `days` after today (the operator's 90-day rule: nothing is expected to be published that far ahead)."""
    try:
        return bool(today) and d is not None and (date.fromisoformat(d) - date.fromisoformat(today)).days > days
    except ValueError:
        return False


def _other_edition(theirs: str, ours: str, today: str) -> bool:
    """Two different dates that are not a disagreement about one date: more than 180 days apart (another edition: Troopers 2026 vs 2027), or the
    customer's date has already passed while ours is still ahead (they hold the earlier round: Climate Change). Reported separately, never as 'differ'."""
    try:
        if abs((date.fromisoformat(theirs) - date.fromisoformat(ours)).days) > 180:
            return True
        return bool(today) and theirs < today <= ours
    except ValueError:
        return False


def customer_agreement(db: str, today: str = "", kind: str = "conference") -> dict:
    con = sqlite3.connect(db)
    try:
        ours = _our_deadlines(con, kind)
        rows = con.execute(
            "select client_key, their_name, event_id, their_deadline from client_conferences "
            "where lower(trim(submission_date_verified)) = 'verified' and trim(their_deadline) != '' "
            "and coalesce(withdrawn_by_customer, 0) = 0").fetchall()
    finally:
        con.close()
    counts = {k: 0 for k in CLASSES}
    side = {"edition": 0, "excused": 0}
    detail = []
    unmatched = 0
    for client, name, eid, theirs in rows:
        if eid not in ours:
            unmatched += 1
            continue
        t, o = parse_their_date(theirs), ours[eid]
        if t is None:
            cls = "unreadable"
        elif not o:
            cls = "excused" if _far(t, today) else "blank"      # 90-day rule: no call is expected to be published yet
        elif t == o:
            cls = "agree"
        else:
            cls = "edition" if _other_edition(t, o, today) else "differ"
        if cls in ("edition", "excused"):                        # reported beside the figure, kept out of it
            side[cls] += 1
        else:
            counts[cls] += 1
        is_live = bool(today) and ((t is not None and t >= today) or (o != "" and o >= today))
        detail.append({"client": client, "name": name, "event_id": eid, "theirs": theirs.strip(), "ours": o, "class": cls, "live": is_live})
    live_counts = {k: sum(1 for d in detail if d["live"] and d["class"] == k) for k in CLASSES}
    live_side = {k: sum(1 for d in detail if d["live"] and d["class"] == k) for k in side}
    return {"rows": sum(counts.values()), "counts": counts, "other_edition": side["edition"], "excused": side["excused"], "live_side": live_side, "unmatched_to_our_db": unmatched, "detail": detail,
            "live_counts": live_counts, "live_rows": sum(live_counts.values())}


def provable_live(db: str, today: str, kind: str = "conference") -> dict:
    """How many LIVE stored deadlines (on or after `today`) are proven on their cited page. See the module docstring.
    kind "conference": events on the Cybersecurity/Utility seed sheets (grounding_facts).
    kind "award": award_grounding_facts rows on an award list of those markets (award_markets)."""
    con = sqlite3.connect(db)
    try:
        if kind == "award":
            rows = con.execute(
                "select a.event_id, a.name, a.deadline, a.verify_state, coalesce(a.verify_detail,''), coalesce(a.deadline_evidence_url,''), '', '', 0 "
                "from award_grounding_facts a where trim(a.deadline) != '' and a.deadline >= ? "
                "and a.event_id in (select award_key from award_markets where market in ('Cybersecurity','Utility'))", (today,)).fetchall()
            ids = {r[0] for r in rows}
        else:
            from src.cfp_monitor.identity import market_canonical_ids      # the one owner of seed-file reading
            ids = market_canonical_ids(db)
            have = {r[1] for r in con.execute("pragma table_info(grounding_facts)")}
            extra = ", ".join(f"coalesce({c},{d})" if c in have else d for c, d in (("start_date", "''"), ("status", "''"), ("is_projected", "0")))
            rows = con.execute("select event_id, name, deadline, verify_state, coalesce(verify_detail,''), coalesce(deadline_evidence_url,''), "
                               f"{extra} from grounding_facts where trim(deadline) != '' and deadline >= ?", (today,)).fetchall()
    finally:
        con.close()
    counts = {k: 0 for k in ("verified", "withdrawn", "unreadable", "notfound", "contradicted", "unchecked")}
    detail = []
    operator = excused = 0
    from scripts.pinned_rows import load_pins
    pinned_deadline = {p["canonical"]: str(p["set"].get("SUBMISSION DEADLINE", "")).strip() for p in load_pins()
                       if kind == "conference" and p.get("set", {}).get("SUBMISSION DEADLINE") and (not p.get("until") or p["until"] >= today)}
    for eid, name, dl, state, why, ev, start, status, proj in rows:
        if eid not in ids:
            continue
        if pinned_deadline.get(eid) == dl:
            cls = "verified"                               # the operator read this date on the event's own page: proven by a person
            operator += 1
        elif _far(start, today) and not (status.strip().lower() == "open" or (dl and not proj)) and state != "contradicted":
            excused += 1                                   # 90-day rule: event far off, no firm call: no evidence is expected yet
            continue
        elif not ev.strip():
            cls = "withdrawn"
        elif state == "verified":
            cls = "verified"
        elif state == "contradicted":
            cls = "contradicted"
        elif "could not be read" in why or why.startswith("unreadable"):
            cls = "unreadable"
        elif state in ("unverified", "", None):
            cls = "unchecked"
        else:
            cls = "notfound"
        counts[cls] += 1
        detail.append({"event_id": eid, "name": name, "deadline": dl, "class": cls})
    return {"rows": sum(counts.values()), "counts": counts, "operator_verified": operator, "excused_far_future": excused,
            "detail": sorted(detail, key=lambda d: d["deadline"])}


def _host(u: str) -> str:
    s = (u or "").lower().strip().split("://", 1)[-1].split("/", 1)[0]
    return s[4:] if s.startswith("www.") else s


def coverage_live(db: str, today: str, kind: str = "conference") -> dict:
    """Of the customers' live (their date ahead), verified, dated, not-withdrawn rows: how many have an event in our database?
    Covered = their event_id is ours, or their site is a site we research (host of any grounding_facts url or conference key)."""
    con = sqlite3.connect(db)
    try:
        table = TABLE_OF[kind]
        ours = {r[0] for r in con.execute(f"select event_id from {table}")}
        hosts = set()
        for u, k in con.execute(f"select coalesce(url,''), coalesce(conference_key,'') from {table}"):
            hosts |= {_host(u), _host(k)}
        hosts.discard("")
        rows = con.execute("select client_key, their_name, event_id, their_deadline, coalesce(their_url,'') from client_conferences "
                           "where lower(trim(submission_date_verified))='verified' and trim(their_deadline)!='' "
                           "and coalesce(withdrawn_by_customer,0)=0").fetchall()
    finally:
        con.close()
    covered, missing = 0, []
    for client, name, eid, theirs, url in rows:
        d = parse_their_date(theirs)
        if d is None or d < today:
            continue
        if kind == "award" and eid not in ours:
            continue                                   # a customer line is an AWARD only if it links to an award row
        if eid in ours or (kind == "conference" and url and _host(url) in hosts):
            covered += 1
        else:
            missing.append({"client": client, "name": name, "theirs": theirs.strip()})
    return {"rows": covered + len(missing), "covered": covered, "missing": missing}


def freshness_last_run(markets_dir: str, today: str = "", kind: str = "conference") -> dict:
    """Rows genuinely researched recently: not a stub ('Audit Exception' in STATUS DETAILS: every search attempt failed) and, when `today`
    is given, with a SOURCE_AS_OF stamp within 14 days. Same definition for both kinds.
    conference: the last Saturday research output of each market. award: the awards file the customer page reads (the promoted
    Awards_audited.final.csv if there is one, else the newest dated Awards_*_out.csv)."""
    from datetime import timedelta
    cutoff = (date.fromisoformat(today) - timedelta(days=14)).isoformat() if today else ""
    if kind == "award":
        d = Path(markets_dir)
        final = d / "Awards_audited.final.csv"
        files = [final] if final.exists() else sorted(d.glob("Awards_2*_out.csv"), key=lambda p: p.stat().st_mtime)[-1:]
    else:
        files = [Path(markets_dir) / f"{m}_audited.csv" for m in ("Cybersecurity", "Utility")]
    total = fresh = stubs = 0
    for p in files:
        if not p.exists():
            continue
        with open(p, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                total += 1
                stub = "Audit Exception" in (r.get("STATUS DETAILS") or "")
                stubs += stub
                if not stub and (not cutoff or (r.get("SOURCE_AS_OF") or "").strip() >= cutoff):
                    fresh += 1
    return {"rows": total, "researched": fresh, "stubs": stubs}


def call_health(markets_dir: str) -> dict:
    ok = tot = 0
    for m in ("Cybersecurity", "Utility"):
        p = Path(markets_dir) / f"{m}_audited.health.json"
        if p.exists():
            c = json.loads(p.read_text(encoding="utf-8"))["call_health"]["counts"]["gemini_call"]
            ok += c.get("ok", 0)
            tot += sum(c.values())
    return {"calls": tot, "grounded": ok}


SPOTCHECKS = ROOT / "docs" / "design" / "field_spotchecks.json"


def spotcheck_summary(path: Path = SPOTCHECKS, kind: str = "conference") -> dict:
    """Rows read against their own pages, and how many carried a wrong non-deadline fact."""
    checks = json.loads(path.read_text(encoding="utf-8"))["checks"] if path.exists() else []
    checks = [c for c in checks if c.get("kind", "conference") == kind]
    return {"rows": sum(c["rows"] for c in checks), "bad": sum(c["rows_with_error"] for c in checks), "checks": len(checks)}


def process_drivers(db_markets_dir: str, today: str, kind: str) -> list[str]:
    """Process health shown beside Complete/Accurate, never scored (the old index scored freshness as quality; it is a measure of the job, not the data)."""
    fresh = freshness_last_run(db_markets_dir, today, kind)
    out = []
    if fresh["rows"]:
        what = "Saturday run" if kind == "conference" else "awards file the page reads (stamped within 14 days, not a stub)"
        out.append(f"{fresh['researched']} of {fresh['rows']} rows genuinely researched in the {what} ({fresh['stubs']} stubs)")
    if kind == "conference":
        calls = call_health(db_markets_dir)
        if calls.get("calls"):
            out.append(f"{calls['grounded']} of {calls['calls']} Saturday research calls returned a grounded answer ({round(100 * calls['grounded'] / calls['calls'])}%): "
                       "retries and last week's approved rows cover most of the gap")
    else:
        out.append("The Friday awards research job was disabled from 2026-09-30 and re-enabled on 2026-10-03; awards freshness stays low until its first run (Fri 2026-10-09 02:00)")
    return out


GRACE_DAYS = 90
NO_DEADLINE_MODELS = ("Not Announced", "Invitation Only", "Rolling Form")
FACT_FIELDS = {"conference": ("start_date", "city", "country", "main_info_url"), "award": ("main_info_url",)}
CALL_FIELDS = ("deadline", "submission_url", "deadline_evidence_url", "deadline_quote")
PIN_COLUMN = {"START DATE": "start_date", "CITY": "city", "COUNTRY": "country", "MAIN_INFO_URL": "main_info_url", "DEADLINE": "deadline",
              "CFP_SUBMISSION_URL": "submission_url"}


def call_is_open(r: dict, today: str) -> bool:
    """A call we can see: the row says Open, or it carries a firm (not projected) deadline on or after today. Evidence can then be expected."""
    return (r.get("status") or "").strip().lower() == "open" or (bool((r.get("deadline") or "").strip()) and (r.get("deadline") or "") >= today
                                                                 and not r.get("is_projected"))


def far_future(r: dict, today: str, kind: str = "conference") -> bool:
    """Start date more than GRACE_DAYS ahead and no open call: no evidence is expected to exist yet (operator's 90-day rule, 2026-10-03).
    Awards have no event start: their grace is a Closed award with no new cycle announced."""
    s = (r.get("start_date") or "").strip()
    if kind != "conference" or not s or call_is_open(r, today):
        return False
    try:
        return (date.fromisoformat(s) - date.fromisoformat(today)).days > GRACE_DAYS
    except ValueError:
        return False


def dormant_award(r: dict, today: str) -> bool:
    """An award whose cycle has ended and whose next one has not been announced: Closed, no deadline or opening date still ahead, no open call. Nothing is published to find yet,
    so a blank deadline, link or evidence is not a miss (the awards version of the 90-day rule; awards have no event start date, 2026-10-04)."""
    if (r.get("status") or "").strip().lower() != "closed":
        return False
    ahead = [d for d in ((r.get("deadline") or "").strip(), (r.get("submission_opens") or "").strip()) if d and d >= today]
    return not ahead and not call_is_open(r, today)


def in_scope(r: dict, today: str) -> bool:
    """Rows a customer could still act on: the event or its deadline is not past (edition year if neither is dated)."""
    s, d = (r.get("start_date") or "").strip(), (r.get("deadline") or "").strip()
    if s or d:
        return max(s, d) >= today
    return (r.get("edition") or "") >= today[:4]


def expected_fields(r: dict, today: str, kind: str = "conference") -> tuple[list[str], list[str]]:
    """(expected, excused). Edition facts are always expected. Call fields (deadline, link, evidence) are excused while the event is far off
    and no call is open, and when the start date itself is unknown and no call is open."""
    exp = list(FACT_FIELDS[kind])
    excused = []
    if far_future(r, today, kind) or (kind == "conference" and not (r.get("start_date") or "").strip() and not call_is_open(r, today)) or (kind == "award" and dormant_award(r, today)):
        excused = list(CALL_FIELDS)
    elif kind == "award" and (r.get("cfp_model") or "").strip() in NO_DEADLINE_MODELS:
        excused = [f for f in CALL_FIELDS if f != "submission_url"]       # research says no date is published (Not Announced) or there is none by design (Invitation Only, Rolling Form)
        exp += ["submission_url"]
    else:
        exp += list(CALL_FIELDS)
    return exp, excused


def split_scores(rows: list[dict], today: str, kind: str, pins: list[dict] | None = None, cov: dict | None = None,
                 cur: dict | None = None, spot: dict | None = None) -> dict:
    """COMPLETE % and ACCURATE % for one kind (operator's definitions, 2026-10-03). Pure over `rows` (dicts of grounding_facts columns).
    Complete = expected fields that are filled (or are a pinned honest blank) / expected fields; far-future call fields are excused, not missed.
    Accurate = of the facts we state: proven / (proven + contradicted); unproven is shown beside it, never counted wrong; far-future unproven is excused.
    A contradiction is never excused by the grace period."""
    pinned: dict[str, dict] = {}
    for p in pins or []:
        pinned[p.get("canonical", "")] = {PIN_COLUMN[k]: v for k, v in (p.get("set") or {}).items() if k in PIN_COLUMN}
    exp_n = filled = excused_n = excused_rows = 0
    missing: dict[str, int] = {}
    proven = contra = unproven = unproven_excused = 0
    contradicted_names: list[str] = []
    scored = 0
    for r in rows:
        if not in_scope(r, today):
            continue
        scored += 1
        pin = pinned.get(r.get("event_id", ""), {})
        exp, exc = expected_fields(r, today, kind)
        excused_n += len(exc)
        excused_rows += bool(exc)
        for f in exp:
            if (r.get(f) or "").strip() or (f in pin and str(pin[f]).strip() == ""):
                filled += 1
            else:
                missing[f] = missing.get(f, 0) + 1
            exp_n += 1
        # accuracy of what is stated
        facts = []
        dl = (r.get("deadline") or "").strip()
        if dl and dl >= today:                                          # a passed deadline's page moves on to the next edition: not scored
            st = r.get("verify_state")
            facts.append("proven" if st == "verified" and (r.get("deadline_evidence_url") or "").strip() else "contradicted" if st == "contradicted" else "unproven")
        s = (r.get("start_date") or "").strip()
        if s and (r.get("edition") or "").isdigit() and s[:4] != r["edition"]:
            facts.append("contradicted")                                  # year rule: the date is not in the edition it sits on
        for f, v in pin.items():
            if str(v).strip() and (r.get(f) or "").strip():
                facts.append("proven" if str(r.get(f)).strip() == str(v).strip() else "contradicted")
        for fct in facts:
            if fct == "proven":
                proven += 1
            elif fct == "contradicted":
                contra += 1
                contradicted_names.append((r.get("name") or "")[:40])
            elif far_future(r, today, kind):
                unproven_excused += 1
            else:
                unproven += 1
    if cur:
        lc = cur.get("live_counts") or {}
        proven += lc.get("agree", 0)
        contra += lc.get("differ", 0)
    if spot and spot.get("rows"):
        proven += spot["rows"] - spot["bad"]
        contra += spot["bad"]
    fill_pct = 100 * filled / exp_n if exp_n else None
    cov_pct = 100 * cov["covered"] / cov["rows"] if cov and cov.get("rows") else None
    parts = [x for x in (fill_pct, cov_pct) if x is not None]
    complete = sum(parts) / len(parts) if parts else None
    checked = proven + contra
    accurate = 100 * proven / checked if checked else None
    return {"kind": kind, "rows_scored": scored, "grace_days": GRACE_DAYS,
            "complete": None if complete is None else round(complete), "fill_pct": None if fill_pct is None else round(fill_pct),
            "coverage_pct": None if cov_pct is None else round(cov_pct), "expected": exp_n, "filled": filled, "missing_by_field": missing,
            "excused_fields": excused_n, "excused_rows": excused_rows,
            "accurate": None if accurate is None else round(accurate), "proven": proven, "contradicted": contra,
            "unproven": unproven, "unproven_excused": unproven_excused,
            "unproven_share": None if not (checked + unproven) else round(100 * unproven / (checked + unproven)),
            "contradicted_names": contradicted_names[:10]}


def split_for(db: str, markets_dir: str, today: str, kind: str) -> dict:
    from scripts.pinned_rows import load_pins
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        if kind == "award":
            ids = {r[0] for r in con.execute("select award_key from award_markets where market in ('Cybersecurity','Utility')")}
        else:
            from src.cfp_monitor.identity import market_canonical_ids
            ids = market_canonical_ids(db)
        rows = [dict(r) for r in con.execute(f"select * from {TABLE_OF[kind]}") if r["event_id"] in ids]
    finally:
        con.close()
    pins = load_pins() if kind == "conference" else []
    return split_scores(rows, today, kind, pins, coverage_live(db, today, kind), customer_agreement(db, today, kind), spotcheck_summary(kind=kind))


def render(cur: dict, prev: dict | None, examples: int) -> str:
    c = cur["counts"]
    readable = c["agree"] + c["blank"] + c["differ"]
    pct = f"{100 * c['agree'] / readable:.0f}%" if readable else "n/a"
    lc = cur.get("live_counts")
    lines = []
    if lc is not None:
        lr = lc["agree"] + lc["blank"] + lc["differ"]
        lines.append(f"Customer agreement, LIVE rows (a date still ahead): {lc['agree']} of {lr} agree "
                     f"({100 * lc['agree'] // lr if lr else 0}%); our blank {lc['blank']}, different {lc['differ']}")
    lines += [f"Customer agreement, ALL rows (rough; includes past dates and old editions): {c['agree']} of {readable} readable rows agree ({pct})",
             f"  agree {c['agree']} | our deadline blank {c['blank']} | different date {c['differ']} | unreadable customer date {c['unreadable']}",
             f"  coverage gap: {cur['unmatched_to_our_db']} more customer-verified, dated rows have NO matching event of ours "
             f"(they track it, we do not research it)"]
    if prev:
        p = prev["counts"]
        lines.append("  since the backup: " + ", ".join(f"{k} {p[k]} -> {c[k]}" for k in CLASSES))
    for cls in ("differ", "blank"):
        shown = [d for d in cur["detail"] if d["class"] == cls][:examples]
        if shown:
            lines.append(f"  {cls}:")
            lines += [f"    - [{d['client']}] {d['name'][:48]}: customer {d['theirs']} / ours {d['ours'] or '(blank)'}" for d in shown]
    return "\n".join(lines)


def update_status(cur: dict, today: str, path: Path = STATUS_JSON, prov: dict | None = None, quality: dict | None = None) -> None:
    """Rewrite headline.customer (and headline.provable when `prov` is given). LIVE figures lead; the all-rows figure stays in the note."""
    data = json.loads(path.read_text(encoding="utf-8"))
    c = cur["counts"]
    lc = cur.get("live_counts")
    h = data["headline"]["customer"]
    use = lc if lc is not None else c
    h["rows"] = cur.get("live_rows", cur["rows"]) if lc is not None else cur["rows"]
    h["levels"] = [{"key": "agree", "label": "Same date", "n": use["agree"], "tone": "good"},
                   {"key": "blank", "label": "Our deadline blank", "n": use["blank"], "tone": "warn"},
                   {"key": "differ", "label": "Different date", "n": use["differ"], "tone": "bad"}]
    ls = cur.get("live_side") or {}
    if ls.get("edition"):
        h["levels"].append({"key": "edition", "label": "Customer row is another edition or round (not scored)", "n": ls["edition"], "tone": "mute"})
    if ls.get("excused"):
        h["levels"].append({"key": "excused", "label": "Our date blank, event more than 90 days off (not scored)", "n": ls["excused"], "tone": "mute"})
    h["rows"] += sum(ls.values()) if lc is not None else 0          # the not-scored rows are shown, so they are part of the row count
    if use["unreadable"]:
        h["levels"].append({"key": "unreadable", "label": "Customer date unreadable", "n": use["unreadable"], "tone": "none"})
    if lc is not None:
        readable_all = c["agree"] + c["blank"] + c["differ"]
        h["label"] = "Agreement with customer-verified dates (live rows)"
        h["definition"] = ("Rows where the customer's team marked the date Verified and has a date, the customer has not withdrawn the row, and the "
                           "customer's date or ours is still ahead: does ours match? Rows whose dates have both passed are not scored here.")
        h["note"] = (f"All rows, rough (includes past dates and old editions): {c['agree']} of {readable_all} agree. Scored: the live rows where both sides "
                     "name the same edition. Not scored, shown beside it: a customer row holding another edition or an earlier round (more than 180 days apart, or "
                     "their date already passed while ours is ahead: Troopers, CyberDefenseCon, Climate Change), and our blank on an event more than 90 days off, "
                     "where no call is expected to be published yet. Those are coverage or timing questions, not disagreements about one date.")
    h["source"] = f"scripts/board_metrics.py, client_conferences joined to our deadlines, {today}; customer-withdrawn rows excluded"
    if prov is not None:
        pc = prov["counts"]
        ph = data["headline"]["provable"]
        ph["label"] = "Provable submission date (live deadlines)"
        ph["definition"] = ("Deadlines still ahead for events on the Cybersecurity and Utility market lists. Proven = our verifier found the stored date on "
                            "the cited page and a citation exists. A deadline that has already passed is not scored: its page moves on to the next edition.")
        ph["rows"] = prov["rows"]
        ph["open_rows"] = prov["rows"]
        ph["open_confirmed"] = pc["verified"]
        ph["levels"] = [
            {"key": "confirmed", "label": "Date on the cited page", "n": pc["verified"], "tone": "good"},
            {"key": "withdrawn", "label": "Citation withdrawn by agreement (honestly unproven)", "n": pc["withdrawn"], "tone": "warn"},
            {"key": "nopage", "label": "Cited page blocks our plain reader (a browser read would settle it)", "n": pc["unreadable"], "tone": "mute"},
            {"key": "absent", "label": "Page read, date not on it", "n": pc["notfound"], "tone": "bad"},
            {"key": "mismatch", "label": "Page read, shows a different date", "n": pc["contradicted"], "tone": "bad"}]
        ph["definition"] += (" Proven also includes dates you verified yourself on the event's own page (pinned: "
                             f"{prov.get('operator_verified', 0)} today). Events more than 90 days off with no firm call are not counted ({prov.get('excused_far_future', 0)} today): no page is expected to state a date yet.")
        ph["note"] = ("The earlier 28% (11 of 39) counted every stored deadline, including 44 of 48 that had already passed; the purpose audit itself said "
                      "15 of 16 'absent' and 11 of 12 'unreadable' rows were already-passed deadlines, 'not errors'. On live deadlines the unproven ones are "
                      "a deliberate citation withdrawal and pages that refuse a plain fetch, not wrong dates.")
        ph["source"] = f"scripts/board_metrics.py provable_live, {today}; experiments/purpose_audit/RESULT.md for the all-rows audit"
        for g in data["objective"]["good"]:
            if g["label"].startswith("Provable submission dates"):
                g["now"] = f"{pc['verified']} of {prov['rows']} live deadlines proven on their cited page; the rest are a deliberate withdrawal or pages our plain reader cannot open"
            if g["label"].startswith("Agreement with customer-verified dates") and lc is not None:
                lr = lc["agree"] + lc["blank"] + lc["differ"]
                g["now"] = f"{lc['agree']} of {lr} live rows today ({100 * lc['agree'] // lr if lr else 0}%); {c['agree']} of {c['agree'] + c['blank'] + c['differ']} counting past dates and old editions"
    if quality is not None:
        data["quality"] = {
            "as_of": today,
            "conference": {**quality["conference"], "label": "Conferences: complete and accurate"},
            "awards": {**quality["awards"], "label": "Awards: complete and accurate"},
            "not_measured": ("Sponsorship, overview and categories have no measure at all for conferences, and nothing beyond the deadline is measured for awards. "
                             "The non-deadline facts rest on a small spot-check (docs/design/field_spotchecks.json). Conferences and awards are deliberately not blended. "
                             "The old six-component weighted index was retired on 2026-10-03: its parts are now Complete and Accurate, and freshness is shown as process health."),
            "split_method": (f"COMPLETE % = expected fields that are filled (a pinned honest blank counts as filled) averaged with coverage of customer-tracked events. Edition facts "
                             f"(start date, city, country, main page) are always expected; the call fields (deadline, link, evidence) are excused while the event starts more than "
                             f"{GRACE_DAYS} days ahead and no call is open, because nothing is published yet. ACCURATE % = proven / (proven + contradicted) over facts we state "
                             "(deadline vs its cited page, start year vs edition, pinned facts, customer-verified dates, spot checks); unproven is shown beside it and never counted wrong; "
                             "a contradiction is never excused by the 90-day rule. Awards have no event start: their grace is a Closed award with no new cycle announced (no deadline or opening date ahead, no open call)."),
            "source": "scripts/board_metrics.py split_for, process_drivers; docs/design/field_spotchecks.json"}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--previous-db")
    ap.add_argument("--examples", type=int, default=6)
    ap.add_argument("--update-status", action="store_true")
    ap.add_argument("--today", default=date.today().isoformat())
    a = ap.parse_args(argv)
    cur = customer_agreement(a.db, a.today)
    prev = customer_agreement(a.previous_db, a.today) if a.previous_db else None
    print(render(cur, prev, a.examples))
    prov = provable_live(a.db, a.today)
    pc = prov["counts"]
    print(f"Provable submission date, LIVE deadlines ({a.today} or later, on the market lists): {pc['verified']} of {prov['rows']} proven on the cited page"
          f" | of which verified by you {prov.get('operator_verified', 0)} | excused (90 days) {prov.get('excused_far_future', 0)} | citation withdrawn {pc['withdrawn']} | page unreadable by plain fetch {pc['unreadable']} | date not on page {pc['notfound']} | different date {pc['contradicted']}")
    for d in prov["detail"]:
        if d["class"] != "verified":
            print(f"    {d['class']:12} {d['deadline']}  {d['name'][:56]}")
    sc = split_for(a.db, str(MARKETS_DIR), a.today, "conference")
    sa = split_for(a.db, str(MARKETS_DIR), a.today, "award")
    for label, s in (("CONFERENCES", sc), ("AWARDS", sa)):
        print(f"COMPLETE {s['complete']}% (fields filled {s['filled']} of {s['expected']} expected = {s['fill_pct']}%, coverage {s['coverage_pct'] if s['coverage_pct'] is not None else 'n/a'}%; "
              f"{s['excused_fields']} call fields on {s['excused_rows']} far-future rows excused) | ACCURATE {s['accurate']}% "
              f"({s['proven']} proven, {s['contradicted']} contradicted; unproven {s['unproven']} not counted wrong, {s['unproven_excused']} excused) - {label}")
    sc["drivers"], sa["drivers"] = process_drivers(str(MARKETS_DIR), a.today, "conference"), process_drivers(str(MARKETS_DIR), a.today, "award")
    for label, s in (("CONFERENCES", sc), ("AWARDS", sa)):
        for dr in s["drivers"]:
            print(f"    process, not scored ({label}): {dr}")
    if a.update_status:
        update_status(cur, a.today, prov=prov, quality={"conference": {"split": sc}, "awards": {"split": sa}})
        print(f"updated headline.customer in {STATUS_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
