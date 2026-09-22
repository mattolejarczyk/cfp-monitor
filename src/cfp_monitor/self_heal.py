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

import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

from src.cfp_monitor.verify_methods import BROWSER_LADDER, DEADLINE_PASSED, FETCH_PLAIN

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


# The conference's own dates need a DIFFERENT context word than a deadline: "the conference is
# held ..." not "abstracts due ...". Same date-locating machinery, different proof context.
# STRONG cues only. A bare "conference"/"expo"/"dates" appears all over a page (media partners,
# promos, embargo notes) and produced false positives on 2026-09-22 - a date matched near loose
# boilerplate. These phrases specifically INTRODUCE the event's own dates.
EVENT_CONTEXT = re.compile(
    r"held|takes? place|will take place|taking place|scheduled for|save the date|"
    r"mark your calend|conference dates|event dates|dates:", re.IGNORECASE)


def _find_date_in_context(page_text, iso, context_re, context_window=160):
    """(found, quote). A date FORM appears on the page AND a context word sits within
    `context_window` chars - so a bare date (an event date, an early-bird price) is not mistaken
    for the claim. Deterministic, so it is fully unit-testable. The shared core of both finders."""
    if not page_text or not iso:
        return False, ""
    for form in deadline_forms(iso):
        idx = page_text.find(form)
        while idx != -1:
            lo, hi = max(0, idx - context_window), idx + len(form) + context_window
            if context_re.search(page_text[lo:hi]):
                return True, _sentence_around(page_text, idx)
            idx = page_text.find(form, idx + 1)
    return False, ""


def find_deadline_sentence(page_text: str, iso: str, context_window: int = 160):
    """The deadline, confirmed only in a SUBMISSION context (abstracts due, deadline, call for)."""
    return _find_date_in_context(page_text, iso, DEADLINE_CONTEXT, context_window)


def find_conference_dates_sentence(page_text: str, iso_start: str, context_window: int = 140):
    """The conference's OWN dates, confirmed in an EVENT context (held, takes place, venue)."""
    return _find_date_in_context(page_text, iso_start, EVENT_CONTEXT, context_window)


@dataclass
class VerifyResult:
    confirmed: bool
    method: str                 # PROVENANCE - how the evidence was produced. Never blank.
    url: str = ""
    quote: str = ""
    status: str = "checked"     # 'checked' | 'unavailable' (an outage is not a finding, 2.5)
    evidence: dict = None        # grounded step: {queries, source_hosts} - captured for the trail


def _decide(method: str, url: str, text: str, deadline_iso: str) -> VerifyResult:
    """Given page text, decide confirmed / not / unavailable - shared by both verifiers so the
    match logic never diverges between the plain and browser paths."""
    if not (text or "").strip():
        # A 403/JS-only/dead page yields no text - an outage, not a disproof (2.5).
        return VerifyResult(False, method, url, status="unavailable")
    found, quote = find_deadline_sentence(text, deadline_iso)
    return VerifyResult(found, method, url, quote=quote)


class DateContextVerifier:
    """FREE, floor method (fetch-plain+regex): a plain HTTP GET, deadline located on the page.
    Fetching is imported lazily so the module and its tests do not need the network."""
    method = FETCH_PLAIN

    def verify(self, event_name: str, deadline_iso: str, url: str) -> VerifyResult:
        if not url:
            return VerifyResult(False, self.method, url, status="unavailable")
        try:
            from src.cfp_monitor.verify import fetch_text
            text, _note = fetch_text(url)          # (visible text, note); note is set on failure
        except Exception:                                                # noqa: BLE001
            return VerifyResult(False, self.method, url, status="unavailable")
        return _decide(self.method, url, text, deadline_iso)


class BrowserLadderVerifier:
    """FREE escalation (browser-ladder+regex): read the SAME page in the real signed-in Chrome
    on :9222 (investigate_event.render_targets), for the JS/403 pages a plain GET cannot. No
    grounded quota; slower. The match logic is identical - only the fetch is stronger."""
    method = BROWSER_LADDER

    def verify(self, event_name: str, deadline_iso: str, url: str) -> VerifyResult:
        if not url:
            return VerifyResult(False, self.method, url, status="unavailable")
        try:
            import importlib.util
            from pathlib import Path
            spec = importlib.util.spec_from_file_location(
                "_ie", Path(__file__).resolve().parents[2] / "scripts" / "investigate_event.py")
            ie = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ie)
            text = (ie.render_targets([url]) or {}).get(url, "")
        except Exception:                                                # noqa: BLE001
            return VerifyResult(False, self.method, url, status="unavailable")
        return _decide(self.method, url, text, deadline_iso)


