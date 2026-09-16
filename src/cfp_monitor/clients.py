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

# ---------------------------------------------------------------- their vocabulary --
# THEIR PIPELINE STATES, defined ONCE. Until 2026-09-16 there were two copies that disagreed:
# `sheet_reconcile.SETTLED` counted "closed" as settled and `customer_context.DONE` did not, so
# the review page and the remediation tool ranked the same row differently. Matched as a
# lower-case PREFIX of the customer's value, exactly as both copies already did.
LIVE_STATES = ("info needed", "drafting abstract", "in progress", "reviewing", "interested")
DONE_STATES = ("submitted", "accepted", "declined", "client declined", "rejected", "withdrawn",
               "not pursuing", "passed", "no longer")
# RECOGNISED, DELIBERATELY NOT CLASSIFIED - awaiting the operator's reading of the word.
# "Closed" looked like "the call has closed" and mostly is: 8 of Arnica's 10 have a passed
# deadline. But Black Hat Asia (deadline 2026-10-20) and USENIX Security (2027-01-29) are marked
# Closed with deadlines still ahead, and 6 of Utility's 7 carry no deadline at all. Classifying it
# as DONE would bury a live deadline. Each consumer keeps its pre-2026-09-16 behaviour until the
# meaning is settled; the shape check reports the count every week so it is not forgotten.
UNDECIDED_STATES = ("closed", "not appropriate")

# Values each controlled column may hold, for the shape check. A value outside these is not an
# error - the customer owns the column - but our logic will not understand it, so it is REPORTED.
KNOWN_VALUES = {
    "priority": ("urgent", "high", "medium", "low"),
    "submission_date_verified": ("verified", "needs verification"),
}

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def is_contact_only(value: str) -> bool:
    """True when a cell holds nothing but email addresses and separators.

    Arnica fills SPEAKER & ABSTRACTS SUBMITTED with organiser contacts - six rows on 2026-09-16,
    every one an address (it-sa, two OWASP events, LabsCon). `customer_context` read ANY value
    there as "already submitted" and ranked those rows as not worth working. An address is who to
    write to, not a record that anything was sent.
    """
    rest = _EMAIL.sub("", value or "")
    return bool(_EMAIL.search(value or "")) and not re.sub(r"[\s,;/|&]+|and", "", rest)


def records_a_submission(value: str) -> bool:
    """Does SPEAKER & ABSTRACTS SUBMITTED actually record something submitted?"""
    v = (value or "").strip()
    if v.lower() in ("", "0", "no", "false", "none", "n/a", "-"):
        return False
    return not is_contact_only(v)


