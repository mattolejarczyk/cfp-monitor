"""What changed in a client's sheet since last week, and what they have NOT touched.

TWO QUESTIONS, AND THE SECOND IS THE IMPORTANT ONE

  What did they act on?   Their edits are the most reliable data in the system - a human who
                          emailed the organiser knows things no crawl will produce.

  What did they NOT act on?   Usually fine. Nobody works every row every week. It is only a
                          problem when the row is about to close, and that is the one case
                          where silence costs the customer a submission.

So this reports inaction only where inaction has a cost. A report that lists 53 untouched rows
every week trains the reader to skip it, which is the same failure the weekly digest had.

WHAT COUNTS AS "ACTING"
Only a change to a field the CUSTOMER owns (rule C1). If our own pipeline corrects a deadline,
that is us, not them - counting it would tell us they are engaged when they have not opened the
sheet. `LATEST UPDATE` is excluded for the same reason and because it moves in bulk.
"""
from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

# Their columns, by owner. A change in each class means something different.
CUSTOMER_OWNED = ("STATUS", "STATUS DETAILS", "PRIORITY", "SPEAKER & ABSTRACTS SUBMITTED",
                  "NOTES", "NOTIFICATION DATE", "NOTIFCATION DATE")
REQUEST = ("SUBMISSION DATE VERIFIED",)
EVIDENCE = ("SUBMISSION DEADLINE", "SUBMISSION URL", "CONFERENCE URL", "LOCATION",
            "EVENT START DATE", "OVERVIEW", "CATEGORIES", "COORDINATOR CONTACT INFO")
# Moves in bulk and is not a statement of intent - never evidence that anyone did anything.
IGNORED = ("LATEST UPDATE",)

KEY = "CONFERENCE"

# Urgency bands, in the same order the customer page uses them. The point of the bands is that
# they decide how loudly silence is reported, not how the row is displayed.
URGENT_DAYS = 7
SOON_DAYS = 30


