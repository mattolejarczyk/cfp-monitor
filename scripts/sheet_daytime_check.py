"""The daytime check: load the customer sheets in the daytime, rehearse the customer-context step, and tell Matt BEFORE 02:00 if tonight is at risk.

    python scripts/sheet_daytime_check.py --kind auto          # Thursday = for Friday 02:00 (awards), Friday = for Saturday 02:00 (conferences)
    python scripts/sheet_daytime_check.py --kind friday|saturday

WHY (Matt, 2026-11-13, D67 = A: "I don't mind doing it in the morning, say 7:30 AM, and then later in the day around 6PM"; and "next week I expect this will
not happen again"). The 02:00 load is the only load, and its failure was found at 02:00 or after. Two real loads on the day before, each saving copies,
mean a failed 02:00 load usually meets a copy that is only hours old, and a problem (a revoked share, a changed sheet, a crashed context step) is seen with
a whole working day left to fix it.

WHAT EACH RUN DOES (registered by `scripts/register_sheet_daytime.ps1`, Matt runs it: Thursday and Friday at 07:30 and 18:15)
  1. A REAL load of all four sheets with the usual retries (3 tries over about 15 minutes): copies are saved in Markets\\customer_snapshots, exactly as the
     02:00 load does. Nothing is loaded into the database and no research is touched.
  2. The REAL step 0a4 block of run_monthly.ps1 is run on scratch copies (scripts/step_0a4_rehearsal.py): a usage error, no verdict line, FAILED, UNKNOWN or
     zero rows is RED. This is what would have caught the 2026-11-13 crash on Thursday.
  3. A verdict for the research that follows, with the hours left before 02:00 and the age each copy will have AT 02:00 (D67: a research proceeds on a copy
     no older than CFP_SHEETS_MAX_AGE_HOURS, default 24, if its own load fails):
       GREEN   every sheet loaded and the context rehearsal is good. No email (the log and runs_out/sheet_daytime_status.json say so).
       YELLOW  a sheet failed but its copy will still be fresh enough at 02:00, or only a sheet tomorrow's research does not need failed, or the context
               rehearsal is DEGRADED. Email at once: tonight's research would still proceed.
       RED     a sheet tomorrow's research needs failed and its copy will be too old (or there is none) by 02:00, or the context rehearsal failed. Email at
               once with the hours left and the time the copy ages out: the 02:00 research would be HELD (or run without context) unless this is fixed.
Exit codes (the AgentOS convention, HEALTHY 0 / FAILED 1 / DEGRADED 2): 0 GREEN, 2 YELLOW, 1 RED or the check itself failed. The LAST printed line is the verdict (SHEET DAYTIME: ...). The email is not the once-a-day
CRITICAL email of the 02:00 load: a daytime alert never uses that one up."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, time as dtime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import customer_sheet_load as csl      # noqa: E402
import step_0a4_rehearsal as rh        # noqa: E402

KIND_BY_WEEKDAY = {3: "friday", 4: "saturday"}          # Thursday -> Friday's awards research; Friday -> Saturday's conference research
TARGET_WEEKDAY = {"friday": 4, "saturday": 5}
WINDOW = dtime(2, 0)
STATUS = csl.RUNS_OUT / "sheet_daytime_status.json"
RANK = {"GREEN": 0, "YELLOW": 1, "RED": 2}


def next_window(kind: str, at: datetime) -> datetime:
    """The next 02:00 of the research this check protects (Friday's awards, Saturday's conferences)."""
    for i in range(8):
        day = at.date() + timedelta(days=i)
        if day.weekday() == TARGET_WEEKDAY[kind] and datetime.combine(day, WINDOW) > at:
            return datetime.combine(day, WINDOW)
    raise ValueError("no window found")


def worst(*levels: str) -> str:
    return max(levels, key=lambda v: RANK[v])


def judge_sheets(clients: list[str], needed: list[str], failed: list[str], ages: dict, hours_left: float, limit_h: float, absent: list[str] | tuple = ()) -> dict:
    """{client: {'level', 'why', 'age_now', 'age_at_window', 'ages_out'}} for every sheet. Pure.
    Ages are compared UNROUNDED and a copy dated in the future never counts (Codex review 2026-11-13: rounding let 24 h 1 min pass as 24.0, and a negative age passed
    the upper bound); a sheet tomorrow's research needs that is not in the settings file at all is RED, never silently skipped."""
    rows = {}
    for c in absent:
        rows[c] = {"level": "RED", "why": "is needed by tomorrow's research but is not in the sheet settings file (customer_sheets.json), so it can never load",
                   "age_now": None, "age_at_window": None, "ages_out": None}
    for c in clients:
        a = ages.get(c) or {"age_h": None, "taken": None, "copy": None}
        now_h = a["age_h"]
        usable = now_h is not None and now_h >= 0
        at_raw = now_h + hours_left if usable else None
        at_window = None if at_raw is None else round(at_raw, 1)                  # display only
        ages_out = None if a["taken"] is None or limit_h <= 0 else a["taken"] + timedelta(hours=limit_h)
        if c not in failed:
            rows[c] = {"level": "GREEN", "why": "loaded", "age_now": now_h, "age_at_window": at_window, "ages_out": ages_out}
        elif c not in needed:
            rows[c] = {"level": "YELLOW", "why": "did not load; tomorrow's research does not need it, a later one does", "age_now": now_h,
                       "age_at_window": at_window, "ages_out": ages_out}
        elif usable and limit_h > 0 and at_raw <= limit_h:
            rows[c] = {"level": "YELLOW", "why": f"did not load; its copy will be {at_window:g} h old at 02:00, within the {limit_h:g} h limit",
                       "age_now": now_h, "age_at_window": at_window, "ages_out": ages_out}
        else:
            if now_h is None:
                why = "did not load and there is no copy"
            elif now_h < 0:
                why = "did not load and its newest copy is dated in the future (a clock or file-name fault), so it cannot be trusted"
            elif limit_h <= 0:
                why = "did not load and the copy fallback is switched off (limit 0)"
            else:
                why = f"did not load and its copy will be {at_window:g} h old at 02:00, over the {limit_h:g} h limit"
            rows[c] = {"level": "RED", "why": why, "age_now": now_h, "age_at_window": at_window, "ages_out": ages_out}
    return rows


