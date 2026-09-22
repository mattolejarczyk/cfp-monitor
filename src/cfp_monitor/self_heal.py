"""Self-heal, Phase 1: confirm a not_found deadline against the page the row already cites.

Verification-first (see docs/design/self-heal-verification-proposal.md): most not_found rows
carry a candidate page, so the common case is a FREE fetch, not a grounded request. This module
is REPORT-ONLY - it shows what it would confirm and never writes to the database. Applying
confirmations is a later, separately-verified phase.

Everything a confirmation would need is produced here and labelled with its PROVENANCE - the
`method` that produced it - so a stored fact can always be traced to how it was verified:
  fetch:date-context   the deadline is stated on the row's already-cited page (free)
An un-labelled result is a defect.

Design for testability: the VERIFIER is a seam. `find_deadline_sentence` is a pure function
(page text in, sentence out) so it is tested without a network, and the real fetch is injected.
Nothing here trusts an answerer - a confirmation is a verbatim sentence located on a real page.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date

# A row the customer is actively working is SURFACED, never auto-resolved: their in-flight
# state (a verbal agreement, a submission past the shown deadline) is truth no page shows.
# Same set the merge tool treats as "do not touch on suspicion".
CUSTOMER_WORKING = ("Drafting Abstract", "Info Needed", "In Talks", "Submitted", "Accepted")

DEADLINE_CONTEXT = re.compile(
    r"abstract|submission|submit|deadline|call for|proposal|papers?|due|closes?|cfp",
    re.IGNORECASE)

_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"]


def deadline_forms(iso: str) -> list[str]:
    """The textual forms an ISO date is likely to appear as on a page. '' inputs yield []."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", (iso or "").strip())
    if not m:
        return []
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    month, mon = _MONTHS[mo - 1], _MONTHS[mo - 1][:3]
    return [
        iso, f"{y}-{mo:02d}-{d:02d}",
        f"{month} {d}, {y}", f"{month} {d} {y}", f"{d} {month} {y}", f"{d} {month}, {y}",
        f"{mon} {d}, {y}", f"{mon} {d} {y}", f"{d} {mon} {y}",
        f"{mo}/{d}/{y}", f"{mo:02d}/{d:02d}/{y}",
    ]


def _sentence_around(text: str, at: int, width: int = 240) -> str:
    lo = text.rfind(".", 0, at)
    hi = text.find(".", at)
    lo = 0 if lo < 0 else lo + 1
    hi = len(text) if hi < 0 else hi + 1
    return re.sub(r"\s+", " ", text[max(lo, at - width):min(hi, at + width)]).strip()


def find_deadline_sentence(page_text: str, iso: str, context_window: int = 160):
    """(found, quote). The deadline is confirmed only when one of its date forms appears on the
    page AND a submission-context word sits within `context_window` chars - a bare date could be
    the event date or an early-bird price. Deterministic, so it is fully unit-testable."""
    if not page_text or not iso:
        return False, ""
    for form in deadline_forms(iso):
        idx = page_text.find(form)
        while idx != -1:
            lo, hi = max(0, idx - context_window), idx + len(form) + context_window
            if DEADLINE_CONTEXT.search(page_text[lo:hi]):
                return True, _sentence_around(page_text, idx)
            idx = page_text.find(form, idx + 1)
    return False, ""


@dataclass
class VerifyResult:
    confirmed: bool
    method: str                 # PROVENANCE - how the evidence was produced. Never blank.
    url: str = ""
    quote: str = ""
    status: str = "checked"     # 'checked' | 'unavailable' (an outage is not a finding, 2.5)


class DateContextVerifier:
    """The default Phase-1 verifier: fetch the row's cited page and locate the deadline on it.
    Produces method='fetch:date-context'. Fetching is imported lazily so the module and its
    tests do not need the network; tests exercise `find_deadline_sentence` and a fake verifier.
    """
    method = "fetch:date-context"

    def verify(self, event_name: str, deadline_iso: str, url: str) -> VerifyResult:
        if not url:
            return VerifyResult(False, self.method, url, status="unavailable")
        try:
            from src.cfp_monitor.verify import fetch_text
            text, _note = fetch_text(url)          # (visible text, note); note is set on failure
        except Exception:                                                # noqa: BLE001
            return VerifyResult(False, self.method, url, status="unavailable")
        if not (text or "").strip():
            # A 403/JS-only/dead page yields no text - an outage, not a disproof (2.5).
            return VerifyResult(False, self.method, url, status="unavailable")
        found, quote = find_deadline_sentence(text, deadline_iso)
        return VerifyResult(found, self.method, url, quote=quote)


