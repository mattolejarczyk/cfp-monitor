"""Source-of-truth store for the CFP monitor (own-DB decision, 2026-07-03).

SQLite now (single file, zero infra); the schema ports to Postgres later. Brandable
reads FROM this. Stdlib only — fully offline / unit-testable.

Responsibilities (VOC-driven):
- Persist the rich `ConferenceResult` as the master record (source of truth).
- **Run history** — every crawl run recorded with quality counts.
- **Change detection** — diff a new crawl vs the stored record; record typed changes.
- **Verification lifecycle** — needs_verified -> verified; human-verified values are
  NEVER silently overwritten by a later crawl (correction-precedence).
- **last_checked** — updated on EVERY crawl, even when nothing changed (customer wants
  to see "when did we last look").
- **Past-event rollover** — flag rows whose event date has passed, to re-check for the
  next-year edition.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Iterable, Optional

from .models import ConferenceResult
from .quality_gate import Quality

# Fields we track for change detection + expose to the customer view.
TRACKED_FIELDS = (
    "name", "location", "conference_dates", "cfp_status",
    "cfp_close_date", "submission_url", "categories",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conferences (
    id                  INTEGER PRIMARY KEY,
    key                 TEXT UNIQUE NOT NULL,   -- normalized url (natural key)
    url                 TEXT,
    name                TEXT,
    location            TEXT,
    conference_dates    TEXT,
    cfp_status          TEXT,
    cfp_close_date      TEXT,
    submission_url      TEXT,
    coordinator_email   TEXT,
    overview            TEXT,
    categories          TEXT,                   -- comma-separated market tags
    priority            TEXT,
    notes               TEXT,                   -- human-owned free notes (customer column)
    status_details      TEXT,
    quality             TEXT,                   -- PASS / PARTIAL / BLOCKED / ERROR
    result_json         TEXT,                   -- full ConferenceResult
    verification_status TEXT DEFAULT 'needs_verified',
    verified_fields     TEXT DEFAULT '{}',      -- {field: human-verified value}
    event_is_past       INTEGER DEFAULT 0,
    first_seen          TEXT,
    last_checked        TEXT,
    last_changed        TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY,
    started_at   TEXT,
    finished_at  TEXT,
    url_count    INTEGER DEFAULT 0,
    pass_count   INTEGER DEFAULT 0,
    partial_count INTEGER DEFAULT 0,
    blocked_count INTEGER DEFAULT 0,
    error_count  INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS changes (
    id            INTEGER PRIMARY KEY,
    conference_id INTEGER,
    run_id        INTEGER,
    field         TEXT,
    old_value     TEXT,
    new_value     TEXT,
    change_type   TEXT,                         -- new_record / updated / conflicts_verified
    detected_at   TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_key(url: str) -> str:
    """Natural key for a conference: scheme/host-insensitive, no www, no trailing
    slash, no fragment. Dedupes http vs https and bare vs www."""
    u = (url or "").strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    u = u.split("#", 1)[0]
    return u.rstrip("/")


def _fields_from_result(result: ConferenceResult, categories) -> dict:
    cats = categories if isinstance(categories, str) else ",".join(sorted(set(categories or [])))
    return {
        "url": result.canonical_url or result.start_url,
        "name": result.name.value,
        "location": result.location.value,
        "conference_dates": result.conference_dates.value,
        "cfp_status": result.cfp_status.value,
        "cfp_close_date": result.cfp_close_date.value,
        "submission_url": result.submission_url.value,
        "coordinator_email": None,
        "overview": result.description or result.audience_topics.value,
        "categories": cats,
        "status_details": result.reason or result.status_basis,
    }


@dataclass
class Change:
    field: str
    old: Optional[str]
    new: Optional[str]
    type: str


@dataclass
class UpsertOutcome:
    key: str
    created: bool
    changes: list = field(default_factory=list)      # list[Change]
    preserved_verified: list = field(default_factory=list)  # fields kept over a crawl


# ---- past-event detection (best-effort, conservative) -----------------------
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def guess_event_past(dates_text: Optional[str], today: Optional[date] = None) -> Optional[bool]:
    """True if the event clearly ended before `today`, False if clearly future,
    None if undeterminable. Never guesses a date it cannot support."""
    if not dates_text:
        return None
    today = today or date.today()
    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", dates_text)]
    if not years:
        return None
    yr = max(years)
    mon = 12
    for name, num in _MONTHS.items():
        if name in dates_text.lower():
            mon = max(mon if mon != 12 else 0, num)  # take the latest month mentioned
    mon = mon or 12
    # Use the 28th as a safe in-month day; we only need coarse past/future.
    try:
        end = date(yr, mon, 28)
    except ValueError:
        end = date(yr, 12, 28)
    return end < today


class Store:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self._migrate()
        self.db.commit()

    def _migrate(self) -> None:
        """Add columns introduced after a DB was first created (safe on existing files)."""
        have = {r["name"] for r in self.db.execute("PRAGMA table_info(conferences)")}
        for col in ("notes",):
            if col not in have:
                self.db.execute(f"ALTER TABLE conferences ADD COLUMN {col} TEXT")

    def close(self) -> None:
        self.db.close()

    # ---- runs ----
    def start_run(self) -> int:
        cur = self.db.execute("INSERT INTO runs (started_at) VALUES (?)", (_now(),))
        self.db.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, counts: dict) -> None:
        self.db.execute(
            "UPDATE runs SET finished_at=?, url_count=?, pass_count=?, partial_count=?, "
            "blocked_count=?, error_count=? WHERE id=?",
            (_now(), counts.get("url_count", 0), counts.get(Quality.PASS.value, 0),
             counts.get(Quality.PARTIAL.value, 0), counts.get(Quality.BLOCKED.value, 0),
             counts.get(Quality.ERROR.value, 0), run_id),
        )
        self.db.commit()

    # ---- upsert with change detection + correction-precedence ----
    def upsert(self, result: ConferenceResult, quality: Quality, categories=None,
               run_id: Optional[int] = None) -> UpsertOutcome:
        key = normalize_key(result.canonical_url or result.start_url)
        new = _fields_from_result(result, categories)
        now = _now()
        row = self.db.execute("SELECT * FROM conferences WHERE key=?", (key,)).fetchone()
        past = guess_event_past(new.get("conference_dates"))
        past_int = 1 if past else 0

        if row is None:
            self.db.execute(
                "INSERT INTO conferences (key, url, name, location, conference_dates, cfp_status,"
                " cfp_close_date, submission_url, coordinator_email, overview, categories,"
                " status_details, quality, result_json, event_is_past, first_seen, last_checked, last_changed)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (key, new["url"], new["name"], new["location"], new["conference_dates"], new["cfp_status"],
                 new["cfp_close_date"], new["submission_url"], new["coordinator_email"], new["overview"],
                 new["categories"], new["status_details"], quality.value,
                 result.model_dump_json(), past_int, now, now, now),
            )
            conf_id = int(self.db.execute("SELECT id FROM conferences WHERE key=?", (key,)).fetchone()["id"])
            self._log_change(conf_id, run_id, "record", None, new["name"], "new_record", now)
            self.db.commit()
            return UpsertOutcome(key=key, created=True,
                                 changes=[Change("record", None, new["name"], "new_record")])

        conf_id = int(row["id"])
        verified = json.loads(row["verified_fields"] or "{}")
        changes: list[Change] = []
        preserved: list[str] = []
        updates: dict[str, object] = {}

        # A failed / blocked crawl extracted nothing real - don't touch the stored facts at all
        # (protects the source of truth from a bad crawl day). last_checked/quality still update.
        skip_fields = quality in (Quality.ERROR, Quality.BLOCKED)
        for f in TRACKED_FIELDS:
            if skip_fields:
                break
            old_val = row[f]
            new_val = new.get(f)
            if f in verified:
                # Correction-precedence: keep the human-verified value. If the crawl
                # now disagrees, record the conflict (for re-verification) but DON'T overwrite.
                if new_val is not None and str(new_val) != str(verified[f]):
                    changes.append(Change(f, verified[f], new_val, "conflicts_verified"))
                    self._log_change(conf_id, run_id, f, verified[f], new_val, "conflicts_verified", now)
                    preserved.append(f)
                continue
            # Never let a crawl blank out an existing value: a failed / thin / timed-out re-crawl
            # returns nulls, and the source of truth must not degrade because of a bad crawl day.
            # (Clearing a field is only ever done through the human-verify/correct path.)
            if not new_val and old_val:
                continue
            if (new_val or None) != (old_val or None):
                updates[f] = new_val
                changes.append(Change(f, old_val, new_val, "updated"))
                self._log_change(conf_id, run_id, f, old_val, new_val, "updated", now)

        # Always refresh non-tracked columns + last_checked; last_changed only if changed.
        updates["url"] = new["url"]
        updates["coordinator_email"] = row["coordinator_email"] or new["coordinator_email"]
        updates["overview"] = new["overview"] or row["overview"]
        updates["status_details"] = new["status_details"] or row["status_details"]
        updates["quality"] = quality.value
        updates["result_json"] = result.model_dump_json()
        updates["event_is_past"] = past_int
        updates["last_checked"] = now
        if changes and any(c.type == "updated" for c in changes):
            updates["last_changed"] = now

        set_clause = ", ".join(f"{k}=?" for k in updates)
        self.db.execute(f"UPDATE conferences SET {set_clause} WHERE id=?",
                        (*updates.values(), conf_id))
        self.db.commit()
        return UpsertOutcome(key=key, created=False, changes=changes, preserved_verified=preserved)

    def _log_change(self, conf_id, run_id, fieldname, old, new, ctype, when) -> None:
        self.db.execute(
            "INSERT INTO changes (conference_id, run_id, field, old_value, new_value, change_type, detected_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (conf_id, run_id, fieldname, old, str(new) if new is not None else None, ctype, when),
        )

    # ---- verification lifecycle ----
    def verify(self, key: str, fields: Optional[dict] = None) -> None:
        """Mark a record human-verified. `fields` = {field: corrected_value} that must
        be preserved against future crawls; passing None just flips the status."""
        key = normalize_key(key)
        row = self.db.execute("SELECT * FROM conferences WHERE key=?", (key,)).fetchone()
        if row is None:
            raise KeyError(key)
        verified = json.loads(row["verified_fields"] or "{}")
        col_updates = {}
        if fields:
            for f, v in fields.items():
                verified[f] = v
                if f in TRACKED_FIELDS:
                    col_updates[f] = v
        col_updates["verified_fields"] = json.dumps(verified)
        col_updates["verification_status"] = "verified"
        set_clause = ", ".join(f"{k}=?" for k in col_updates)
        self.db.execute(f"UPDATE conferences SET {set_clause} WHERE key=?",
                        (*col_updates.values(), key))
        self.db.commit()

    # Columns a human may edit directly (not produced by the crawl) — whitelist guards SQL.
    _PLAIN_EDITABLE = frozenset({"name", "coordinator_email", "overview", "priority",
                                 "status_details", "notes"})

    def set_fields(self, key: str, fields: dict) -> None:
        """Directly persist human-owned columns (priority, notes, email, ...). No crawl conflict."""
        cols = {k: v for k, v in fields.items() if k in self._PLAIN_EDITABLE}
        if not cols:
            return
        set_clause = ", ".join(f"{k}=?" for k in cols)
        self.db.execute(f"UPDATE conferences SET {set_clause} WHERE key=?",
                        (*cols.values(), normalize_key(key)))
        self.db.commit()

    def correct(self, key: str, fields: dict) -> None:
        """Persist a human value for a CRAWL-tracked field: update the column AND record it in
        verified_fields so a later crawl can't silently overwrite it (correction-precedence).
        Does NOT change the verification_status flag — that's the human's explicit checkbox."""
        key = normalize_key(key)
        row = self.db.execute("SELECT verified_fields FROM conferences WHERE key=?", (key,)).fetchone()
        if row is None:
            raise KeyError(key)
        verified = json.loads(row["verified_fields"] or "{}")
        cols = {}
        for f, v in fields.items():
            if f in TRACKED_FIELDS:
                verified[f] = v
                cols[f] = v
        if not cols:
            return
        cols["verified_fields"] = json.dumps(verified)
        set_clause = ", ".join(f"{k}=?" for k in cols)
        self.db.execute(f"UPDATE conferences SET {set_clause} WHERE key=?", (*cols.values(), key))
        self.db.commit()

    def set_verified(self, key: str, verified: bool) -> None:
        """Flip only the human verification flag (SUBMISSION DATE VERIFIED column)."""
        self.db.execute("UPDATE conferences SET verification_status=? WHERE key=?",
                        ("verified" if verified else "needs_verified", normalize_key(key)))
        self.db.commit()

    # ---- reads ----
    def get(self, key: str) -> Optional[dict]:
        row = self.db.execute("SELECT * FROM conferences WHERE key=?", (normalize_key(key),)).fetchone()
        return dict(row) if row else None

    def all_records(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM conferences ORDER BY name")]

    def changes_for(self, key: str) -> list[dict]:
        cid = self.db.execute("SELECT id FROM conferences WHERE key=?", (normalize_key(key),)).fetchone()
        if not cid:
            return []
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM changes WHERE conference_id=? ORDER BY id", (int(cid["id"]),))]

    def rollover_candidates(self) -> list[dict]:
        """Rows whose event date has passed — re-check for the next-year edition."""
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM conferences WHERE event_is_past=1 ORDER BY name")]

    def export_dicts(self) -> list[dict]:
        """Normalized dicts for the customer-format transform (customer_format.py)."""
        out = []
        for r in self.all_records():
            out.append({
                "key": r["key"],
                "name": r["name"], "url": r["url"], "location": r["location"],
                "start_dates": r["conference_dates"], "last_checked": r["last_checked"],
                "submission_deadline": r["cfp_close_date"],
                "verified": r["verification_status"] == "verified",
                "priority": r["priority"], "status": r["cfp_status"],
                "status_details": r["status_details"], "submission_url": r["submission_url"],
                "coordinator_email": r["coordinator_email"], "overview": r["overview"],
                "categories": r["categories"], "notes": r["notes"],
            })
        return out
