"""Pinned rows: a person's ruling on a row holds over the research until the call closes or the person removes it.

WHY (2026-10-03). The operator read the live pages and ruled on two rows: CODASPY (two tracks on one page: the earlier, abstract deadline is the default and both dates
go in the details) and Apres-Cyber (the aggregator the research cited does not list the event; the organizer's own Sessionize page stands). The carry rules
protect against BLANKS only; a fresh answer WITH evidence overrides last week's, so next Saturday the research could put the paper date and the bad aggregator
back. A ruling that a person made must survive until a person changes it.

HOW. `docs/operations/pinned_rows.json` lists pins: the row's canonical id, the cells a person ruled on, who and when and why, and an `until` date (the day after the
pinned deadline; a pin lapses by itself once the call has closed, and a person can delete it earlier). `weekend_import.py` applies them after the carry rules and before the
year checks and the gate, so the pinned values are checked like any others: the gate still reads the pinned quote on its page, and a quote that has left the page fails
the row and the row rule keeps last week's version (which carries the same ruling). Every pin that changed something is in the import report with what the research
said, so the ruling can be revisited (post_load_qa lists them). GROUNDING_CONFIDENCE follows IS_PROJECTED (R11). Pure function; no I/O except `load_pins`."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

PINS_FILE = Path(__file__).resolve().parents[1] / "docs" / "operations" / "pinned_rows.json"
# The cells a ruling may set: the deadline and its evidence, the call link, and the plain-language details. Identity and customer columns are never pinned.
ALLOWED = ("SUBMISSION DEADLINE", "DEADLINE_EVIDENCE_URL", "DEADLINE_QUOTE", "IS_PROJECTED", "CFP_SUBMISSION_URL", "STATUS DETAILS")


def load_pins(path: Path = PINS_FILE) -> list[dict]:
    if not Path(path).exists():
        return []
    return json.loads(Path(path).read_text(encoding="utf-8")).get("pins", [])


def apply_pins(rows: list[dict], lookup: dict, to_canonical, pins: list[dict], today: date | None = None) -> tuple[list[dict], dict]:
    """Returns (rows, report). Rows are modified in place. report = {"applied": [...], "unchanged": n, "lapsed": [...]}."""
    today = today or date.today()
    live, report = {}, {"applied": [], "unchanged": 0, "lapsed": []}
    for p in pins:
        bad = [k for k in p.get("set", {}) if k not in ALLOWED]
        if bad:
            raise ValueError(f"pin for {p.get('canonical')} sets a column a ruling may not set: {bad}")
        if p.get("until") and date.fromisoformat(p["until"]) < today:
            report["lapsed"].append(p.get("event") or p["canonical"])
            continue
        live[p["canonical"]] = p
    for r in rows:
        p = live.get(to_canonical((r.get("EVENT_ID") or "").strip(), lookup))
        if not p:
            continue
        diffs = {}
        for col, val in p["set"].items():
            if col in r and (r.get(col) or "") != val:
                diffs[col] = {"research": r.get(col, ""), "pinned": val}
                r[col] = val
        if "IS_PROJECTED" in p["set"] and "GROUNDING_CONFIDENCE" in r:
            conf = f"{'Projected' if p['set']['IS_PROJECTED'] == 'true' else 'Verified'} ({(r.get('EDITION') or '').strip()})"
            if r["GROUNDING_CONFIDENCE"] != conf:
                diffs["GROUNDING_CONFIDENCE"] = {"research": r["GROUNDING_CONFIDENCE"], "pinned": conf}
                r["GROUNDING_CONFIDENCE"] = conf
        if diffs:
            report["applied"].append({"conference": r.get("CONFERENCE", ""), "canonical": p["canonical"], "ruled_on": p.get("ruled_on", ""),
                                      "why": p.get("why", ""), "changed": diffs})
        else:
            report["unchanged"] += 1
    return rows, report