def compose(kind: str, at: datetime, window: datetime, hours_left: float, limit_h: float, rows: dict, result: dict, rehearsal: dict, overall: str,
            info: dict, snapshots: Path, evidence: Path | None) -> tuple[str, str]:
    what = csl.CONTEXTS[kind][0]
    bad = [c for c, r in rows.items() if r["level"] != "GREEN"]
    bits = []
    if bad:
        bits.append(", ".join(csl.LABELS.get(c, c) for c in bad) + " did not load")
    if rehearsal["verdict"] != "GREEN":
        bits.append("the context step " + ("would fail" if rehearsal["verdict"] == "RED" else "is degraded"))
    subject = f"CFP customer sheets {at:%H:%M} check: {overall} - " + "; ".join(bits)[:120] + f" ({hours_left:.1f} h before 02:00)"
    L = [subject, "", "WHEN",
         f"Checked {at:%a %d %b %H:%M}. {what[0].upper() + what[1:]} starts at {window:%a %d %b %H:%M}, {hours_left:.1f} hours from now. "
         f"Rule (D67): if its own load fails, it proceeds on a copy no older than {limit_h:g} hours, and is held otherwise.", "", "THE SHEETS"]
    for c, r in rows.items():
        line = f"- {csl.LABELS.get(c, c)}: {r['level']} - {r['why']}"
        if r["level"] != "GREEN":
            o = result["outcomes"].get(c, {})
            line += f". Error: {(o.get('reason') or '')[:240]}"
            if r["age_now"] is not None:
                line += f". Copy now {r['age_now']:.1f} h old, {r['age_at_window']:g} h old at 02:00"
                if r["ages_out"]:
                    line += f", too old after {r['ages_out']:%a %H:%M}"
        L.append(line)
    L += ["", "THE CUSTOMER CONTEXT STEP (the real step 0a4 block, run on scratch copies; nothing live was touched)",
          f"- {rehearsal['verdict']}: {rehearsal['reason']}"]
    if rehearsal.get("lint"):
        L += [f"- lint: {x}" for x in rehearsal["lint"]]
    L += ["", "WHAT THIS MEANS FOR 02:00"]
    reds = [c for c, r in rows.items() if r["level"] == "RED"]
    yellows = [c for c, r in rows.items() if r["level"] == "YELLOW"]
    if reds:
        times = [rows[c]["ages_out"] for c in reds if rows[c]["ages_out"]]
        L.append(f"- RED: {', '.join(csl.LABELS.get(c, c) for c in reds)} would NOT have a fresh enough copy at 02:00, so the research would be HELD unless its own 02:00 "
                 f"load succeeds. Fix it before then" + (f" (the copy is too old after {max(times):%a %H:%M})." if times else "."))
    if yellows:
        L.append(f"- YELLOW: {', '.join(csl.LABELS.get(c, c) for c in yellows)} did not load, but the research would still proceed on the copy (YELLOW in the recap).")
    if rehearsal["verdict"] == "RED":
        L.append("- RED: the customer context would NOT build: the research would run WITHOUT it (or be held, once patch ACT-76 is applied). "
                 "Send the line above to the Claude session that built it.")
    elif rehearsal["verdict"] == "YELLOW":
        L.append("- YELLOW: the customer context would build, with a warning (see above).")
    L.append("")
    if result["failed"]:
        L += csl.cause_sections(result, info, snapshots, kind)
    L += ["EVIDENCE", f"- Every try and its output: {evidence}" if evidence else "- (no evidence file was written)",
          f"- Re-run just the sheet load any time: {csl.rerun_command(result['failed'] or result['clients'])}", "",
          "This email goes to you only. No secret is in it."]
    return subject, csl.redact("\n".join(L) + "\n")


