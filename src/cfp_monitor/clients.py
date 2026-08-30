"""The client layer: a customer's own sheet, kept apart from the shared industry list.

THE DISTINCTION THIS EXISTS TO HOLD
An INDUSTRY LIST is shared. One canonical row per conference, joined into one or more
industries by `conference_markets` - CES already sits in four. That layer is verified by the
pipeline and is the same for everybody.

A CLIENT SHEET is not shared. Arnica and a second cybersecurity client would both track Black
Hat, and each needs their OWN status, priority, notes and submission history against that one
conference. `conferences` cannot hold that: its columns are single-valued and shared.

    conferences.status_details    349/373 filled - OURS, crawl-derived
    conferences.overview          257/373 filled - OURS, crawl-derived
    conferences.priority            0/373        - empty, and NOT free for the taking

Importing a customer's STATUS DETAILS into `conferences.status_details` would destroy 349 rows
of our own data and merge two different meanings under one name. Per-client values live here
and only here.

THE FLYWHEEL
A client row we cannot match to the industry list is not an error - it is research the customer
did for us. Arnica tracks KubeCon, IEEE S&P and Infosecurity Europe; the next cybersecurity
client will want all three. Those rows land in `industry_candidates` as a PENDING administrative
decision, never as a silent addition to an industry list.
"""
from __future__ import annotations

import csv
import re
import sqlite3
from datetime import date
from pathlib import Path

# Their header -> our column. Keys are normalised (upper, single-spaced) before lookup, because
# the two sheets we have already disagree with each other: "NOTIFCATION DATE" in one and
# "NOTIFICATION DATE" in the other. An exact match would silently drop a column.
COLUMN_MAP = {
    "CONFERENCE": "their_name",
    "CONFERENCE URL": "their_url",
    "LOCATION": "location",
    "EVENT START DATE": "event_start_date",
    "LATEST UPDATE": "latest_update",
    "SUBMISSION DEADLINE": "their_deadline",
    "SUBMISSION DATE VERIFIED": "submission_date_verified",
    "PRIORITY": "priority",
    "STATUS": "status",
    "STATUS DETAILS": "status_details",
    "SUBMISSION URL": "their_submission_url",
    "SPEAKER & ABSTRACTS SUBMITTED": "speaker_abstracts_submitted",
    "SPEAKER AND ABSTRACTS SUBMITTED": "speaker_abstracts_submitted",
    "NOTIFICATION DATE": "notification_date",
    "NOTIFCATION DATE": "notification_date",          # as spelled in the Utility sheet
    "OVERVIEW": "overview",
    "CATEGORIES": "categories",
    "COORDINATOR CONTACT INFO": "coordinator_contact",
    "NOTES": "notes",
}

# Never loaded, whatever the snapshot happens to contain. The snapshot tool already redacts
# these; this is the second lock, because a hand-exported CSV can reach the loader directly.
NEVER_LOAD = {"LOGIN", "PW", "PASSWORD", "USER", "USERNAME", "API KEY", "TOKEN"}

VALUE_COLUMNS = sorted(set(COLUMN_MAP.values()) - {"their_name"})

SCHEMA = """
create table if not exists clients (
    client_key   text primary key,
    name         text not null,
    industry     text,
    subindustry  text,
    sheet_url    text,
    sheet_gid    text,
    active       integer not null default 1,
    first_seen   text,
    note         text
);

create table if not exists client_conferences (
    client_key   text not null,
    their_name   text not null,
    event_id     text,
    match_method text,
    their_url    text, their_deadline text, their_submission_url text,
    submission_date_verified text,
    status text, status_details text, priority text,
    speaker_abstracts_submitted text, notification_date text,
    notes text, coordinator_contact text, overview text, categories text,
    location text, event_start_date text, latest_update text,
    first_seen text, last_seen_in_sheet text,
    withdrawn_by_customer integer not null default 0,
    snapshot_file text,
    primary key (client_key, their_name)
);

create index if not exists ix_client_conf_event on client_conferences(event_id);

create table if not exists industry_candidates (
    id           integer primary key autoincrement,
    client_key   text not null,
    their_name   text not null,
    their_url    text,
    industry     text,
    subindustry  text,
    first_seen   text,
    decision     text,
    decided_at   text,
    decided_by   text,
    note         text,
    unique (client_key, their_name)
);
"""


def norm_header(h: str) -> str:
    return re.sub(r"\s+", " ", (h or "").strip()).upper()