class GroundedVerifier:
    """LAST resort (grounded-search+verify): ask ONE specific question via grounded Google search,
    then FETCH the sources it returns and prove the claimed deadline is on one. Grounded search is
    upstream's half, so this SHELLS to Markets/grounded_ask.py under an interpreter that has
    google-genai - cfp-monitor never imports it. The grounded answer is only a lead; a confirmation
    is still a verbatim sentence on a page we fetched. Queries + source hosts are captured as
    evidence. Spends a grounded request per row - budgeted and spike-guarded by the caller."""
    method = "grounded-search+verify"

    def __init__(self, helper: str, python: str = "py", max_sources: int = 4, timeout: int = 120):
        self.helper, self.python, self.max_sources, self.timeout = helper, python, max_sources, timeout

    def verify(self, event_name: str, deadline_iso: str, url: str) -> VerifyResult:
        import json
        import subprocess
        q = (f"What is the abstract or paper submission deadline for {event_name}? "
             f"Give the official source page.")
        try:
            p = subprocess.run([self.python, self.helper, "--question", q],
                               capture_output=True, text=True, timeout=self.timeout)
            data = json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else {}
        except Exception:                                                # noqa: BLE001
            return VerifyResult(False, self.method, url, status="unavailable")
        if not data.get("ok") or not data.get("searched"):
            return VerifyResult(False, self.method, url, status="unavailable")
        sources = data.get("sources", [])
        ev = {"queries": data.get("queries", []),
              "source_hosts": sorted({(s.get("title") or "").lower() for s in sources if s.get("title")})}
        try:
            from src.cfp_monitor.verify import fetch_text
        except Exception:                                                # noqa: BLE001
            return VerifyResult(False, self.method, url, evidence=ev)
        for s in sources[:self.max_sources]:
            uri = s.get("uri", "")            # a Google redirect that resolves to the real page
            if not uri:
                continue
            text, _note = fetch_text(uri)     # urllib follows the redirect to the deep page
            found, quote = find_deadline_sentence(text, deadline_iso)
            if found:
                # Store the RESOLVED page, never the vertexaisearch redirect (which is not an
                # admissible citation host - the gate's R22 would reject it).
                real = _resolve_final_url(uri) or ("https://" + (s.get("title") or "").strip("/"))
                return VerifyResult(True, self.method, real, quote=quote, evidence=ev)
        return VerifyResult(False, self.method, url, evidence=ev)   # searched, none confirmed the date


