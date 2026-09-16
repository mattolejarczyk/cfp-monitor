"""The shared shape of a weekly QA report, so every step's report can sit in one drill-down.

Asked for by the operator on 2026-09-16: for each step of the weekly cycle, a report that shows
that step's output against the previous week's, which a future dashboard can open for any step of
any week. Two reports exist (intake, build); five steps remain. They share this so they cannot
drift into five layouts.

ONE FOLDER PER CYCLE, keyed by the Monday it publishes. The cycle runs Saturday (intake,
research) -> Sunday (verify) -> Monday (build, send). Filing each report under the day it happened
to run would scatter one week across three folders, and a by-hand run on a Wednesday across a
fourth. So every report files under the Monday on or after the day it ran:

    runs_out/qa/<cycle Monday>/<step>.json    what a dashboard reads
    runs_out/qa/<cycle Monday>/<step>.md      the same, for a person

THE JSON SHAPE

    {"step", "cycle", "ran_at", "status": "PASS" | "FLAG", "summary",
     "sections": [{"title", "columns": [...], "rows": [[...]], "flags": [...], "note"}],
     "flags": [...]}

A FLAG is something a person should look at, never a failure of the run. These reports are read,
not enforced, and nothing here changes pipeline data.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

QA_ROOT = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor\runs_out\qa")


def cycle_of(day: date) -> date:
    """The Monday a run on `day` feeds: that Monday itself, or the next one."""
    return day + timedelta(days=(7 - day.weekday()) % 7)


def new_report(step: str, day: date) -> dict:
    return {"step": step, "cycle": cycle_of(day).isoformat(), "ran_on": day.isoformat(),
            "ran_at": datetime.now().isoformat(timespec="seconds"),
            "status": "PASS", "summary": "", "sections": [], "flags": []}


def finish(report: dict, summary_pass: str) -> dict:
    report["status"] = "FLAG" if report["flags"] else "PASS"
    report["summary"] = summary_pass if not report["flags"] else \
        f"{len(report['flags'])} thing(s) to look at"
    return report


def _cell(v) -> str:
    if v is None:
        return "-"
    return str(v).replace("|", "/").replace("\n", " ")


def to_markdown(report: dict, title: str) -> str:
    out = [f"# {title} - cycle {report['cycle']}", "",
           f"**{report['status']}** - {report['summary']}  ",
           f"ran {report['ran_at']}", ""]
    if report["flags"]:
        out += ["## Look at", ""] + [f"- {f}" for f in report["flags"]] + [""]
    for s in report["sections"]:
        out += [f"## {s['title']}", ""]
        if s.get("note"):
            out += [s["note"], ""]
        if s.get("rows"):
            out += ["| " + " | ".join(s["columns"]) + " |", "|" + "---|" * len(s["columns"])]
            out += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in s["rows"]]
            out.append("")
        elif s.get("columns"):
            out += ["_none_", ""]
    return "\n".join(out)


def write(report: dict, markdown: str, root: Path = QA_ROOT) -> Path:
    d = Path(root) / report["cycle"]
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{report['step']}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                              encoding="utf-8")
    (d / f"{report['step']}.md").write_text(markdown, encoding="utf-8")
    return d


def change(before, now):
    """A signed change for a table cell, or '-' when either side is unknown."""
    if before is None or now is None:
        return None
    d = now - before
    return f"{d:+d}" if d else "0"
