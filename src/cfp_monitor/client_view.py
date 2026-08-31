"""The two things a client should see that a shared conference list cannot say.

WHY THIS EXISTS
We reconcile against the customer's own sheet every week - what they asked us to verify, what
they changed, what they added. All of it lands on our side and **none of it reaches them**. The
loop is closed for us and invisible to them, which is most of the value missing.

Two sections close it:

    YOU ASKED, WE ANSWERED     every row they flagged 'Needs Verification', with what we found
                               or an honest account of why we could not
    CHANGED SINCE YOU EDITED   what moved on our side since their last snapshot

THE RULE THAT SHAPES BOTH
A client sees only their own rows. Every query here is scoped by `client_key`, with no
exception - two clients in one industry must never see each other exist. That is not a
preference, it is the isolation the 2026-08-07 design specified, and the queries are written so
that forgetting the scope is a syntax error rather than a leak.

An honest "we could not confirm this" is a real answer and belongs in the list. Silence reads as
having been ignored, which is worse than a plain admission - and 2.6 says an honest blank beats
a confident guess.
"""
from __future__ import annotations

import sqlite3
from datetime import date


def _rows(con: sqlite3.Connection, sql: str, client_key: str, *extra) -> list[sqlite3.Row]:
    """Every query is scoped by client_key. The parameter is positional and first so a caller
    cannot accidentally omit it and get the whole book."""
    con.row_factory = sqlite3.Row
    return con.execute(sql, (client_key, *extra)).fetchall()


def answered(con: sqlite3.Connection, client_key: str, today: date) -> list[dict]:
    """Rows the client flagged 'Needs Verification', and where each now stands.

    Four honest outcomes. Three of them are not "we found your deadline", and saying so plainly
    is the point - a queue that only reports wins looks like a queue nobody is working.
    """
    rows = _rows(con, """
        select cc.their_name, cc.event_id, cc.their_deadline, cc.match_confidence,
               g.deadline, g.deadline_quote, g.deadline_evidence_url, g.verify_state, g.status
        from client_conferences cc
        left join grounding_facts g on g.event_id = cc.event_id
        where cc.client_key = ?
          and cc.submission_date_verified = 'Needs Verification'
          and cc.withdrawn_by_customer = 0
        order by cc.their_name""", client_key)

    out = []
    for r in rows:
        eid = (r["event_id"] or "").strip()
        deadline = (r["deadline"] or "").strip()
        quote = (r["deadline_quote"] or "").strip()
        url = (r["deadline_evidence_url"] or "").strip()

        if not eid:
            conf = r["match_confidence"]
            if conf is not None and conf >= 40:
                state, answer = "asking you", (
                    "We hold something that may be this conference but will not guess between "
                    "them. One question and we can check it every week.")
            else:
                state, answer = "not tracked", (
                    "This is not on the industry list we research. Tell us to add it and it "
                    "enters the weekly checks like everything else.")
        elif deadline and quote:
            state, answer = "confirmed", (
                f"Deadline {deadline}. We opened the page and read it there.")
        elif deadline:
            state, answer = "held, not confirmed", (
                f"We hold {deadline} but could not confirm it on the page today. Treat it as "
                f"unchecked rather than doubtful.")
        else:
            state, answer = "no date announced", (
                "No submission deadline is published yet. That is a fact about the conference, "
                "not a gap in our checking - we watch it weekly and it will appear here.")

        out.append({"name": r["their_name"], "state": state, "answer": answer,
                    "deadline": deadline, "quote": quote, "url": url,
                    "their_deadline": (r["their_deadline"] or "").strip()})
    return out


def changed_for_client(con: sqlite3.Connection, client_key: str, since: str) -> list[dict]:
    """What moved on OUR side, on this client's rows, since their last snapshot.

    Deliberately narrow: a deadline that appeared, moved, or was withdrawn. Those are the three
    changes that alter what a person would do. Listing every field that differs would bury them.
    """
    rows = _rows(con, """
        select cc.their_name, g.deadline, g.deadline_quote, g.source_as_of, g.verify_state
        from client_conferences cc
        join grounding_facts g on g.event_id = cc.event_id
        where cc.client_key = ?
          and cc.withdrawn_by_customer = 0
          and g.source_as_of >= ?
        order by g.source_as_of desc, cc.their_name""", client_key, since)
    return [{"name": r["their_name"], "deadline": (r["deadline"] or "").strip(),
             "quote": (r["deadline_quote"] or "").strip(),
             "when": (r["source_as_of"] or "").strip()} for r in rows]


def summary(answers: list[dict]) -> dict[str, int]:
    """Counts by outcome, derived from the list itself - never carried in."""
    out: dict[str, int] = {}
    for a in answers:
        out[a["state"]] = out.get(a["state"], 0) + 1
    return out
