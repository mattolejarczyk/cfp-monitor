"""Alert rules engine (M6) — turn stored changes + deadlines into prioritized alerts.

Rules (VOC):
- CFP status -> Open              HIGH
- Deadline within 30 days         HIGH
- New conference discovered       MEDIUM
- Conference dates changed        MEDIUM
- Submission URL changed          LOW

Produces a markdown digest. Email delivery is scaffolded but OFF unless SMTP env vars
are set — so scheduled runs never fail for lack of creds.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from .storage import Store

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_LEVEL_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def _safe_date(y, mo, d) -> Optional[date]:
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_deadline(text) -> Optional[date]:
    """Best-effort parse of a deadline string (ISO / '15 May 2026' / 'May 15, 2026' /
    DD/MM/YYYY). None if unparseable — never guesses."""
    if not text:
        return None
    s = str(text).strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return _safe_date(int(m[1]), int(m[2]), int(m[3]))
    low = s.lower()
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3,9})\.?\s+(\d{4})", low)
    if m and m[2][:3] in _MONTHS:
        return _safe_date(int(m[3]), _MONTHS[m[2][:3]], int(m[1]))
    m = re.search(r"([a-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", low)
    if m and m[1][:3] in _MONTHS:
        return _safe_date(int(m[3]), _MONTHS[m[1][:3]], int(m[2]))
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", s)
    if m:
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        return _safe_date(y, b, a) or _safe_date(y, a, b)
    return None


@dataclass
class Alert:
    level: str        # HIGH / MEDIUM / LOW
    kind: str
    conference: str
    message: str
    url: Optional[str] = None


def compute_alerts(store: Store, run_id: Optional[int] = None, today: Optional[date] = None) -> list[Alert]:
    """Alerts from change history (optionally limited to one run) + deadline-approaching."""
    today = today or date.today()
    alerts: list[Alert] = []
    for r in store.all_records():
        name, url = r["name"] or r["key"], r["url"]
        for ch in store.changes_for(r["key"]):
            if run_id is not None and ch.get("run_id") != run_id:
                continue
            f, ctype, new, old = ch["field"], ch["change_type"], ch["new_value"], ch["old_value"]
            if ctype == "new_record":
                alerts.append(Alert("MEDIUM", "new_conference", name, f"New conference discovered: {name}", url))
            elif f == "cfp_status" and (new or "").lower() == "open":
                alerts.append(Alert("HIGH", "cfp_open", name, f"CFP now OPEN: {name}", url))
            elif f == "conference_dates":
                alerts.append(Alert("MEDIUM", "dates_changed", name, f"Dates changed ({old} -> {new}): {name}", url))
            elif f == "submission_url":
                alerts.append(Alert("LOW", "submission_url_changed", name, f"Submission URL changed: {name}", url))
        d = parse_deadline(r["cfp_close_date"])
        if d and today <= d <= today + timedelta(days=30):
            alerts.append(Alert("HIGH", "deadline_soon", name,
                                f"Deadline in {(d - today).days}d ({d.isoformat()}): {name}", url))
    return alerts


def digest_markdown(alerts: list[Alert], title: str = "PR Monitor — Alerts") -> str:
    if not alerts:
        return f"# {title}\n\n_No new alerts._\n"
    lines = [f"# {title}", ""]
    for lvl in ("HIGH", "MEDIUM", "LOW"):
        grp = [a for a in alerts if a.level == lvl]
        if grp:
            lines.append(f"## {lvl} ({len(grp)})")
            for a in grp:
                lines.append(f"- {a.message}" + (f" — {a.url}" if a.url else ""))
            lines.append("")
    return "\n".join(lines)


def maybe_send_email(subject: str, body: str, config: Optional[dict] = None) -> bool:
    """Send the digest via SMTP IF fully configured (env CFP_SMTP_*). Returns True if sent,
    False if not configured (a no-op so scheduled runs don't fail without creds)."""
    import os
    import smtplib
    from email.mime.text import MIMEText

    c = config or {
        "host": os.getenv("CFP_SMTP_HOST"), "port": int(os.getenv("CFP_SMTP_PORT", "587")),
        "user": os.getenv("CFP_SMTP_USER"), "password": os.getenv("CFP_SMTP_PASS"),
        "to": os.getenv("CFP_ALERT_TO"),
        "from": os.getenv("CFP_SMTP_FROM") or os.getenv("CFP_SMTP_USER"),
    }
    if not all([c.get("host"), c.get("user"), c.get("password"), c.get("to")]):
        return False
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, c["from"], c["to"]
    with smtplib.SMTP(c["host"], c["port"]) as s:
        s.starttls()
        s.login(c["user"], c["password"])
        s.sendmail(c["from"], [c["to"]], msg.as_string())
    return True