def daytime(kind: str, now=datetime.now, snapshots: Path | None = None, config: Path | None = None, env: dict | None = None, mailer=None,
            state: Path | None = None, qa_root: Path | None = None, runner=None, sleep=time.sleep, rehearse_fn=None, status_path: Path | None = None,
            alert_files=None) -> tuple[int, list[str]]:
    """(exit code, printed lines; the LAST line is the verdict). A real load, the context rehearsal, a verdict, an email when it is not GREEN."""
    snapshots, config = Path(snapshots or csl.SNAPSHOTS), Path(config or csl.CONFIG)
    clients = csl.expand("all", config)
    needed = list(csl.CONTEXTS[kind][2])                                      # NOT cut down to the config: a needed sheet the config lacks is RED (Codex 2026-11-13)
    absent = [c for c in needed if c not in clients]
    result = csl.safe_load(clients, config, snapshots, csl.WAITS, sleep, runner, now)
    at = now()
    window = next_window(kind, at)
    hours_left_raw = (window - at).total_seconds() / 3600                       # compared unrounded (Codex pass 2); rounded only for the text
    hours_left = round(hours_left_raw, 2)
    limit_h = csl.max_age_hours(env)
    rows = judge_sheets(clients, needed, result["failed"], csl.copy_ages(clients, snapshots, at), hours_left_raw, limit_h, absent)
    rehearsal = (rehearse_fn or rh.rehearse)(kind)
    overall = worst(*(r["level"] for r in rows.values()), rehearsal["verdict"] if rehearsal["verdict"] in RANK else "RED")
    info = csl.config_info(config)
    evidence = csl.write_evidence({"kind": kind, "at": at.isoformat(timespec="seconds"), "window": window.isoformat(timespec="seconds"), "hours_left": hours_left,
                                   "limit_h": limit_h, "overall": overall, "sheets": {c: {k: v for k, v in r.items() if k != "ages_out"} for c, r in rows.items()},
                                   "rehearsal": {k: v for k, v in rehearsal.items() if k != "lint"}, **result}, at, qa_root)
    email = "no email (GREEN)"
    if overall != "GREEN":
        subject, body = compose(kind, at, window, hours_left, limit_h, rows, result, rehearsal, overall, info, snapshots, evidence)
        csl.write_alert_file(body, alert_files)
        email = "email " + csl.send(subject, body, at.date(), at, mailer, state, once_a_day=False)
    elif not result["failed"]:
        csl.clear_alert_files(alert_files)                                    # everything loaded: an older Desktop alert is out of date
    try:
        p = Path(status_path or STATUS)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"kind": kind, "at": at.isoformat(timespec="seconds"), "window": window.isoformat(timespec="seconds"), "hours_left": hours_left,
                                 "overall": overall, "sheets": {c: r["level"] for c, r in rows.items()}, "context": rehearsal.get("line")}, indent=2), encoding="utf-8")
    except Exception:                                                         # noqa: BLE001
        pass
    sheet_txt = (f"all {len(clients)} sheet(s) loaded" if not result["failed"] else
                 f"{len(result['failed'])} of {len(clients)} did not load ({', '.join(result['failed'])})")
    ctx_txt = f"context rehearsal {rehearsal['verdict']}" + (f" ({rehearsal['reason'][:90]})" if rehearsal["verdict"] != "GREEN" else "")
    line = (f"SHEET DAYTIME: {overall} - {sheet_txt}; {ctx_txt}; {hours_left:.1f} h before the {window:%a %H:%M} research; {email}; evidence: {evidence}")
    return {"GREEN": 0, "YELLOW": 2, "RED": 1}[overall], [line]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kind", choices=["auto", "friday", "saturday"], default="auto",
                    help="which research this protects; auto = by weekday (Thursday: Friday's awards, Friday: Saturday's conferences)")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                                         # noqa: BLE001
        pass
    kind = a.kind if a.kind != "auto" else KIND_BY_WEEKDAY.get(datetime.now().weekday())
    if kind is None:
        print("SHEET DAYTIME: GREEN - nothing to check today (it runs on Thursday and Friday)")
        return 0
    try:
        code, lines = daytime(kind)
    except Exception as exc:                                                  # noqa: BLE001
        print(f"SHEET DAYTIME: RED - the check itself failed ({type(exc).__name__}: {exc})")
        return 1
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
