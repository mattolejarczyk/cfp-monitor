"""License enforcement core — pure stdlib, fully unit-testable (no network, no web framework).

A SQLite store of per-customer license keys + a deterministic `authorize()` decision. The HTTP
server (server.py) is a thin shell that calls into this; all the ENFORCEMENT lives here so it can
be tested offline and reasoned about in one place.
"""
from __future__ import annotations

import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

# HTTP-ish status codes for each denial, so the server can map decisions straight to responses.
OK = 200
UNAUTHORIZED = 401       # unknown key
PAYMENT_REQUIRED = 402   # quota exhausted (billing)
FORBIDDEN = 403          # revoked / feature not entitled
UPGRADE_REQUIRED = 426   # client version below the floor

_SCHEMA = """
CREATE TABLE IF NOT EXISTS licenses (
    key            TEXT PRIMARY KEY,
    customer       TEXT,
    plan           TEXT,
    active         INTEGER DEFAULT 1,       -- 0 = revoked / suspended (the kill switch)
    version_floor  TEXT DEFAULT '',         -- min client version, e.g. "1.2.0" ('' = no floor)
    features       TEXT DEFAULT '',         -- comma-separated entitlements
    quota_tokens   INTEGER DEFAULT -1,      -- token cap for the period (-1 = unlimited)
    used_tokens    INTEGER DEFAULT 0,
    issued_at      TEXT,
    revoked_at     TEXT,
    notes          TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS usage (
    id                INTEGER PRIMARY KEY,
    key               TEXT,
    at                TEXT,
    model             TEXT,
    prompt_tokens     INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens      INTEGER DEFAULT 0
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_version(v: str) -> tuple:
    """'1.10.2' -> (1, 10, 2). Non-numeric / empty -> (0,), so comparisons stay total."""
    parts = re.findall(r"\d+", v or "")
    return tuple(int(p) for p in parts) or (0,)


def version_lt(a: str, b: str) -> bool:
    """True if version a < version b (component-wise, zero-padded)."""
    ta, tb = _parse_version(a), _parse_version(b)
    n = max(len(ta), len(tb))
    ta += (0,) * (n - len(ta))
    tb += (0,) * (n - len(tb))
    return ta < tb


@dataclass
class Decision:
    allowed: bool
    status: int
    reason: str
    license: Optional[dict] = None


class LicenseStore:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # ---- issuance / lifecycle -------------------------------------------------
    def issue(self, customer: str, plan: str = "standard", version_floor: str = "",
              features=(), quota_tokens: int = -1, key: Optional[str] = None) -> str:
        key = key or ("cfp_" + secrets.token_urlsafe(24))
        feats = features if isinstance(features, str) else ",".join(sorted(set(features or ())))
        self.db.execute(
            "INSERT INTO licenses (key, customer, plan, active, version_floor, features,"
            " quota_tokens, used_tokens, issued_at) VALUES (?,?,?,1,?,?,?,0,?)",
            (key, customer, plan, version_floor, feats, quota_tokens, _now()),
        )
        self.db.commit()
        return key

    def revoke(self, key: str) -> bool:
        cur = self.db.execute("UPDATE licenses SET active=0, revoked_at=? WHERE key=?", (_now(), key))
        self.db.commit()
        return cur.rowcount > 0

    def reactivate(self, key: str) -> bool:
        cur = self.db.execute("UPDATE licenses SET active=1, revoked_at=NULL WHERE key=?", (key,))
        self.db.commit()
        return cur.rowcount > 0

    def set_version_floor(self, key: str, floor: str) -> bool:
        cur = self.db.execute("UPDATE licenses SET version_floor=? WHERE key=?", (floor, key))
        self.db.commit()
        return cur.rowcount > 0

    def set_quota(self, key: str, quota_tokens: int, reset_used: bool = False) -> bool:
        if reset_used:
            cur = self.db.execute("UPDATE licenses SET quota_tokens=?, used_tokens=0 WHERE key=?",
                                  (quota_tokens, key))
        else:
            cur = self.db.execute("UPDATE licenses SET quota_tokens=? WHERE key=?", (quota_tokens, key))
        self.db.commit()
        return cur.rowcount > 0

    # ---- reads ---------------------------------------------------------------
    def get(self, key: str) -> Optional[dict]:
        row = self.db.execute("SELECT * FROM licenses WHERE key=?", (key,)).fetchone()
        return dict(row) if row else None

    def all(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM licenses ORDER BY issued_at")]

    # ---- the decision (pure, deterministic) ----------------------------------
    def authorize(self, key: str, client_version: str = "", feature: Optional[str] = None) -> Decision:
        lic = self.get(key)
        if lic is None:
            return Decision(False, UNAUTHORIZED, "unknown license key")
        if not lic["active"]:
            return Decision(False, FORBIDDEN, "license revoked or suspended", lic)
        floor = lic["version_floor"] or ""
        if floor and version_lt(client_version, floor):
            return Decision(False, UPGRADE_REQUIRED,
                            f"client version {client_version or '?'} is below the required {floor}; please update", lic)
        if feature:
            feats = {f for f in (lic["features"] or "").split(",") if f}
            if feature not in feats:
                return Decision(False, FORBIDDEN, f"feature '{feature}' is not included in this plan", lic)
        if lic["quota_tokens"] is not None and lic["quota_tokens"] >= 0 and lic["used_tokens"] >= lic["quota_tokens"]:
            return Decision(False, PAYMENT_REQUIRED, "token quota for the period has been reached", lic)
        return Decision(True, OK, "ok", lic)

    # ---- metering ------------------------------------------------------------
    def record_usage(self, key: str, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        total = int(prompt_tokens or 0) + int(completion_tokens or 0)
        self.db.execute(
            "INSERT INTO usage (key, at, model, prompt_tokens, completion_tokens, total_tokens)"
            " VALUES (?,?,?,?,?,?)",
            (key, _now(), model, int(prompt_tokens or 0), int(completion_tokens or 0), total),
        )
        self.db.execute("UPDATE licenses SET used_tokens = used_tokens + ? WHERE key=?", (total, key))
        self.db.commit()

    def usage_summary(self, key: Optional[str] = None) -> dict:
        if key:
            row = self.db.execute(
                "SELECT COUNT(*) calls, COALESCE(SUM(total_tokens),0) tokens FROM usage WHERE key=?",
                (key,)).fetchone()
            return {"key": key, "calls": row["calls"], "tokens": row["tokens"]}
        rows = self.db.execute(
            "SELECT key, COUNT(*) calls, COALESCE(SUM(total_tokens),0) tokens FROM usage GROUP BY key")
        return {r["key"]: {"calls": r["calls"], "tokens": r["tokens"]} for r in rows}

    def billing(self, period: Optional[str] = None, rate_per_mtok: float = 0.0) -> list[dict]:
        """Per-customer usage for invoicing. `period` filters by 'YYYY-MM' (None = all time).
        `rate_per_mtok` = your cost/price in $ per MILLION tokens -> a `cost` column. Every license
        appears (LEFT JOIN), even with zero usage, so nobody is missed on the invoice."""
        join = "LEFT JOIN usage u ON u.key = l.key"
        params: tuple = ()
        if period:
            join += " AND u.at LIKE ?"
            params = (period + "%",)
        rows = self.db.execute(
            "SELECT l.key key, l.customer customer, l.plan plan, l.active active, "
            "COUNT(u.id) calls, COALESCE(SUM(u.total_tokens),0) tokens "
            f"FROM licenses l {join} GROUP BY l.key ORDER BY tokens DESC", params).fetchall()
        out = []
        for r in rows:
            out.append({"key": r["key"], "customer": r["customer"], "plan": r["plan"],
                        "active": bool(r["active"]), "calls": r["calls"], "tokens": r["tokens"],
                        "cost": round(r["tokens"] / 1_000_000 * rate_per_mtok, 4)})
        return out