def read(path: Path) -> dict[str, dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return {(r.get(KEY) or "").strip(): r
                for r in csv.DictReader(fh) if (r.get(KEY) or "").strip()}


def _cells(before: dict, after: dict, cols) -> list[tuple[str, str, str]]:
    out = []
    for c in cols:
        if c not in after and c not in before:
            continue
        b, a = (before.get(c) or "").strip(), (after.get(c) or "").strip()
        if b != a:
            out.append((c, b, a))
    return out


def _days_to(value: str, today: date) -> int | None:
    """Days until a deadline, or None if it is not a plain date. Their deadline column also
    carries prose ('Call opens... closes...' and 'Sponsorship Required - $12,500'), and a
    number invented from prose is worse than no number."""
    v = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return (datetime.strptime(v[:10], fmt).date() - today).days
        except ValueError:
            continue
    return None


def diff(before_path: Path, after_path: Path, today: date) -> dict:
    before, after = read(before_path), read(after_path)

    added = [n for n in after if n not in before]
    removed = [n for n in before if n not in after]

    acted, corrected, requested, untouched = [], [], [], []
    for name, row in after.items():
        if name not in before:
            continue
        prev = before[name]
        own = _cells(prev, row, CUSTOMER_OWNED)
        req = _cells(prev, row, REQUEST)
        evi = _cells(prev, row, EVIDENCE)
        if own:
            acted.append({"name": name, "changes": own})
        if req:
            requested.append({"name": name, "changes": req})
        if evi:
            corrected.append({"name": name, "changes": evi})
        if not (own or req or evi):
            untouched.append({"name": name, "row": row})

    # Silence only matters where it costs something. A row closing inside the window that the
    # customer has neither touched nor already moved on is the whole reason to look at inaction.
    at_risk = []
    for u in untouched:
        r = u["row"]
        d = _days_to(r.get("SUBMISSION DEADLINE", ""), today)
        if d is None or d < 0:
            continue
        status = (r.get("STATUS") or "").strip().lower()
        if status in ("submitted", "accepted", "closed", "declined", "not appropriate",
                      "client declined"):
            continue                       # already dealt with; silence is correct
        if d <= SOON_DAYS:
            at_risk.append({"name": u["name"], "days": d,
                            "deadline": (r.get("SUBMISSION DEADLINE") or "").strip(),
                            "status": (r.get("STATUS") or "").strip() or "(blank)",
                            "band": "closing this week" if d <= URGENT_DAYS
                                    else "closing this month"})
    at_risk.sort(key=lambda x: x["days"])

    return {"rows_before": len(before), "rows_after": len(after),
            "added": added, "removed": removed,
            "acted": acted, "requested": requested, "corrected": corrected,
            "untouched": len(untouched), "at_risk": at_risk}


def render(d: dict, client: str, today: date) -> str:
    """A report shaped for a decision, not a log. Same discipline as the weekly digest: say what
    it means, who acts, and by when - and never present inaction as a finding on its own."""
    L = [f"# {client} - sheet changes as at {today.isoformat()}", ""]
    moved = len(d["acted"]) + len(d["requested"]) + len(d["corrected"]) \
        + len(d["added"]) + len(d["removed"])
    if not moved:
        L += [f"**No change since the last snapshot.** {d['rows_after']} row(s), none edited. "
              "That is a normal week.", ""]
    else:
        L += ["## At a glance", "",
              "| What | Count | What it means | Who acts |", "|---|---:|---|---|",
              f"| They acted on a row | {len(d['acted'])} | Their own status, notes or "
              "priority moved | Read it - this is the best data we get |",
              f"| They asked us to verify | {len(d['requested'])} | `SUBMISSION DATE VERIFIED` "
              "changed | **Us**, this week |",
              f"| They corrected a fact | {len(d['corrected'])} | A deadline or URL we also "
              "hold | **Us** - reconcile, do not overwrite |",
              f"| Rows added | {len(d['added'])} | Conferences we may not track | **Us** - "
              "match, then propose for the industry list |",
              f"| Rows removed | {len(d['removed'])} | Not a deletion (2.1) | **Us** - flag and "
              "ask |", ""]

    for key, title, note in (
            ("acted", "They acted on these",
             "Their own fields moved. Never overwrite any of this."),
            ("requested", "They asked us to verify these",
             "A direct request. Answer with a citation, or say honestly that we could not."),
            ("corrected", "They changed a fact we also hold",
             "A customer edit with a note beside it outranks our crawl (C3). Without a note it "
             "is a signal to re-verify, not a verdict.")):
        if d[key]:
            L += [f"## {title} ({len(d[key])})", "", note, ""]
            for e in d[key]:
                L.append(f"- **{e['name']}**")
                for c, b, a in e["changes"]:
                    L.append(f"    - `{c}`: {b or '(blank)'}  ->  {a or '(blank)'}")
            L.append("")

    if d["added"]:
        L += [f"## Rows they added ({len(d['added'])})", "",
              "The most valuable signal in the sheet: it is the only direct measure of what we "
              "fail to find.", ""]
        L += [f"- {n}" for n in d["added"]] + [""]
    if d["removed"]:
        L += [f"## Rows that disappeared ({len(d['removed'])})", "",
              "**Not a deletion.** They may have filtered or sorted. Kept and flagged (C4).", ""]
        L += [f"- {n}" for n in d["removed"]] + [""]

    L += [f"## Untouched: {d['untouched']} row(s)", "",
          "Nobody works every row every week, and this number is not a problem by itself. "
          "Listing them all",
          "would train the reader to skip this report. Only the ones where silence has a cost "
          "appear below.", ""]

    if d["at_risk"]:
        L += [f"## NOT ACTED ON AND CLOSING SOON ({len(d['at_risk'])})", "",
              "**This is the safety net.** Not edited since the last snapshot, not yet in a "
              "settled state",
              "(submitted, accepted, closed or declined), and the deadline is inside 30 days.",
              "A row still being drafted, or blocked waiting on information, counts - that is "
              "precisely",
              "the row that gets missed. Each of these is a submission the customer may be "
              "about to lose.", "",
              "| Conference | Deadline | Days | Their status | Band |", "|---|---|---:|---|---|"]
        for a in d["at_risk"]:
            L.append(f"| {a['name']} | {a['deadline']} | {a['days']} | {a['status']} | "
                     f"{a['band']} |")
        L.append("")
    else:
        L += ["**Nothing untouched is closing inside 30 days.** The safety net is clear.", ""]
    return "\n".join(L) + "\n"
