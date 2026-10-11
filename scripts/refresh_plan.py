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
Reads the live database read-only. Without --apply it only prints the plan and the estimated saving.

CONFERENCE MODE (ACT-33, 2026-10-11): `--market Cybersecurity` or `--market Utility` applies the operator-approved four-group policy (numbers in docs/operations/refresh_policy.json, read here with the
defaults built in) to the two live conference markets, decided each Saturday BEFORE the research. See the section "CONFERENCE POLICY" below and docs/operations/WEEKEND-PROCESS.md. The awards
behaviour above is unchanged."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
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


# ======================================================================================= CONFERENCE POLICY (ACT-33)
# Approved by the operator 2026-10-11 for the two live conference markets. Decided each Saturday BEFORE the research; the audit skips a marked row exactly as it skips a DUP_OF row, and the weekend import
# carries last week's accepted row for it. The state of a row is its LAST ACCEPTED row (<Market>_audited.final.csv, matched through identity.to_canonical): that is the row that would be carried.
#   Group 1  not Closed (Open, Upcoming, Needs Verification, blank) ........ researched weekly.
#   Group 2  Closed, event ended MORE than group2_after_days (60) ago ...... researched every group2_every_weeks (2) weeks (stable_hash(id) % 2 == week % 2).
#   Group 3  Closed, event ended within the last 60 days ................... ONE check, on the Saturday where days since the end are in [group3_check_from_days, group3_check_to_days) = [14, 21); skipped otherwise.
#   Group 4  Closed (call closed) but the event is still ahead ............. by days to the event START: <= 30 weekly; 31..90 every 2 weeks; over 90 every 4 weeks.
#   ALWAYS researched: a customer-facing link recorded dead in link_checks, an id named in docs/operations/refresh_overrides.txt, a row with no accepted row (new event), a row whose dates cannot be read
#   (doubt means research), and EVERY row on the first Saturday of January (year rollover).
# 'Event ended' uses the END of CONFERENCE DATES when it can be read, else START DATE. The week number is counted continuously (ordinal // 7), not ISO, so the rotation does not hiccup at year end.
CONF_MARKETS = ("Cybersecurity", "Utility")
POLICY_FILE = ROOT / "docs" / "operations" / "refresh_policy.json"
OVERRIDES_FILE = ROOT / "docs" / "operations" / "refresh_overrides.txt"
DEFAULT_POLICY = {
    "group2_after_days": 60, "group2_every_weeks": 2,
    "group3_check_from_days": 14, "group3_check_to_days": 21,
    "group4_near_days": 30, "group4_mid_days": 90, "group4_mid_every_weeks": 2, "group4_far_every_weeks": 4,
    "guard_max_skip_share": 0.5,
    "cost_per_row_usd": 0.12,           # an ESTIMATE: about 8-9 grounded searches per row at 14 USD per 1,000
}
LINK_COLUMNS = ("CONFERENCE URL", "SUBMISSION URL", "MAIN_INFO_URL", "CFP_SUBMISSION_URL", "SPONSOR_URL")


def load_policy(path: Path | None = None) -> dict:
    """The built-in defaults, overridden by the numbers in the policy file when it exists. A typo'd key or a nonsense number raises (the caller then researches everything)."""
    pol = dict(DEFAULT_POLICY)
    p = Path(path) if path else POLICY_FILE
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError(f"{p.name}: expected a JSON object")
        for k, v in data.items():
            if k.startswith("_"):
                continue
            if k not in DEFAULT_POLICY:
                raise ValueError(f"{p.name}: unknown setting '{k}' (known: {', '.join(DEFAULT_POLICY)})")
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError(f"{p.name}: '{k}' must be a number")
            pol[k] = v
    for k in ("group2_after_days", "group3_check_from_days", "group3_check_to_days", "group4_near_days", "group4_mid_days"):
        if pol[k] < 0:
            raise ValueError(f"policy: '{k}' cannot be negative")
    for k in ("group2_every_weeks", "group4_mid_every_weeks", "group4_far_every_weeks"):
        if int(pol[k]) != pol[k] or pol[k] < 1:
            raise ValueError(f"policy: '{k}' must be a whole number of weeks, 1 or more")
    if not pol["group3_check_from_days"] < pol["group3_check_to_days"]:
        raise ValueError("policy: group3_check_from_days must be below group3_check_to_days")
    if not pol["group4_near_days"] < pol["group4_mid_days"]:
        raise ValueError("policy: group4_near_days must be below group4_mid_days")
    if not 0 <= pol["guard_max_skip_share"] <= 1:
        raise ValueError("policy: guard_max_skip_share must be between 0 and 1")
    if pol["cost_per_row_usd"] < 0:
        raise ValueError("policy: cost_per_row_usd cannot be negative")
    return pol


