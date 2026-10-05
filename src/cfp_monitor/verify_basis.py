"""The BASIS of a verification label (ACT-18, 2026-10-05; failure point C6).

`verify_state = 'verified'` has meant two different things:
    date     the deadline DATE was found on a page (the claim and the page agree: `[L2] page states 2026-11-16`, `[L0] our crawl of the page also reports ...`,
             an awards pass `verified <date> <url>`, a merge that confirmed the quote);
    status   only the call's STATUS was read (`[L0s] the page itself states the call is open/closed/upcoming`, `the page confirms the call is closed`): the call
             was seen open or closed, the date was NOT found.
Both read 'verified', both count as 'proven' on the board and 'Confirmed' on the customer page. A person reading "verified" assumes the date was seen.

THE FIX IS A SEPARATE COLUMN, NOT A NEW STATE. `verify_basis` (TEXT, in grounding_facts and award_grounding_facts) records what kind of evidence produced the state; the
states themselves, the board's figures and the customer label are untouched by this change (a later, separate decision may make 'status' read as 'Open, date unconfirmed').
Values:  date | status | link | none-found | ''  (blank = never classified: an old row or a writer that does not set it yet; derive with `basis_from_detail`).
        link        the submission link answered 404 (a contradiction about the LINK, not the date)
        none-found  nothing was found (state not_found / unverified)

Pure functions plus `ensure_column`, which the migration script (scripts/migrate_verify_basis.py) calls; nothing here runs on its own."""
from __future__ import annotations

import re
import sqlite3

BASES = ("date", "status", "link", "none-found", "")
_TABLES = ("grounding_facts", "award_grounding_facts")


def basis_from_detail(state: str, detail: str) -> str:
    """Classify a stored (verify_state, verify_detail) pair. Deterministic and conservative: anything not recognised is '' (never guessed). Pure."""
    s = (state or "").strip().lower()
    d = (detail or "").strip().lower()
    if s in ("", "unverified", "not_found") and not d.startswith("verified"):
        return "none-found" if s in ("not_found", "unverified") else ""
    if "[l1]" in d or "returns 404" in d or "does not exist" in d:
        return "link"
    if "[l0s]" in d or re.search(r"the page (itself )?(states|confirms) the call is", d):
        return "status"
    if "page states" in d or "our crawl of the page also reports" in d or "page gives a different deadline" in d or d.startswith("verified ") \
            or "quote confirmed on the cited page" in d or "[l0]" in d or "[merge]" in d or "[selfheal]" in d:
        return "date"
    return ""


def has_column(con: sqlite3.Connection, table: str) -> bool:
    return "verify_basis" in {r[1] for r in con.execute(f"PRAGMA table_info({table})")}


def ensure_column(con: sqlite3.Connection, table: str) -> bool:
    """Add the column if missing (additive, NULL default). Returns True when it had to be added."""
    if has_column(con, table):
        return False
    con.execute(f"ALTER TABLE {table} ADD COLUMN verify_basis TEXT")
    return True


def backfill(con: sqlite3.Connection, table: str) -> dict:
    """Fill verify_basis where it is NULL, from the stored state and detail. Returns {basis: count} of what was written. Never overwrites a non-NULL value and
    never touches any other column."""
    written: dict[str, int] = {}
    for eid, st, det in list(con.execute(f"SELECT event_id, verify_state, verify_detail FROM {table} WHERE verify_basis IS NULL")):
        b = basis_from_detail(st, det)
        con.execute(f"UPDATE {table} SET verify_basis=? WHERE event_id=?", (b, eid))
        written[b or "(unclassified)"] = written.get(b or "(unclassified)", 0) + 1
    return written


def write_verify(con: sqlite3.Connection, table: str, key_col: str, key: str, state: str, detail: str) -> int:
    """Write state and detail, and the basis too when the column exists (so code can ship before the live migration is applied). Returns rows changed."""
    if has_column(con, table):
        return con.execute(f"UPDATE {table} SET verify_state=?, verify_detail=?, verify_basis=? WHERE {key_col}=?",
                           (state, detail, basis_from_detail(state, detail), key)).rowcount
    return con.execute(f"UPDATE {table} SET verify_state=?, verify_detail=? WHERE {key_col}=?", (state, detail, key)).rowcount
