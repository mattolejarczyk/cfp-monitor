"""Narrow-prompt overlay: keep last week's fields the narrow research question does not ask.

WHY (2026-10-03). With CFP_PROMPT_MODE=narrow-first the research asks only ten fields (status, deadline, start date, evidence,
format ...). Every other column of the audited row is copied from the INPUT list or derived from it: ORGANIZER came back blank
on all 130 rows, CITY became the first segment of LOCATION (a venue such as "Marina Bay Sands" on 28 rows), and OVERVIEW,
CATEGORIES and COORDINATOR EMAIL fell back to the input list's older text. Last week's accepted row holds the better values.

WHAT. For a row researched this week (source "new") that has a prior accepted row of the SAME edition, take the carried fields
from the prior row when the prior value is not blank. Fresh narrow answers (status, deadline, evidence, format, sponsorship,
confidence ...) are never touched. A new edition, a new event or a row with no prior is left exactly as researched, so the
existing row rule and gate still judge it. A row that already carries an ORGANIZER came from the full prompt and is skipped.

Contract: 2.6 (honest blank beats a guess; nothing invented here, every value is last week's accepted one), v2.4 (this changes
which accepted value is kept, never what a claim says; the gate still runs on the result). Every overlay is in the report so a
carried value is never mistaken for fresh research. Pure function; no I/O."""
from __future__ import annotations

from datetime import date

# Fields the narrow prompt does not return. Identity, customer-owned and fresh-research columns are deliberately absent.
CARRY_FIELDS = ("LOCATION", "CITY", "STATE_PROVINCE", "COUNTRY", "OVERVIEW", "CATEGORIES", "COORDINATOR EMAIL",
                "ORGANIZER", "MAIN_INFO_URL", "CFP MODEL TYPE", "SUBMISSION URL")


def _year(row: dict) -> str:
    return (row.get("EDITION") or "").strip()


def narrow_shaped(row: dict) -> bool:
    """The signature of a narrow answer: ORGANIZER is never asked for, so it is blank (a full answer carries it)."""
    return not (row.get("ORGANIZER") or "").strip()


EVIDENCE_UNIT = ("DEADLINE_EVIDENCE_URL", "DEADLINE_QUOTE", "IS_PROJECTED", "GROUNDING_CONFIDENCE")


def carry_evidence(r: dict, prior: dict, today: date) -> list[str]:
    """NEVER LOSE VERIFIED EVIDENCE (2026-10-03). The narrow question sometimes returns no quote. A blank must not replace a verified answer
    we hold: the live load of 2026-10-03 dropped the evidence of RSA Conference 2027 and Black Hat Asia's call for summits and lost
    Nullcon's deadline. When this week's row has NO evidence page and NO quote, and last week's accepted row has both and was verified
    (IS_PROJECTED false), carry the evidence as one unit (page, quote, projected flag, confidence label: R11 stays bound) when
      (a) this week's deadline equals last week's, or
      (b) this week's deadline is blank and last week's has not passed (it is carried with the evidence).
    A different deadline this week is a fresh answer and is never overridden. The gate still checks the carried quote against its
    page (check 3): a quote that has left the page fails the row and the row rule keeps last week's version. Returns the fields carried."""
    if (r.get("DEADLINE_EVIDENCE_URL") or "").strip() or (r.get("DEADLINE_QUOTE") or "").strip():
        return []
    if not ((prior.get("DEADLINE_EVIDENCE_URL") or "").strip() and (prior.get("DEADLINE_QUOTE") or "").strip()):
        return []
    if (prior.get("IS_PROJECTED") or "").strip().lower() != "false":
        return []
    mine, theirs = (r.get("SUBMISSION DEADLINE") or "").strip(), (prior.get("SUBMISSION DEADLINE") or "").strip()
    carried = []
    if mine and mine != theirs:
        return []
    if not mine:
        try:
            if not theirs or date.fromisoformat(theirs) < today:
                return []
        except ValueError:
            return []
        r["SUBMISSION DEADLINE"] = theirs
        carried.append("SUBMISSION DEADLINE")
    for f in EVIDENCE_UNIT:
        if f in r and (r.get(f) or "") != (prior.get(f) or ""):
            r[f] = prior.get(f, "")
            carried.append(f)
    return carried


def overlay_narrow(rows: list[dict], sources: list[str], prior_by_canon: dict[str, dict], lookup: dict,
                   to_canonical, fields: tuple[str, ...] = CARRY_FIELDS, today: date | None = None) -> tuple[list[dict], dict]:
    """Returns (rows, report). `rows` are modified in place (same objects) and returned."""
    today = today or date.today()
    report: dict = {"overlaid": [], "skipped_new_edition": 0, "skipped_full_prompt": 0, "skipped_no_prior": 0, "fields": {},
                    "evidence_carried": []}
    for i, r in enumerate(rows):
        if sources[i] != "new":
            continue
        prior = prior_by_canon.get(to_canonical(r.get("EVENT_ID", ""), lookup))
        if prior is None:
            report["skipped_no_prior"] += 1
            continue
        if not narrow_shaped(r):
            report["skipped_full_prompt"] += 1
            continue
        if _year(prior) != _year(r):
            report["skipped_new_edition"] += 1
            continue
        changed = []
        # CONFERENCE DATES (2026-10-03): the input list's text disagreed with the research START DATE on 66 rows while last week's accepted
        # CONFERENCE DATES agreed with it on 16 of 17 comparable rows. Restore last week's text ONLY when it names the same full date
        # (year included) as this week's START DATE and this week's text does not: the year can never be mixed by this rule.
        from scripts.start_date_arbiter import first_date
        sd, mine, theirs = (r.get("START DATE") or "").strip(), first_date(r.get("CONFERENCE DATES", "")), first_date(prior.get("CONFERENCE DATES", ""))
        if sd and theirs and theirs.isoformat() == sd and (mine is None or mine.isoformat() != sd):
            r["CONFERENCE DATES"] = prior["CONFERENCE DATES"]
            changed.append("CONFERENCE DATES")
            report["fields"]["CONFERENCE DATES"] = report["fields"].get("CONFERENCE DATES", 0) + 1
        for f in fields:
            pv = (prior.get(f) or "").strip()
            if pv and f in r and (r.get(f) or "").strip() != pv:
                r[f] = prior[f]
                changed.append(f)
                report["fields"][f] = report["fields"].get(f, 0) + 1
        ev = carry_evidence(r, prior, today)
        if ev:
            changed += ev
            report["evidence_carried"].append({"conference": r.get("CONFERENCE", ""), "fields": ev})
        if changed:
            report["overlaid"].append({"conference": r.get("CONFERENCE", ""), "canonical": to_canonical(r.get("EVENT_ID", ""), lookup),
                                       "fields": changed})
    return rows, report