def max_explained_days(pol: dict | None = None) -> int:
    """The longest a row can go without being researched under the policy, plus one week of slack (ACT-33; scripts/carry_age.rows_carried_whole flags anything older).
    Group 2 waits group2_every_weeks; group 4 far waits group4_far_every_weeks; a group 3 row waits from its one check (day group3_check_to_days at the latest)
    to the first group 2 slot after day group2_after_days."""
    pol = pol or load_policy()
    g3 = (pol["group2_after_days"] - pol["group3_check_from_days"]) + 7 * int(pol["group2_every_weeks"])
    return max(7 * int(pol["group2_every_weeks"]), 7 * int(pol["group4_mid_every_weeks"]), 7 * int(pol["group4_far_every_weeks"]), g3) + 7


def week_index(d: date) -> int:
    """Continuous week number (Monday-to-Sunday blocks), so a Saturday is always exactly one more than last Saturday, across New Year too."""
    return d.toordinal() // 7


def read_overrides(path: Path | None = None) -> set[str]:
    """Canonical ids named in docs/operations/refresh_overrides.txt (one per line; blank lines and # comments ignored). A missing file means none."""
    p = Path(path) if path else OVERRIDES_FILE
    if not p.exists():
        return set()
    out = set()
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(line)
    return out


def event_dates(rec: dict) -> tuple[date | None, date | None, str]:
    """(start, end, note). The END of CONFERENCE DATES when it reads, else START DATE. (None, None, why) when the dates cannot be read or disagree: the caller researches (doubt means research)."""
    from scripts.input_list_audit import parse_range, to_iso
    hint = _d(to_iso(rec.get("START DATE", "")))
    s_txt, e_txt = parse_range(rec.get("CONFERENCE DATES", ""))
    s, e = _d(s_txt), _d(e_txt)
    if s and e and s > e:                                   # 'December 30 - January 2, 2027': the start belongs to the year before
        s = _plus_years(s, -1)
        if s > e:
            s = e = None
    if s is None or e is None:
        s = e = None
    if hint and s and hint != s:
        return None, None, f"START DATE {hint} and CONFERENCE DATES start {s} disagree"
    start = hint or s
    if start is None:
        return None, None, "no readable START DATE or CONFERENCE DATES"
    return start, (e if e and e >= start else start), ""


def _slot(canon: str, every: int, today: date) -> bool:
    return stable_hash(canon) % every == week_index(today) % every


def classify_conference(rec: dict, canon: str, today: date, pol: dict) -> dict:
    """The schedule alone (no overrides): {'group': 'G1'..'G4' or '', 'research': bool, 'reason': str, 'start', 'end'}. `rec` is the row's last accepted row."""
    status = (rec.get("STATUS") or "").strip()
    out = {"group": "", "research": True, "reason": "", "start": None, "end": None}
    start, end, why = event_dates(rec)
    out["start"], out["end"] = start, end
    if status.lower() != "closed":
        out.update(group="G1", reason=f"not Closed ({status or 'blank'}): weekly")
        return out
    if start is None:
        out["reason"] = f"dates unreadable ({why}): doubt means research"
        out["doubt"] = True
        return out
    if end < today:
        d = (today - end).days
        if d > pol["group2_after_days"]:
            n = int(pol["group2_every_weeks"])
            go = _slot(canon, n, today)
            out.update(group="G2", research=go, reason=f"Closed, ended {d} days ago (over {pol['group2_after_days']}): every {n} weeks, "
                       + ("this is its week" if go else "not its week"))
        else:
            lo, hi = pol["group3_check_from_days"], pol["group3_check_to_days"]
            go = lo <= d < hi
            out.update(group="G3", research=go, reason=f"Closed, ended {d} days ago: one check at {lo}-{hi - 1} days, "
                       + ("this is the check" if go else ("check still to come" if d < lo else "check done")))
        return out
    dts = (start - today).days
    if dts <= pol["group4_near_days"]:
        out.update(group="G4", reason=f"call closed, event starts in {dts} days (within {pol['group4_near_days']}): weekly")
    elif dts <= pol["group4_mid_days"]:
        n = int(pol["group4_mid_every_weeks"])
        go = _slot(canon, n, today)
        out.update(group="G4", research=go, reason=f"call closed, event starts in {dts} days: every {n} weeks, " + ("this is its week" if go else "not its week"))
    else:
        n = int(pol["group4_far_every_weeks"])
        go = _slot(canon, n, today)
        out.update(group="G4", research=go, reason=f"call closed, event starts in {dts} days (over {pol['group4_mid_days']}): every {n} weeks, "
                   + ("this is its week" if go else "not its week"))
    return out


