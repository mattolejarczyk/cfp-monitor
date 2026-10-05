"""How old is a value the load CARRIED instead of re-confirming? (ACT-17, 2026-10-05; failure point D8)

The carry rules keep last week's value when this week's research brings nothing: the narrow overlay (organizer and the fields the short question does not
ask), the evidence carry (page + quote + projected flag as a unit) and the sponsorship carry. Each is right on its own, and together they let a value age
silently: nobody re-verifies it, the row keeps shipping, and the page looks current. This module records, per event and per unit, WHEN THE VALUE WAS LAST
CONFIRMED (fresh in research, not carried), and the load QA flags any carried longer than LIMIT_WEEKS.

    UNITS      evidence      DEADLINE_EVIDENCE_URL, DEADLINE_QUOTE, IS_PROJECTED, GROUNDING_CONFIDENCE, SUBMISSION DEADLINE (the verified-deadline unit)
               sponsorship   SPONSOR_* (the sponsorship unit)
               organizer     ORGANIZER
    (CITY, OVERVIEW and the other unasked fields also carry every week under the short question; they are not aged here: they are not what the customer acts on.)

LEDGER  <data root>/carry_ledger.json  { canonical id: {"name": ..., "units": {unit: {"confirmed": "YYYY-MM-DD", "last_carried": "YYYY-MM-DD"}}} }
An entry exists only while a value is carried. A unit that comes back fresh is deleted (its age is zero by definition). The date a value was last
confirmed starts as the prior approved row's SOURCE_AS_OF (when that row was last researched), and never moves while the value keeps being carried.
LIMIT_WEEKS is a proposal (6 weeks, an estimate: Saturday research runs weekly, so six consecutive carries); change it here and in QA-REGISTER A26.
Pure functions plus `load_ledger` / `save_ledger`; the importer writes the ledger only after a load that stuck."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

LIMIT_WEEKS = 6
EVIDENCE_FIELDS = {"DEADLINE_EVIDENCE_URL", "DEADLINE_QUOTE", "IS_PROJECTED", "GROUNDING_CONFIDENCE", "SUBMISSION DEADLINE"}
SPONSOR_FIELDS = {"SPONSOR_REQUIRED", "SPONSOR_URL", "SPONSOR_COST", "SPONSOR_QUOTE"}
UNITS = ("evidence", "sponsorship", "organizer")


def unit_of(field: str) -> str:
    if field in EVIDENCE_FIELDS:
        return "evidence"
    if field in SPONSOR_FIELDS:
        return "sponsorship"
    if field == "ORGANIZER":
        return "organizer"
    return ""


def _iso(v: str) -> str:
    try:
        return datetime.strptime((v or "").strip()[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return ""


def carried_units(overlay_report: dict, sponsor_report: dict, prior_by_canon: dict[str, dict]) -> dict[str, dict]:
    """{canonical: {"name": ..., "units": {unit: prior row's SOURCE_AS_OF}}} for everything the carry rules kept this week. Pure."""
    out: dict[str, dict] = {}

    def add(canon: str, name: str, fields: list[str]):
        for f in fields:
            u = unit_of(f)
            if not u:
                continue
            e = out.setdefault(canon, {"name": name, "units": {}})
            e["units"][u] = _iso((prior_by_canon.get(canon) or {}).get("SOURCE_AS_OF", ""))

    for o in overlay_report.get("overlaid", []):
        add(o["canonical"], o["conference"], o["fields"])
    for c in sponsor_report.get("carried", []):
        add(c["canonical"], c["conference"], c["fields"])
    return out


def update_ledger(ledger: dict, today: date, carried: dict[str, dict], researched: set[str]) -> dict:
    """New ledger. For every event researched this week (and shipped fresh): a unit carried keeps its recorded confirmation date (or starts at the prior row's
    SOURCE_AS_OF, or today when that is unknown), a unit NOT carried is dropped (it came back fresh). Events not researched this week are left as they were. Pure."""
    new = {k: {"name": v.get("name", ""), "units": {u: dict(d) for u, d in v.get("units", {}).items()}} for k, v in ledger.items()}
    for canon in researched:
        have = new.get(canon, {"name": "", "units": {}})
        cur = carried.get(canon, {"name": have.get("name", ""), "units": {}})
        units = {}
        for u, prior_confirmed in cur["units"].items():
            old = have["units"].get(u)
            units[u] = {"confirmed": (old or {}).get("confirmed") or prior_confirmed or today.isoformat(), "last_carried": today.isoformat()}
        if units:
            new[canon] = {"name": cur.get("name") or have.get("name", ""), "units": units}
        else:
            new.pop(canon, None)
    return new


def stale(ledger: dict, today: date, limit_weeks: int = LIMIT_WEEKS) -> list[dict]:
    """Carried values last confirmed more than `limit_weeks` weeks ago, oldest first. Pure."""
    out = []
    for canon, v in ledger.items():
        for u, d in v.get("units", {}).items():
            try:
                weeks = (today - date.fromisoformat(d["confirmed"])).days // 7
            except (ValueError, KeyError):
                continue
            if weeks > limit_weeks:
                out.append({"canonical": canon, "name": v.get("name", ""), "unit": u, "confirmed": d["confirmed"], "weeks": weeks})
    return sorted(out, key=lambda x: (-x["weeks"], x["name"]))


def load_ledger(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_ledger(path: Path, ledger: dict) -> None:
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(ledger, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