@dataclass
class RowOutcome:
    event_id: str
    name: str
    deadline: str
    url: str
    action: str                 # 'confirm' | 'flag' | 'skip:customer-working' | 'skip:no-page'
    method: str = ""
    quote: str = ""
    reason: str = ""


def select_unconfirmed(con: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    """not_found rows that carry BOTH a deadline and a cited page - verifiable for free, now.
    Ordered by a soonest-first deadline so the budget is spent where it matters."""
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT event_id, name, deadline, deadline_evidence_url AS url "
        "FROM grounding_facts "
        "WHERE verify_state='not_found' AND COALESCE(deadline,'')<>'' "
        "AND COALESCE(deadline_evidence_url,'')<>'' "
        "ORDER BY deadline ASC").fetchall()
    return rows[:limit] if limit else rows


def customer_working_status(con: sqlite3.Connection, event_id: str) -> str:
    """The customer's own status for this row, if they are actively working it - else ''."""
    try:
        r = con.execute(
            "SELECT status FROM client_conferences WHERE event_id=? AND status IS NOT NULL",
            (event_id,)).fetchall()
    except sqlite3.Error:
        return ""
    for row in r:
        s = (row[0] or "").strip()
        if s in CUSTOMER_WORKING:
            return s
    return ""


def resolve_rows(con: sqlite3.Connection, rows, verifier, pace=None) -> list[RowOutcome]:
    out: list[RowOutcome] = []
    for row in rows:
        eid, name, dl, url = row["event_id"], row["name"], row["deadline"], row["url"]
        working = customer_working_status(con, eid)
        if working:
            out.append(RowOutcome(eid, name, dl, url, "skip:customer-working",
                                  reason=f"customer status '{working}' - surface, do not heal"))
            continue
        if pace:
            pace()
        res = verifier.verify(name, dl, url)
        if res.status == "unavailable":
            out.append(RowOutcome(eid, name, dl, url, "skip:no-page", res.method,
                                  reason="page could not be read - an outage is not a finding"))
        elif res.confirmed:
            out.append(RowOutcome(eid, name, dl, url, "confirm", res.method, res.quote))
        else:
            out.append(RowOutcome(eid, name, dl, url, "flag", res.method,
                                  reason="deadline not found in a submission context on the cited page"))
    return out


def render(outcomes: list[RowOutcome]) -> str:
    by = {}
    for o in outcomes:
        by.setdefault(o.action, []).append(o)
    n_conf = len(by.get("confirm", []))
    lines = [f"SELF-HEAL (Phase 1, report-only) - {len(outcomes)} row(s) checked",
             f"  {n_conf} confirmable, {len(by.get('flag', []))} still need a person, "
             f"{len(by.get('skip:customer-working', []))} left to the customer, "
             f"{len(by.get('skip:no-page', []))} unreadable", ""]
    if by.get("confirm"):
        lines.append("CONFIRMABLE (deadline located on the cited page) [method: fetch:date-context]")
        for o in by["confirm"]:
            lines.append(f"- {o.name[:52]}  deadline {o.deadline}")
            lines.append(f"    {o.url}")
            lines.append(f"    quote: \"{o.quote[:150]}\"")
    for label, head in (("flag", "STILL NEED A PERSON (cited page did not confirm the deadline)"),
                        ("skip:customer-working", "LEFT TO THE CUSTOMER (they are working this row)"),
                        ("skip:no-page", "UNREADABLE (no finding - retry later)")):
        if by.get(label):
            lines += ["", head]
            for o in by[label]:
                lines.append(f"- {o.name[:52]}  ({o.reason})")
    return "\n".join(lines)


def to_records(outcomes: list[RowOutcome]) -> list[dict]:
    """The machine trail: one record per row, each carrying its method (provenance)."""
    return [{"kind": "self_heal", "phase": 1, "event_id": o.event_id, "name": o.name,
             "deadline": o.deadline, "url": o.url, "action": o.action, "method": o.method,
             "quote": o.quote, "reason": o.reason} for o in outcomes]