def next_due(rec: dict, canon: str, today: date, pol: dict, horizon_weeks: int = 110) -> str:
    """The first Saturday AFTER today on which the schedule alone researches this row ('' when none within the horizon)."""
    d = today + timedelta(days=(5 - today.weekday()) % 7 or 7)             # the coming Saturday
    for _ in range(horizon_weeks):
        if classify_conference(rec, canon, d, pol)["research"]:
            return d.isoformat()
        d += timedelta(days=7)
    return ""


def first_saturday_of_january(today: date) -> bool:
    return today.month == 1 and today.day <= 7


def dead_links(rec: dict, states: dict[str, str]) -> list[str]:
    from scripts.sponsor_prefill import link_state
    return [u for u in ((rec.get(c) or "").strip() for c in LINK_COLUMNS) if u and link_state(u, states) == "dead"]


def conference_plan(rows: list[dict], prior_by_canon: dict[str, dict], states: dict[str, str], overrides: set[str], today: date, pol: dict) -> dict:
    """{'decisions': [per candidate row dict], 'skip': {row_index: mark}, 'counts': {...}, 'fuse': text or '', 'rows': n}. Rows labelled DUP_OF are left to the audit's own rule."""
    decisions = []
    jan = first_saturday_of_january(today)
    for i, r in enumerate(rows):
        if (r.get("DUP_OF") or "").strip():
            continue
        canon = (r.get("EVENT_ID_CANON") or "").strip()
        prior = prior_by_canon.get(canon) if canon else None
        d = {"index": i, "canonical": canon, "conference": r.get("CONFERENCE", ""), "prior_status": "", "start": None, "end": None,
             "group": "", "research": True, "kind": "", "reason": "", "override": "", "next_due": ""}
        if prior is None:
            d.update(kind="override", override="new",
                     reason="new: no accepted row yet (never skipped)" if canon else "no permanent id on the input row (never skipped)")
        else:
            c = classify_conference(prior, canon, today, pol)
            d.update(prior_status=(prior.get("STATUS") or "").strip(), start=c["start"], end=c["end"], group=c["group"], reason=c["reason"], research=c["research"])
            if c["research"]:
                d["kind"] = "override" if c.get("doubt") else "group"
                if c.get("doubt"):
                    d["override"] = "dates"
            else:
                forced = []
                if jan:
                    forced.append(("january", "first Saturday of January: every row is researched (year rollover)"))
                if canon in overrides:
                    forced.append(("named", "named in refresh_overrides.txt (a customer-sheet flag or an upstream note)"))
                dead = dead_links(prior, states)
                if dead:
                    forced.append(("dead-link", "customer-facing link recorded dead: " + dead[0]))
                if forced:
                    d.update(research=True, kind="override", override="+".join(k for k, _ in forced),
                             reason=c["reason"] + "; FORCED: " + "; ".join(t for _, t in forced))
            d["next_due"] = next_due(prior, canon, today, pol)
        decisions.append(d)
    n = len(decisions)
    skipped = [d for d in decisions if not d["research"]]
    fuse = ""
    if n and len(skipped) / n > pol["guard_max_skip_share"]:
        fuse = (f"GUARD: the plan would skip {len(skipped)} of {n} rows ({100 * len(skipped) // n}%, over the {int(pol['guard_max_skip_share'] * 100)}% limit): "
                f"skipping nothing, something is off with the data")
        for d in skipped:
            d["research"], d["kind"], d["reason"] = True, "group", d["reason"] + " (plan voided by the guard)"
        skipped = []
    skip = {}
    for d in skipped:
        d["mark"] = f"{d['group']} dormant: {d['reason'][:80]}; next check {d['next_due'] or 'n/a'}"
        skip[d["index"]] = d["mark"]
    counts = {"g1": 0, "g2": 0, "g3": 0, "g4": 0, "overrides": 0}
    for d in decisions:
        if not d["research"]:
            continue
        counts["overrides" if d["kind"] == "override" else d["group"].lower()] += 1
    return {"decisions": decisions, "skip": skip, "counts": counts, "fuse": fuse, "rows": n, "researched": n - len(skip)}


