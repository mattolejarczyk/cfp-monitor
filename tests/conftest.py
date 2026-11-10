"""Shared test guard (2026-11-09): no test may ever send a real email.

scripts/customer_sheet_load.py sends a CRITICAL email through alerts.maybe_send_email, which reads CFP_SMTP_* and CFP_RECAP_TO from the
environment, and this PC has them set at user level. A test that forgot to stub the mailer would email Matt. With the variables removed for
every test, maybe_send_email returns False ('not configured') instead of sending."""
import pytest

MAIL_VARS = ("CFP_SMTP_HOST", "CFP_SMTP_PORT", "CFP_SMTP_USER", "CFP_SMTP_PASS", "CFP_SMTP_FROM", "CFP_RECAP_TO", "CFP_ALERT_TO")


@pytest.fixture(autouse=True)
def _no_real_email(monkeypatch):
    for name in MAIL_VARS:
        monkeypatch.delenv(name, raising=False)
