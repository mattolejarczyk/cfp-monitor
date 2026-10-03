"""Which STEP failed, for every row that did not ship this week's research? (2026-10-03)

WHY. The question 'where do we get quality results, and where should a tool be changed?' needs evidence per STEP, not per tool. Each Saturday load already records, row by row, why a
row kept last week's version or was held back (the decision list in the weekend_import report). This reads those reasons and counts them by the step that failed, appends the counts
to a history file, and shows the trend, so the evidence builds itself every week at no cost. It reads and classifies; it changes nothing.

THE STEPS (a row is counted once, under the FIRST step that failed it)
  IDENTITY  the row cannot be tied to one event (no permanent id, a second row for the same event, an id another row holds): upstream's and our identity rules, not a tool
  FIND      the research cited a page that is a 404 or cannot be read, or the research call itself failed (a composed or stale URL; every search attempt failed)
  PROVE     the cited page exists but the quote is not on it (a paraphrase: the date is right, the wording is not; quote and date both absent)
  READ      the page was found and quoted but the claim is wrong or inconsistent (active-call wording on a projected row, a past deadline shown open, a year check, an enum)
  FORMAT    the file or a schema rule (CSV shape, GATED_STATUS filled, R11 wording)
  COVERAGE  last week's event was not covered by this week's research and was carried over (not a failure: the research list did not include it)
Pure functions plus a small JSON-lines history."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

STEPS = ("IDENTITY", "FIND", "PROVE", "READ", "FORMAT", "COVERAGE")


def classify(reasons: list[str], action: str) -> str:
    """The step a decision's reasons point at."""
    text = " ".join(reasons)
    low = text.lower()
    if action == "carried-over" or "not covered by this week's research" in low:
        return "COVERAGE"
    if "no permanent id" in low or "a second row for the same event" in low or "already uses its id" in low or "id collision" in low:
        return "IDENTITY"
    if "not researched this week" in low or "every search attempt failed" in low:
        return "FIND"
    if "year check" in low:
        return "READ"
    m = re.search(r"\[(\w+)\]", text)
    num = m.group(1) if m else ""
    if num in ("2", "2s") or re.search(r"http 40[34]|http 410|could not be read|unreadable", low):
        return "FIND"
    if num == "3" or "paraphrase" in low or "quote and date both absent" in low or "not on the cited page" in low:
        return "PROVE"
    if num in ("4", "5", "5b", "6", "6b", "R16", "2.1b", "2.1", "R12", "R8b", "R8d", "R8c", "R18a", "R18b", "R22", "R22b"):
        return "READ"
    if num in ("1", "R8a", "R11", "2.6", "R2"):
        return "FORMAT"
    return "READ"


def summarize(decisions: list[dict]) -> dict:
    """{step: {"rows": n, "examples": [...]}} over decisions that did not ship this week's research (kept-last-week, held-back, carried-over)."""
    out = {s: {"rows": 0, "examples": []} for s in STEPS}
    for d in decisions:
        if d.get("action") not in ("kept-last-week", "held-back", "carried-over"):
            continue
        step = classify(d.get("reasons", []), d.get("action", ""))
        out[step]["rows"] += 1
        if len(out[step]["examples"]) < 3:
            out[step]["examples"].append((d.get("conference") or "")[:40])
    return out


def counts(summary: dict) -> dict:
    return {s: summary[s]["rows"] for s in STEPS}


def append_history(path: Path, record: dict) -> None:
    """One JSON line per market per load, de-duplicated on (stamp, market) so a re-run of the report does not double count."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                seen.add((r.get("stamp"), r.get("market")))
            except json.JSONDecodeError:
                pass
    if (record.get("stamp"), record.get("market")) in seen:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_history(path: Path, market: str, n: int = 4) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("market") == market:
            rows.append(r)
    rows.sort(key=lambda r: r.get("stamp", ""))
    return rows[-n:]


def rises(now: dict, before: dict | None, threshold: int = 5, steps: tuple = ("FIND", "PROVE", "READ", "IDENTITY", "FORMAT")) -> list[str]:
    """Steps whose count rose by `threshold` or more since the previous load (COVERAGE excluded: a different research list is not a failure)."""
    if not before:
        return []
    return [f"{s} {before.get(s, 0)} -> {now.get(s, 0)}" for s in steps if now.get(s, 0) - before.get(s, 0) >= threshold]


def line(c: dict) -> str:
    """One plain line for the recap: 'FIND 7, PROVE 6, READ 2, IDENTITY 11'."""
    parts = [f"{s} {c[s]}" for s in ("FIND", "PROVE", "READ", "IDENTITY", "FORMAT") if c.get(s)]
    return ", ".join(parts) or "none"