def sheet_shape(path: Path) -> dict:
    """Reconcile a customer sheet's STRUCTURE against what we load, before loading it.

    Run first after every download (weekly_intake does). It never changes anything and never
    raises for a malformed sheet - it reports:

      missing_fields     a field we load that no column in this sheet feeds. load_sheet keeps
                         last week's values for it rather than blanking every row.
      unmapped_columns   a column they added that we do not read - their data, silently dropped
      duplicate_names    CONFERENCE is the row identity; a repeat means one row overwrites another
      blank_names        rows with no CONFERENCE, which cannot be loaded at all
      credentials_filled LOGIN/PW-style columns holding something (COUNT only, never the value)
      unrecognised       values in status/priority/verified columns our logic does not understand
      undecided          statuses we recognise but have deliberately not classified yet
    """
    with open(path, encoding="utf-8-sig", newline="") as fh:
        raw = list(csv.DictReader(fh))
        fh.seek(0)
        header = next(csv.reader(fh), [])
    heads = [norm_header(h) for h in header]
    fed = {COLUMN_MAP[h] for h in heads if h in COLUMN_MAP}
    names = [(r.get(next((k for k in r if norm_header(k) == "CONFERENCE"), ""), "") or "").strip()
             for r in raw]
    counts: dict[str, int] = {}
    for n in names:
        counts[n] = counts.get(n, 0) + 1

    def col(field):
        return next((k for k in (raw[0] if raw else {}) if COLUMN_MAP.get(norm_header(k)) == field),
                    None)

    unrecognised: dict[str, dict[str, int]] = {}
    undecided: dict[str, int] = {}
    st_col = col("status")
    for r in raw:
        v = (r.get(st_col) or "").strip() if st_col else ""
        low = v.lower()
        if not v:
            continue
        if any(low.startswith(s) for s in UNDECIDED_STATES):
            undecided[v] = undecided.get(v, 0) + 1
        elif not any(low.startswith(s) for s in LIVE_STATES + DONE_STATES):
            unrecognised.setdefault("STATUS", {})[v[:80]] = \
                unrecognised.get("STATUS", {}).get(v[:80], 0) + 1
    for field, known in KNOWN_VALUES.items():
        c = col(field)
        for r in raw:
            v = (r.get(c) or "").strip() if c else ""
            if v and v.lower() not in known:
                label = norm_header(c)
                unrecognised.setdefault(label, {})[v[:80]] = \
                    unrecognised.get(label, {}).get(v[:80], 0) + 1
    sp = col("speaker_abstracts_submitted")
    contact_only = sum(1 for r in raw if sp and is_contact_only(r.get(sp) or ""))

    return {
        "rows": len(raw), "columns": len(header),
        "missing_fields": sorted(set(COLUMN_MAP.values()) - fed),
        "unmapped_columns": [h for h in heads if h and h not in COLUMN_MAP and h not in NEVER_LOAD],
        "duplicate_names": sorted(n for n, k in counts.items() if n and k > 1),
        "blank_names": counts.get("", 0),
        "credentials_filled": {h: sum(1 for r in raw if (r.get(k) or "").strip())
                               for k, h in zip(header, heads) if h in NEVER_LOAD
                               and any((r.get(k) or "").strip() for r in raw)},
        "unrecognised": unrecognised,
        "undecided": undecided,
        "speaker_column_contact_only": contact_only,
    }

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

    # A FIELD NO COLUMN FEEDS IS KEPT, NEVER BLANKED. Until 2026-09-16 a missing column meant
    # `r.get(c, "")` for every row and `c = excluded.c` on conflict - so if the customer renamed
    # or deleted one column, the next load would silently erase that field for every row we hold,
    # and the diff would read as the customer clearing it. A new row still gets a blank; an
    # existing row keeps last week's value, and the field is reported.
    fed = {COLUMN_MAP[h] for h in _headers(path) if h in COLUMN_MAP}
    missing = [c for c in VALUE_COLUMNS if c not in fed]

    before = {r[0]: r[1] for r in con.execute(
        "select their_name, event_id from client_conferences where client_key = ?",
        (client_key,))}

    added, updated = 0, 0
    for r in rows:
        cols = {c: r.get(c, "") for c in VALUE_COLUMNS}
        params = {"k": client_key, "n": r["their_name"], "t": today,
                  "f": path.name, **cols}
        sets = ", ".join(f"{c} = excluded.{c}" for c in VALUE_COLUMNS if c not in missing)
        colnames = ", ".join(VALUE_COLUMNS)
        placeholders = ", ".join(f":{c}" for c in VALUE_COLUMNS)
        con.execute(
            f"""insert into client_conferences
                  (client_key, their_name, {colnames}, first_seen, last_seen_in_sheet,
                   snapshot_file, withdrawn_by_customer)
                values (:k, :n, {placeholders}, :t, :t, :f, 0)
                on conflict(client_key, their_name) do update set
                  {sets + ',' if sets else ''}
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
            "unmapped_columns": unmapped, "missing_fields_kept": missing,
            "not_yet_matched": unmatched}


def _headers(path: Path) -> list[str]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return [norm_header(h) for h in next(csv.reader(fh), [])]


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
    applied = review = absent = kept = 0
    conflicts: list[str] = []
    existing = {r[0]: ((r[1] or "").strip(), r[2] or "") for r in con.execute(
        "select their_name, event_id, match_method from client_conferences where client_key = ?",
        (client_key,))}
    for m in matches:
        name = (m.get("their_name") or "").strip()
        if not name:
            continue
        conf = m.get("confidence")
        conf = float(conf) if conf is not None else 0.0
        eid = (m.get("event_id") or "").strip()
        certain = conf >= CERTAIN and eid

        # A LINK WE ALREADY HOLD IS NEVER REWRITTEN BY AN AUTOMATIC RUN. From 2026-09-16 the matcher
        # runs every week, unattended, so two locks:
        #   - a DIFFERENT certain answer does not replace a link. It is reported. The first dry run
        #     would have moved Horizons Asia onto Horizons Week and Carbon Capture USA onto another
        #     expo, both wrongly - a person decides between two links, never a re-run.
        #   - a less certain re-run leaves the row alone entirely. The old update blanked
        #     match_method whenever it was not certain, and 18 linked rows had already lost the
        #     record of how they were linked. "human review" and resolve_client_matches links are
        #     the ones a re-run must never touch.
        held, method = existing.get(name, ("", ""))
        if held:
            if certain and eid != held:
                conflicts.append(f"{name}: linked to {held} ({method or 'method unrecorded'}); "
                                 f"the matcher is now certain of {eid}")
            elif certain and eid == held:
                con.execute("""update client_conferences set match_confidence = :conf,
                                 match_justification = :why, matched_at = :now,
                                 match_method = case when coalesce(match_method,'') = ''
                                                     then 'match_customer_sheet' else match_method end
                               where client_key = :k and their_name = :n""",
                            {"conf": conf, "why": (m.get("justification") or "")[:400], "now": now,
                             "k": client_key, "n": name})
            kept += 1
            continue
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
    return {"applied": applied, "needs_review": review, "no_match": absent,
            "already_linked": kept, "conflicts": conflicts}


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