# A match is only applied automatically when the matcher is CERTAIN. Its three certain tests -
# exact URL, a domain that resolves to exactly one row in the whole database, and name+city+date
# agreeing - each return 100 on their own. Anything below that is a vote, and a vote is a
# suggestion: contract 2.5 says decline rather than guess.
CERTAIN = 100.0
# Below this the matcher found nothing worth a human's time, so the row is genuinely absent from
# the industry list and becomes a promotion candidate. Between the two it goes to review.
NO_MATCH = 40.0


def ensure_schema(con: sqlite3.Connection) -> None:
    """Additive only. Nothing here alters or drops an existing table."""
    con.executescript(SCHEMA)
    have = {r[1] for r in con.execute("pragma table_info(client_conferences)")}
    for col in ("match_confidence real", "match_justification text", "matched_at text"):
        if col.split()[0] not in have:
            con.execute(f"alter table client_conferences add column {col}")
    con.commit()


def upsert_client(con: sqlite3.Connection, client_key: str, name: str, industry: str = "",
                  subindustry: str = "", sheet_url: str = "", sheet_gid: str = "",
                  note: str = "") -> None:
    con.execute(
        """insert into clients (client_key, name, industry, subindustry, sheet_url, sheet_gid,
                                first_seen, note)
           values (:k, :n, :i, :s, :u, :g, :t, :note)
           on conflict(client_key) do update set
             name = excluded.name, industry = excluded.industry,
             subindustry = excluded.subindustry, sheet_url = excluded.sheet_url,
             sheet_gid = excluded.sheet_gid, note = excluded.note""",
        {"k": client_key, "n": name, "i": industry, "s": subindustry, "u": sheet_url,
         "g": sheet_gid, "t": date.today().isoformat(), "note": note})
    con.commit()


def read_sheet(path: Path) -> tuple[list[dict], list[str]]:
    """Rows keyed by OUR column names, plus any headers we did not recognise.

    utf-8-sig because a Google CSV export carries a BOM, and CONFERENCE is the join column.
    """
    with open(path, encoding="utf-8-sig", newline="") as fh:
        raw = list(csv.DictReader(fh))
    if not raw:
        return [], []
    headers = [norm_header(h) for h in raw[0].keys()]
    unmapped = [h for h in headers
                if h and h not in COLUMN_MAP and h not in NEVER_LOAD]

    out = []
    for r in raw:
        row = {}
        for k, v in r.items():
            h = norm_header(k)
            if h in NEVER_LOAD:
                continue
            col = COLUMN_MAP.get(h)
            if col:
                row[col] = (v or "").strip()
        if row.get("their_name"):
            out.append(row)
    return out, unmapped


def load_sheet(con: sqlite3.Connection, client_key: str, path: Path,
               *, industry: str) -> dict:
    """Load one snapshot into the client layer. Returns a summary of what moved.

    NEVER touches `conferences`, `grounding_facts` or `conference_markets`. A customer's value
    is stored exactly as they typed it - we do not normalise, reformat or 'correct' a field we
    do not own (rule C1).
    """
    rows, unmapped = read_sheet(path)
    today = date.today().isoformat()
    seen = {r["their_name"] for r in rows}

    before = {r[0]: r[1] for r in con.execute(
        "select their_name, event_id from client_conferences where client_key = ?",
        (client_key,))}

    added, updated = 0, 0
    for r in rows:
        cols = {c: r.get(c, "") for c in VALUE_COLUMNS}
        params = {"k": client_key, "n": r["their_name"], "t": today,
                  "f": path.name, **cols}
        sets = ", ".join(f"{c} = excluded.{c}" for c in VALUE_COLUMNS)
        colnames = ", ".join(VALUE_COLUMNS)
        placeholders = ", ".join(f":{c}" for c in VALUE_COLUMNS)
        con.execute(
            f"""insert into client_conferences
                  (client_key, their_name, {colnames}, first_seen, last_seen_in_sheet,
                   snapshot_file, withdrawn_by_customer)
                values (:k, :n, {placeholders}, :t, :t, :f, 0)
                on conflict(client_key, their_name) do update set
                  {sets},
                  last_seen_in_sheet = excluded.last_seen_in_sheet,
                  snapshot_file = excluded.snapshot_file,
                  withdrawn_by_customer = 0""", params)
        if r["their_name"] in before:
            updated += 1
        else:
            added += 1

    # Rule C4: a row leaving their sheet is not a deletion. It is flagged and kept, exactly as
    # an unmatched delivery row is kept and declared rather than dropped (contract 2.1).
    gone = [n for n in before if n not in seen]
    for n in gone:
        con.execute("update client_conferences set withdrawn_by_customer = 1 "
                    "where client_key = ? and their_name = ?", (client_key, n))

    con.commit()

    # NOTE what is deliberately NOT done here: promotion candidates. Loading knows nothing
    # about whether a row exists in the industry list - `event_id` is still null because
    # matching is a separate stage with its own tool (scripts/match_customer_sheet.py). The
    # first version of this function treated "new to the client layer" as "unknown to the
    # industry list" and reported 111 candidates on first load, when roughly 84 of those rows
    # match lists we already hold. That is a number that reads as a finding and is an artifact
    # of when it was computed. Candidates come from refresh_candidates, AFTER matching.
    unmatched = con.execute(
        "select count(*) from client_conferences where client_key = ? and "
        "(event_id is null or trim(event_id) = '') and withdrawn_by_customer = 0",
        (client_key,)).fetchone()[0]
    return {"rows": len(rows), "added": added, "updated": updated,
            "withdrawn": len(gone), "withdrawn_names": gone,
            "unmapped_columns": unmapped, "not_yet_matched": unmatched}