def summary_line(market: str, pl: dict, pol: dict, dry: bool = False) -> str:
    c, n, k, s = pl["counts"], pl["rows"], pl["researched"], len(pl["skip"])
    line = (f"REFRESH-PLAN {market}: {n} rows, {k} researched (g1 {c['g1']}, g2 {c['g2']}, g3 {c['g3']}, g4 {c['g4']}, overrides {c['overrides']}), "
            f"{s} skipped (saving about {s * pol['cost_per_row_usd']:.2f} USD, an estimate)")
    return line + (f" [{pl['fuse']}]" if pl["fuse"] else "") + (" [DRY RUN: nothing was marked, so every row is researched this week]" if dry else "")


def prior_rows_by_canon(final_path: Path, up_to_canon: dict[str, str]) -> dict[str, dict]:
    """Last week's accepted rows keyed by permanent id (identity.to_canonical, never a direct EVENT_ID join), first row wins as in weekend_import."""
    from src.cfp_monitor.identity import to_canonical
    out: dict[str, dict] = {}
    with open(final_path, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            out.setdefault(to_canonical(r.get("EVENT_ID", ""), up_to_canon), r)
    return out


REPORT_COLUMNS = ["market", "row", "canonical_id", "conference", "prior_status", "event_start", "event_end", "group", "decision", "kind", "override",
                  "reason", "next_due_saturday", "mark"]


def write_conference_report(out_dir: Path, market: str, pl: dict, pol: dict, today: date, line: str, stale_marks: int) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_p, md_p = out_dir / f"refresh_plan_{market}.csv", out_dir / f"refresh_plan_{market}.md"
    with open(csv_p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=REPORT_COLUMNS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for d in pl["decisions"]:
            w.writerow({"market": market, "row": d["index"] + 2, "canonical_id": d["canonical"], "conference": d["conference"], "prior_status": d["prior_status"],
                        "event_start": d["start"] or "", "event_end": d["end"] or "", "group": d["group"], "decision": "research" if d["research"] else "skip",
                        "kind": d["kind"], "override": d["override"], "reason": d["reason"], "next_due_saturday": d["next_due"], "mark": d.get("mark", "")})
    lines = [f"# Refresh plan {market} for {today}", "", line, ""]
    if pl["fuse"]:
        lines += [f"**{pl['fuse']}**", ""]
    if stale_marks:
        lines += [f"WARNING: {stale_marks} row(s) of the input list still carry a REFRESH_SKIP mark from an earlier --apply; the audit WILL skip them unless this plan is applied (or --clear is run).", ""]
    lines += [f"The saving is an ESTIMATE: {pol['cost_per_row_usd']} USD per researched row (about 8-9 grounded searches at 14 USD per 1,000).",
              f"Policy used: {json.dumps({k: pol[k] for k in DEFAULT_POLICY})}", "", "## Skipped this week", ""]
    for d in pl["decisions"]:
        if not d["research"]:
            lines.append(f"- {d['conference']} ({d['canonical']}): {d['reason']}; next check {d['next_due'] or 'n/a'}")
    lines += ["", "## Researched because of an override or doubt", ""]
    for d in pl["decisions"]:
        if d["research"] and d["kind"] == "override":
            lines.append(f"- {d['conference']} ({d['canonical']}): {d['reason']}")
    md_p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return csv_p, md_p


def verify_marks(path: Path, before: list[dict], skip: dict) -> str | None:
    """Read-back proof after apply_marks: same row count, no cell other than REFRESH_SKIP changed, and the column holds exactly the intended marks. Returns the fault or None."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        after = list(csv.DictReader(fh))
    if len(after) != len(before):
        return f"row count changed {len(before)} -> {len(after)}"
    for i, (b, a) in enumerate(zip(before, after)):
        for k, v in b.items():
            if k != COLUMN and (a.get(k) or "") != (v or ""):
                return f"row {i + 2}: column {k} changed"
        if (a.get(COLUMN) or "") != skip.get(i, ""):
            return f"row {i + 2}: {COLUMN} is not what was intended"
    return None


def apply_conference_marks(inp: Path, skip: dict) -> str:
    """apply_marks (cleared first, once-a-day backup) then the read-back proof; a failed proof puts the file back and raises."""
    with open(inp, encoding="utf-8-sig", newline="") as fh:
        before = list(csv.DictReader(fh))
    raw = inp.read_bytes()
    apply_marks(inp, skip)
    fault = verify_marks(inp, before, skip)
    if fault:
        inp.write_bytes(raw)
        raise RuntimeError(f"read-back proof failed ({fault}); the input list was put back as it was")
    return f"marked {len(skip)} row(s) in {inp.name} (column {COLUMN}); read-back proof OK; backup {inp.stem}.pre-refresh.csv"


def conference_main(a) -> int:
    """Always exits 0; any fault prints `REFRESH-PLAN <market>: UNKNOWN - why`, marks nothing (and, with --apply, clears an older mark so a failed week researches everything)."""
    market = a.market
    inp = Path(a.markets_dir) / f"{market}_input.csv"
    try:
        today = date.fromisoformat(a.today)
        out_dir = Path(a.out_dir) if a.out_dir else Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor" / "runs_out" / "qa" / today.isoformat()
        if not inp.exists():
            raise FileNotFoundError(f"no input file {inp}")
        if a.clear:
            apply_marks(inp, {})
            print(f"REFRESH-PLAN {market}: cleared every REFRESH_SKIP mark (backup {inp.stem}.pre-refresh.csv); every row will be researched")
            return 0
        pol = load_policy(Path(a.policy) if a.policy else None)
        with open(inp, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        stale = sum(1 for r in rows if (r.get(COLUMN) or "").strip())
        from src.cfp_monitor.identity import assert_mapped, seed_map
        up_to_canon, roots = seed_map(str(a.db))
        assert_mapped(up_to_canon, roots, minimum=a.min_mapped)
        final = Path(a.markets_dir) / f"{market}_audited.final.csv"
        if not final.exists():
            raise FileNotFoundError(f"no approved file {final.name}: nothing to carry, so nothing may be skipped")
        prior = prior_rows_by_canon(final, up_to_canon)
        from scripts.sponsor_prefill import read_link_states
        states = read_link_states(Path(a.db))
        pl = conference_plan(rows, prior, states, read_overrides(Path(a.overrides) if a.overrides else None), today, pol)
    except (Exception, SystemExit) as e:                             # noqa: BLE001  a planning fault (assert_mapped exits) must never cost the research window
        print(f"REFRESH-PLAN {market}: UNKNOWN - {type(e).__name__}: {e}; nothing skipped, every row will be researched")
        if a.apply and inp.exists() and not a.clear:
            try:
                apply_marks(inp, {})
                print(f"  cleared any older REFRESH_SKIP marks in {inp.name}")
            except Exception as e2:                                  # noqa: BLE001
                print(f"  WARNING: could not clear older marks ({type(e2).__name__}: {e2})")
        return 0
    line = summary_line(market, pl, pol, dry=not a.apply)
    print(line)
    if pl["fuse"]:
        print("  " + pl["fuse"])
    if stale and not a.apply:
        print(f"  WARNING: {stale} row(s) of {inp.name} still carry an older REFRESH_SKIP mark and WILL be skipped; run with --apply to replace them or --clear to remove them")
    try:
        csv_p, md_p = write_conference_report(out_dir, market, pl, pol, today, line, stale)
        print(f"  report: {md_p} ; per-row: {csv_p}")
    except Exception as e:                                           # noqa: BLE001
        print(f"  (report not written: {type(e).__name__}: {e})")
    if a.apply:
        try:
            print("  " + apply_conference_marks(inp, pl["skip"]))
        except Exception as e:                                       # noqa: BLE001
            print(f"REFRESH-PLAN {market}: UNKNOWN - marks not written: {type(e).__name__}: {e}; every row will be researched")
            try:
                apply_marks(inp, {})
            except Exception:                                        # noqa: BLE001
                pass
    else:
        print("  dry run: the input list was not changed (add --apply)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--market", default="Awards", choices=["Awards", *CONF_MARKETS])
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--max-skip-fraction", type=float, default=0.7)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--policy", default="", help="conference mode: the policy file (default docs/operations/refresh_policy.json)")
    ap.add_argument("--overrides", default="", help="conference mode: the always-research ids file (default docs/operations/refresh_overrides.txt)")
    ap.add_argument("--out-dir", default="", help="conference mode: where the report goes (default runs_out/qa/<date>)")
    ap.add_argument("--clear", action="store_true", help="conference mode: remove every REFRESH_SKIP mark (switching the policy off)")
    ap.add_argument("--min-mapped", type=int, default=50, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.market in CONF_MARKETS:
        return conference_main(a)
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