def _resolve_final_url(uri: str) -> str:
    """Follow a Google grounding redirect to the real page URL. '' if it will not resolve to a
    real host (never return the vertexaisearch redirect - it is not an admissible citation)."""
    try:
        import urllib.request
        req = urllib.request.Request(uri, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            final = r.geturl()
        return "" if "vertexaisearch" in (final or "") else final
    except Exception:                                                    # noqa: BLE001
        return ""


@dataclass
class RowOutcome:
    event_id: str
    name: str
    deadline: str
    url: str
    action: str                 # closed-passed | confirm | flag | skip:customer-working | skip:no-page
    method: str = ""
    quote: str = ""
    reason: str = ""
    evidence: dict = None        # grounded step: {queries, source_hosts}


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


def resolve_rows(con: sqlite3.Connection, rows, verifiers, pace=None, today=None) -> list[RowOutcome]:
    """`verifiers` is an ordered list, cheapest first. Before ANY fetch we resolve the free cases:
    a customer-worked row (surface, never heal) and a PASSED deadline (the call is closed - not
    a thing to hunt a citation for). Only a future-deadline row reaches the verifiers, which
    ESCALATE only on 'unavailable'. The recorded method is whichever produced the decisive result.
    A single verifier may be passed for tests."""
    if not isinstance(verifiers, (list, tuple)):
        verifiers = [verifiers]
    today = (today or date.today()).isoformat()
    out: list[RowOutcome] = []
    for row in rows:
        eid, name, dl, url = row["event_id"], row["name"], row["deadline"], row["url"]
        working = customer_working_status(con, eid)
        if working:
            out.append(RowOutcome(eid, name, dl, url, "skip:customer-working",
                                  reason=f"customer status '{working}' - surface, do not heal"))
            continue
        if re.match(r"^\d{4}-\d{2}-\d{2}$", dl or "") and dl < today:
            # Cheapest resolution: the deadline is in the past, so the call is closed. not_found
            # is expected here (the page came down), and no fetch or search is worth spending.
            out.append(RowOutcome(eid, name, dl, url, "closed-passed", DEADLINE_PASSED,
                                  reason=f"deadline {dl} has passed (as of {today}) - call closed"))
            continue
        res = None
        for v in verifiers:
            if pace:
                pace()
            res = v.verify(name, dl, url)
            if res.status != "unavailable":
                break                       # got a readable page - decide on it, do not escalate
        if res.status == "unavailable":
            out.append(RowOutcome(eid, name, dl, url, "skip:no-page", res.method,
                                  reason="page could not be read by any method - an outage is not a finding"))
        elif res.confirmed:
            out.append(RowOutcome(eid, name, dl, url, "confirm", res.method, res.quote))
        else:
            out.append(RowOutcome(eid, name, dl, url, "flag", res.method,
                                  reason="deadline not found in a submission context on the cited page"))
    return out


def discover_flagged(outcomes: list[RowOutcome], verifier, max_grounded: int,
                     spike_threshold: int, pace=None):
    """The LAST step, gated. Runs the grounded verifier over the rows the free methods FLAGGED -
    and only those. Returns (outcomes, note). Two guards so a broken pipeline cannot pound the
    grounded API:
      - SPIKE: if more rows are flagged than `spike_threshold`, REFUSE the whole step (a spike is
        an upstream break, not a real discovery need) - 0 grounded requests spent.
      - BUDGET: otherwise ground at most `max_grounded` rows, cheapest-first (soonest deadline).
    """
    flagged = [o for o in outcomes if o.action == "flag"]
    if not flagged:
        return outcomes, "grounded step: nothing flagged - not needed"
    if len(flagged) > spike_threshold:
        return outcomes, (f"grounded step REFUSED: {len(flagged)} rows flagged (> spike guard "
                          f"{spike_threshold}) - a spike means an upstream break, not discovery. "
                          f"0 grounded requests spent; investigate before grounding.")
    grounded = 0
    for o in sorted(flagged, key=lambda o: o.deadline)[:max_grounded]:
        if pace:
            pace()
        res = verifier.verify(o.name, o.deadline, o.url)
        grounded += 1
        o.evidence = res.evidence
        if res.confirmed:
            o.action, o.method, o.quote, o.url, o.reason = "confirm", res.method, res.quote, res.url, ""
        elif res.status == "unavailable":
            o.reason = "grounded search unavailable (quota/outage) - still needs a person"
        else:
            o.reason = "grounded search found no source stating the claimed deadline - needs a person"
    return outcomes, f"grounded step: {len(flagged)} flagged, grounded {grounded} (budget {max_grounded})"


def render(outcomes: list[RowOutcome]) -> str:
    by = {}
    for o in outcomes:
        by.setdefault(o.action, []).append(o)
    n_conf = len(by.get("confirm", []))
    lines = [f"SELF-HEAL (Phase 1, report-only) - {len(outcomes)} row(s) checked",
             f"  {len(by.get('closed-passed', []))} closed (deadline passed, free), "
             f"{n_conf} confirmable, {len(by.get('flag', []))} still need a person, "
             f"{len(by.get('skip:customer-working', []))} left to the customer, "
             f"{len(by.get('skip:no-page', []))} unreadable", ""]
    if by.get("closed-passed"):
        lines.append("CLOSED - deadline already passed (no action, no search) [method: deadline-passed]")
        for o in by["closed-passed"]:
            lines.append(f"- {o.name[:52]}  deadline {o.deadline} (past)")
        lines.append("")
    if by.get("confirm"):
        lines.append("CONFIRMABLE (deadline located on the cited page)")
        for o in by["confirm"]:
            lines.append(f"- {o.name[:52]}  deadline {o.deadline}  [method: {o.method}]")
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


def apply_confirmations(con: sqlite3.Connection, outcomes: list[RowOutcome], db_path=None):
    """Write ONLY the confirmed rows, and only what was proven. For each confirm: verify_state ->
    verified, store the verbatim quote and (for a grounded confirm) the resolved citation URL, and
    record the method in verify_detail so the change is traceable. Backs up the DB file first, logs
    every change old->new, and NEVER touches a non-confirmed row or a customer-owned field. Returns
    (log, backup_path). The gate still decides what ships - this only raises our own verify state.
    """
    confirmed = [o for o in outcomes if o.action == "confirm"]
    backup = None
    if confirmed and db_path and os.path.isfile(db_path):
        import shutil
        backup = f"{os.path.splitext(db_path)[0]}.before-selfheal-{datetime.now():%Y%m%d-%H%M%S}.db"
        shutil.copy2(db_path, backup)
    log = []
    for o in confirmed:
        before = con.execute("SELECT verify_state, deadline_evidence_url FROM grounding_facts "
                             "WHERE event_id=?", (o.event_id,)).fetchone()
        if before is None:
            continue
        # A grounded confirm brings a fresh URL; a free-method confirm re-verifies the cited one.
        # Never store a vertexaisearch redirect (R22 would reject it) - keep the existing URL then.
        clean = o.url if re.match(r"^https?://", o.url or "") and "vertexaisearch" not in (o.url or "") \
            else (before[0 + 1] or "")
        con.execute("UPDATE grounding_facts SET verify_state='verified', deadline_quote=?, "
                    "deadline_evidence_url=?, verify_detail=? WHERE event_id=?",
                    (o.quote, clean, f"self-heal:{o.method}", o.event_id))
        log.append({"event_id": o.event_id, "name": o.name, "method": o.method,
                    "before": {"verify_state": before[0], "url": before[1]},
                    "after": {"verify_state": "verified", "url": clean, "quote": (o.quote or "")[:80]}})
    con.commit()
    return log, backup


def to_records(outcomes: list[RowOutcome]) -> list[dict]:
    """The machine trail: one record per row, each carrying its method (provenance)."""
    return [{"kind": "self_heal", "phase": 1, "event_id": o.event_id, "name": o.name,
             "deadline": o.deadline, "url": o.url, "action": o.action, "method": o.method,
             "quote": o.quote, "reason": o.reason, "evidence": o.evidence} for o in outcomes]