def apply_matches(con: sqlite3.Connection, client_key: str,
                  matches: list[dict]) -> dict:
    """Write matcher results onto the client's rows. Only CERTAIN matches set an event_id.

    `matches` is the matcher's output: their name, an EVENT_ID, a confidence and a
    justification. Three outcomes, and keeping them distinct is the point:

        100        applied. The matcher's certain tests are definitive on their own.
        40 to 99   recorded, event_id LEFT NULL, sent to a human. A vote is a suggestion.
        under 40   the matcher found nothing; the row is genuinely absent from the industry
                   list, and only these become promotion candidates.

    Collapsing the middle band into either neighbour is the error to avoid. Treated as matched
    it invents a join; treated as absent it proposes adding a conference we already hold.
    """
    now = date.today().isoformat()
    applied = review = absent = 0
    for m in matches:
        name = (m.get("their_name") or "").strip()
        if not name:
            continue
        conf = m.get("confidence")
        conf = float(conf) if conf is not None else 0.0
        eid = (m.get("event_id") or "").strip()
        certain = conf >= CERTAIN and eid
        con.execute(
            """update client_conferences
                 set event_id = case when :certain then :eid else event_id end,
                     match_method = :method,
                     match_confidence = :conf,
                     match_justification = :why,
                     matched_at = :now
               where client_key = :k and their_name = :n""",
            {"certain": 1 if certain else 0, "eid": eid, "conf": conf,
             "method": "match_customer_sheet" if certain else "",
             "why": (m.get("justification") or "")[:400], "now": now,
             "k": client_key, "n": name})
        if certain:
            applied += 1
        elif conf >= NO_MATCH:
            review += 1
        else:
            absent += 1
    con.commit()
    return {"applied": applied, "needs_review": review, "no_match": absent}


def refresh_candidates(con: sqlite3.Connection, client_key: str, industry: str,
                       subindustry: str = "") -> dict:
    """Raise a PENDING promotion candidate for each row the matcher looked at and could not place.

    Runs AFTER matching, never during load: a row with no `event_id` before the matcher has run
    is simply unexamined, and calling that a candidate manufactures work out of nothing.

    It also requires the matcher to have RUN on that row (`matched_at` set) and to have found
    nothing worth reviewing (`match_confidence` under NO_MATCH). A row sitting at 80% is a
    likely match awaiting a human, not a conference we are missing - proposing it for promotion
    would ask Nicolia's team to add something we already hold.

    A candidate is a question for them, never an addition. Nothing reaches an industry list
    without `decision` being set by a person.
    """
    today = date.today().isoformat()
    rows = con.execute(
        "select their_name, their_url from client_conferences where client_key = ? and "
        "(event_id is null or trim(event_id) = '') and withdrawn_by_customer = 0 "
        "and matched_at is not null "
        "and coalesce(match_confidence, 0) < ?",
        (client_key, NO_MATCH)).fetchall()
    for name, url in rows:
        con.execute(
            """insert into industry_candidates
                 (client_key, their_name, their_url, industry, subindustry, first_seen,
                  decision)
               values (:k, :n, :u, :i, :s, :t, null)
               on conflict(client_key, their_name) do nothing""",
            {"k": client_key, "n": name, "u": url, "i": industry, "s": subindustry,
             "t": today})
    con.commit()
    pending = con.execute(
        "select count(*) from industry_candidates where client_key = ? and decision is null",
        (client_key,)).fetchone()[0]
    return {"raised": len(rows), "pending": pending}
