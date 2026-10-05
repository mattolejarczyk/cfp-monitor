"""Render docs/operations/FAILURE-POINTS.md from docs/operations/failure_points.json (2026-10-05).

    python scripts/failure_points_doc.py [--check]

WHY. The QA register lists CHECKS and the runbook lists SYMPTOMS. This is the third view the operator asked for: every ROOT-CAUSE failure point in the process, grouped by the six macro
steps on the status board, ordered by how often it occurs and how much it hurts, with what has overcome it and what is still open. A root cause is not page specific: pages appear only as
evidence, because the same cause will show up on the next site we crawl.
The data lives in the JSON (add a failure point or change a status there); this script only formats, so the document and the counts cannot disagree.
SCORE = frequency x impact (each 1 to 3). Frequency: 3 = seen on many rows or every week, 2 = seen several times, 1 = seen once or hypothetical. Impact: 3 = wrong or missing data can reach
the customer, or a whole run is lost; 2 = row-level quality or real cost; 1 = internal friction. Within a step: highest score first, then highest impact, then highest frequency.
STATUS: OVERCOME = a control prevents or detects it automatically and it has been shown to work; MITIGATED = detected or partly prevented, a residual remains; WATCH = a control is built
but not yet proven in a live run; PENDING = known, no working control yet.
--check exits 1 when the document on disk differs from what the data would produce."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "operations" / "failure_points.json"
OUT = ROOT / "docs" / "operations" / "FAILURE-POINTS.md"
STATUSES = ("OVERCOME", "MITIGATED", "WATCH", "PENDING")


def score(i: dict) -> int:
    return i["freq"] * i["impact"]


def ordered(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda i: (-score(i), -i["impact"], -i["freq"], i["id"]))


def counts(items: list[dict]) -> dict:
    return {s: sum(1 for i in items if i["status"] == s) for s in STATUSES}


def validate(d: dict) -> list[str]:
    errs, seen = [], set()
    for i in d["items"]:
        for k in ("id", "step", "cause", "evidence", "controls", "remains", "freq", "impact", "status"):
            if k not in i or i[k] in ("", None):
                errs.append(f"{i.get('id', '?')}: missing {k}")
        if i.get("id") in seen:
            errs.append(f"duplicate id {i['id']}")
        seen.add(i.get("id"))
        if i.get("step") not in d["steps"]:
            errs.append(f"{i.get('id')}: unknown step {i.get('step')}")
        if i.get("status") not in STATUSES:
            errs.append(f"{i.get('id')}: unknown status {i.get('status')}")
        if i.get("freq") not in (1, 2, 3) or i.get("impact") not in (1, 2, 3):
            errs.append(f"{i.get('id')}: freq and impact must be 1 to 3")
        if not str(i.get("id", "")).startswith(i.get("step", "?")):
            errs.append(f"{i.get('id')}: id does not start with its step letter")
    return errs


def render(d: dict) -> str:
    items = d["items"]
    L = []
    L += [f"# Process failure points by root cause - {d['as_of']}", "",
          "Every way the CFP process can produce missing, wrong or late data, described by its ROOT CAUSE and not by the web page where we happened to see it. A page is only evidence: the same cause will appear on the next site we discover and crawl. "
          "Grouped by the six macro steps on the status board, and inside each step ordered by how often the cause occurs and how much it hurts. Generated from `docs/operations/failure_points.json` by `scripts/failure_points_doc.py`; "
          "the QA register (`QA-REGISTER.md`) lists the checks, the runbook (`market-runbook.md`) lists the symptoms, this lists the causes.", "",
          "**How to read it.** SCORE = frequency x impact, each 1 to 3. Frequency: 3 = seen on many rows or every week; 2 = seen several times; 1 = seen once or hypothetical. Impact: 3 = wrong or missing data can reach the customer, or a whole run is lost; "
          "2 = row-level quality or real cost; 1 = internal friction. **Status:** OVERCOME = a control prevents or detects it automatically and it has been shown to work; MITIGATED = detected or partly prevented, a residual remains; "
          "WATCH = a control is built but not yet proven in a live run; PENDING = known, no working control yet. The scores are a judgment made from the evidence quoted under each item; correct any that you see differently.", ""]
    total = counts(items)
    L += ["## Scoreboard", "", "| Macro step | Failure points | Overcome | Mitigated | Watch | Pending |", "|---|---:|---:|---:|---:|---:|"]
    for sid, name in d["steps"].items():
        its = [i for i in items if i["step"] == sid]
        c = counts(its)
        L.append(f"| **{sid}** {name} | {len(its)} | {c['OVERCOME']} | {c['MITIGATED']} | {c['WATCH']} | {c['PENDING']} |")
    L.append(f"| **All** | {len(items)} | {total['OVERCOME']} | {total['MITIGATED']} | {total['WATCH']} | {total['PENDING']} |")
    L += ["", f"{total['OVERCOME']} of {len(items)} are overcome and {total['MITIGATED'] + total['WATCH']} more are mitigated or being proven. "
          f"Weighted by score, {sum(score(i) for i in items if i['status'] == 'OVERCOME')} of {sum(score(i) for i in items)} points of risk are overcome.", ""]
    if d.get("progress"):
        L += ["## How far we have come", "", "| Measure | Before | Now | Note |", "|---|---|---|---|"]
        for p in d["progress"]:
            L.append(f"| {p['measure']} | {p['before']} | {p['now']} | {p.get('note', '')} |")
        L.append("")
    open_items = [i for i in ordered(items) if i["status"] != "OVERCOME"]
    L += ["## The highest remaining risks", "", "Not yet overcome, highest score first (the order to attack them in):", ""]
    for n, i in enumerate(open_items[:12], 1):
        L.append(f"{n}. **{i['id']}** [{i['status']}, score {score(i)}] {i['cause']} - *open:* {i['remains']}")
    L.append("")
    for sid, name in d["steps"].items():
        its = ordered([i for i in items if i["step"] == sid])
        c = counts(its)
        L += [f"## {sid}. {name}", "", f"{len(its)} failure points: {c['OVERCOME']} overcome, {c['MITIGATED']} mitigated, {c['WATCH']} to prove live, {c['PENDING']} pending.", ""]
        for n, i in enumerate(its, 1):
            since = f" (since {i['since']})" if i.get("since") else ""
            up = " - closed only by upstream" if i.get("upstream") else ""
            L += [f"### {i['id']}. {i['cause']}", "",
                  f"Rank {n} of {len(its)} in this step. **{i['status']}**{since}; score {score(i)} (frequency {i['freq']} x impact {i['impact']}){up}", "",
                  f"- **Seen as:** {i['evidence']}",
                  f"- **What overcame or reduces it:** {i['controls']}",
                  f"- **What remains:** {i['remains']}", ""]
    ups = [i for i in ordered(items) if i.get("upstream") and i["status"] != "OVERCOME"]
    L += ["## Failure points only upstream can close", "", "We can detect these and hold the row; the fix is in upstream's research or writer:", ""]
    for i in ups:
        L.append(f"- **{i['id']}** [{i['status']}] {i['cause']} - {i['remains']}")
    L += ["", "## Limits of this view", "",
          "- Frequencies come from the evidence in the repository's documents and the last two weeks of runs; the process is young and several figures are single runs or small samples (14 events for the finder comparison).",
          "- A status of OVERCOME means the control has worked where it was tested, not that the cause can never return on a new kind of page.",
          "- The causes are the ones we have seen. The register grows when a new failure is found: add it to the data file with its evidence, then regenerate.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    d = json.loads(DATA.read_text(encoding="utf-8"))
    errs = validate(d)
    if errs:
        print("failure_points.json is invalid:\n  " + "\n  ".join(errs))
        return 1
    text = render(d)
    if a.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("FAILURE-POINTS.md is current" if same else "FAILURE-POINTS.md is OUT OF DATE: run python scripts/failure_points_doc.py")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT} ({len(d['items'])} failure points)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
